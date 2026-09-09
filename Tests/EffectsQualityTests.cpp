// Effects quality regressions. These establish DSP behavior and numerical
// accuracy, not a match to an unrecorded SH-201's proprietary effects.
#include "DSP/DelayInterpolation.h"
#include "DSP/SeptumEngine.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <complex>
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

struct Audio
{
    explicit Audio (std::size_t count) : left (count), right (count) {}
    std::vector<float> left, right;

    double peak() const
    {
        double result = 0.0;
        for (std::size_t i = 0; i < left.size(); ++i)
            result = std::max ({ result, std::abs (double (left[i])),
                                std::abs (double (right[i])) });
        return result;
    }

    double rms (std::size_t from = 0, std::size_t to = 0) const
    {
        if (to == 0)
            to = left.size();
        double sum = 0.0;
        for (std::size_t i = from; i < to; ++i)
            sum += double (left[i]) * left[i] + double (right[i]) * right[i];
        return std::sqrt (sum / (2.0 * (to - from)));
    }

    bool finite() const
    {
        for (std::size_t i = 0; i < left.size(); ++i)
            if (! std::isfinite (left[i]) || ! std::isfinite (right[i]))
                return false;
        return true;
    }
};

Audio render (septum::Engine& engine, std::size_t frames, int block = 256)
{
    Audio output (frames);
    for (std::size_t position = 0; position < frames; position += block)
        engine.process (output.left.data() + position, output.right.data() + position,
                        static_cast<int> (std::min (std::size_t (block), frames - position)));
    return output;
}

septum::Patch effectPatch (bool reverb)
{
    septum::Patch patch;
    patch.upper.osc1.wave = septum::Waveform::Sine;
    patch.upper.filterType = septum::FilterType::Bypass;
    patch.upper.ampEnvRelease = 0;
    patch.upper.level = 100;
    patch.delayOn = ! reverb;
    patch.reverbOn = reverb;
    patch.upper.delayDepth = reverb ? 0 : 100;
    patch.upper.reverbDepth = reverb ? 100 : 0;
    patch.delay.time = 80;
    patch.delay.feedback = 0;
    patch.reverb.time = 0;
    patch.reverb.size = 0;
    patch.reverb.lfDampGain = patch.reverb.hfDampGain = 0;
    return patch;
}

std::complex<double> response (double fraction, double radians)
{
    std::complex<double> result {};
    for (std::size_t i = 0; i < 4; ++i)
    {
        std::array<double, 4> basis {};
        basis[i] = 1.0;
        const double weight = septum::detail::delayLagrange4 (
            basis[0], basis[1], basis[2], basis[3], fraction);
        result += weight * std::polar (1.0, radians * (double (i) - 1.0));
    }
    return result;
}

void interpolationTests()
{
    using septum::detail::delayLagrange4;
    expect (delayLagrange4 (100.0, 0.123456789, -20.0, 300.0, 0.0) == 0.123456789,
            "integer delay returns its original stored sample exactly");
    expect (delayLagrange4 (100.0, -20.0, 0.123456789, 300.0, 1.0) == 0.123456789,
            "next integer endpoint returns its original stored sample exactly");
    double maximumGain = 0.0;
    for (int step = 0; step <= 100; ++step)
    {
        const double fraction = step / 100.0;
        expect (std::abs (delayLagrange4 (0.37, 0.37, 0.37, 0.37, fraction) - 0.37)
                    < 1.0e-12,
                "every interpolation phase preserves DC");
        // A Lagrange interpolator must reproduce polynomials through its
        // order. This checks coefficients independently of a sine fixture.
        const auto cubic = [] (double x) { return 0.7 * x * x * x - 0.2 * x * x + x - 0.4; };
        expect (std::abs (delayLagrange4 (cubic (-1), cubic (0), cubic (1), cubic (2),
                                        fraction) - cubic (fraction)) < 1.0e-12,
                "four-point interpolation reproduces a cubic exactly");
        for (int bin = 0; bin <= 512; ++bin)
            maximumGain = std::max (maximumGain, std::abs (response (fraction, pi * bin / 512)));
    }
    expect (maximumGain <= 1.0 + 1.0e-12,
            "fractional-delay response never boosts a frequency inside the feedback loop");
    for (double hz : { 10000.0, 15000.0 })
    {
        const double angle = 2.0 * pi * hz / 44100.0;
        const double linear = std::cos (angle * 0.5);
        const double lagrange = std::abs (response (0.5, angle));
        expect (lagrange > linear && lagrange <= 1.0,
                "half-sample interpolation reduces high-frequency loss without adding gain");
        std::printf ("44.1k half-sample delay, %.0f Hz: old linear %.3f dB/echo, "
                     "Lagrange %.3f dB/echo\n", hz,
                     20.0 * std::log10 (linear), 20.0 * std::log10 (lagrange));
    }
    const double lowFrequencyError = std::abs (
        response (0.37, 2.0 * pi * 1000.0 / 44100.0)
        - std::polar (1.0, 0.37 * 2.0 * pi * 1000.0 / 44100.0));
    expect (lowFrequencyError < 1.0e-5,
            "passband interpolation preserves both amplitude and fractional timing");
}

void bypassLifecycleTests()
{
    for (bool reverb : { false, true })
    {
        const auto take = [reverb] (bool cycle)
        {
            septum::Engine engine;
            engine.prepare (44100.0, 256);
            auto patch = effectPatch (reverb);
            engine.setPatch (patch);
            engine.reset();
            engine.noteOn (60, 110);
            (void) render (engine, 8 * 256);
            engine.noteOff (60);
            (void) render (engine, 14 * 256);
            if (cycle)
            {
                patch.delayOn = patch.reverbOn = false;
                engine.setPatch (patch);
            }
            (void) render (engine, 345 * 256); // two seconds OFF, with no new input
            patch.delayOn = ! reverb;
            patch.reverbOn = reverb;
            engine.setPatch (patch);
            return render (engine, 100 * 256);
        };
        const auto cycled = take (true);
        const auto decayed = take (false);
        expect (cycled.peak() < 1.0e-5,
                std::string (reverb ? "reverb" : "delay")
                    + " does not resurrect old notes after two seconds OFF (peak "
                    + std::to_string (cycled.peak()) + ")");
        std::printf ("%s OFF->ON after2s: peak %.9f, uninterrupted decay %.9f\n",
                     reverb ? "Reverb" : "Delay", cycled.peak(), decayed.peak());

        // Running the network while bypassed must not accidentally record
        // the notes played during OFF. Compare against sends that were zero.
        const auto silentInput = [reverb] (bool send)
        {
            septum::Engine engine;
            engine.prepare (44100.0, 256);
            auto patch = effectPatch (reverb);
            patch.delayOn = patch.reverbOn = false;
            if (! send)
                patch.upper.delayDepth = patch.upper.reverbDepth = 0;
            engine.setPatch (patch);
            engine.reset();
            engine.noteOn (60, 110);
            (void) render (engine, 4096);
            engine.noteOff (60);
            (void) render (engine, 4096);
            patch.delayOn = ! reverb;
            patch.reverbOn = reverb;
            engine.setPatch (patch);
            return render (engine, 44100);
        };
        const auto sends = silentInput (true), noSends = silentInput (false);
        expect (sends.left == noSends.left && sends.right == noSends.right,
                "bypassed effects accept no new direct sends");
    }
}

void engineInterpolationResponseTests()
{
    for (double hz : { 1000.0, 10000.0, 15000.0 })
    {
        const auto take = [hz] (bool send)
        {
            septum::Engine engine;
            engine.prepare (44100.0, 256);
            auto patch = effectPatch (false);
            patch.upper.osc1.wave = septum::Waveform::ExtIn;
            patch.upper.delayDepth = send ? 127 : 0;
            patch.delay.time = 45; // 559.50548 samples: almost half a sample.
            engine.setPatch (patch);
            engine.reset();
            engine.noteOn (60, 110);
            Audio input (44100), output (44100);
            for (std::size_t i = 0; i < input.left.size(); ++i)
                input.left[i] = input.right[i] = static_cast<float> (
                    0.001 * std::sin (2.0 * pi * hz * double (i) / 44100.0));
            for (std::size_t i = 0; i < input.left.size(); i += 256)
                engine.process (output.left.data() + i, output.right.data() + i,
                    static_cast<int> (std::min (std::size_t (256), input.left.size() - i)),
                    input.left.data() + i, input.right.data() + i);
            return output;
        };
        const auto withSend = take (true), dry = take (false);
        std::complex<double> wetBin {}, dryBin {};
        // A quiet external sine makes the existing nonlinear stages nearly
        // linear. Dividing wet by dry cancels the oscillator/input/output
        // response, so this checks the real delay path, not just its helper.
        for (std::size_t i = 22050; i < dry.left.size(); ++i)
        {
            const auto phase = std::polar (1.0, -2.0 * pi * hz * double (i) / 44100.0);
            wetBin += (double (withSend.left[i]) - dry.left[i]) * phase;
            dryBin += double (dry.left[i]) * phase;
        }
        const double delay = septum::mapping::delaySeconds (45) * 44100.0;
        const double expected = std::abs (
            response (std::ceil (delay) - delay, 2.0 * pi * hz / 44100.0));
        const double measured = std::abs (wetBin / dryBin);
        expect (std::abs (dryBin) > 0.01 && std::abs (measured - expected) < 0.0002,
                "engine wet/dry transfer follows the four-point delay response at "
                    + std::to_string (hz) + " Hz (gain " + std::to_string (measured) + ")");
    }
}

void bypassContinuityTests()
{
    for (bool reverb : { false, true })
    {
        auto patch = effectPatch (reverb);
        const auto take = [&] (bool wet, std::size_t switchAt)
        {
            septum::Engine engine;
            engine.prepare (44100.0, 256);
            auto current = patch;
            if (! wet)
                current.upper.delayDepth = current.upper.reverbDepth = 0;
            engine.setPatch (current);
            engine.reset();
            engine.noteOn (36, 110);
            Audio output (44100);
            for (std::size_t position = 0; position < output.left.size();)
            {
                if (position == switchAt)
                {
                    current.delayOn = current.reverbOn = false;
                    engine.setPatch (current);
                }
                const auto next = position < switchAt ? switchAt : output.left.size();
                const auto count = std::min ({ std::size_t (256), next - position,
                                               output.left.size() - position });
                engine.process (output.left.data() + position, output.right.data() + position,
                                static_cast<int> (count));
                position += count;
            }
            return output;
        };
        const auto dry = take (false, 44100), always = take (true, 44100);
        std::vector<double> wet (44100);
        for (std::size_t i = 0; i < wet.size(); ++i)
            wet[i] = double (always.left[i]) - dry.left[i];
        // Switch near the strongest wet sample, rather than accidentally
        // testing a zero crossing where even a hard cut sounds continuous.
        std::size_t audiblePeak = 22050;
        for (std::size_t i = 20000; i < 24000; ++i)
            if (std::abs (wet[i]) > std::abs (wet[audiblePeak]))
                audiblePeak = i;
        const auto switchAt = audiblePeak - septum::AnalogOutput::latencySamples;
        const auto switched = take (true, switchAt);
        double steadyJump = 0.0, switchJump = 0.0;
        for (std::size_t i = 19000; i < 25000; ++i)
            steadyJump = std::max (steadyJump, std::abs (wet[i] - wet[i - 1]));
        const auto end = switchAt + static_cast<std::size_t> (
            44100.0 * septum::mapping::effectsSwitchFadeSeconds)
            + 2 * septum::AnalogOutput::latencySamples;
        for (std::size_t i = switchAt + 1; i < end; ++i)
        {
            const double now = double (switched.left[i]) - dry.left[i];
            const double before = double (switched.left[i - 1]) - dry.left[i - 1];
            switchJump = std::max (switchJump, std::abs (now - before));
        }
        expect (std::abs (wet[audiblePeak]) > 0.001, "bypass continuity test has audible wet audio");
        expect (switchJump < 4.0 * steadyJump + 1.0e-7,
                std::string (reverb ? "reverb" : "delay")
                    + " OFF fades instead of stepping (jump ratio "
                    + std::to_string (switchJump / steadyJump) + ")");
        std::printf ("%s bypass: transition/steady jump %.3fx\n",
                     reverb ? "Reverb" : "Delay", switchJump / steadyJump);
    }
}

void enabledInputContinuityTests()
{
    for (bool reverb : { false, true })
    {
        auto patch = effectPatch (reverb);
        patch.upper.delayDepth = reverb ? 0 : 127;
        patch.upper.reverbDepth = reverb ? 127 : 0;
        const auto take = [&] (std::size_t onAt, bool send)
        {
            septum::Engine engine;
            engine.prepare (44100.0, 256);
            auto current = patch;
            current.delayOn = current.reverbOn = false;
            if (! send)
                current.upper.delayDepth = current.upper.reverbDepth = 0;
            engine.setPatch (current);
            engine.reset();
            engine.noteOn (36, 110);
            Audio output (44100);
            for (std::size_t position = 0; position < output.left.size();)
            {
                if (position == onAt)
                {
                    current.delayOn = ! reverb;
                    current.reverbOn = reverb;
                    engine.setPatch (current);
                }
                const auto next = position < onAt ? onAt : output.left.size();
                const auto count = std::min ({ std::size_t (256), next - position,
                                               output.left.size() - position });
                engine.process (output.left.data() + position, output.right.data() + position,
                                static_cast<int> (count));
                position += count;
            }
            return output;
        };
        const auto dry = take (44100, false);
        std::size_t peak = 11025;
        for (std::size_t i = 11000; i < 12000; ++i)
            if (std::abs (dry.left[i]) > std::abs (dry.left[peak]))
                peak = i;
        const auto onAt = peak - septum::AnalogOutput::latencySamples;
        const auto enabled = take (onAt, true);
        double onsetJump = 0.0, steadyJump = 0.0, wetPeak = 0.0;
        // Examine the first echoes, not only the moment of the switch: a
        // smooth return with an abrupt new send hides its click until later.
        for (std::size_t i = onAt + 1; i < enabled.left.size(); ++i)
        {
            const double wet = double (enabled.left[i]) - dry.left[i];
            const double previous = double (enabled.left[i - 1]) - dry.left[i - 1];
            wetPeak = std::max (wetPeak, std::abs (wet));
            auto& jump = i < 33075 ? onsetJump : steadyJump;
            jump = std::max (jump, std::abs (wet - previous));
        }
        expect (wetPeak > 0.001, "dynamic ON test has audible delayed audio");
        expect (onsetJump < 4.0 * steadyJump + 1.0e-7,
                std::string (reverb ? "reverb" : "delay")
                    + " enabling the send avoids a click in the first echoes (jump ratio "
                    + std::to_string (onsetJump / steadyJump) + ")");
        std::printf ("%s ON first echoes: onset/steady jump %.3fx\n",
                     reverb ? "Reverb" : "Delay", onsetJump / steadyJump);
    }
}

void causalAndPanicTests()
{
    for (double rate : { 32000.0, 44100.0, 48000.0, 96000.0, 192000.0 })
    {
        const auto impulse = [rate] (bool send)
        {
            septum::Engine engine;
            engine.prepare (rate, 256);
            auto patch = effectPatch (false);
            patch.upper.osc1.wave = septum::Waveform::ExtIn;
            patch.upper.delayDepth = send ? 127 : 0;
            patch.delay.time = 0;
            patch.delay.modulationRate = patch.delay.modulationDepth = 127;
            engine.setPatch (patch);
            engine.reset();
            engine.noteOn (60, 110);
            const auto at = static_cast<std::size_t> (rate * 0.11);
            Audio input (at + 4096), output (at + 4096);
            input.left[at] = input.right[at] = 0.2f;
            for (std::size_t i = 0; i < input.left.size(); i += 256)
                engine.process (output.left.data() + i, output.right.data() + i,
                    static_cast<int> (std::min (std::size_t (256), input.left.size() - i)),
                    input.left.data() + i, input.right.data() + i);
            return std::pair { output, engine.latencySamples() - septum::AnalogOutput::latencySamples };
        };
        const auto withSend = impulse (true), dry = impulse (false);
        const auto earliest = static_cast<std::size_t> (rate * 0.11) + withSend.second + 2;
        double early = 0.0, wet = 0.0;
        for (std::size_t i = 0; i < withSend.first.left.size(); ++i)
        {
            const double difference = std::abs (double (withSend.first.left[i]) - dry.first.left[i]);
            if (i < earliest)
                early = std::max (early, difference);
            else
                wet = std::max (wet, difference);
        }
        expect (early == 0.0 && wet > 0.001,
                "shortest modulated delay remains causal and returns the impulse");

        septum::Engine engine;
        engine.prepare (rate, 256);
        auto patch = effectPatch (false);
        patch.delay.feedback = 98;
        patch.delay.time = 48;
        patch.delay.modulationRate = patch.delay.modulationDepth = 127;
        patch.reverbOn = true;
        patch.upper.reverbDepth = 100;
        patch.reverb.time = 127;
        engine.setPatch (patch);
        engine.reset();
        engine.noteOn (100, 110);
        const auto active = render (engine, static_cast<std::size_t> (rate * 0.25));
        engine.noteOff (100);
        const auto tail = render (engine, static_cast<std::size_t> (rate));
        expect (active.finite() && tail.finite() && active.peak() <= 1.05 && tail.peak() <= 1.05,
                "max feedback/modulation and long reverb remain finite and bounded");
        engine.allSoundOff();
        const auto panic = render (engine, static_cast<std::size_t> (rate * 1.5));
        expect (panic.peak() < 1.0e-9,
                "panic prevents all cubic taps and reverb buffers from reading stale audio");
        engine.noteOn (60, 110);
        expect (render (engine, 4096).peak() > 0.001,
                "post-panic notes still render through the running effects");
    }
}

void rapidBypassCycleTest()
{
    constexpr int offAt = 13231, onAt = offAt + 882, frames = 66150;
    const auto take = [] (bool wet, bool toggle)
    {
        septum::Engine engine;
        engine.prepare (44100.0, 256);
        auto patch = effectPatch (false);
        patch.delay.time = 115; // A 660 ms echo arrives after the return reopens.
        patch.upper.delayDepth = wet ? 127 : 0;
        engine.setPatch (patch);
        engine.reset();
        engine.noteOn (36, 110);
        Audio output (frames);
        for (int position = 0; position < frames;)
        {
            if (toggle && (position == offAt || position == onAt))
            {
                patch.delayOn = position == onAt;
                engine.setPatch (patch);
            }
            const int boundary = position < offAt ? offAt : position < onAt ? onAt : frames;
            const int count = std::min (256, boundary - position);
            engine.process (output.left.data() + position, output.right.data() + position, count);
            position += count;
        }
        return output;
    };
    const auto dry = take (false, false), steady = take (true, false), cycled = take (true, true);
    const int expected = offAt + static_cast<int> (septum::mapping::delaySeconds (115) * 44100.0)
                         + septum::AnalogOutput::latencySamples;
    double steadyJump = 0.0, cycleJump = 0.0, wetPeak = 0.0;
    for (int i = expected - 256; i < expected + 256; ++i)
    {
        const double normal = double (steady.left[i]) - dry.left[i];
        const double normalPrevious = double (steady.left[i - 1]) - dry.left[i - 1];
        const double cycle = double (cycled.left[i]) - dry.left[i];
        const double cyclePrevious = double (cycled.left[i - 1]) - dry.left[i - 1];
        wetPeak = std::max (wetPeak, std::abs (normal));
        steadyJump = std::max (steadyJump, std::abs (normal - normalPrevious));
        cycleJump = std::max (cycleJump, std::abs (cycle - cyclePrevious));
    }
    expect (wetPeak > 0.001 && cycleJump < 4.0 * steadyJump + 1.0e-7,
            "rapid OFF->ON does not replay an abrupt send cutoff in a later echo");
    std::printf ("Delay OFF20ms->ON: later echo/steady jump %.3fx\n", cycleJump / steadyJump);
}

void feedbackDecayTests()
{
    // Bounded output alone can hide a runaway feedback loop behind the
    // output limiter. Both feedback polarities must actually lose energy
    // after excitation ends, including with HF damping set to BYPASS.
    for (double rate : { 44100.0, 96000.0 })
    {
        for (int feedback : { -98, 98 })
        {
            septum::Engine engine;
            engine.prepare (rate, 256);
            auto patch = effectPatch (false);
            patch.upper.level = 20;
            patch.delay.time = 40;
            patch.delay.feedback = feedback;
            engine.setPatch (patch);
            engine.reset();
            engine.noteOn (60, 110);
            (void) render (engine, static_cast<std::size_t> (rate * 0.1));
            engine.noteOff (60);
            const auto tail = render (engine, static_cast<std::size_t> (rate * 3.0));
            const double early = tail.rms (static_cast<std::size_t> (rate * 0.05),
                                           static_cast<std::size_t> (rate * 0.25));
            const double late = tail.rms (static_cast<std::size_t> (rate * 2.5));
            expect (early > 1.0e-5 && late < early * 0.01 && tail.finite(),
                    "maximum positive and negative feedback decay after excitation ends");
        }
    }
}

void idleBenchmark()
{
    septum::Engine engine;
    engine.prepare (44100.0, 256);
    std::array<float, 256> left {}, right {};
    const auto start = std::chrono::steady_clock::now();
    for (int i = 0; i < 44100; i += 256)
        engine.process (left.data(), right.data(), std::min (256, 44100 - i));
    std::printf ("Both effects OFF, no voices: %.4fx realtime CPU\n",
                 std::chrono::duration<double> (std::chrono::steady_clock::now() - start).count());
}
} // namespace

int main()
{
    interpolationTests();
    engineInterpolationResponseTests();
    bypassLifecycleTests();
    bypassContinuityTests();
    enabledInputContinuityTests();
    causalAndPanicTests();
    rapidBypassCycleTest();
    feedbackDecayTests();
    idleBenchmark();
    std::printf ("Effects quality: %d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
