#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>

namespace septum
{
// MIDI Timing Clock is 24 pulses per quarter note. A six-interval moving
// average suppresses timestamp jitter while acquiring in one interval.
// Estimation and dropout handling are plug-in policies, not recovered Roland
// firmware. All timing uses rendered samples, including offline processing.
class MidiTempoClock
{
public:
    void prepare (double sampleRate) noexcept
    {
        rate = sampleRate;
        reset();
    }

    void reset() noexcept
    {
        intervals.fill (0.0);
        elapsed = 0;
        count = 0;
        write = 0;
        sum = 0.0;
        havePulse = false;
    }

    [[nodiscard]] bool running() const noexcept { return count > 0; }
    [[nodiscard]] double bpm() const noexcept
    {
        return running() ? 60.0 * rate * count / (24.0 * sum) : 120.0;
    }

    void pulse() noexcept
    {
        if (havePulse && elapsed == 0)
            return; // duplicate timestamps cannot establish a tempo
        if (havePulse)
        {
            const double interval = static_cast<double> (elapsed);
            // Differences of rounded absolute timestamps can differ from the
            // ideal interval by nearly one sample, including at 300 BPM.
            if (interval >= rate / 120.0 - 1.0 && interval <= rate * 0.5 + 1.0)
            {
                sum -= intervals[write];
                intervals[write] = interval;
                sum += interval;
                write = (write + 1) % intervals.size();
                count = std::min (count + 1, static_cast<int> (intervals.size()));
            }
            else
            {
                reset();
            }
        }
        havePulse = true;
        elapsed = 0;
    }

    [[nodiscard]] int samplesUntilTimeout (int maximum) const noexcept
    {
        if (! havePulse)
            return maximum;
        const auto limit = timeout();
        return static_cast<int> (std::min<std::uint64_t> (
            static_cast<std::uint64_t> (maximum), limit > elapsed ? limit - elapsed : 1));
    }

    void advance (int samples) noexcept
    {
        if (! havePulse)
            return;
        elapsed += static_cast<std::uint64_t> (samples);
        if (elapsed >= timeout())
            reset();
    }

private:
    [[nodiscard]] std::uint64_t timeout() const noexcept
    {
        // At slow tempi, allow three expected clocks; otherwise allow 500ms.
        const double period = running() ? sum / count : rate * 0.5;
        return static_cast<std::uint64_t> (std::ceil (std::max (rate * 0.5, 3.0 * period))) + 1;
    }
    double rate { 44100.0 };
    std::array<double, 6> intervals {};
    std::uint64_t elapsed { 0 };
    std::size_t write { 0 };
    int count { 0 };
    double sum { 0.0 };
    bool havePulse { false };
};
} // namespace septum
