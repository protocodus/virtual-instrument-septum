// OM p. 38: AMP ENV controls the onset and release of the same sounding
// note. The oversampler's transport must not advance that envelope relative
// to its audio. See Docs/fidelity/source-audits/amp-envelope-latency.md.
#include "DSP/SeptumEngine.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

namespace
{
int checks = 0, failures = 0;
constexpr double pi = 3.14159265358979323846;

void expect (bool ok, const std::string& message)
{
    ++checks;
    if (! ok)
    {
        ++failures;
        std::fprintf (stderr, "FAIL: %s\n", message.c_str());
    }
}

septum::Patch patchForTest()
{
    septum::Patch patch;
    patch.patchLevel = 127;
    patch.upper.osc1.wave = septum::Waveform::Sine;
    patch.upper.balance = -63;
    patch.upper.filterType = septum::FilterType::Bypass;
    patch.upper.level = 24;
    patch.upper.ampEnvAttack = patch.upper.ampEnvDecay = patch.upper.ampEnvRelease = 0;
    patch.upper.ampEnvSustain = 127;
    patch.delayOn = patch.reverbOn = false;
    return patch;
}

std::vector<float> render (septum::Engine& engine, int count, int block)
{
    std::vector<float> left (static_cast<std::size_t> (count)), right (left.size());
    for (int pos = 0; pos < count; pos += block)
        engine.process (left.data() + pos, right.data() + pos, std::min (block, count - pos));
    return left;
}

void testAudioEnvelopeAlignment()
{
    for (double rate : { 44100.0, 48000.0, 96000.0, 192000.0 })
        for (int block : { 1, 37, 256 })
        {
            septum::Engine engine;
            engine.prepare (rate, 256);
            engine.setPatch (patchForTest());
            engine.setMasterLevel (127);
            engine.reset();
            const int transport = engine.latencySamples() - septum::AnalogOutput::latencySamples;
            const int onSamples = static_cast<int> (rate * 0.004);
            engine.noteOn (69, 127);
            auto audio = render (engine, onSamples, block);
            engine.noteOff (69);
            const auto released = render (engine, static_cast<int> (rate * 0.012), block);
            audio.insert (audio.end(), released.begin(), released.end());

            // The independent reference is a sine multiplied by the mapped
            // envelope, then transported as one signal. The clean shaper is
            // a pure delay, so swapping its order with multiplication is
            // valid only when the modulation is delayed by the same amount.
            septum::AnalogOutput output;
            output.prepare (rate);
            std::vector<double> expected (audio.size());
            const double attackSamples = septum::mapping::attackSeconds (0) * rate;
            const double releaseSamples = septum::mapping::decaySeconds (0) * rate;
            for (std::size_t i = 0; i < expected.size(); ++i)
            {
                const int source = static_cast<int> (i) - transport;
                double raw = 0.0;
                if (source >= 0)
                {
                    double env = std::min (1.0, (source + 1.0) / attackSamples);
                    if (source >= onSamples)
                    {
                        env = std::exp (-6.907755 * (source - onSamples + 1.0) / releaseSamples);
                        if (env < 1.0e-5)
                            env = 0.0;
                    }
                    raw = env * std::sin (2.0 * pi * 440.0 * (source + 1.0) / rate);
                }
                expected[i] = output.processSample (raw);
            }
            // Fit only constant gain; it cannot conceal attack shape or
            // release timing. All panel gains are static in this fixture.
            double xy = 0.0, xx = 0.0, yy = 0.0;
            for (std::size_t i = 0; i < audio.size(); ++i)
            {
                xy += audio[i] * expected[i];
                xx += expected[i] * expected[i];
                yy += double (audio[i]) * audio[i];
            }
            const double gain = xy / xx;
            double error = 0.0;
            for (std::size_t i = 0; i < audio.size(); ++i)
                error += std::pow (audio[i] - gain * expected[i], 2.0);
            const double relative = std::sqrt (error / yy);
            if (block == 256)
                std::printf ("AMP timing %.0f Hz: transport %d samples, relative error %.9g\n",
                             rate, transport, relative);
            expect (relative < 1.0e-5, "AMP envelope follows transported note at "
                    + std::to_string (int (rate)) + " Hz / block " + std::to_string (block));
            expect (engine.activeVoiceCount() == 0, "transported release eventually frees voice");
        }
}

void testReleaseDrainAndPanic()
{
    for (double rate : { 44100.0, 48000.0, 96000.0, 192000.0 })
    {
        septum::Engine engine;
        engine.prepare (rate, 256);
        engine.setPatch (patchForTest());
        engine.noteOn (69, 127);
        render (engine, static_cast<int> (rate * 0.02), 256);
        engine.noteOff (69);
        const int transport = engine.latencySamples() - septum::AnalogOutput::latencySamples;
        const int releaseToIdle = static_cast<int> (std::floor (
            std::log (1.0e-5) * septum::mapping::decaySeconds (0) * rate / -6.907755)) + 1;
        render (engine, releaseToIdle, 1);
        expect (engine.activeVoiceCount() == (transport > 0 ? 1 : 0),
                "a voice remains allocated while its delayed envelope is audible");
        if (transport > 0)
            render (engine, transport, 1);
        expect (engine.activeVoiceCount() == 0, "voice frees after envelope delay drains");

        engine.noteOn (72, 127);
        render (engine, 8, 1);
        engine.allSoundOff();
        expect (engine.activeVoiceCount() == 0, "panic does not wait for envelope transport");
        const auto silence = render (engine, 256, 1);
        expect (std::all_of (silence.begin(), silence.end(), [] (float y) { return y == 0.0f; }),
                "panic also discards the queued envelope audio");
    }
}
} // namespace

int main()
{
    testAudioEnvelopeAlignment();
    testReleaseDrainAndPanic();
    std::printf ("AMP envelope latency: %d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
