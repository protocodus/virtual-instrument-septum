// Experimental host-rate boundary for the fixed 44.1 kHz Septum model.
// This is an offline/comparison prototype, not the plug-in's default engine.
#pragma once

#include "SeptumEngine.h"

#include <array>
#include <cstdint>
#include <vector>

namespace septum
{
namespace detail
{
// Causal stereo fractional-delay FIR, exposed for focused converter tests.
// Push source samples in order, then read a delayed source-time coordinate.
// All tables and history storage are allocated by prepare, never push/read.
class ReferenceRateConverter
{
public:
    static constexpr int phases = 1024;
    static constexpr int baseHalfWidth = 64;

    void prepare (double sourceRate, double destinationRate);
    void reset() noexcept;
    void push (float left, float right) noexcept;
    [[nodiscard]] std::array<float, 2> read (double sourcePosition) const noexcept;
    [[nodiscard]] int groupDelay() const noexcept { return halfWidth_; }
    [[nodiscard]] int taps() const noexcept { return taps_; }

private:
    int halfWidth_ { baseHalfWidth }, taps_ { 2 * baseHalfWidth + 1 };
    std::size_t historyMask_ { 0 };
    std::int64_t written_ { 0 };
    std::vector<double> coefficients_;
    std::vector<std::array<float, 2>> history_;
};
} // namespace detail

// Controls are inherited and affect the next internal sample rendered. Render
// calls deliberately use one internal sample: this makes control/envelope
// cadence independent of host block and event segmentation, but changes the
// incumbent engine's 8-sample control evaluation and costs more CPU. Do not
// substitute this through an Engine pointer: lifecycle/render methods are not
// virtual. The native engine remains available for comparison.
//
// FIR reconstruction is causal (no synthesis ahead of the host clock). At host
// rates below 44.1 kHz, an immediate control can reach a pending internal frame
// less than one host sample before its nominal host timestamp. At higher rates
// it reaches the next internal frame within one internal sample. This explicit
// quantisation limit is a prototype constraint, not sample-exact MIDI alignment.
class ReferenceRateEngine : public Engine
{
public:
    static constexpr double referenceRateHz = 44100.0;

    void prepare (double hostRate, int maximumBlockSize);
    void reset();
    void process (float* left, float* right, int numSamples,
                  const float* inputLeft = nullptr,
                  const float* inputRight = nullptr);

    [[nodiscard]] double sampleRate() const noexcept { return hostRate_; }
    // Synth/MIDI path: the core's reported latency plus output FIR group delay.
    // Ceil is the conservative integer a host can report; fractional delay is
    // not silently rounded inside the converter itself.
    [[nodiscard]] int latencySamples() const noexcept;
    [[nodiscard]] double exactLatencySamples() const noexcept;
    [[nodiscard]] int inputConversionLatencySamples() const noexcept
    {
        return inputConverter_.groupDelay();
    }
    // External audio also crosses the input FIR. It therefore has a different
    // delay from MIDI-generated sound; this prototype does not align the two.
    [[nodiscard]] int externalInputLatencySamples() const noexcept;
    [[nodiscard]] std::uint64_t renderedInternalSamples() const noexcept
    {
        return internalFrames_;
    }

private:
    double hostRate_ { referenceRateHz };
    std::uint64_t hostFrames_ { 0 }, internalFrames_ { 0 };
    detail::ReferenceRateConverter inputConverter_, outputConverter_;
    bool prepared_ { false };
};
} // namespace septum
