#include "ReferenceRateEngine.h"

#include <algorithm>
#include <cmath>

namespace septum
{
namespace
{
constexpr double pi = 3.14159265358979323846;
constexpr double kaiserBeta = 8.6;

double besselI0 (double x) noexcept
{
    // Power series, used only while constructing the coefficient table.
    double sum = 1.0, term = 1.0;
    const double square = x * x * 0.25;
    for (int k = 1; k < 64; ++k)
    {
        term *= square / (k * k);
        sum += term;
        if (term < sum * 1.0e-15)
            break;
    }
    return sum;
}
} // namespace

void detail::ReferenceRateConverter::prepare (double sourceRate,
                                             double destinationRate)
{
    // Windowed-sinc bandlimited interpolation with a lower cutoff when
    // decimating; mathematical reference: Julius O. Smith, Physical Audio
    // Signal Processing, "Windowed Sinc Interpolation":
    // https://www.dsprelated.com/freebooks/pasp/Windowed_Sinc_Interpolation.html
    //
    // Stretch the support with the downsampling factor. Keeping only 128
    // source taps at 192 -> 44.1 kHz would widen the transition into the audio
    // band. 129 taps at unity provides a symmetric, integer 64-frame delay;
    // the table includes both phase endpoints for continuous interpolation.
    const double ratio = std::min (1.0, destinationRate / sourceRate);
    halfWidth_ = static_cast<int> (std::ceil (baseHalfWidth / ratio));
    taps_ = halfWidth_ * 2 + 1;
    const double cutoff = 0.475 * ratio;
    const double inverseWindowPeak = 1.0 / besselI0 (kaiserBeta);
    coefficients_.resize (static_cast<std::size_t> ((phases + 1) * taps_));
    for (int phase = 0; phase <= phases; ++phase)
    {
        const double fraction = phase / static_cast<double> (phases);
        double sum = 0.0;
        const auto row = static_cast<std::size_t> (phase * taps_);
        for (int tap = 0; tap < taps_; ++tap)
        {
            const double distance = tap - halfWidth_ - fraction;
            const double relative = distance / halfWidth_;
            const double window = std::abs (relative) > 1.0 ? 0.0
                : besselI0 (kaiserBeta * std::sqrt (
                      std::max (0.0, 1.0 - relative * relative))) * inverseWindowPeak;
            const double arg = 2.0 * cutoff * distance;
            const double sinc = std::abs (arg) < 1.0e-12 ? 1.0
                : std::sin (pi * arg) / (pi * arg);
            const double value = 2.0 * cutoff * sinc * window;
            coefficients_[row + static_cast<std::size_t> (tap)] = value;
            sum += value;
        }
        for (int tap = 0; tap < taps_; ++tap)
            coefficients_[row + static_cast<std::size_t> (tap)] /= sum;
    }
    std::size_t capacity = 1;
    while (capacity < static_cast<std::size_t> (taps_ + 8))
        capacity *= 2;
    history_.resize (capacity);
    historyMask_ = capacity - 1;
    reset();
}

void detail::ReferenceRateConverter::reset() noexcept
{
    written_ = 0;
    std::fill (history_.begin(), history_.end(), std::array<float, 2> {});
}

void detail::ReferenceRateConverter::push (float left, float right) noexcept
{
    history_[static_cast<std::size_t> (written_) & historyMask_] = { left, right };
    ++written_;
}

std::array<float, 2> detail::ReferenceRateConverter::read (
    double sourcePosition) const noexcept
{
    const auto centre = static_cast<std::int64_t> (std::floor (sourcePosition));
    const double fraction = sourcePosition - static_cast<double> (centre);
    const double phasePosition = fraction * phases;
    const int phase = std::min (phases - 1, static_cast<int> (phasePosition));
    const double blend = phasePosition - phase;
    const auto row = static_cast<std::size_t> (phase * taps_);
    double left = 0.0, right = 0.0;
    for (int tap = 0; tap < taps_; ++tap)
    {
        const auto index = centre - halfWidth_ + tap;
        if (index < 0 || index >= written_
            || written_ - index > static_cast<std::int64_t> (history_.size()))
            continue; // Initial history is silence, never future samples.
        const auto& value = history_[static_cast<std::size_t> (index) & historyMask_];
        const auto coefficient = row + static_cast<std::size_t> (tap);
        const double weight = coefficients_[coefficient]
            + blend * (coefficients_[coefficient + static_cast<std::size_t> (taps_)]
                       - coefficients_[coefficient]);
        left += value[0] * weight;
        right += value[1] * weight;
    }
    return { static_cast<float> (left), static_cast<float> (right) };
}

void ReferenceRateEngine::prepare (double hostRate, int maximumBlockSize)
{
    // The prototype's supported rate range bounds FIR preparation/storage.
    hostRate_ = std::isfinite (hostRate) ? std::clamp (hostRate, 8000.0, 384000.0)
                                       : referenceRateHz;
    (void) maximumBlockSize; // Streaming history is independent of block size.
    Engine::prepare (referenceRateHz, 16);
    inputConverter_.prepare (hostRate_, referenceRateHz);
    outputConverter_.prepare (referenceRateHz, hostRate_);
    prepared_ = true;
    reset();
}

void ReferenceRateEngine::reset()
{
    Engine::reset();
    inputConverter_.reset();
    outputConverter_.reset();
    hostFrames_ = internalFrames_ = 0;
}

double ReferenceRateEngine::exactLatencySamples() const noexcept
{
    return (Engine::latencySamples() + outputConverter_.groupDelay())
           * hostRate_ / referenceRateHz;
}

int ReferenceRateEngine::latencySamples() const noexcept
{
    return static_cast<int> (std::ceil (exactLatencySamples()));
}

int ReferenceRateEngine::externalInputLatencySamples() const noexcept
{
    return static_cast<int> (std::ceil (exactLatencySamples()
                                       + inputConversionLatencySamples()));
}

void ReferenceRateEngine::process (float* left, float* right, int numSamples,
                                   const float* inputLeft, const float* inputRight)
{
    if (! prepared_ || numSamples <= 0)
    {
        if (numSamples > 0)
        {
            std::fill_n (left, numSamples, 0.0f);
            std::fill_n (right, numSamples, 0.0f);
        }
        return;
    }
    for (int i = 0; i < numSamples; ++i)
    {
        // Read inputs before overwriting output so in-place host buffers work.
        inputConverter_.push (inputLeft != nullptr ? inputLeft[i] : 0.0f,
                              inputRight != nullptr ? inputRight[i] : 0.0f);
        // Integer frame counters and an absolute clock avoid per-block
        // rounding or an accumulating fractional phase error. Never advance
        // the engine beyond the host sample currently being emitted.
        const long double hostTime = static_cast<long double> (hostFrames_);
        while (static_cast<long double> (internalFrames_) * hostRate_
               <= hostTime * referenceRateHz)
        {
            const double inputTime = static_cast<double> (
                static_cast<long double> (internalFrames_) * hostRate_
                / referenceRateHz);
            const auto input = inputConverter_.read (
                inputTime - inputConverter_.groupDelay());
            float coreLeft = 0.0f, coreRight = 0.0f;
            Engine::process (&coreLeft, &coreRight, 1, &input[0], &input[1]);
            outputConverter_.push (coreLeft, coreRight);
            ++internalFrames_;
        }
        const double outputTime = static_cast<double> (
            hostTime * referenceRateHz / hostRate_);
        const auto output = outputConverter_.read (
            outputTime - outputConverter_.groupDelay());
        left[i] = output[0];
        right[i] = output[1];
        ++hostFrames_;
    }
}
} // namespace septum
