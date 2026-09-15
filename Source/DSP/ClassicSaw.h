#pragma once

#include <algorithm>
#include <array>
#include <cmath>

namespace septum::classic_saw
{
// [measured, provisional] A unit ramp with the frozen asymmetric wrap
// correction fitted through the complete engine to the original dry Saw
// recording. This improves cross-pitch harmonic/alias agreement, with retained
// counterexamples; it does not identify Roland's oscillator architecture.
// See Docs/fidelity/source-audits/saw-w4-engine-comparison-2026-09-15.md.
// The 4/44100-second support is fixed in time. Non-44.1 kHz folding has not
// been measured against hardware; the host oscillator clock stays native.
inline constexpr double referenceRate = 44100.0;
inline constexpr double support = 4.0;
inline constexpr double maxReferenceIncrement = 0.45 * (768000.0 / referenceRate);
inline constexpr std::array<double, 22> knots {
    0, 0, 0, 0, .5, .5, 1, 1, 1.5, 1.5, 2, 2,
    2.5, 2.5, 3, 3, 3.5, 3.5, 4, 4, 4, 4
};
inline constexpr std::array<double, 16> negative {
    -0.5176792366136211, -0.46931955147310944,
    -1.0134254782559298, -1.3373042368950236,
    -1.363868567569721, -0.8911412716438063,
    -0.46487346950818725, 0.10062466836509,
    0.22203910231735358, 0.2223404475361894,
    0.18720486905653594, 0.0471512406234926,
    -0.08061217371443616, -0.06184653654990931,
    -0.08525998851231155, -0.023782484738024356
};
inline constexpr std::array<double, 16> positive {
    1.696147678480432, 1.6586152754187593,
    1.606374895453979, 0.8561332841015539,
    0.2537557929166875, -0.570640623484416,
    -0.421373504730979, -0.2106120194626956,
    0.20578702428066792, 0.5082534377831136,
    0.44183767452384154, 0.3127716399360764,
    0.045169037423127015, -0.13242349858581756,
    -0.10444488533356389, -0.10924406938854202
};
inline constexpr double meanIntegral = []
{
    double result = 0.0;
    for (std::size_t j = 0; j < negative.size(); ++j)
        result += (negative[j] + positive[j]) * (knots[j + 4] - knots[j]) / 4;
    return result;
}();

// Four active control points and six De Boor interpolations, without heap
// storage or evaluating all 32 basis functions. The final two control points
// are zero: each side reaches zero value and slope at the support boundary.
// Keep this evaluation order identical to the independently checked prototype.
[[nodiscard]] inline double curve (double t, const std::array<double, 16>& c) noexcept
{
    if (t < 0.0 || t >= support)
        return 0.0;
    const int span = 3 + 2 * static_cast<int> (std::floor (t * 2));
    std::array<double, 4> d {};
    for (int j = 0; j < 4; ++j)
    {
        const int i = span - 3 + j;
        d[j] = i < 16 ? c[i] : 0.0;
    }
    for (int r = 1; r <= 3; ++r)
        for (int j = 3; j >= r; --j)
        {
            const int i = span - 3 + j;
            const double a = (t - knots[i]) / (knots[i + 4 - r] - knots[i]);
            d[j] = (1 - a) * d[j - 1] + a * d[j];
        }
    return d[3];
}

// position is the already-advanced waveform phase in [0,1). The engine bounds
// host rate to 8..768 kHz and native increment to .45. Even at their joint
// maximum the periodic support includes at most 63 integer wraps; at 44.1 kHz
// at most four. Summing every wrap also covers high-pitch overlapping kernels.
[[nodiscard]] inline double sample (double position, double referenceIncrement) noexcept
{
    if (! std::isfinite (position) || position < 0.0 || position >= 1.0)
        return 0.0;
    if (! std::isfinite (referenceIncrement) || referenceIncrement <= 0.0)
        return 2 * position - 1;
    const double inc = std::min (referenceIncrement, maxReferenceIncrement);
    // This removes the continuous-phase mean, including overlapping copies.
    // It does not remove the DC of an arbitrary finite sampled window.
    double value = (2 * position - 1) - inc * meanIntegral;
    const int first = static_cast<int> (std::ceil (position - support * inc));
    const int last = static_cast<int> (std::floor (position + support * inc));
    for (int k = first; k <= last; ++k)
    {
        const double t = (position - k) / inc;
        value += t < 0.0 ? curve (-t, negative) : curve (t, positive);
    }
    return value;
}
} // namespace septum::classic_saw
