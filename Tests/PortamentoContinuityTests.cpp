// Roland SH-201 OM p. 19 defines portamento as a smooth pitch transition;
// SOLO changes envelope articulation, while LEGATO omits the next attack.
// https://static.roland.com/assets/media/pdf/SH-201_OM.pdf#page=19
// These audio tests separate those contracts without assuming a hardware
// portamento time curve, which remains unmeasured.
#include "DSP/SeptumEngine.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

namespace
{
int checks = 0, failures = 0;

void expect (bool condition, const std::string& label)
{
    ++checks;
    if (! condition)
    {
        ++failures;
        std::fprintf (stderr, "FAIL: %s\n", label.c_str());
    }
}

septum::Patch patchFor (bool lower, bool secondOscillator,
                        septum::MonoMode mode)
{
    septum::Patch patch;
    patch.keyboardPart = lower ? septum::KeyboardPart::Lower
                               : septum::KeyboardPart::Upper;
    auto& tone = lower ? patch.lower : patch.upper;
    tone.mono = mode;
    tone.portamento = true;
    tone.portamentoTime = 100;
    tone.osc1.wave = tone.osc2.wave = septum::Waveform::Sine;
    tone.osc1.coarse = tone.osc2.coarse = 0;
    tone.osc1.fine = tone.osc2.fine = 0;
    tone.osc1.pitchEnvDepth = tone.osc2.pitchEnvDepth = 0;
    tone.balance = secondOscillator ? 63 : -63;
    tone.filterType = septum::FilterType::Bypass;
    tone.ampEnvAttack = tone.ampEnvDecay = 0;
    tone.ampEnvSustain = 127;
    tone.ampEnvRelease = 100;
    tone.level = 40;
    tone.levelVelocitySens = 0;
    tone.lfo1.depth1 = tone.lfo1.depth2 = 0;
    tone.lfo2.depth1 = tone.lfo2.depth2 = 0;
    patch.delayOn = patch.reverbOn = false;
    return patch;
}

std::vector<float> render (septum::Engine& engine, int samples, int blockSize)
{
    std::vector<float> left (static_cast<std::size_t> (samples));
    std::vector<float> right (static_cast<std::size_t> (samples));
    for (int offset = 0; offset < samples; offset += blockSize)
    {
        const int count = std::min (blockSize, samples - offset);
        engine.process (left.data() + offset, right.data() + offset, count);
    }
    return left;
}

double energy (const std::vector<float>& audio)
{
    double result = 0.0;
    for (float sample : audio)
        result += sample * static_cast<double> (sample);
    return result;
}

double peakDifference (const std::vector<float>& a, const std::vector<float>& b)
{
    double result = 0.0;
    for (std::size_t i = 0; i < a.size(); ++i)
        result = std::max (result, std::abs (static_cast<double> (a[i]) - b[i]));
    return result;
}

void testInterruptedGlides()
{
    double worstError = 0.0;
    for (double rate : { 44100.0, 48000.0, 96000.0 })
        for (bool lower : { false, true })
            for (bool secondOscillator : { false, true })
                for (int direction : { -1, 1 })
                    for (int blockSize : { 37, 256 })
                    {
                        septum::Engine solo, legato;
                        solo.prepare (rate, blockSize);
                        legato.prepare (rate, blockSize);
                        solo.setPatch (patchFor (lower, secondOscillator,
                                                 septum::MonoMode::Solo));
                        legato.setPatch (patchFor (lower, secondOscillator,
                                                   septum::MonoMode::SoloLegato));
                        // Start at C4, then move two octaves away. Interrupt
                        // that unfinished glide with a one-octave target.
                        // All envelopes are sustained and pitch modulation
                        // is absent, so the two articulation modes must have
                        // the same oscillator pitch trajectory.
                        for (auto* engine : { &solo, &legato })
                        {
                            engine->noteOn (60, 100);
                            render (*engine, static_cast<int> (rate * 0.1), blockSize);
                            engine->noteOn (60 + 24 * direction, 100);
                            render (*engine, static_cast<int> (rate * 0.04), blockSize);
                            engine->noteOn (60 + 12 * direction, 100);
                        }
                        const int count = static_cast<int> (rate * 0.12);
                        const auto a = render (solo, count, blockSize);
                        const auto b = render (legato, count, blockSize);
                        const double error = peakDifference (a, b);
                        worstError = std::max (worstError, error);
                        const auto label = std::string (lower ? "lower" : "upper")
                            + " osc=" + std::to_string (secondOscillator ? 2 : 1)
                            + " direction=" + std::to_string (direction)
                            + " rate=" + std::to_string (rate)
                            + " block=" + std::to_string (blockSize);
                        expect (energy (a) > 1.0e-4, label + " is audible");
                        expect (error < 2.0e-7,
                                label + " SOLO glide stays on its current pitch");

                        // Releasing the latest key returns to the earlier
                        // held target. That interruption must be smooth too.
                        solo.noteOff (60 + 12 * direction);
                        legato.noteOff (60 + 12 * direction);
                        const auto returnedSolo = render (solo, count, blockSize);
                        const auto returnedLegato = render (legato, count, blockSize);
                        expect (peakDifference (returnedSolo, returnedLegato) < 2.0e-7,
                                label + " return to held key preserves glide pitch");
                        expect (solo.activeVoiceCount() == 1,
                                label + " SOLO still uses one voice");
                    }
    std::printf ("Interrupted SOLO/LEGATO glide maximum audio difference %.9g\n",
                 worstError);
}

void testSoloStillRetriggersAttack()
{
    constexpr double rate = 48000.0;
    septum::Engine solo, legato;
    for (bool useLegato : { false, true })
    {
        auto patch = patchFor (false, false,
            useLegato ? septum::MonoMode::SoloLegato : septum::MonoMode::Solo);
        patch.upper.ampEnvAttack = 32;
        patch.upper.ampEnvSustain = 20;
        auto& engine = useLegato ? legato : solo;
        engine.prepare (rate, 256);
        engine.setPatch (patch);
        engine.noteOn (60, 100);
        render (engine, 9600, 256);
        engine.noteOn (72, 100);
    }
    const double soloEnergy = energy (render (solo, 960, 256));
    const double legatoEnergy = energy (render (legato, 960, 256));
    expect (soloEnergy > 4.0 * legatoEnergy,
            "SOLO retriggers amp attack while LEGATO sustains");
}
} // namespace

int main()
{
    testInterruptedGlides();
    testSoloStillRetriggersAttack();
    std::printf ("Portamento continuity: %d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
