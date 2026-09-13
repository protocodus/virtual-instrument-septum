// Hardware contracts from Roland SH-201 OM pp. 63/66 and the AK4552
// datasheet MS0055-E-01 pp. 5/10. These tests verify documented behavior and
// numerical realizations; they are not comparisons to captured hardware.
#include "DSP/SeptumEngine.h"
#include "DSP/AnalogInput.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

namespace
{
constexpr double pi = 3.14159265358979323846;
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

void codecDcRemovalTests()
{
    for (double rate : { 44100.0, 48000.0, 96000.0, 192000.0 })
    {
        for (double frequency : { 1.0, 3.4, 20.0, 1000.0 })
        {
            septum::AnalogInput input;
            input.prepare (rate);
            double sine = 0.0, cosine = 0.0;
            const int warm = static_cast<int> (rate);
            const int measured = static_cast<int> (5.0 * rate);
            for (int i = 0; i < warm + measured; ++i)
            {
                const double phase = 2.0 * pi * frequency * i / rate;
                const double y = input.processSample (std::sin (phase));
                if (i >= warm)
                {
                    sine += y * std::sin (phase);
                    cosine += y * std::cos (phase);
                }
            }
            const double gain = 2.0 * std::hypot (sine, cosine) / measured;
            // Independently specified continuous one-pole response. Bilinear
            // warping is negligible around the published 3.4/20 Hz points.
            const double reference = frequency / std::hypot (frequency, 3.4);
            const double errorDb = 20.0 * std::log10 (gain / reference);
            expect (std::abs (errorDb) < 0.0001,
                    "codec HPF response at " + std::to_string (frequency)
                    + " Hz / " + std::to_string (rate) + " Hz");
            if (frequency == 20.0)
                std::printf ("codec HPF %.0f Hz: gain at 20 Hz = %.5f dB\n",
                             rate, 20.0 * std::log10 (gain));
        }
        septum::AnalogInput input;
        input.prepare (rate);
        double last = 0.0;
        for (int i = 0; i < static_cast<int> (2.0 * rate); ++i)
            last = input.processSample (0.5);
        expect (std::abs (last) < 1.0e-12, "codec rejects sustained input DC");
        input.reset();
        expect (input.processSample (0.0) == 0.0, "codec reset clears its history");
    }

    // The engine must filter the external oscillator tap too. A held EXT-IN
    // voice fed DC used to sustain DC internally; ring modulation exposed it
    // as an audible copy of OSC2 even after the input should have settled.
    septum::Engine engine;
    engine.prepare (44100.0, 256);
    septum::Patch patch;
    patch.upper.osc1.wave = septum::Waveform::ExtIn;
    patch.upper.filterType = septum::FilterType::Bypass;
    patch.upper.osc2.wave = septum::Waveform::Sine;
    patch.upper.mixType = septum::MixModType::Ring;
    patch.upper.balance = -63;
    patch.delayOn = patch.reverbOn = false;
    engine.setPatch (patch);
    septum::ExternalInput external;
    external.inputVolume = 127;
    engine.setExternalInput (external);
    engine.reset();
    engine.noteOn (60, 127);
    std::array<float, 256> constant, left {}, right {};
    constant.fill (0.5f);
    double latePeak = 0.0;
    for (int block = 0; block < 1750; ++block)
    {
        engine.process (left.data(), right.data(), 256, constant.data(), constant.data());
        if (block >= 1730)
            for (float y : left)
                latePeak = std::max (latePeak, std::abs (double (y)));
    }
    std::printf ("codec ring integration late peak %.9g\n", latePeak);
    expect (latePeak < 1.0e-6, "codec DC removal precedes the EXT-IN ring-modulation tap");
}

std::vector<float> delayTake (double amplitude, int feedback, bool modulated = false)
{
    constexpr int rate = 16000;
    septum::Engine engine;
    engine.prepare (rate, 256);
    septum::Patch patch;
    patch.upper.osc1.wave = septum::Waveform::ExtIn;
    patch.upper.filterType = septum::FilterType::Bypass;
    patch.upper.level = 127;
    patch.upper.delayDepth = 127;
    patch.upper.reverbDepth = 0;
    patch.delayOn = true;
    patch.reverbOn = false;
    patch.delay.time = modulated ? 15 : 127; // voiced endpoint: 1.3 s, integer samples
    patch.delay.feedback = feedback;
    patch.delay.hfDamp = 17;
    patch.delay.modulationDepth = modulated ? 127 : 0;
    patch.delay.modulationRate = modulated ? 127 : 0;
    engine.setPatch (patch);
    septum::ExternalInput external;
    external.inputVolume = 127;
    engine.setExternalInput (external);
    engine.reset();
    engine.noteOn (60, 127);
    std::vector<float> signal (rate * 6), out (signal.size()), right (signal.size());
    for (int i = 0; i < rate / 5; ++i)
        signal[static_cast<std::size_t> (i)] = static_cast<float> (
            amplitude * std::sin (2.0 * pi * 1000.0 * i / rate));
    for (std::size_t i = 0; i < signal.size(); i += 256)
        engine.process (out.data() + i, right.data() + i,
                        static_cast<int> (std::min (std::size_t (256), signal.size() - i)),
                        signal.data() + i, signal.data() + i);
    return out;
}

void delayFeedbackTests()
{
    constexpr int rate = 16000, delay = 20800;
    for (int feedback : { -98, -50, 0, 50, 98 })
    {
        const auto quiet = delayTake (0.1, feedback);
        const auto loud = delayTake (1.0, feedback);
        double error = 0.0, energy = 0.0;
        for (int i = delay + rate / 20; i < delay + rate / 6; ++i)
        {
            const double reference = 10.0 * quiet[static_cast<std::size_t> (i)];
            error += std::pow (loud[static_cast<std::size_t> (i)] - reference, 2.0);
            energy += reference * reference;
        }
        const double relativeError = std::sqrt (error / energy);
        expect (relativeError < 1.0e-6,
                "delay first echo remains linear at feedback " + std::to_string (feedback));
        for (int echo = 1; echo < 3; ++echo)
        {
            double cross = 0.0, norm = 0.0;
            for (int i = delay + rate / 20; i < delay + rate / 6; ++i)
            {
                const double first = loud[static_cast<std::size_t> (i)];
                cross += first * loud[static_cast<std::size_t> (i + echo * delay)];
                norm += first * first;
            }
            const double measured = cross / norm;
            const double expected = std::pow (feedback / 100.0, echo);
            expect (std::abs (measured - expected) < 2.0e-6,
                    "delay repeat preserves signed feedback percent " + std::to_string (feedback));
            if (echo == 1)
                std::printf ("delay feedback %+d%%: measured repeat ratio %.8f, linearity error %.3g\n",
                             feedback, measured, relativeError);
        }
    }
    for (int feedback : { -98, 98 })
    {
        const auto stressed = delayTake (1.0, feedback, true);
        bool finite = true;
        double latePeak = 0.0;
        for (std::size_t i = 0; i < stressed.size(); ++i)
        {
            finite = finite && std::isfinite (stressed[i]);
            if (i >= stressed.size() - rate)
                latePeak = std::max (latePeak, std::abs (double (stressed[i])));
        }
        expect (finite && latePeak < 1.0e-5,
                "maximum signed feedback and modulation settle after the source stops");
        std::printf ("delay modulation stress %+d%%: final-second peak %.9g\n",
                     feedback, latePeak);
    }
}

void arpDeadlineTests()
{
    constexpr double rate = 44100.0, bpm = 137.0;
    const double step = rate * 60.0 / bpm / 6.0; // OM 1/24 = six grids per beat
    for (int block : { 7, 64, 257 })
        for (bool tied : { false, true })
        {
            septum::Patch patch;
            patch.delayOn = patch.reverbOn = false;
            patch.upper.filterType = septum::FilterType::Bypass;
            patch.upper.ampEnvRelease = 0;
            patch.tempo = bpm;
            patch.arpeggio.on = true;
            patch.arpeggio.grid = septum::ArpeggioGrid::TwentyFourth;
            patch.arpeggio.duration = septum::ArpeggioDuration::P30;
            patch.arpeggio.style = septum::ArpeggioStyle {};
            patch.arpeggio.style.endStep = tied ? 3 : 1;
            patch.arpeggio.style.cells[0][0] = 100;
            if (tied)
                patch.arpeggio.style.cells[1][0] = septum::arpeggioTie;
            septum::Engine engine;
            engine.prepare (rate, block);
            engine.setPatch (patch);
            engine.reset();
            engine.noteOn (60, 100);
            std::vector<float> left (block), right (block);
            int position = 0;
            const auto at = [&] (int sample, int held)
            {
                while (position < sample)
                {
                    const int count = std::min (block, sample - position);
                    engine.process (left.data(), right.data(), count);
                    position += count;
                }
                engine.process (left.data(), right.data(), 1);
                ++position;
                expect (engine.heldVoiceCount (true) == held,
                        "arp sample " + std::to_string (sample) + ", block "
                        + std::to_string (block) + (tied ? ", tied" : ", plain"));
            };
            // Compare both sides of 24 independent note boundaries. The
            // fractional step period must not be truncated and accumulated.
            for (int cycle = 0; cycle < 24; ++cycle)
            {
                const double start = cycle * (tied ? 3.0 : 1.0) * step;
                const int on = static_cast<int> (std::ceil (start));
                const int off = static_cast<int> (std::ceil (start + (tied ? 1.3 : 0.3) * step));
                if (cycle > 0)
                    at (on - 1, 0);
                at (on, 1);
                at (off - 1, 1);
                at (off, 0);
            }
        }
}

void arpOverlapAndWrapTests()
{
    constexpr double rate = 48000.0, step = rate * 60.0 / 193.0 / 4.0;
    for (bool wrappedTie : { false, true })
        for (int block : { 31, 256 })
        {
            septum::Patch patch;
            patch.delayOn = patch.reverbOn = false;
            patch.tempo = 193;
            patch.arpeggio.on = true;
            patch.arpeggio.motif = septum::ArpeggioMotif::Up;
            patch.arpeggio.grid = septum::ArpeggioGrid::Sixteenth;
            patch.arpeggio.duration = wrappedTie ? septum::ArpeggioDuration::P30
                                                 : septum::ArpeggioDuration::P120;
            patch.arpeggio.style = septum::ArpeggioStyle {};
            patch.arpeggio.style.endStep = wrappedTie ? 3 : 1;
            patch.arpeggio.style.cells[wrappedTie ? 2 : 0][0] = 100;
            if (wrappedTie)
                patch.arpeggio.style.cells[0][0] = septum::arpeggioTie;
            septum::Engine engine;
            engine.prepare (rate, block);
            engine.setPatch (patch);
            engine.reset();
            engine.noteOn (60, 100);
            engine.noteOn (67, 100);
            std::vector<float> left (block), right (block);
            int position = 0;
            const auto at = [&] (int sample, int held)
            {
                while (position < sample)
                {
                    const int count = std::min (block, sample - position);
                    engine.process (left.data(), right.data(), count);
                    position += count;
                }
                engine.process (left.data(), right.data(), 1);
                ++position;
                expect (engine.heldVoiceCount (true) == held,
                        std::string (wrappedTie ? "wrapped tie" : "120% overlap")
                        + " gate deadline at sample " + std::to_string (sample));
            };
            for (int cycle = 0; cycle < 12; ++cycle)
            {
                if (wrappedTie)
                {
                    const int on = static_cast<int> (std::ceil ((3 * cycle + 2) * step));
                    const int off = static_cast<int> (std::ceil ((3 * cycle + 3.3) * step));
                    at (on - 1, 0);
                    at (on, 1);
                    at (off - 1, 1);
                    at (off, 0);
                }
                else
                {
                    const int on = static_cast<int> (std::ceil ((cycle + 1) * step));
                    const int off = static_cast<int> (std::ceil ((cycle + 1.2) * step));
                    at (on - 1, 1);
                    at (on, 2);
                    at (off - 1, 2);
                    at (off, 1);
                }
            }
        }
}

void arpTempoEditTest()
{
    constexpr double rate = 44100.0;
    const double oldStep = rate * 60.0 / 137.0 / 6.0;
    const double newStep = rate * 60.0 / 193.0 / 6.0;
    septum::Patch patch;
    patch.delayOn = patch.reverbOn = false;
    patch.tempo = 137;
    patch.arpeggio.on = true;
    patch.arpeggio.grid = septum::ArpeggioGrid::TwentyFourth;
    patch.arpeggio.duration = septum::ArpeggioDuration::P30;
    patch.arpeggio.style = septum::ArpeggioStyle {};
    patch.arpeggio.style.endStep = 1;
    patch.arpeggio.style.cells[0][0] = 100;
    septum::Engine engine;
    engine.prepare (rate, 31);
    engine.setPatch (patch);
    engine.reset();
    engine.noteOn (60, 100);
    std::array<float, 31> left {}, right {};
    int position = 0;
    const auto at = [&] (int sample, int held)
    {
        while (position < sample)
        {
            const int count = std::min (31, sample - position);
            engine.process (left.data(), right.data(), count);
            position += count;
        }
        engine.process (left.data(), right.data(), 1);
        ++position;
        expect (engine.heldVoiceCount (true) == held,
                "arpeggio tempo edit preserves gate at sample " + std::to_string (sample));
    };
    at (static_cast<int> (std::ceil (oldStep * 0.3)), 0);
    patch.tempo = 193;
    engine.setPatch (patch);
    // An edit preserves the pending interval; subsequently scheduled grids
    // and their gates use the new tempo. This lifecycle policy is a plug-in
    // choice, while six grids per beat and 30% gates are Roland's contract.
    for (int cycle = 0; cycle < 12; ++cycle)
    {
        const double start = oldStep + cycle * newStep;
        const int on = static_cast<int> (std::ceil (start));
        const int off = static_cast<int> (std::ceil (start + 0.3 * newStep));
        at (on - 1, 0);
        at (on, 1);
        at (off - 1, 1);
        at (off, 0);
    }
}
} // namespace

int main()
{
    codecDcRemovalTests();
    delayFeedbackTests();
    arpDeadlineTests();
    arpOverlapAndWrapTests();
    arpTempoEditTest();
    std::printf ("Hardware performance fidelity: %d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
