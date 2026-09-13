#pragma once

#include <algorithm>
#include <array>
#include <cstddef>

namespace septum::detail
{
// Crossfade fixed delay taps instead of moving a read head through the audio.
// Convex weights avoid a gain boost inside the feedback loop. Keeping every
// current weight makes an interrupted fade continuous even when automation
// visits a third position before the previous transition has finished.
template <std::size_t Positions>
struct ReverbReadHeads
{
    static constexpr double fadeSeconds = 0.010; // artifact-suppression policy
    std::array<double, Positions> weights { 1.0 };
    std::size_t target { 0 };
    bool moving { false };

    void reset (int position) noexcept
    {
        target = static_cast<std::size_t> (std::clamp (
            position, 0, static_cast<int> (Positions) - 1));
        weights.fill (0.0);
        weights[target] = 1.0;
        moving = false;
    }

    void advance (int position, double step) noexcept
    {
        const auto next = static_cast<std::size_t> (std::clamp (
            position, 0, static_cast<int> (Positions) - 1));
        if (! moving && next == target)
            return;
        target = next;
        const double remaining = 1.0 - weights[target];
        if (remaining <= step)
        {
            reset (position);
            return;
        }
        const double scale = (remaining - step) / remaining;
        for (std::size_t index = 0; index < Positions; ++index)
            if (index != target)
                weights[index] *= scale;
        weights[target] += step;
        moving = true;
    }

    template <typename Read>
    [[nodiscard]] double read (Read&& readPosition) const noexcept
    {
        if (! moving)
            return readPosition (target);
        double result = 0.0;
        for (std::size_t index = 0; index < Positions; ++index)
            if (weights[index] > 0.0)
                result += weights[index] * readPosition (index);
        return result;
    }
};
} // namespace septum::detail
