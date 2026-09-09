// These are isolated audio-rate controller tests, not a claim that every
// control-rate modulation in the synthesizer is host-block invariant. The
// oscillator, envelopes, filter switches and LFO depths are settled before
// changing only the gain or pan under test.
#include "DSP/SeptumEngine.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <string>
#include <utility>
#include <vector>

namespace
{
constexpr double pi = 3.14159265358979323846;
int checks = 0, failures = 0;

void expect (bool passed, const std::string& message)
{
    ++checks;
    if (! passed)
    {
        ++failures;
        std::fprintf (stderr, "FAIL: %s\n", message.c_str());
    }
}

struct Audio
{
    std::vector<float> left, right;
    explicit Audio (int size) : left (static_cast<std::size_t> (size)), right (left.size()) {}
};

double difference (const Audio& a, const Audio& b, int channel = -1, int start = 0)
{
    double result = 0.0;
    for (std::size_t i = static_cast<std::size_t> (start); i < a.left.size(); ++i)
    {
        if (! std::isfinite (a.left[i]) || ! std::isfinite (a.right[i])
            || ! std::isfinite (b.left[i]) || ! std::isfinite (b.right[i]))
            return INFINITY;
        if (channel != 1)
            result = std::max (result, std::abs (static_cast<double> (a.left[i]) - b.left[i]));
        if (channel != 0)
            result = std::max (result, std::abs (static_cast<double> (a.right[i]) - b.right[i]));
    }
    return result;
}

double rms (const std::vector<float>& audio, int from)
{
    double energy = 0.0;
    for (std::size_t i = static_cast<std::size_t> (from); i < audio.size(); ++i)
        energy += audio[i] * static_cast<double> (audio[i]);
    return std::sqrt (energy / static_cast<double> (audio.size() - static_cast<std::size_t> (from)));
}

enum class Control { Master, PatchLevel, PartLevel, Upper, Lower, Both, Input, Monitor, Pan, None };

const char* name (Control control)
{
    switch (control)
    {
        case Control::Master: return "master";
        case Control::PatchLevel: return "patch level";
        case Control::PartLevel: return "CC7 part level";
        case Control::Upper: return "expression upper";
        case Control::Lower: return "expression lower";
        case Control::Both: return "expression both";
        case Control::Input: return "input volume";
        case Control::Monitor: return "monitor master";
        case Control::Pan: return "CC10 pan";
        case Control::None: return "steady reference";
    }
    return "unknown";
}

bool externalOnly (Control control)
{
    return control == Control::Input || control == Control::Monitor;
}

septum::Patch sinePatch (bool dual)
{
    septum::Patch patch;
    patch.patchLevel = 127;
    patch.keyboardMode = dual ? septum::KeyboardMode::Dual : septum::KeyboardMode::Single;
    for (auto* tone : { &patch.upper, &patch.lower })
    {
        tone->osc1.wave = septum::Waveform::Sine;
        tone->balance = -63;
        tone->filterType = septum::FilterType::Bypass;
        tone->level = 100; // Keep the output limiter below its knee.
        tone->ampEnvAttack = 0;
        tone->ampEnvSustain = 127;
        tone->lfo1.depth1 = tone->lfo1.depth2 = 0;
        tone->lfo2.depth1 = tone->lfo2.depth2 = 0;
        tone->delayDepth = tone->reverbDepth = 0;
    }
    if (dual)
    {
        patch.upper.pan = -64;
        patch.lower.pan = 63;
        patch.lower.octaveShift = -1;
    }
    return patch;
}

void apply (septum::Engine& engine, Control control, double value)
{
    switch (control)
    {
        case Control::Master:
        case Control::Monitor:
            engine.setMasterLevel (static_cast<int> (std::lround (127.0 * value)));
            break;
        case Control::PatchLevel:
        {
            auto patch = engine.currentPatch();
            patch.patchLevel = static_cast<int> (std::lround (127.0 * value));
            engine.setPatch (patch);
            break;
        }
        case Control::PartLevel: engine.setPartLevel (value); break;
        case Control::Upper:
        case Control::Lower:
        case Control::Both: engine.setExpression (value); break;
        case Control::Input:
        {
            auto input = engine.externalInput();
            input.inputVolume = static_cast<int> (std::lround (127.0 * value));
            engine.setExternalInput (input);
            break;
        }
        case Control::Pan: engine.setPartPan (2.0 * value - 1.0); break;
        case Control::None: break;
    }
}

struct Event { int frame; double value; };

std::vector<Event> moves (double rate)
{
    return { { 0, 0.0 }, { static_cast<int> (std::lround (rate * 0.0173)), 0.73 },
             { static_cast<int> (std::lround (rate * 0.0567)), 0.13 },
             { static_cast<int> (std::lround (rate * 0.0991)), 1.0 } };
}

Audio inputSignal (int size, double rate, int offset = 0)
{
    Audio input (size);
    for (int i = 0; i < size; ++i)
    {
        input.left[static_cast<std::size_t> (i)] =
            static_cast<float> (0.04 * std::sin (2.0 * pi * 211.0 * (i + offset) / rate));
        input.right[static_cast<std::size_t> (i)] =
            static_cast<float> (0.03 * std::sin (2.0 * pi * 337.0 * (i + offset) / rate));
    }
    return input;
}

Audio render (double rate, int chunk, Control control, const std::vector<Event>& events,
              double duration = 0.16, bool dual = true, int note = 69,
              double initialPan = 0.0, bool monitor = false)
{
    septum::Engine engine;
    engine.prepare (rate, 256);
    auto patch = sinePatch (dual);
    patch.expressionDestination = control == Control::Upper ? septum::ToneDestination::Upper
                                : control == Control::Lower ? septum::ToneDestination::Lower
                                                            : septum::ToneDestination::Both;
    engine.setPatch (patch);
    septum::ExternalInput input;
    input.inputVolume = 127;
    engine.setExternalInput (input);
    engine.setMasterLevel (127);
    engine.setPartPan (initialPan);
    engine.reset();
    const bool useInput = externalOnly (control) || monitor;
    if (! useInput)
        engine.noteOn (note, 100);

    const int warm = static_cast<int> (std::lround (rate * 0.3));
    Audio discard (warm);
    const auto warmInput = inputSignal (warm, rate);
    for (int position = 0; position < warm;)
    {
        const int count = std::min (256, warm - position);
        engine.process (discard.left.data() + position, discard.right.data() + position, count,
                        useInput ? warmInput.left.data() + position : nullptr,
                        useInput ? warmInput.right.data() + position : nullptr);
        position += count;
    }

    const int size = static_cast<int> (std::lround (rate * duration));
    Audio output (size);
    const auto signal = inputSignal (size, rate, warm);
    std::size_t nextEvent = 0;
    for (int position = 0; position < size;)
    {
        while (nextEvent < events.size() && events[nextEvent].frame == position)
            apply (engine, control, events[nextEvent++].value);
        const int boundary = nextEvent < events.size() ? events[nextEvent].frame : size;
        const int count = std::min ({ chunk, size - position, boundary - position });
        engine.process (output.left.data() + position, output.right.data() + position, count,
                        useInput ? signal.left.data() + position : nullptr,
                        useInput ? signal.right.data() + position : nullptr);
        position += count;
    }
    return output;
}

void testPartitions()
{
    for (double rate : { 44100.0, 48000.0, 96000.0, 192000.0 })
        for (Control control : { Control::Master, Control::PatchLevel, Control::PartLevel,
                                  Control::Upper, Control::Lower, Control::Both,
                                  Control::Input, Control::Monitor, Control::Pan })
        {
            const auto events = moves (rate);
            const auto reference = render (rate, 1, control, events);
            double worst = 0.0;
            for (int chunk : { 3, 7, 8, 31 })
            {
                const auto actual = render (rate, chunk, control, events);
                const double error = difference (reference, actual);
                worst = std::max (worst, error);
                expect (error < 2.0e-7, std::string (name (control)) + " partition "
                        + std::to_string (chunk) + " at " + std::to_string (rate)
                        + " Hz; peak error " + std::to_string (error));
            }
            std::printf ("partition %.0f Hz %-18s max error %.9g\n", rate, name (control), worst);
        }
}

// A separate closed-form exponential, evaluated from each event's initial
// value, checks the existing time constant rather than merely checking two
// render partitions against each other. Input gain precedes the monitor's
// voice-alignment delay; master gain follows it. Both precede AnalogOutput.
void testExternalReference()
{
    for (double rate : { 44100.0, 48000.0, 96000.0, 192000.0 })
        for (Control control : { Control::Input, Control::Monitor })
        {
            const auto events = moves (rate);
            const auto actual = render (rate, 31, control, events);
            const int warm = static_cast<int> (std::lround (rate * 0.3));
            const int total = warm + static_cast<int> (actual.left.size());
            const auto signal = inputSignal (total, rate);
            septum::Engine latency;
            latency.prepare (rate, 256);
            const int transport = latency.latencySamples() - septum::AnalogOutput::latencySamples;
            std::array<septum::AnalogOutput, 2> output;
            for (auto& stage : output)
                stage.prepare (rate);
            Audio delayed (total), expected (static_cast<int> (actual.left.size()));
            double from = 1.0, target = 1.0, gain = 1.0;
            int start = 0;
            std::size_t nextEvent = 0;
            for (int i = 0; i < total; ++i)
            {
                if (nextEvent < events.size() && i == warm + events[nextEvent].frame)
                {
                    from = gain;
                    start = i;
                    const int raw = static_cast<int> (std::lround (127.0 * events[nextEvent++].value));
                    target = control == Control::Input ? septum::mapping::externalInputGain (raw)
                                                       : raw / 127.0;
                }
                gain = target + (from - target)
                     * std::exp (-(i - start + 1.0) / (rate * septum::mapping::masterSlewSeconds));
                const auto frame = static_cast<std::size_t> (i);
                delayed.left[frame] = static_cast<float> (signal.left[frame] * (control == Control::Input ? gain : 1.0));
                delayed.right[frame] = static_cast<float> (signal.right[frame] * (control == Control::Input ? gain : 1.0));
                for (int channel = 0; channel < 2; ++channel)
                {
                    const auto& samples = channel == 0 ? delayed.left : delayed.right;
                    const double x = i >= transport ? samples[static_cast<std::size_t> (i - transport)] : 0.0;
                    const auto y = static_cast<float> (output[static_cast<std::size_t> (channel)].processSample (
                        x * (control == Control::Monitor ? gain : 1.0)));
                    if (i >= warm)
                        (channel == 0 ? expected.left : expected.right)[static_cast<std::size_t> (i - warm)] = y;
                }
            }
            const double error = difference (actual, expected);
            expect (error < 2.0e-7, std::string (name (control)) + " matches exponential/time-order reference at "
                    + std::to_string (rate) + " Hz; peak error " + std::to_string (error));
            std::printf ("reference %.0f Hz %-18s max error %.9g\n", rate, name (control), error);
        }
}

void testExpressionRoutes()
{
    const double rate = 48000.0;
    const auto reference = render (rate, 31, Control::None, {}, 0.3);
    const int tail = static_cast<int> (rate * 0.2);
    for (Control control : { Control::Upper, Control::Lower, Control::Both })
    {
        const auto muted = render (rate, 31, control, { { 0, 0.0 } }, 0.3);
        for (int channel = 0; channel < 2; ++channel)
        {
            const bool affected = control == Control::Both
                               || (channel == 0 ? control == Control::Upper : control == Control::Lower);
            const auto& samples = channel == 0 ? muted.left : muted.right;
            const auto& original = channel == 0 ? reference.left : reference.right;
            if (affected)
                expect (rms (samples, tail) < 0.005 * rms (original, tail),
                        std::string (name (control)) + " mutes the named tone");
            else
                expect (difference (reference, muted, channel) < 2.0e-7,
                        std::string (name (control)) + " preserves the unnamed tone throughout the move");
        }
    }
}

void testPan()
{
    for (double rate : { 44100.0, 48000.0, 96000.0, 192000.0 })
    {
        // A low, settled sine keeps ordinary carrier travel smaller than a
        // hard pan switch. Subtract the otherwise identical unautomated take
        // before differentiating, so note onset and output-filter latency are
        // not mistaken for an automation click.
        const auto reference = render (rate, 31, Control::None, {}, 0.08, false, 24);
        for (double destination : { -1.0, 1.0 })
        {
            const auto moved = render (rate, 31, Control::Pan,
                                        { { 0, (destination + 1.0) * 0.5 } }, 0.08, false, 24);
            double carrierStep = 0.0, residualStep = 0.0;
            for (std::size_t i = 1; i < reference.left.size(); ++i)
            {
                carrierStep = std::max (carrierStep, std::abs (static_cast<double> (reference.left[i]) - reference.left[i - 1]));
                for (const auto pair : { std::pair { &moved.left, &reference.left },
                                         std::pair { &moved.right, &reference.right } })
                {
                    const double previous = static_cast<double> ((*pair.first)[i - 1]) - (*pair.second)[i - 1];
                    const double current = static_cast<double> ((*pair.first)[i]) - (*pair.second)[i];
                    residualStep = std::max (residualStep, std::abs (current - previous));
                }
            }
            expect (carrierStep > 1.0e-6 && residualStep < 4.0 * carrierStep,
                    "pan switch residual is bounded by four steady-carrier sample steps at "
                    + std::to_string (rate) + " Hz, ratio " + std::to_string (residualStep / carrierStep));
            std::printf ("pan %.0f Hz to %+.0f residual/carrier step %.9g\n", rate, destination, residualStep / carrierStep);
        }

        const auto center = render (rate, 31, Control::None, {}, 0.4, false);
        const double centerLevel = rms (center.left, 0);
        expect (std::isfinite (centerLevel) && centerLevel > 0.001,
                "pan reference is finite and audible");
        expect (std::abs (rms (center.right, 0) / centerLevel - 1.0) < 1.0e-6,
                "pan center preserves equal left/right gains");
        const int tail = static_cast<int> (rate * 0.32);
        for (double destination : { -1.0, 1.0 })
        {
            const auto endpoint = render (rate, 31, Control::None, {}, 0.4, false, 69, destination);
            const auto& open = destination < 0.0 ? endpoint.left : endpoint.right;
            const auto& closed = destination < 0.0 ? endpoint.right : endpoint.left;
            expect (std::abs (rms (open, 0) / centerLevel - std::sqrt (2.0)) < 2.0e-5
                        && rms (closed, 0) < 1.0e-7,
                    "pan endpoint preserves constant power and silence on the opposite side");

            const auto moved = render (rate, 31, Control::Pan,
                { { 0, (destination + 1.0) * 0.5 } }, 0.4, false);
            const auto& movedOpen = destination < 0.0 ? moved.left : moved.right;
            const auto& movedClosed = destination < 0.0 ? moved.right : moved.left;
            // The analog coupling capacitor retains a small DC transient
            // from moving a gain on a nonzero sample. Measure settled RMS,
            // allowing 0.5% for that transient rather than requiring a null
            // against a differently excited analog state.
            expect (std::abs (rms (movedOpen, tail) / rms (open, tail) - 1.0) < 0.005
                        && rms (movedClosed, tail) < 0.005 * centerLevel,
                    "pan automation actually reaches its requested endpoint");
        }
        const auto recentered = render (rate, 31, Control::Pan,
            { { 0, 0.0 }, { static_cast<int> (std::lround (rate * 0.08)), 1.0 },
              { static_cast<int> (std::lround (rate * 0.16)), 0.5 } }, 0.4, false);
        expect (std::abs (rms (recentered.left, tail) / rms (center.left, tail) - 1.0) < 0.005
                    && std::abs (rms (recentered.right, tail) / rms (center.right, tail) - 1.0) < 0.005,
                "pan automation returns to the original unity center after crossing both sides");
        const auto monitor = render (rate, 31, Control::None, {}, 0.16, true, 69, 0.0, true);
        const auto pannedMonitor = render (rate, 31, Control::Pan, moves (rate), 0.16, true, 69, 0.0, true);
        expect (difference (monitor, pannedMonitor) < 2.0e-7,
                "CC10 leaves the direct input monitor unchanged");
    }
}
} // namespace

int main()
{
    testPartitions();
    testExternalReference();
    testExpressionRoutes();
    testPan();
    std::printf ("Control smoothing: %d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
