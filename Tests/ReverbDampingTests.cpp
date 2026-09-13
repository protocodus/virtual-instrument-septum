// Published gain semantics (SH-201 OM p. 63) and their shelf realization.
// These checks do not identify the hardware's proprietary reverb algorithm.
#include "DSP/ReverbDamping.h"
#include "DSP/SeptumEngine.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <complex>
#include <cstdio>
#include <string>
#include <vector>

namespace
{
constexpr double pi = 3.14159265358979323846;
int checks = 0, failures = 0;

void expect (bool condition, const std::string& message)
{
    ++checks;
    if (! condition)
    {
        ++failures;
        std::fprintf (stderr, "FAIL: %s\n", message.c_str());
    }
}

std::complex<double> measuredResponse (bool lowShelf, double corner,
                                       double gain, double rate, double frequency)
{
    const double coefficient = septum::detail::reverbDampingCoefficient (corner, rate);
    const double poleMagnitude = std::abs (1.0 - 2.0 * coefficient);
    const int samples = std::max (1024, static_cast<int> (
        std::ceil (32.0 / (1.0 - poleMagnitude))));
    std::complex<double> response {}, phase { 1.0, 0.0 };
    const auto step = std::polar (1.0, -2.0 * pi * frequency / rate);
    septum::detail::ReverbDampingState state;
    for (int i = 0; i < samples; ++i)
    {
        const double input = i == 0 ? 1.0 : 0.0;
        const double output = lowShelf
            ? septum::detail::reverbLowShelf (input, gain, coefficient, state)
            : septum::detail::reverbHighShelf (input, gain, coefficient, state);
        response += output * phase;
        phase *= step;
    }
    return response;
}

void transferTests()
{
    for (double rate : { 8000.0, 22050.0, 44100.0, 48000.0, 96000.0, 192000.0 })
        for (bool low : { false, true })
        {
            std::vector<double> corners;
            if (low)
                corners.assign (septum::reverbLfDampHz.begin(), septum::reverbLfDampHz.end());
            else
                corners.assign (septum::reverbHfDampHz.begin(), septum::reverbHfDampHz.end());
            for (double corner : corners)
                for (int db : { -36, -6, 0 })
                {
                    const double gain = std::pow (10.0, db / 20.0);
                    const auto dc = measuredResponse (low, corner, gain, rate, 0.0);
                    const auto nyquist = measuredResponse (low, corner, gain, rate, rate * 0.5);
                    expect (std::abs (dc - (low ? gain : 1.0)) < 1.0e-10,
                            "damping shelf reaches its documented DC endpoint");
                    expect (std::abs (nyquist - (low ? 1.0 : gain)) < 1.0e-10,
                            "damping shelf reaches its documented Nyquist endpoint");
                }
        }

    // Compare the actual impulse response with the independently specified
    // continuous prototype H_L(s)=(s+gain)/(s+1), H_H(s)=(1+gain*s)/(1+s).
    // Frequency prewarping maps the published corner to s=j exactly.
    for (double rate : { 44100.0, 96000.0 })
        for (bool low : { false, true })
            for (double corner : { 50.0, 4000.0, 12500.0 })
                for (int db : { -36, -6, 0 })
                    for (double frequency : { corner * 0.25, corner, rate * 0.45 })
                    {
                        const double gain = std::pow (10.0, db / 20.0);
                        const std::complex<double> s (0.0,
                            std::tan (pi * frequency / rate) / std::tan (pi * corner / rate));
                        const auto reference = low ? (s + gain) / (s + 1.0)
                                                   : (1.0 + gain * s) / (1.0 + s);
                        const auto measured = measuredResponse (low, corner, gain, rate, frequency);
                        expect (std::abs (measured - reference) < 1.0e-9,
                                "measured magnitude and phase match the shelf prototype");
                        expect (std::abs (measured) >= gain - 1.0e-10
                                && std::abs (measured) <= 1.0 + 1.0e-10,
                                "damping remains passive throughout the transition");
                    }

    septum::detail::ReverbDampingState lowState, highState;
    for (int i = 0; i < 4096; ++i)
    {
        const double input = std::sin (i * 0.57) + 0.3 * std::cos (i * 0.21);
        const double coefficient = septum::detail::reverbDampingCoefficient (
            i < 2048 ? 50.0 : 12500.0, 44100.0);
        const double gain = i < 1024 ? 0.1 : 1.0;
        const double low = septum::detail::reverbLowShelf (input, gain, coefficient, lowState);
        const double high = septum::detail::reverbHighShelf (input, gain, coefficient, highState);
        if (gain == 1.0)
            expect (low == input && high == input,
                    "0 dB is exact unity even with nonzero state and frequency changes");
    }
}

void frequencyEditTests()
{
    double largestError = 0.0;
    for (double rate : { 8000.0, 22050.0, 44100.0, 48000.0, 96000.0, 192000.0 })
        for (bool low : { false, true })
        {
            const std::vector<double> corners = low
                ? std::vector<double> (septum::reverbLfDampHz.begin(), septum::reverbLfDampHz.end())
                : std::vector<double> (septum::reverbHfDampHz.begin(), septum::reverbHfDampHz.end());
            for (double from : corners)
                for (double to : corners)
                {
                    const double before = septum::detail::reverbDampingCoefficient (from, rate);
                    const double after = septum::detail::reverbDampingCoefficient (to, rate);
                    const double gain = std::pow (10.0, -36.0 / 20.0);
                    septum::detail::ReverbDampingState state;
                    const auto filter = [&] (double input, double coefficient)
                    {
                        return low ? septum::detail::reverbLowShelf (input, gain, coefficient, state)
                                   : septum::detail::reverbHighShelf (input, gain, coefficient, state);
                    };
                    // At Nyquist every low-pass has zero settled output, so
                    // changing its corner should not expose hidden integrator
                    // energy. A TPT state at a corner clamped near Nyquist
                    // formerly produced a 19.05-unit burst from +/-0.1 input.
                    const int warm = std::max (16000, static_cast<int> (std::ceil (
                        32.0 / (1.0 - std::abs (1.0 - 2.0 * before))))) & ~1;
                    for (int i = 0; i < warm; ++i)
                        (void) filter (i % 2 == 0 ? 0.1 : -0.1, before);
                    double maximumError = 0.0;
                    for (int i = 0; i < 64; ++i)
                    {
                        const double input = i % 2 == 0 ? 0.1 : -0.1;
                        maximumError = std::max (maximumError,
                            std::abs (filter (input, after) - input * (low ? 1.0 : gain)));
                    }
                    largestError = std::max (largestError, maximumError);
                    expect (maximumError < 1.0e-10,
                            "live damping frequency edits do not unmask internal near-Nyquist energy");
                }
        }
    std::printf ("Maximum damping-frequency-edit transient error %.9g\n", largestError);
}

std::vector<float> tail (bool low, int db, double frequency, int block = 256)
{
    constexpr int rate = 44100, frames = rate;
    septum::Engine engine;
    engine.prepare (rate, block);
    septum::Patch patch;
    patch.upper.osc1.wave = septum::Waveform::ExtIn;
    patch.upper.filterType = septum::FilterType::Bypass;
    patch.upper.balance = -63;
    patch.upper.level = 80;
    patch.upper.ampEnvAttack = patch.upper.ampEnvRelease = 0;
    patch.upper.reverbDepth = 127;
    patch.reverbOn = true;
    patch.reverb.time = 100;
    patch.reverb.size = 7;
    patch.reverb.highCut = 20;
    patch.reverb.hfDampFrequency = 0;  // 4000 Hz
    patch.reverb.lfDampFrequency = 19; // 4000 Hz
    patch.reverb.lfDampGain = low ? db : 0;
    patch.reverb.hfDampGain = low ? 0 : db;
    engine.setPatch (patch);
    septum::ExternalInput external;
    external.inputVolume = 127;
    engine.setExternalInput (external);
    engine.reset();
    engine.noteOn (60, 100);

    std::vector<float> left (frames), right (frames), input (frames);
    for (int i = 0; i < 2205; ++i) // 50 ms sine burst, then silence
        input[static_cast<std::size_t> (i)] = static_cast<float> (
            0.1 * std::sin (2.0 * pi * frequency * i / rate));
    for (int i = 0; i < frames; i += block)
        engine.process (left.data() + i, right.data() + i, std::min (block, frames - i),
                        input.data() + i, input.data() + i);
    return left;
}

double energy (const std::vector<float>& samples, double start, double end)
{
    double sum = 0.0;
    for (int i = static_cast<int> (44100 * start); i < static_cast<int> (44100 * end); ++i)
        sum += double (samples[static_cast<std::size_t> (i)]) * samples[static_cast<std::size_t> (i)];
    return sum;
}

void engineTests()
{
    const auto neutral = tail (true, 0, 12000.0);
    const auto lowCut = tail (true, -36, 12000.0);
    const auto highCut = tail (false, -6, 12000.0);
    const double neutralEnergy = energy (neutral, 0.3, 0.6);
    const double lowRatio = energy (lowCut, 0.3, 0.6) / neutralEnergy;
    const double highRatio = energy (highCut, 0.3, 0.6) / neutralEnergy;
    std::printf ("12 kHz tail energy / neutral, 0.3-0.6 s: LF -36 dB %.6f, HF -6 dB %.6f\n",
                 lowRatio, highRatio);
    expect (neutralEnergy > 1.0e-8, "integration probe excites an audible reverb tail");
    expect (lowRatio > 0.4, "LF damping preserves the upper-band reverb tail");
    expect (highRatio < 0.007, "HF damping removes upper-band feedback instead of leaking dry treble");

    const auto neutralOtherFrequency = tail (false, 0, 12000.0);
    expect (neutral == neutralOtherFrequency, "both neutral shelf modes produce identical complete audio");
    const auto fragmented = tail (true, -36, 12000.0, 17);
    const double fragmentedEnergy = energy (fragmented, 0.3, 0.6);
    std::printf ("Fragmented tail energy ratio %.9f\n", fragmentedEnergy / energy (lowCut, 0.3, 0.6));
    expect (std::abs (fragmentedEnergy / energy (lowCut, 0.3, 0.6) - 1.0) < 1.0e-6,
            "upper-band damping remains consistent across process block sizes");
    expect (std::all_of (lowCut.begin(), lowCut.end(),
                         [] (float value) { return std::isfinite (value); }),
            "full reverb tail remains finite");
}
} // namespace

int main()
{
    transferTests();
    frequencyEditTests();
    engineTests();
    std::printf ("Reverb damping: %d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
