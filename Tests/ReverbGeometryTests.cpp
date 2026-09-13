// Large delay changes: fixed read-head crossfades, following J. O. Smith's
// Physical Audio Signal Processing. The 10 ms fade is a quality policy,
// not an identified SH-201 firmware constant.
#include "DSP/SeptumEngine.h"
#ifndef SEPTUM_GEOMETRY_BASELINE
#include "DSP/ReverbReadHeads.h"
#endif

#include <algorithm>
#include <array>
#include <bit>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <numeric>
#include <string>
#include <vector>

namespace
{
int checks = 0, failures = 0;
constexpr double pi = 3.14159265358979323846;
void expect (bool condition, const char* message)
{
    ++checks;
    if (! condition)
    {
        ++failures;
        std::fprintf (stderr, "FAIL: %s\n", message);
    }
}

#ifndef SEPTUM_GEOMETRY_BASELINE
template <std::size_t Positions>
void headTests()
{
    for (double rate : { 8000.0, 22050.0, 44100.0, 48000.0, 96000.0, 192000.0 })
    {
        septum::detail::ReverbReadHeads<Positions> heads;
        heads.reset (0);
        const double step = 1.0 / (rate * heads.fadeSeconds);
        auto signal = [] (std::size_t position) { return position % 2 ? 1.0 : -1.0; };
        double previous = heads.read (signal);
        for (int sample = 0; sample < static_cast<int> (rate * 0.2); ++sample)
        {
            // Cycle every sample, deliberately making all published positions
            // active before an earlier transition can finish.
            heads.advance (1 + sample % (Positions - 1), step);
            const double output = heads.read (signal);
            const double total = std::accumulate (heads.weights.begin(), heads.weights.end(), 0.0);
            expect (std::abs (total - 1.0) < 1.0e-11,
                    "rapid retargeting keeps the sum of read gains at unity");
            expect (std::all_of (heads.weights.begin(), heads.weights.end(),
                                [] (double value) { return value >= 0.0 && value <= 1.0; }),
                    "every active read has a nonnegative gain no greater than one");
            expect (std::abs (output - previous) <= 2.0 * step + 1.0e-11,
                    "automation between opposite taps has a bounded per-sample change");
            expect (std::abs (output) <= 1.0 + 1.0e-11,
                    "read crossfade never boosts bounded feedback samples");
            previous = output;
        }
        const int finalPosition = static_cast<int> (Positions) - 1;
        for (int sample = 0; sample <= static_cast<int> (std::ceil (rate * heads.fadeSeconds)); ++sample)
            heads.advance (finalPosition, step);
        expect (! heads.moving && heads.read (signal) == signal (finalPosition),
                "interrupted transition settles exactly within one fade duration");
        int reads = 0;
        (void) heads.read ([&] (std::size_t position) { ++reads; return double (position); });
        expect (reads == 1, "settled geometry reads exactly one tap");

        for (std::size_t position = 0; position < Positions; ++position)
        {
            heads.reset (static_cast<int> (position));
            expect (heads.read (signal) == signal (position),
                    "reset starts at the saved position without an unwanted fade");
        }
    }
}

void worstCaseBenchmark()
{
    septum::detail::ReverbReadHeads<126> predelay;
    septum::detail::ReverbReadHeads<8> size;
    predelay.reset (0);
    size.reset (0);
    std::array<double, 8192> buffer;
    for (std::size_t i = 0; i < buffer.size(); ++i)
        buffer[i] = std::sin (i * 0.023);
    constexpr int frames = 48000 * 4;
    double checksum = 0.0;
    const auto start = std::chrono::steady_clock::now();
    for (int i = 0; i < frames; ++i)
    {
        predelay.advance (i % 126, 1.0 / 480.0);
        size.advance (i % 8, 1.0 / 480.0);
        checksum += predelay.read ([&] (std::size_t position)
            { return buffer[(i + position * 59) % buffer.size()]; });
        for (int line = 0; line < 8; ++line)
            checksum += size.read ([&] (std::size_t position)
                { return buffer[(i + line * 67 + position * 97) % buffer.size()]; });
    }
    const double elapsed = std::chrono::duration<double> (
        std::chrono::steady_clock::now() - start).count();
    std::printf ("Worst-case read mixing, 126 pre-delay + 8 x 8 SIZE positions: %.6f s / 4 audio s (%.3f%%), checksum %.9g\n",
                 elapsed, 100.0 * elapsed / 4.0, checksum);
    expect (std::isfinite (checksum), "worst-case automation benchmark remains finite");
}
#endif

septum::Patch reverbPatch()
{
    septum::Patch patch;
    patch.upper.osc1.wave = septum::Waveform::ExtIn;
    patch.upper.filterType = septum::FilterType::Bypass;
    patch.upper.balance = -63;
    patch.upper.level = 80;
    patch.upper.ampEnvAttack = patch.upper.ampEnvRelease = 0;
    patch.upper.reverbDepth = 127;
    patch.reverbOn = true;
    patch.reverb.time = 127;
    patch.reverb.size = 0;
    patch.reverb.preDelay = 0;
    patch.reverb.highCut = 20;
    patch.reverb.lfDampGain = patch.reverb.hfDampGain = 0;
    return patch;
}

// mode 0: unchanged, 1: one PRE DELAY edit, 2: one SIZE edit,
// 3: fast edits throughout a decaying tail, 4: same plus panic.
std::vector<float> render (int rate, int block, int mode, double seconds = 0.6,
                          int initialSize = 0, int initialPreDelay = 0)
{
    septum::Engine engine;
    engine.prepare (rate, block);
    auto patch = reverbPatch();
    patch.reverb.size = initialSize;
    patch.reverb.preDelay = initialPreDelay;
    engine.setPatch (patch);
    septum::ExternalInput external;
    external.inputVolume = 127;
    engine.setExternalInput (external);
    engine.reset();
    engine.noteOn (60, 100);
    const int frames = static_cast<int> (rate * seconds);
    const int edit = static_cast<int> (rate * 0.25) / 8 * 8;
    const int panic = static_cast<int> (rate * 0.75) / 8 * 8;
    std::vector<float> left (frames), right (frames), input (frames);
    for (int i = 0; i < frames; ++i)
        if (mode < 3 || i < edit)
            input[static_cast<std::size_t> (i)] = static_cast<float> (
                0.07 * std::sin (2 * pi * 337.0 * i / rate)
                + 0.025 * std::sin (2 * pi * 1789.0 * i / rate));
    for (int offset = 0; offset < frames;)
    {
        int next = frames;
        if (offset < edit)
            next = edit;
        else if (mode >= 3)
        {
            // Extreme jumps plus all intermediate positions every 8 samples.
            const int tick = (offset - edit) / 8;
            patch.reverb.preDelay = (tick % 4 == 0 ? 125 : tick % 126);
            patch.reverb.size = (tick % 4 == 0 ? 7 : tick % 8);
            engine.setPatch (patch);
            next = offset + 8;
            if (mode == 4 && offset == panic)
                engine.allSoundOff();
        }
        else if (offset == edit)
        {
            if (mode == 1) patch.reverb.preDelay = 125;
            if (mode == 2) patch.reverb.size = 7;
            engine.setPatch (patch);
        }
        const int count = std::min ({ block, frames - offset, next - offset });
        engine.process (left.data() + offset, right.data() + offset, count,
                        input.data() + offset, input.data() + offset);
        offset += count;
    }
    // Keep both channels in the stability and silence checks.
    left.insert (left.end(), right.begin(), right.end());
    return left;
}

void engineTests()
{
    for (int rate : { 8000, 22050, 44100, 48000, 96000, 192000 })
    {
        const auto steady = render (rate, 256, 0);
        for (int mode : { 1, 2 })
        {
            const auto edited = render (rate, 256, mode);
            const int edit = static_cast<int> (rate * 0.25) / 8 * 8;
            const int firstReturn = mode == 1
                ? static_cast<int> (septum::mapping::reverbLineSeconds[0]
                                  * septum::mapping::reverbSizeScale (0) * rate) | 1
                : 0;
            double firstMillisecond = 0.0, fullDifference = 0.0;
            for (int sample = edit; sample < edit + rate / 20; ++sample)
            {
                const double difference = std::abs (edited[sample] - steady[sample]);
                fullDifference = std::max (fullDifference, difference);
                if (sample < edit + firstReturn + septum::AnalogOutput::latencySamples + rate / 1000)
                    firstMillisecond = std::max (firstMillisecond, difference);
            }
            std::printf ("%d Hz %s edit: peak difference first 1 ms %.9g, first 50 ms %.9g\n",
                         rate, mode == 1 ? "PRE DELAY" : "SIZE", firstMillisecond, fullDifference);
            expect (fullDifference > 1.0e-5, "geometry edit reaches the audio output");
            expect (firstMillisecond < (mode == 1 ? 0.00003 : 0.0003),
                    "live geometry does not expose a full tap discontinuity at the edit boundary");
        }
        const auto tail = render (rate, 256, 3, 3.0);
        double peak = 0.0, early = 0.0, late = 0.0;
        for (std::size_t i = 0; i < tail.size(); ++i)
        {
            peak = std::max (peak, std::abs (double (tail[i])));
            expect (std::isfinite (tail[i]), "maximum-decay tail stays finite under repeated geometry changes");
            const int sample = static_cast<int> (i) % (rate * 3);
            if (sample >= rate / 2 && sample < rate) early += double (tail[i]) * tail[i];
            if (sample >= rate * 5 / 2) late += double (tail[i]) * tail[i];
        }
        std::printf ("%d Hz rapid-retarget tail peak %.9g, final/early energy %.9g\n", rate, peak, late / early);
        expect (peak < 0.5, "maximum-decay automation produces no amplitude runaway");
        expect (late < early, "maximum-decay tail loses energy with continuing geometry automation");
        const auto panic = render (rate, 256, 4, 1.0);
        double afterPanic = 0.0;
        for (std::size_t i = 0; i < panic.size(); ++i)
            if (static_cast<int> (i) % rate > rate * 0.9)
                afterPanic = std::max (afterPanic, std::abs (double (panic[i])));
        std::printf ("%d Hz post-panic peak %.9g\n", rate, afterPanic);
        expect (afterPanic < 1.0e-8, "panic invalidates every active geometry read head");
    }
    for (int mode : { 1, 2, 3 })
    {
        const auto normal = render (48000, 256, mode);
        const auto fragmented = render (48000, 17, mode);
        double error = 0.0;
        for (std::size_t i = 0; i < normal.size(); ++i)
            if (i % (normal.size() / 2) > 48000 * 0.27)
                error = std::max (error, std::abs (double (normal[i]) - fragmented[i]));
        std::printf ("Mode %d block-fragmentation peak error %.9g\n", mode, error);
        expect (error < 1.0e-6, "geometry fades follow samples independently of host block segmentation");
    }
}

void engineBenchmark()
{
    for (int mode : { 0, 3 })
    {
        const auto start = std::chrono::steady_clock::now();
        const auto output = render (48000, 8, mode, 4.0);
        const double elapsed = std::chrono::duration<double> (
            std::chrono::steady_clock::now() - start).count();
        std::printf ("Complete engine, %s geometry at 48 kHz: %.6f s / 4 audio s (%.3f%%), sample %.9g\n",
                     mode == 0 ? "settled" : "rapid-retarget", elapsed,
                     100.0 * elapsed / 4.0, output.back());
    }
}
} // namespace

int main (int argc, char** argv)
{
    if (argc == 2 && std::string (argv[1]) == "--static")
    {
        std::uint64_t hash = 1469598103934665603ull;
        for (int rate : { 8000, 44100, 192000 })
            for (int size = 0; size < 8; ++size)
                for (int predelay : { 0, 1, 63, 125 })
                    for (float value : render (rate, 256, 0, 0.3, size, predelay))
                    {
                        hash ^= std::bit_cast<std::uint32_t> (value);
                        hash *= 1099511628211ull;
                    }
        std::printf ("Settled geometry audio hash %016llx\n", static_cast<unsigned long long> (hash));
        return 0;
    }
#ifndef SEPTUM_GEOMETRY_BASELINE
    headTests<8>();
    headTests<126>();
    worstCaseBenchmark();
#endif
    engineTests();
    engineBenchmark();
    std::printf ("Reverb geometry: %d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
