#pragma once

#include <algorithm>
#include <cmath>

namespace septum::detail
{

// OM p. 63 specifies independent LF/HF damping gains in dB. A shelf must
// reach that gain at one end of the spectrum and unity at the other. Mixing
// a one-pole smoother with dry audio cannot do this: its low-pass response
// remains nonzero at Nyquist, leaking treble through the HF cut and applying
// an unintended treble cut in the LF section.
//
// First-order analog shelves, discretised by a prewarped bilinear transform:
// https://www.dsprelated.com/freebooks/filters/Low_High_Shelving_Filters.html
// The low-pass and its complementary high-pass sum to the input exactly.
// This is a numerical realization of the documented controls, not evidence
// for Roland's proprietary filter order or transition shape.
[[nodiscard]] inline double reverbDampingCoefficient (double frequency,
                                                       double sampleRate) noexcept
{
    // Published corners above a low host rate's Nyquist cannot be represented.
    // Keep the limiting transition just inside Nyquist, with a strictly stable
    // pole, rather than allowing the prewarp tangent to wrap negative.
    const double ratio = std::clamp (frequency / std::max (8000.0, sampleRate),
                                     1.0e-6, 0.499);
    const double g = std::tan (3.14159265358979323846 * ratio);
    return g / (1.0 + g);
}

struct ReverbDampingState
{
    double previousInput { 0.0 };
    double previousLow { 0.0 };
};

[[nodiscard]] inline double reverbDampingLowpass (double input,
                                                  double coefficient,
                                                  ReverbDampingState& state) noexcept
{
    // Direct form I preserves actual preceding input/output samples across
    // frequency edits. A trapezoidal integrator's internal state can grow
    // large near Nyquist even when its output is tiny; changing its corner
    // can expose that state as a burst inside the reverb feedback loop.
    const double low = coefficient * (input + state.previousInput)
                       + (1.0 - 2.0 * coefficient) * state.previousLow;
    state.previousInput = input;
    state.previousLow = low;
    return low;
}

[[nodiscard]] inline double reverbHighShelf (double input, double gain,
                                              double coefficient,
                                              ReverbDampingState& state) noexcept
{
    const double low = reverbDampingLowpass (input, coefficient, state);
    return input + (gain - 1.0) * (input - low);
}

[[nodiscard]] inline double reverbLowShelf (double input, double gain,
                                             double coefficient,
                                             ReverbDampingState& state) noexcept
{
    const double low = reverbDampingLowpass (input, coefficient, state);
    return input + (gain - 1.0) * low;
}

} // namespace septum::detail
