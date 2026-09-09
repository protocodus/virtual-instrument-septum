#pragma once

namespace septum::detail
{
// Four-point Lagrange interpolation between centre and next. Unlike the
// previous two-point interpolation, its amplitude error is fourth-order at
// low frequencies, reducing unintended damping inside the delay feedback
// loop. Parameter mappings and integer-delay samples are unchanged.
//
// The caller must retain one sample before centre and two after it, and keep
// those taps in the past. This is a numerical reconstruction choice, not a
// claim about Roland's undocumented interpolation algorithm.
// Reference: J.O. Smith, Physical Audio Signal Processing, "Delay-Line
// Interpolation": https://www.dsprelated.com/freebooks/pasp/Delay_Line_Interpolation.html
[[nodiscard]] inline double delayLagrange4 (double previous, double centre,
                                           double next, double afterNext,
                                           double fraction) noexcept
{
    // Besides avoiding unnecessary work at integer times, these endpoints
    // return the original stored sample exactly.
    if (fraction <= 0.0)
        return centre;
    if (fraction >= 1.0)
        return next;
    const double before = -fraction * (1.0 - fraction) * (2.0 - fraction) / 6.0;
    const double first = (1.0 + fraction) * (1.0 - fraction) * (2.0 - fraction) / 2.0;
    const double second = (1.0 + fraction) * fraction * (2.0 - fraction) / 2.0;
    const double after = -(1.0 + fraction) * fraction * (1.0 - fraction) / 6.0;
    return before * previous + first * centre + second * next + after * afterNext;
}
} // namespace septum::detail
