#pragma once

#include <algorithm>
#include <array>
#include <cmath>

namespace septum
{
// Explicit experimental model data, independent of patch/SysEx parameters.
// Disabled sections use the production equations without table interpolation.
// These bounds constrain numerical experiments; they do not certify a match
// to hardware. Construct from Engine::defaultTimbreCalibration().
struct TimbreCalibration
{
    using Table = std::array<double, 128>;
    bool filterEnabled { false }, envelopeEnabled { false };
    bool wavesEnabled { false }, superSawEnabled { false };
    Table cutoffHz {}, resonanceDamping {}, secondStageDamping {};
    Table attackSeconds {}, decaySeconds {}, sustainLevel {}, releaseSeconds {};
    std::array<double, 5> phaseCycles {}, waveGain {};
    Table pulseDuty {};
    Table superDetune {}, superCenterGain {}, superSideGain {};
    std::array<double, 7> superOffsets {};
    double superHpfRatio { 1.0 }, superHpfQ { 0.7071067811865476 };
    double superNormalization { 0.4 };

    static double lookup (const Table& table, double control) noexcept
    {
        const double x = std::clamp (control, 0.0, 127.0);
        const auto index = static_cast<std::size_t> (x);
        const auto next = std::min (index + 1, std::size_t { 127 });
        return table[index] + (table[next] - table[index]) * (x - index);
    }

    [[nodiscard]] bool valid() const noexcept
    {
        const auto scalar = [] (double value, double lo, double hi)
        { return std::isfinite (value) && value >= lo && value <= hi; };
        const auto array = [&] (const auto& values, double lo, double hi, int order = 0)
        {
            for (std::size_t i = 0; i < values.size(); ++i)
                if (! scalar (values[i], lo, hi)
                    || (i > 0 && order > 0 && values[i] < values[i - 1])
                    || (i > 0 && order < 0 && values[i] > values[i - 1]))
                    return false;
            return true;
        };
        if (filterEnabled && (! array (cutoffHz, 5, 40000, 1)
            || ! array (resonanceDamping, -0.04, 4, -1)
            || ! array (secondStageDamping, 0.25, 4, -1))) return false;
        if (envelopeEnabled && (! array (attackSeconds, 0.00001, 120, 1)
            || ! array (decaySeconds, 0.00001, 120, 1)
            || ! array (releaseSeconds, 0.00001, 120, 1)
            || ! array (sustainLevel, 0, 1, 1)
            || sustainLevel.front() != 0 || sustainLevel.back() != 1)) return false;
        if (wavesEnabled && (! array (phaseCycles, 0, 1)
            || std::any_of (phaseCycles.begin(), phaseCycles.end(), [] (double p) { return p >= 1; })
            || ! array (waveGain, -2, 2) || ! array (pulseDuty, 0.01, 0.99, 1))) return false;
        if (superSawEnabled)
        {
            if (! array (superDetune, 0, 2) || ! array (superOffsets, -0.25, 0.25, 1)
                || superOffsets[3] != 0 || ! array (superCenterGain, 0, 2)
                || ! array (superSideGain, 0, 2)
                || ! scalar (superHpfRatio, 0.05, 4) || ! scalar (superHpfQ, 0.25, 2)
                || ! scalar (superNormalization, 0.05, 2)) return false;
            for (std::size_t i = 1; i < superOffsets.size(); ++i)
                if (superOffsets[i] <= superOffsets[i - 1]) return false;
        }
        return true;
    }
};
} // namespace septum
