// The fixed-rate boundary is an experiment, not the plug-in's default.
// These tests check its clock, converter and host invariance. They cannot
// establish fidelity to an SH-201 without a measured hardware reference.
#include "DSP/ReferenceRateEngine.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <new>
#include <string>
#include <vector>

namespace allocationAudit
{
bool active = false;
std::size_t count = 0;
}

// The audio path currently owns vectors with ordinary alignment. Instrument
// C++ allocations in this standalone executable so future buffer growth in
// process is caught without introducing hooks into the engine.
void* operator new (std::size_t size)
{
    if (allocationAudit::active)
        ++allocationAudit::count;
    if (void* memory = std::malloc (std::max (std::size_t (1), size)))
        return memory;
    throw std::bad_alloc {};
}
void* operator new[] (std::size_t size) { return ::operator new (size); }
void operator delete (void* memory) noexcept { std::free (memory); }
void operator delete[] (void* memory) noexcept { std::free (memory); }
void operator delete (void* memory, std::size_t) noexcept { std::free (memory); }
void operator delete[] (void* memory, std::size_t) noexcept { std::free (memory); }

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

void near (double value, double target, double tolerance,
           const std::string& message)
{
    expect (std::abs (value - target) <= tolerance,
            message + ": " + std::to_string (value) + " vs "
                + std::to_string (target));
}

struct Audio
{
    explicit Audio (std::size_t length) : left (length), right (length) {}
    std::vector<float> left, right;

    bool finite() const
    {
        for (std::size_t i = 0; i < left.size(); ++i)
            if (! std::isfinite (left[i]) || ! std::isfinite (right[i]))
                return false;
        return true;
    }

    double peak() const
    {
        double result = 0.0;
        for (std::size_t i = 0; i < left.size(); ++i)
            result = std::max ({ result, std::abs (double (left[i])),
                                std::abs (double (right[i])) });
        return result;
    }
};

septum::Patch dryPatch (septum::Waveform wave = septum::Waveform::Sine)
{
    septum::Patch patch;
    patch.upper.osc1.wave = wave;
    patch.upper.balance = -63;
    patch.upper.filterType = septum::FilterType::Bypass;
    patch.upper.level = 80;
    patch.patchLevel = 100;
    return patch;
}

double amplitude (const std::vector<float>& samples, double rate, double hz,
                  double startSeconds = 0.2)
{
    const std::size_t start = static_cast<std::size_t> (startSeconds * rate);
    if (start >= samples.size() - 1)
        return 0.0;
    const auto count = samples.size() - start;
    double real = 0.0, imag = 0.0, windowSum = 0.0;
    for (std::size_t i = 0; i < count; ++i)
    {
        const double window = 0.5 - 0.5 * std::cos (2.0 * pi * i / (count - 1));
        const double angle = 2.0 * pi * hz * i / rate;
        real += samples[start + i] * window * std::cos (angle);
        imag -= samples[start + i] * window * std::sin (angle);
        windowSum += window;
    }
    return 2.0 * std::hypot (real, imag) / windowSum;
}

double db (double value)
{
    return 20.0 * std::log10 (std::max (1.0e-15, value));
}

Audio convertTone (double sourceRate, double outputRate, double hz)
{
    septum::detail::ReferenceRateConverter converter;
    converter.prepare (sourceRate, outputRate);
    Audio output (static_cast<std::size_t> (0.5 * outputRate));
    std::size_t source = 0;
    for (std::size_t i = 0; i < output.left.size(); ++i)
    {
        const double time = i * sourceRate / outputRate;
        while (source <= static_cast<std::size_t> (std::floor (time)))
        {
            const float sample = static_cast<float> (
                std::sin (2.0 * pi * hz * source / sourceRate));
            converter.push (sample, -sample);
            ++source;
        }
        const auto sample = converter.read (time - converter.groupDelay());
        output.left[i] = sample[0];
        output.right[i] = sample[1];
    }
    return output;
}

void converterTests()
{
    septum::detail::ReferenceRateConverter converter;
    converter.prepare (44100.0, 44100.0);
    expect (converter.groupDelay() == 64, "unity converter group delay is 64 frames");
    expect (converter.taps() == 129, "unity converter has odd symmetric support");
    std::array<float, 256> impulse {};
    for (std::size_t i = 0; i < impulse.size(); ++i)
    {
        converter.push (i == 0 ? 1.0f : 0.0f, 0.0f);
        const auto out = converter.read (double (i) - converter.groupDelay());
        impulse[i] = out[0];
        expect (out[1] == 0.0f, "converter stereo history does not leak");
    }
    const auto peak = std::max_element (impulse.begin(), impulse.end());
    expect (peak - impulse.begin() == converter.groupDelay(),
            "unity impulse peak equals converter delay");
    for (int offset = 1; offset <= 64; ++offset)
        near (impulse[static_cast<std::size_t> (64 - offset)],
              impulse[static_cast<std::size_t> (64 + offset)], 1.0e-7,
              "unity impulse is symmetric about reported delay");

    for (double sourceRate : { 32000.0, 44100.0, 48000.0, 88200.0,
                               96000.0, 192000.0 })
    {
        converter.prepare (sourceRate, 44100.0);
        for (int i = 0; i < converter.taps() + 10; ++i)
            converter.push (1.0f, -0.25f);
        // Exercise fractional table interpolation, not only phase zero.
        for (double fraction : { 0.0, 0.001, 0.249, 0.5, 0.999 })
        {
            const auto out = converter.read (converter.taps() + 8.0
                                              - converter.groupDelay() + fraction);
            near (out[0], 1.0, 2.0e-6, "every input phase preserves DC");
            near (out[1], -0.25, 2.0e-6, "both channels preserve their own DC");
        }
    }

    const auto pass = convertTone (192000.0, 44100.0, 1000.0);
    const auto stop = convertTone (192000.0, 44100.0, 30000.0);
    const auto up = convertTone (44100.0, 192000.0, 1000.0);
    const double downAlias = db (amplitude (stop.left, 44100.0, 14100.0));
    const double image = db (amplitude (up.left, 192000.0, 43100.0));
    near (amplitude (pass.left, 44100.0, 1000.0), 1.0, 0.0005,
          "192k input converter preserves a passband tone");
    expect (downAlias < -75.0, "192k input converter rejects 30k alias");
    expect (image < -75.0, "192k output converter rejects first spectral image");
    near (amplitude (up.left, 192000.0, 1000.0), 1.0, 0.0005,
          "output converter preserves a passband tone");
    std::printf ("Converter: 30 kHz input alias %.2f dBFS; first output image %.2f dBFS\n",
                 downAlias, image);

    // Rational conversion: an impulse at source frame 97 must peak around
    // (97 + source-domain FIR delay) * output/source, with no hidden block delay.
    for (const auto rates : { std::array<double, 2> { 48000.0, 44100.0 },
                             std::array<double, 2> { 44100.0, 96000.0 },
                             std::array<double, 2> { 192000.0, 44100.0 } })
    {
        converter.prepare (rates[0], rates[1]);
        int written = 0, peakFrame = 0;
        float peakValue = 0.0f;
        for (int i = 0; i < 1000; ++i)
        {
            const double time = i * rates[0] / rates[1];
            while (written <= static_cast<int> (std::floor (time)))
            {
                converter.push (written == 97 ? 1.0f : 0.0f, 0.0f);
                ++written;
            }
            const float out = converter.read (time - converter.groupDelay())[0];
            if (std::abs (out) > peakValue)
            {
                peakFrame = i;
                peakValue = std::abs (out);
            }
        }
        near (peakFrame, (97 + converter.groupDelay()) * rates[1] / rates[0],
              0.51, "rational converter impulse peak follows its source-domain delay");
    }
}

Audio renderEvents (double rate, int block)
{
    septum::ReferenceRateEngine engine;
    engine.prepare (rate, block);
    auto patch = dryPatch (septum::Waveform::SuperSaw);
    patch.upper.filterType = septum::FilterType::Lpf;
    patch.upper.cutoff = 80;
    patch.upper.resonance = 65;
    patch.upper.filterEnvDepth = 25;
    patch.upper.filterEnvDecay = 65;
    patch.upper.filterEnvSustain = 30;
    patch.upper.lfo1.depth1 = 13;
    patch.upper.lfo1.keyTrigger = true;
    patch.upper.ampEnvRelease = 55;
    patch.delayOn = true;
    patch.upper.delayDepth = 48;
    engine.setPatch (patch);
    engine.setMasterLevel (110);
    // Offsets deliberately fall inside every tested block size.
    constexpr std::array<int, 10> offsets { 0, 137, 239, 1001, 2049,
                                           3131, 4057, 5119, 6173, 8193 };
    Audio output (12000);
    int position = 0;
    std::size_t event = 0;
    while (position < static_cast<int> (output.left.size()))
    {
        if (event < offsets.size() && position == offsets[event])
        {
            switch (event++)
            {
                case 0: engine.noteOn (60, 100); break;
                case 1: engine.noteOn (67, 93); break;
                case 2: engine.setHold (true); break;
                case 3: engine.setPitchBend (0.37); break;
                case 4: engine.noteOff (60); break;
                case 5: engine.setModulation (0.65); break;
                case 6: engine.setPartEnabled (true, false); break;
                case 7: engine.setPartEnabled (true, true); break;
                case 8: engine.noteOff (67); engine.setHold (false); break;
                case 9: engine.noteOn (48, 112); break;
                default: break;
            }
        }
        const int next = event < offsets.size() ? offsets[event]
                                                : static_cast<int> (output.left.size());
        const int count = std::min ({ block, next - position,
                                      static_cast<int> (output.left.size()) - position });
        engine.process (output.left.data() + position, output.right.data() + position,
                        count);
        position += count;
        const auto expected = static_cast<std::uint64_t> (
            std::floor ((position - 1) * 44100.0L / rate)) + 1;
        expect (engine.renderedInternalSamples() == expected,
                "clock renders only internal frames at or before current host sample");
    }
    return output;
}

void clockAndInputTests()
{
    for (double rate : { 32000.0, 44100.0, 48000.0, 88200.0, 96000.0, 192000.0 })
    {
        const auto reference = renderEvents (rate, 64);
        expect (reference.finite() && reference.peak() > 0.001,
                "event score produces finite nonzero audio");
        for (int block : { 127, 256, 1024 })
        {
            const auto other = renderEvents (rate, block);
            expect (reference.left == other.left && reference.right == other.right,
                    "MIDI offsets and output are bit identical across block partitions at "
                        + std::to_string (rate));
        }

        septum::ReferenceRateEngine engine;
        engine.prepare (rate, 127);
        const int inputDelay = static_cast<int> (std::ceil (
            64.0 / std::min (1.0, 44100.0 / rate)));
        const int outputDelay = static_cast<int> (std::ceil (
            64.0 / std::min (1.0, rate / 44100.0)));
        // Derive the core delay. The prototype must track output-stage changes.
        const double exact = (engine.Engine::latencySamples() + outputDelay)
                               * rate / 44100.0;
        near (engine.sampleRate(), rate, 0.0, "public rate is the host rate");
        near (engine.Engine::sampleRate(), 44100.0, 0.0,
              "synthesis core always runs at 44.1 kHz");
        near (engine.exactLatencySamples(), exact, 1.0e-9,
              "MIDI latency includes dynamic core and output FIR delay");
        expect (engine.latencySamples() == static_cast<int> (std::ceil (exact)),
                "reported MIDI latency conservatively rounds fractional delay");
        expect (engine.inputConversionLatencySamples() == inputDelay,
                "input latency is explicit in host frames");
        expect (engine.externalInputLatencySamples()
                    == static_cast<int> (std::ceil (exact + inputDelay)),
                "external input reports its additional conversion delay");
        std::printf ("%.0f Hz host: core %d internal frames; MIDI latency %d, "
                     "external latency %d host frames\n", rate,
                     engine.Engine::latencySamples(), engine.latencySamples(),
                     engine.externalInputLatencySamples());

        auto patch = dryPatch (septum::Waveform::ExtIn);
        engine.setPatch (patch);
        engine.setMasterLevel (127);
        const auto length = static_cast<std::size_t> (rate * 0.08);
        Audio input (length), output (length);
        for (std::size_t i = 0; i < length; ++i)
        {
            input.left[i] = static_cast<float> (0.15 * std::sin (i * 2.0 * pi * 997.0 / rate));
            input.right[i] = static_cast<float> (0.1 * std::cos (i * 2.0 * pi * 601.0 / rate));
        }
        input.left[0] += 0.2f;
        for (int mode = 0; mode < 2; ++mode)
        {
            engine.reset();
            if (mode == 1)
                engine.noteOn (60, 100);
            for (std::size_t position = 0; position < length; position += 127)
            {
                const auto count = std::min (std::size_t (127), length - position);
                engine.process (output.left.data() + position,
                                output.right.data() + position, static_cast<int> (count),
                                input.left.data() + position, input.right.data() + position);
            }
            expect (output.finite() && output.peak() > 0.005,
                    "external input is finite and audible in monitor/oscillator modes");
        }

        engine.reset();
        engine.process (output.left.data(), output.right.data(), 0);
        expect (engine.renderedInternalSamples() == 0,
                "reset and empty process preserve initial clock");
        engine.process (output.left.data(), output.right.data(), 1);
        expect (engine.renderedInternalSamples() == 1,
                "first host frame renders exactly internal frame zero");
    }
}

void spectralTests()
{
    double referenceAlias = 0.0;
    for (double rate : { 44100.0, 48000.0, 88200.0, 96000.0, 192000.0 })
    {
        septum::ReferenceRateEngine engine;
        engine.prepare (rate, 256);
        engine.setPatch (dryPatch (septum::Waveform::SuperSaw));
        engine.setMasterLevel (127);
        engine.noteOn (93, 110); // A6 = 1760 Hz, naive saw harmonic 16 folds to 15940.
        Audio output (static_cast<std::size_t> (rate * 1.2));
        for (std::size_t i = 0; i < output.left.size(); i += 256)
            engine.process (output.left.data() + i, output.right.data() + i,
                            static_cast<int> (std::min (std::size_t (256),
                                                       output.left.size() - i)));
        const double fundamental = amplitude (output.left, rate, 1760.0);
        const double alias = db (amplitude (output.left, rate, 15940.0) / fundamental);
        const double native48kAlias = db (
            amplitude (output.left, rate, 19840.0) / fundamental);
        if (rate == 44100.0)
            referenceAlias = alias;
        else
            near (alias, referenceAlias, 0.15,
                  "A6 reference alias has the same level at every host rate");
        expect (alias > -60.0 && alias < -10.0,
                "test exercises retained internal-rate aliasing");
        expect (alias > native48kAlias + 8.0,
                "host rate does not relocate A6 alias to 48k-native frequency");
        std::printf ("%.0f Hz host: A6 15940 Hz %.3f dBc; 19840 Hz %.3f dBc\n",
                     rate, alias, native48kAlias);
    }
}

void realtimeAndTimingTests()
{
    septum::ReferenceRateEngine separate, inPlace;
    separate.prepare (48000.0, 64);
    inPlace.prepare (48000.0, 1024);
    const auto patch = dryPatch (septum::Waveform::ExtIn);
    separate.setPatch (patch);
    inPlace.setPatch (patch);
    separate.noteOn (60, 100);
    inPlace.noteOn (60, 100);
    Audio input (2048), expected (2048);
    for (std::size_t i = 0; i < input.left.size(); ++i)
    {
        input.left[i] = static_cast<float> (0.1 * std::sin (i * 0.1));
        input.right[i] = static_cast<float> (0.2 * std::cos (i * 0.037));
    }
    auto actual = input;
    allocationAudit::count = 0;
    allocationAudit::active = true;
    separate.process (expected.left.data(), expected.right.data(), 2048,
                      input.left.data(), input.right.data());
    // Processing larger than prepare's block size is safe: no temporary
    // buffer is sized by the caller's block, and inputs are read first.
    inPlace.process (actual.left.data(), actual.right.data(), 2048,
                     actual.left.data(), actual.right.data());
    allocationAudit::active = false;
    expect (allocationAudit::count == 0, "streaming process performs no C++ allocations");
    expect (expected.left == actual.left && expected.right == actual.right,
            "in-place stereo input matches separate buffers exactly");

    // Public-inherited immediate controls cannot retrospectively timestamp
    // pending core frames at host rates below the reference rate. Record this
    // limitation explicitly: at 32 kHz an event at frame8 reaches core frame10,
    // 1.025 core frames early (23.24 us), still under one host frame.
    septum::ReferenceRateEngine lowRate;
    lowRate.prepare (32000.0, 64);
    std::array<float, 8> left {}, right {};
    lowRate.process (left.data(), right.data(), 8);
    const auto nextCore = lowRate.renderedInternalSamples();
    const double eventInCoreFrames = 8.0 * 44100.0 / 32000.0;
    const double earlySeconds = (eventInCoreFrames - nextCore) / 44100.0;
    lowRate.noteOn (60, 100);
    expect (lowRate.renderedInternalSamples() == nextCore,
            "immediate MIDI does not render future core audio");
    expect (earlySeconds > 1.0 / 44100.0 && earlySeconds < 1.0 / 32000.0,
            "32k immediate MIDI has the documented one-host-frame timing bound");

    septum::ReferenceRateEngine unprepared;
    left.fill (1.0f);
    right.fill (1.0f);
    unprepared.process (left.data(), right.data(), 8);
    expect (std::all_of (left.begin(), left.end(), [] (float v) { return v == 0.0f; })
                && std::all_of (right.begin(), right.end(), [] (float v) { return v == 0.0f; }),
            "unprepared prototype emits silence safely");
    unprepared.prepare (std::numeric_limits<double>::quiet_NaN(), 64);
    near (unprepared.sampleRate(), 44100.0, 0.0, "invalid host rate falls back to reference");
}

template <typename EngineType>
double benchmark (double rate)
{
    EngineType engine;
    engine.prepare (rate, 256);
    auto patch = dryPatch (septum::Waveform::SuperSaw);
    patch.upper.filterType = septum::FilterType::Lpf;
    patch.upper.cutoff = 93;
    patch.upper.resonance = 65;
    patch.upper.osc2.wave = septum::Waveform::SuperSaw;
    patch.upper.balance = 0;
    patch.upper.osc1.pulseWidth = patch.upper.osc2.pulseWidth = 70;
    patch.upper.level = 40;
    patch.delayOn = patch.reverbOn = true;
    patch.upper.delayDepth = patch.upper.reverbDepth = 35;
    engine.setPatch (patch);
    for (int note = 48; note < 58; ++note)
        engine.noteOn (note, 100);
    std::array<float, 256> left {}, right {};
    const int frames = static_cast<int> (rate * 0.5);
    const auto begin = std::chrono::steady_clock::now();
    for (int i = 0; i < frames; i += 256)
        engine.process (left.data(), right.data(), std::min (256, frames - i));
    const auto elapsed = std::chrono::duration<double> (
        std::chrono::steady_clock::now() - begin).count();
    expect (std::isfinite (left.back()), "benchmark output remains finite");
    return elapsed / 0.5;
}
} // namespace

int main()
{
    converterTests();
    clockAndInputTests();
    spectralTests();
    realtimeAndTimingTests();
    for (double rate : { 44100.0, 48000.0, 96000.0 })
    {
        const auto native = benchmark<septum::Engine> (rate);
        const auto reference = benchmark<septum::ReferenceRateEngine> (rate);
        std::printf ("10 voices, 2 supersaws, filter + FX at %.0f Hz: "
                     "native %.3fx realtime CPU, reference %.3fx, slowdown %.2fx\n",
                     rate, native, reference, reference / native);
    }
    std::printf ("%d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
