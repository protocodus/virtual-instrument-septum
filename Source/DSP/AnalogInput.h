#pragma once

#include <algorithm>
#include <cmath>

namespace septum
{

// The SH-201 service schematic identifies IC22 as an AK4552. Its ADC has a
// digital DC-removal HPF: AKM MS0055-E-01, pp. 5 and 10, gives 3.4 Hz at
// 44.1 kHz and -0.12 dB at 20 Hz. A first-order bilinear HPF reproduces those
// published points; AKM does not publish the original filter coefficients.
// The physical corner stays fixed when the plug-in host rate changes. This
// models the nominal 44.1 kHz device, not a codec reclocked by the host.
class AnalogInput
{
public:
    static constexpr double dcRemovalHz = 3.4;

    void prepare (double sampleRate) noexcept
    {
        const double g = std::tan (3.14159265358979323846 * dcRemovalHz
                                   / std::max (8000.0, sampleRate));
        feedforward_ = 1.0 / (1.0 + g);
        feedback_ = (1.0 - g) / (1.0 + g);
        reset();
    }

    void reset() noexcept { previousInput_ = previousOutput_ = 0.0; }

    [[nodiscard]] double processSample (double input) noexcept
    {
        const double output = feedforward_ * (input - previousInput_)
                              + feedback_ * previousOutput_;
        previousInput_ = input;
        previousOutput_ = std::abs (output) < 1.0e-30 ? 0.0 : output;
        return previousOutput_;
    }

private:
    double feedforward_ { 1.0 }, feedback_ { 0.0 };
    double previousInput_ { 0.0 }, previousOutput_ { 0.0 };
};

} // namespace septum
