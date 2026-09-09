// SH-201 output coupling and active reconstruction filter.
//
// Roland Service Notes 17058418E0, May 2006, printed pp. 36-37 (PDF page 30):
// https://www.synthxl.com/wp-content/uploads/2020/01/Roland-SH-201-Service-Manual.pdf#page=30
// C216/R179 (22 uF/22 kohm) couple the DAC into R175/R176 (4.7/8.2 kohm).
// C219 (270 pF) returns to IC25B's OUTPUT, not ground; C220 (820 pF) goes
// to ground. This is a Sallen-Key filter, not two independent passive poles.
// R169/R170 set gain 2.5; C358 (10 pF) is parallel to R170 (33 kohm).
// The right channel repeats this network with C233/R196/R193/R194/C234/C235,
// IC25A, R187/R188 and C359.
//
// This is the small-signal ideal-op-amp circuit model. The nominal gain 2.5
// is normalised out, preserving the engine's established headroom. No guessed
// op-amp saturation, noise or DAC quantisation is added. Other coupling caps,
// the loaded master pot, line/phones amplifiers and finite op-amp bandwidth
// remain outside this model. C216/R179 is treated as an isolated high-pass;
// its interaction with the following network is negligible in the audio band.
//
// A bilinear discretisation runs at 8x behind linear-phase interpolation and
// decimation filters. This preserves the circuit phase as well as magnitude,
// with bounded numerical frequency warping, and adds 74 base-rate samples of
// transport latency. That latency must be included in host delay compensation.

#pragma once

#include <array>
#include <cmath>
#include <complex>
#include <cstddef>

namespace septum
{
namespace analog_output_detail
{
// Folded odd taps of DC-normalised Parks-McClellan half-band filters.
// Reproducible design: scipy.signal.remez(N, [0, edge, .5-edge, .5],
// [1, 0], fs=1); keep odd taps, centre=.5, scale folded odd sum to .25.
// These filters are numerical sample-rate conversion, not hardware claims.
// N=129, edge=.227: <.00024 dB ripple, >91 dB stopband attenuation.
inline constexpr std::array<double, 32> outerTaps {
    -1.538892892836719e-05, 2.5050850992617275e-05,
    -4.4762568448125e-05, 7.4030935096448862e-05,
    -0.00011585890895102736, 0.00017382487498333096,
    -0.0002521275827128851, 0.00035563811291140963,
    -0.00048992777601916866, 0.00066132425117102086,
    -0.0008769688919648132, 0.0011448816955751818,
    -0.0014740350513820126, 0.0018745238968436546,
    -0.0023577683098338319, 0.0029367956774011775,
    -0.0036267168808547406, 0.0044454650926277969,
    -0.0054147856830518756, 0.0065619725988216929,
    -0.0079223446361525087, 0.0095433895626549099,
    -0.011491481840524818, 0.013863449524886539,
    -0.016807460710853199, 0.020563199902335121,
    -0.025545913930314919, 0.032542489547400306,
    -0.043243621046925848, 0.062052964935443822,
    -0.1051326254064316, 0.31799278669420478
};
// N=33, edge=.18: <.00255 dB ripple, >70 dB stopband attenuation.
inline constexpr std::array<double, 8> middleTaps {
    -0.0005509614757843159, 0.0020627687465320558,
    -0.0055179759817263361, 0.012256819385295844,
    -0.024444365442790196, 0.046709333516118633,
    -0.095074927306226714, 0.314559308558581
};
// N=17, edge=.10: <.00060 dB ripple, >83 dB stopband attenuation.
inline constexpr std::array<double, 4> innerTaps {
    -0.0024718290140259523, 0.016959158839556787,
    -0.067673764721470173, 0.30318643489593938
};

template <std::size_t Pairs>
class HalfBand
{
public:
    explicit HalfBand (const std::array<double, Pairs>& taps) noexcept : taps_ (taps) {}

    void reset() noexcept
    {
        up_.fill (0.0);
        even_.fill (0.0);
        odd_.fill (0.0);
        upWrite_ = downWrite_ = 0;
    }

    std::array<double, 2> upsample (double x) noexcept
    {
        up_[upWrite_] = x;
        const double even = up_[(upWrite_ - Pairs) & mask];
        double odd = 0.0;
        for (std::size_t i = 0; i < Pairs; ++i)
            odd += taps_[i] * (up_[(upWrite_ - i) & mask]
                               + up_[(upWrite_ - (2 * Pairs - 1 - i)) & mask]);
        upWrite_ = (upWrite_ + 1) & mask;
        return { even, 2.0 * odd };
    }

    double downsample (double even, double odd) noexcept
    {
        even_[downWrite_] = even;
        odd_[downWrite_] = odd;
        double y = 0.5 * even_[(downWrite_ - Pairs) & mask];
        for (std::size_t i = 0; i < Pairs; ++i)
            y += taps_[i] * (odd_[(downWrite_ - 1 - i) & mask]
                             + odd_[(downWrite_ - (2 * Pairs - i)) & mask]);
        downWrite_ = (downWrite_ + 1) & mask;
        return y;
    }

private:
    // The downsampler needs a sample 2*Pairs places behind its write head.
    // Keep more than that many slots so writing cannot replace that sample.
    static constexpr std::size_t size = 128;
    static constexpr std::size_t mask = size - 1;
    static_assert (2 * Pairs < size);
    const std::array<double, Pairs>& taps_;
    std::array<double, size> up_ {}, even_ {}, odd_ {};
    std::size_t upWrite_ { 0 }, downWrite_ { 0 };
};

class Oversampling8
{
public:
    // 64 samples for the outer round trip, 16/2 for the middle, 8/4 inner.
    static constexpr int latencySamples = 74;

    void reset() noexcept { outer_.reset(); middle_.reset(); inner_.reset(); }

    template <class Circuit>
    double process (double x, Circuit&& circuit) noexcept
    {
        const auto a = outer_.upsample (x);
        std::array<double, 2> outerResults {};
        for (std::size_t i = 0; i < 2; ++i)
        {
            const auto b = middle_.upsample (a[i]);
            std::array<double, 2> middleResults {};
            for (std::size_t j = 0; j < 2; ++j)
            {
                const auto c = inner_.upsample (b[j]);
                // Explicit evaluation order preserves the circuit state.
                const double first = circuit (c[0]);
                const double second = circuit (c[1]);
                middleResults[j] = inner_.downsample (first, second);
            }
            outerResults[i] = middle_.downsample (middleResults[0], middleResults[1]);
        }
        return outer_.downsample (outerResults[0], outerResults[1]);
    }

private:
    HalfBand<32> outer_ { outerTaps };
    HalfBand<8> middle_ { middleTaps };
    HalfBand<4> inner_ { innerTaps };
};
} // namespace analog_output_detail

class AnalogOutput
{
public:
    static constexpr int latencySamples = analog_output_detail::Oversampling8::latencySamples;
    static constexpr double couplingSeconds = 22.0e-6 * 22000.0;
    static constexpr double r1 = 4700.0, r2 = 8200.0;
    static constexpr double cFeedback = 270.0e-12, cGround = 820.0e-12;
    static constexpr double gain = 1.0 + 33000.0 / 22000.0;
    static constexpr double feedbackSeconds = 33000.0 * 10.0e-12;

    // Nodal analysis of the Sallen-Key network with
    // K(s)=(gain+s*feedbackSeconds)/(1+s*feedbackSeconds):
    // H(s)/gain = (1+s*tau/gain) / (1+d1*s+d2*s^2+d3*s^3).
    static constexpr double skTime = cGround * (r1 + r2)
                                    + cFeedback * r1 * (1.0 - gain);
    static constexpr double skTimeSquared = r1 * r2 * cFeedback * cGround;
    static constexpr double d1 = skTime + feedbackSeconds;
    static constexpr double d2 = skTimeSquared + feedbackSeconds * cGround * (r1 + r2);
    static constexpr double d3 = feedbackSeconds * skTimeSquared;

    // Continuous-time reference for measurement/plots. ADC's 3.4 Hz DC filter
    // is deliberately absent: AK4552 datasheet MS0055-E-01 p.5 assigns it to
    // the ADC, not the DAC/synth output.
    [[nodiscard]] static std::complex<double> analogResponse (double hz) noexcept
    {
        const std::complex<double> s (0.0, 6.28318530717958647692 * hz);
        const auto coupling = s * couplingSeconds / (1.0 + s * couplingSeconds);
        return coupling * (1.0 + s * (feedbackSeconds / gain))
               / (1.0 + s * (d1 + s * (d2 + s * d3)));
    }

    void prepare (double sampleRate) noexcept
    {
        if (! std::isfinite (sampleRate) || sampleRate < 8000.0)
            sampleRate = 44100.0;
        const double c = 2.0 * 8.0 * sampleRate;
        const double t1 = d1 * c, t2 = d2 * c * c, t3 = d3 * c * c * c;
        const double denominator = 1.0 + t1 + t2 + t3;
        a_ = { (3.0 + t1 - t2 - 3.0 * t3) / denominator,
               (3.0 - t1 - t2 + 3.0 * t3) / denominator,
               (1.0 - t1 + t2 - t3) / denominator };
        const double zero = c * feedbackSeconds / gain;
        b_ = { (1.0 + zero) / denominator, (3.0 + zero) / denominator,
               (3.0 - zero) / denominator, (1.0 - zero) / denominator };
        hpPole_ = (c * couplingSeconds - 1.0) / (c * couplingSeconds + 1.0);
        hpGain_ = 0.5 * (1.0 + hpPole_);
        reset();
    }

    void reset() noexcept
    {
        oversampling_.reset();
        z_.fill (0.0);
        hpX_ = hpY_ = 0.0;
    }

    [[nodiscard]] double processSample (double x) noexcept
    {
        return oversampling_.process (x, [this] (double input)
        {
            const double hp = hpGain_ * (input - hpX_) + hpPole_ * hpY_;
            hpX_ = input;
            hpY_ = hp;
            const double y = b_[0] * hp + z_[0];
            z_[0] = b_[1] * hp - a_[0] * y + z_[1];
            z_[1] = b_[2] * hp - a_[1] * y + z_[2];
            z_[2] = b_[3] * hp - a_[2] * y;
            return y;
        });
    }

private:
    analog_output_detail::Oversampling8 oversampling_ {};
    std::array<double, 3> a_ {}, z_ {};
    std::array<double, 4> b_ { 1.0, 0.0, 0.0, 0.0 };
    double hpPole_ { 0.0 }, hpGain_ { 1.0 }, hpX_ { 0.0 }, hpY_ { 0.0 };
};
} // namespace septum
