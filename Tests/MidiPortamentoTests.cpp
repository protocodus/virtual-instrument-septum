// SH-201 OM p. 72 receives CC#84. MIDI 1.0 Detailed Specification pp. 16-17
// defines its one-note scope, switch override and source-voice continuation.
// https://static.roland.com/assets/media/pdf/SH-201_OM.pdf#page=72
// https://www.seriesten.org/docs/protocols/MIDI_1.0_Detailed_Specification.pdf#page=21
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

septum::Patch sinePatch (bool lower, septum::MonoMode mode)
{
    septum::Patch patch;
    patch.keyboardPart = lower ? septum::KeyboardPart::Lower
                               : septum::KeyboardPart::Upper;
    for (auto* tone : { &patch.upper, &patch.lower })
    {
        tone->mono = mode;
        tone->portamento = false;
        tone->portamentoTime = 95;
        tone->osc1.wave = tone->osc2.wave = septum::Waveform::Sine;
        tone->osc1.coarse = tone->osc2.coarse = 0;
        tone->osc1.fine = tone->osc2.fine = 0;
        tone->osc1.pitchEnvDepth = tone->osc2.pitchEnvDepth = 0;
        tone->balance = -63;
        tone->filterType = septum::FilterType::Bypass;
        tone->ampEnvAttack = tone->ampEnvDecay = tone->ampEnvRelease = 0;
        tone->ampEnvSustain = 127;
        tone->level = 30;
        tone->levelVelocitySens = 0;
        tone->lfo1.depth1 = tone->lfo1.depth2 = 0;
        tone->lfo2.depth1 = tone->lfo2.depth2 = 0;
    }
    patch.delayOn = patch.reverbOn = false;
    return patch;
}

std::vector<float> render (septum::Engine& engine, int samples, int block)
{
    std::vector<float> left (static_cast<std::size_t> (samples));
    std::vector<float> right (static_cast<std::size_t> (samples));
    for (int position = 0; position < samples; position += block)
        engine.process (left.data() + position, right.data() + position,
                        std::min (block, samples - position));
    return left;
}

double peakDifference (const std::vector<float>& a, const std::vector<float>& b)
{
    double peak = 0.0;
    for (std::size_t i = 0; i < a.size(); ++i)
        peak = std::max (peak, std::abs (static_cast<double> (a[i]) - b[i]));
    return peak;
}

double energy (const std::vector<float>& audio)
{
    double sum = 0.0;
    for (float sample : audio)
        sum += sample * static_cast<double> (sample);
    return sum;
}

void testForcedGlide()
{
    double worstDifference = 0.0;
    for (double rate : { 44100.0, 48000.0, 96000.0 })
        for (bool lower : { false, true })
            for (auto mode : { septum::MonoMode::Poly, septum::MonoMode::Solo,
                               septum::MonoMode::SoloLegato })
                for (int block : { 31, 256 })
                {
                    auto patch = sinePatch (lower, mode);
                    auto reference = sinePatch (lower, septum::MonoMode::Poly);
                    (lower ? reference.lower : reference.upper).portamento = true;
                    septum::Engine forced, enabled;
                    forced.prepare (rate, block);
                    enabled.prepare (rate, block);
                    forced.setPatch (patch);
                    enabled.setPatch (reference);
                    // No source note is sounding. CC84 must still apply to
                    // the next note, even with PORTAMENTO off or first-key
                    // SOLO+LEGATO articulation.
                    forced.setPortamentoControl (60);
                    enabled.setPortamentoControl (60);
                    forced.noteOn (84, 100);
                    enabled.noteOn (84, 100);
                    const int count = static_cast<int> (rate * 0.16);
                    const auto a = render (forced, count, block);
                    const auto b = render (enabled, count, block);
                    const auto label = "forced glide rate=" + std::to_string (rate)
                        + " lower=" + std::to_string (lower)
                        + " mode=" + std::to_string (static_cast<int> (mode))
                        + " block=" + std::to_string (block);
                    const double difference = peakDifference (a, b);
                    worstDifference = std::max (worstDifference, difference);
                    expect (energy (a) > 1.0e-5, label + " is audible");
                    expect (difference < 2.0e-7, label + " ignores panel switch");
                }
    std::printf ("CC84 forced glide maximum audio difference %.9g\n", worstDifference);
}

void testSourceVoiceHandoff()
{
    for (double rate : { 44100.0, 48000.0, 96000.0 })
        for (bool lower : { false, true })
            for (auto mode : { septum::MonoMode::Poly, septum::MonoMode::Solo,
                               septum::MonoMode::SoloLegato })
            {
                auto patch = sinePatch (lower, mode);
                auto reference = sinePatch (lower, septum::MonoMode::SoloLegato);
                for (auto* p : { &patch, &reference })
                {
                    auto& tone = lower ? p->lower : p->upper;
                    tone.ampEnvAttack = 55;
                    tone.ampEnvSustain = 20;
                }
                (lower ? reference.lower : reference.upper).portamento = true;
                septum::Engine controlled, legato;
                controlled.prepare (rate, 256);
                legato.prepare (rate, 256);
                controlled.setPatch (patch);
                legato.setPatch (reference);
                for (auto* engine : { &controlled, &legato })
                {
                    engine->noteOn (60, 100);
                    render (*engine, static_cast<int> (rate * 0.25), 256);
                }
                controlled.setPortamentoControl (60);
                // A CC84 message itself cannot disturb a sounding voice.
                expect (peakDifference (render (controlled, 960, 256),
                                        render (legato, 960, 256)) < 2.0e-7,
                        "CC84 alone leaves the sounding source unchanged");
                controlled.noteOn (72, 100);
                legato.noteOn (72, 100);
                const auto a = render (controlled, 1920, 256);
                const auto b = render (legato, 1920, 256);
                expect (controlled.activeVoiceCount() == 1,
                        "CC84 transfers source voice without allocating another");
                expect (peakDifference (a, b) < 2.0e-7,
                        "CC84 source handoff glides without retriggering attack");
                controlled.noteOff (60);
                legato.noteOff (60);
                expect (peakDifference (render (controlled, 1920, 256),
                                        render (legato, 1920, 256)) < 2.0e-7,
                        "source note-off does not release the transferred note");
                controlled.noteOff (72);
                render (controlled, static_cast<int> (rate * 0.1), 256);
                expect (controlled.activeVoiceCount() == 0,
                        "target note-off releases the transferred note");
            }
}

void testOneShotAndRouting()
{
    constexpr double rate = 48000.0;
    for (auto mode : { septum::KeyboardMode::Single, septum::KeyboardMode::Dual,
                       septum::KeyboardMode::Split })
    {
        auto patch = sinePatch (false, septum::MonoMode::Poly);
        patch.keyboardMode = mode;
        patch.splitPoint = 60;
        septum::Engine oneShot, explicitPitch;
        for (auto* engine : { &oneShot, &explicitPitch })
        {
            engine->prepare (rate, 256);
            engine->setPatch (patch);
            engine->setPortamentoControl (48);
            engine->noteOn (72, 100);
            render (*engine, 2400, 256);
        }
        // The next incoming key is in the other split half. It must not
        // inherit a CC84 source that only the first key was meant to use.
        oneShot.noteOn (55, 100);
        explicitPitch.setPortamentoControl (55);
        explicitPitch.noteOn (55, 100);
        expect (peakDifference (render (oneShot, 4800, 256),
                                render (explicitPitch, 4800, 256)) < 2.0e-7,
                "CC84 affects one incoming key, not later notes or split parts");
        expect (oneShot.activeVoiceCount() == (mode == septum::KeyboardMode::Dual ? 4 : 2),
                "ordinary second note remains polyphonic");
    }

    auto patch = sinePatch (false, septum::MonoMode::Poly);
    patch.keyboardMode = septum::KeyboardMode::Dual;
    septum::Engine dual;
    dual.prepare (rate, 256);
    dual.setPatch (patch);
    dual.noteOn (60, 100);
    render (dual, 2400, 256);
    dual.setPortamentoControl (60);
    dual.noteOn (72, 100);
    expect (dual.activeVoiceCount (true) == 1 && dual.activeVoiceCount (false) == 1,
            "one CC84 message transfers both layered source voices");

    // An unrelated held polyphonic voice must survive source transfer.
    patch.keyboardMode = septum::KeyboardMode::Single;
    septum::Engine poly;
    poly.prepare (rate, 256);
    poly.setPatch (patch);
    poly.noteOn (60, 100);
    poly.noteOn (67, 100);
    render (poly, 2400, 256);
    poly.setPortamentoControl (60);
    poly.noteOn (72, 100);
    expect (poly.activeVoiceCount() == 2,
            "CC84 leaves unrelated polyphonic voices in place");
    poly.noteOff (60);
    poly.noteOff (72);
    render (poly, 4800, 256);
    expect (poly.activeVoiceCount() == 1,
            "ending the target leaves the unrelated held note sounding");
}

void testResetAndZeroTime()
{
    constexpr double rate = 48000.0;
    for (bool panic : { false, true })
    {
        auto patch = sinePatch (false, septum::MonoMode::Poly);
        septum::Engine marked, plain;
        for (auto* engine : { &marked, &plain })
        {
            engine->prepare (rate, 256);
            engine->setPatch (patch);
        }
        marked.setPortamentoControl (36);
        if (panic)
        {
            marked.allSoundOff();
            plain.allSoundOff();
        }
        else
        {
            marked.reset();
            plain.reset();
        }
        marked.noteOn (84, 100);
        plain.noteOn (84, 100);
        expect (peakDifference (render (marked, 4800, 256),
                                render (plain, 4800, 256)) < 2.0e-7,
                "reset/panic clears unconsumed portamento control");
    }
    auto patch = sinePatch (false, septum::MonoMode::Poly);
    patch.upper.portamentoTime = 0;
    septum::Engine marked, plain;
    for (auto* engine : { &marked, &plain })
    {
        engine->prepare (rate, 256);
        engine->setPatch (patch);
    }
    marked.setPortamentoControl (36);
    marked.noteOn (84, 100);
    plain.noteOn (84, 100);
    expect (peakDifference (render (marked, 4800, 256),
                            render (plain, 4800, 256)) < 2.0e-7,
            "CC84 respects zero portamento time");
}

void testTargetOffBeforeSourceOff()
{
    for (auto mode : { septum::MonoMode::Poly, septum::MonoMode::Solo,
                       septum::MonoMode::SoloLegato })
    {
        septum::Engine engine;
        engine.prepare (48000.0, 256);
        engine.setPatch (sinePatch (false, mode));
        engine.noteOn (60, 100);
        render (engine, 2400, 256);
        engine.setPortamentoControl (60);
        engine.noteOn (72, 100);
        render (engine, 2400, 256);
        engine.noteOff (72);
        render (engine, 4800, 256);
        expect (engine.activeVoiceCount() == 0,
                "target off ends CC84 handoff before the source off arrives");
        engine.noteOff (60);
        render (engine, 4800, 256);
        expect (engine.activeVoiceCount() == 0,
                "late source off cannot revive the ended target");
    }
}

void testReleasingSourceKeepsEnvelope()
{
    for (auto mode : { septum::MonoMode::Poly, septum::MonoMode::Solo })
    {
        auto patch = sinePatch (false, mode);
        patch.upper.portamentoTime = 0;
        patch.upper.ampEnvRelease = 60;
        septum::Engine transferred, releasing;
        for (auto* engine : { &transferred, &releasing })
        {
            engine->prepare (48000.0, 256);
            engine->setPatch (patch);
            engine->noteOn (60, 100);
            render (*engine, 2400, 256);
            engine->noteOff (60);
            render (*engine, 256, 256);
        }
        transferred.setPortamentoControl (60);
        transferred.noteOn (72, 100);
        // Transpose the un-retriggered reference tail by the same octave.
        // This isolates envelope continuation from the glide's time law.
        releasing.setMasterKeyShift (12);
        expect (transferred.activeVoiceCount() == 1,
                "CC84 reuses an audible source already in release");
        expect (peakDifference (render (transferred, 9600, 256),
                                render (releasing, 9600, 256)) < 2.0e-7,
                "releasing source continues its envelope without a new attack");
    }
}
} // namespace

int main()
{
    testForcedGlide();
    testSourceVoiceHandoff();
    testOneShotAndRouting();
    testResetAndZeroTime();
    testTargetOffBeforeSourceOff();
    testReleasingSourceKeepsEnvelope();
    std::printf ("MIDI portamento: %d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
