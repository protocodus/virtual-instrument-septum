// Roland SH-201 OM p. 32 documents OSC1 cycle restart under SYNC. Its
// ReverseMetal and FB Harmonics patches select FB OSC as the slave. These
// tests verify the chosen source-phase reset, not an identified Roland
// feedback-loop topology. See Docs/fidelity/source-audits/feedback-sync.md.
#include "DSP/SeptumEngine.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

namespace
{
int checks = 0, failures = 0;

void expect (bool condition, const std::string& message)
{
    ++checks;
    if (! condition)
    {
        ++failures;
        std::fprintf (stderr, "FAIL: %s\n", message.c_str());
    }
}

septum::Patch feedbackPatch (int feedback, bool sync, int coarse = -12)
{
    septum::Patch patch;
    auto& tone = patch.upper;
    tone.osc1.wave = septum::Waveform::FbOsc;
    tone.osc1.coarse = coarse;
    tone.osc1.fine = 7; // Nonintegral period ratio exercises fractional resets.
    tone.osc1.pulseWidth = feedback;
    tone.osc2.wave = septum::Waveform::Sine;
    tone.osc2.fine = 11; // Avoid exact integer-sample wrap ambiguity at 440 Hz.
    tone.mixType = sync ? septum::MixModType::Sync : septum::MixModType::Mix;
    tone.balance = -63;
    tone.filterType = septum::FilterType::Bypass;
    tone.lowFreq = septum::LowFreqMode::Flat;
    tone.ampEnvAttack = tone.ampEnvDecay = tone.ampEnvRelease = 0;
    tone.ampEnvSustain = 127;
    tone.level = 24; // Keep the comparison below nonlinear output limiting.
    tone.levelVelocitySens = 0;
    patch.delayOn = patch.reverbOn = false;
    return patch;
}

std::vector<float> render (const septum::Patch& patch, double sampleRate,
                           int blockSize = 256)
{
    septum::Engine engine;
    engine.prepare (sampleRate, 256);
    engine.setPatch (patch);
    engine.reset();
    engine.noteOn (69, 127);
    std::vector<float> left (static_cast<std::size_t> (sampleRate * 0.5));
    std::vector<float> right (left.size());
    for (std::size_t pos = 0; pos < left.size(); pos += blockSize)
        engine.process (left.data() + pos, right.data() + pos,
                        static_cast<int> (std::min (left.size() - pos,
                                                   std::size_t (blockSize))));
    return left;
}

double relativeDifference (const std::vector<float>& a,
                           const std::vector<float>& b, std::size_t first)
{
    double error = 0.0, energy = 0.0;
    for (std::size_t i = first; i < a.size(); ++i)
    {
        error += std::pow (double (a[i]) - b[i], 2.0);
        energy += double (a[i]) * a[i];
    }
    return std::sqrt (error / std::max (energy, 1.0e-30));
}

void testFractionalSourceReset()
{
    for (const double rate : { 44100.0, 48000.0, 96000.0 })
    {
        const auto patch = feedbackPatch (0, true);
        const auto audio = render (patch, rate);
        septum::Engine engine;
        engine.prepare (rate, 256);
        const int transport = engine.latencySamples()
                            - septum::AnalogOutput::latencySamples;
        septum::AnalogOutput output;
        output.prepare (rate);
        std::vector<double> reference (audio.size());
        const double masterHz = 440.0 * std::exp2 (11.0 / 1200.0);
        const double ratio = std::exp2 (-1.0 + (7.0 - 11.0) / 1200.0);
        for (std::size_t i = 0; i < reference.size(); ++i)
        {
            // Independently derived: an FB oscillator with feedback zero
            // is a raw ramp. When f1 < f2, synchronization gives
            // 2*(f1/f2)*frac(t*f2)-1. Fractional OSC2 wraps matter here.
            double raw = 0.0;
            if (i >= static_cast<std::size_t> (transport))
            {
                const double phase = (i - transport + 1.0) * masterHz / rate;
                raw = 2.0 * ratio * (phase - std::floor (phase)) - 1.0;
            }
            reference[i] = output.processSample (raw);
        }

        // Fit overall gain and the analog coupling capacitor's startup
        // state. Neither fitted term can hide the wrong period or reset.
        const auto first = static_cast<std::size_t> (rate * 0.2);
        double xx = 0.0, xc = 0.0, cc = 0.0, xy = 0.0, cy = 0.0;
        double sum = 0.0, energy = 0.0;
        const auto coupling = [rate, first] (std::size_t i)
        {
            return std::exp (-double (i - first)
                            / (rate * septum::AnalogOutput::couplingSeconds));
        };
        for (std::size_t i = first; i < audio.size(); ++i)
        {
            const double x = reference[i], c = coupling (i), y = audio[i];
            xx += x * x; xc += x * c; cc += c * c;
            xy += x * y; cy += c * y;
            sum += y; energy += y * y;
        }
        const double determinant = xx * cc - xc * xc;
        const double gain = (xy * cc - cy * xc) / determinant;
        const double dc = (cy * xx - xy * xc) / determinant;
        double error = 0.0;
        for (std::size_t i = first; i < audio.size(); ++i)
            error += std::pow (audio[i] - gain * reference[i] - dc * coupling (i), 2.0);
        const double relative = std::sqrt (error / (energy - sum * sum
                                            / double (audio.size() - first)));
        std::printf ("FB SYNC %.0f Hz: fractional-ramp relative error %.9g\n", rate, relative);
        expect (relative < 0.002, "FB source follows fractional master wraps at "
                                  + std::to_string (int (rate)) + " Hz");
    }
}

void testFeedbackRemainsActive()
{
    constexpr double rate = 44100.0;
    for (const int feedback : { 0, 48, 96, 127 })
    {
        const auto mixed = render (feedbackPatch (feedback, false), rate);
        const auto synced = render (feedbackPatch (feedback, true), rate);
        const double difference = relativeDifference (mixed, synced, 8820);
        std::printf ("FB %d: MIX/SYNC relative difference %.6f\n", feedback, difference);
        expect (difference > 0.25, "SYNC changes FB OSC at feedback "
                                    + std::to_string (feedback));
    }

    // Two octaves below the master, the feedback tap predates the preceding
    // reset. Clearing the comb on every cycle would erase its entire input
    // and make the feedback control ineffective in this fixture.
    const auto dry = render (feedbackPatch (0, true, -24), rate);
    const auto fed = render (feedbackPatch (96, true, -24), rate);
    const double difference = relativeDifference (dry, fed, 8820);
    std::printf ("FB history across master resets: relative difference %.6f\n", difference);
    expect (difference > 0.02, "feedback survives across multiple master cycles");

    // The source clock is audio-rate; host block division cannot move it.
    const auto divided = render (feedbackPatch (96, true, -24), rate, 37);
    expect (relativeDifference (fed, divided, 8820) < 1.0e-6,
            "FB SYNC source reset is independent of host block division");
}

void testMasterOnlyOutputUnchanged()
{
    // Selecting SYNC changes only the slave. With BALANCE fully right, the
    // audible FB oscillator is OSC2 and must be identical in MIX and SYNC.
    auto patch = feedbackPatch (96, false);
    patch.upper.osc1.wave = septum::Waveform::Sine;
    patch.upper.osc2.wave = septum::Waveform::FbOsc;
    patch.upper.osc2.pulseWidth = 96;
    patch.upper.balance = 63;
    const auto mixed = render (patch, 44100.0);
    patch.upper.mixType = septum::MixModType::Sync;
    const auto synced = render (patch, 44100.0);
    expect (relativeDifference (mixed, synced, 8820) == 0.0,
            "FB OSC as an isolated master is unchanged by SYNC");
}
} // namespace

int main()
{
    testFractionalSourceReset();
    testFeedbackRemainsActive();
    testMasterOnlyOutputUnchanged();
    std::printf ("Feedback sync: %d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
