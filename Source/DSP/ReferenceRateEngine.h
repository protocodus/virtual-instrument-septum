// Experimental host-rate boundary for an explicitly selected synthesis rate.
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

// Controls are inherited and affect the next internal sample rendered. Every
// host interval is completed before process returns, so an event at host frame
// H first reaches core frame ceil(H * coreRate / hostRate), never a past frame.
// Its quantisation is therefore causal and shorter than one core sample.
// Render calls deliberately use one internal sample: this makes control/envelope
// cadence independent of host block and event segmentation, but changes the
// incumbent engine's 8-sample control evaluation and costs more CPU. Do not
// substitute this through an Engine pointer: lifecycle/render methods are not
// virtual. The native engine remains available for comparison.
//
// FIR reconstruction uses only input already supplied by the host. Core
// frames inside the last host interval are completed before the next control
// boundary; they cannot affect an output frame already emitted. Compared with
// the first prototype this changes event timing, not the static rate model.
// Neither the default 44.1 kHz nor another selected rate is hardware calibration.
class ReferenceRateEngine : public Engine
{
public:
    static constexpr double referenceRateHz = 44100.0;
    static constexpr double minimumSynthesisRateHz = 8000.0;
    static constexpr double maximumSynthesisRateHz = 192000.0;

    // Invalid synthesis rates throw std::invalid_argument before changing the
    // current setup. Host-rate clamping retains the original two-argument API.
    void prepare (double hostRate, int maximumBlockSize,
                  double synthesisRate = referenceRateHz);
    void reset();
    void process (float* left, float* right, int numSamples,
                  const float* inputLeft = nullptr,
                  const float* inputRight = nullptr);

    [[nodiscard]] double sampleRate() const noexcept { return hostRate_; }
    [[nodiscard]] double synthesisRate() const noexcept { return synthesisRate_; }
    // Synth/MIDI transport: the core's reported latency plus output FIR group
    // delay. Ceil rounds this fixed transport conservatively. An event also
    // quantizes forward by [0, 1/coreRate) seconds depending on its timestamp;
    // this variable scheduling offset is not included in the fixed latency.
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
    void renderInternalSample();
    double hostRate_ { referenceRateHz };
    double synthesisRate_ { referenceRateHz };
    std::uint64_t hostFrames_ { 0 }, internalFrames_ { 0 };
    detail::ReferenceRateConverter inputConverter_, outputConverter_;
    bool prepared_ { false };
};
} // namespace septum
