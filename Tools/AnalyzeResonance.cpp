// Offline resonance audit. Build with analyze_resonance.py; its isolated copy
// of Engine.cpp counts state-limiter activity without changing the signal.
#include "DSP/SeptumEngine.h"
#include "DSP/SeptumPresets.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <string_view>
#include <vector>

unsigned long long septumAuditLimitHits[2] {};
double septumAuditLargestState[2] {};

namespace
{
constexpr double sampleRate = 48000.0;
constexpr double pi = 3.14159265358979323846;
struct Measurement
{
    double amplitude {}, rms {}, peak {}, earlyRms {};
    bool finite { true };
    std::array<unsigned long long, 2> limitHits {};
    std::array<double, 2> largestState {};
};

Measurement render (int resonance, int slope, septum::FilterType type,
                    double ratio, double inputLevel)
{
    septum::Patch patch = septum::initPatch();
    auto& tone = patch.upper;
    patch.patchLevel = 100;
    patch.delayOn = patch.reverbOn = false;
    tone.osc1.wave = septum::Waveform::ExtIn;
    tone.balance = -63;
    tone.filterType = type;
    tone.filterSlope = slope == 12 ? septum::FilterSlope::Db12
                                 : septum::FilterSlope::Db24;
    tone.cutoff = 64;
    tone.keyFollow = tone.cutoffVelocitySens = 0;
    tone.resonance = resonance;
    tone.filterEnvDepth = 0;
    // Attenuation is AFTER the filter, so it does not hide internal limiter
    // activation. It keeps the final safety limiter out of the measurement.
    tone.level = 25;
    tone.levelVelocitySens = 0;
    tone.overdrive = false;
    tone.ampEnvAttack = 0;
    tone.ampEnvSustain = 127;
    tone.delayDepth = tone.reverbDepth = 0;
    tone.lfo1.depth1 = tone.lfo1.depth2 = 0;
    tone.lfo2.depth1 = tone.lfo2.depth2 = 0;
    septum::Engine engine;
    engine.prepare (sampleRate, 256);
    engine.setPatch (patch);
    septum::ExternalInput input;
    input.inputVolume = 127;
    input.filterOn = false;
    engine.setExternalInput (input);
    engine.reset();
    engine.noteOn (60, 127);
    for (int stage = 0; stage < 2; ++stage)
    {
        septumAuditLimitHits[stage] = 0;
        septumAuditLargestState[stage] = 0.0;
    }

    constexpr int total = 96000, from = 48000;
    const double fc = septum::mapping::cutoffHz (64);
    const double f = sampleRate / pi
                     * std::atan (std::tan (pi * fc / sampleRate) * ratio);
    std::vector<float> source (total), left (total), right (total);
    for (int i = 0; i < total; ++i)
        source[static_cast<std::size_t> (i)] =
            static_cast<float> (inputLevel * std::sin (2 * pi * f * i / sampleRate));
    for (int i = 0; i < total; i += 256)
        engine.process (left.data() + i, right.data() + i, std::min (256, total - i),
                        source.data() + i, source.data() + i);

    Measurement result;
    double ys = 0, yc = 0, ss = 0, cc = 0, sc = 0, energy = 0, earlyEnergy = 0;
    for (int i = 0; i < total; ++i)
    {
        const double y = left[static_cast<std::size_t> (i)];
        result.finite &= std::isfinite (y)
                         && std::isfinite (right[static_cast<std::size_t> (i)]);
        result.peak = std::max (result.peak, std::abs (y));
        if (i < from)
            continue;
        const double s = std::sin (2 * pi * f * i / sampleRate);
        const double c = std::cos (2 * pi * f * i / sampleRate);
        ys += y * s;
        yc += y * c;
        ss += s * s;
        cc += c * c;
        sc += s * c;
        energy += y * y;
        if (i < from + (total - from) / 2)
            earlyEnergy += y * y;
    }
    const double det = ss * cc - sc * sc;
    result.amplitude = std::hypot ((ys * cc - yc * sc) / det,
                                   (yc * ss - ys * sc) / det);
    result.rms = std::sqrt (energy / (total - from));
    result.earlyRms = std::sqrt (earlyEnergy / ((total - from) / 2));
    for (int stage = 0; stage < 2; ++stage)
    {
        result.limitHits[static_cast<std::size_t> (stage)] = septumAuditLimitHits[stage];
        result.largestState[static_cast<std::size_t> (stage)] =
            septumAuditLargestState[stage];
    }
    return result;
}
}

int main (int argc, char** argv)
{
    if (argc != 2 || (std::string_view (argv[1]) != "--transfer"
                      && std::string_view (argv[1]) != "--sweep"))
    {
        std::fputs ("Usage: AnalyzeResonance --transfer|--sweep\n", stderr);
        return 2;
    }
    if (std::string_view (argv[1]) == "--transfer")
    {
        std::puts ("resonance,slope,frequency_ratio,input_amplitude,gain_db,theory_db,error_db,output_peak,stage1_limit_hits,stage2_limit_hits");
        for (int resonance : { 31, 44, 64, 100, 110, 118, 120 })
            for (int slope : { 12, 24 })
                for (double ratio : { 0.75, 1.0 })
                    for (double level : { 0.001, 1.0 })
                    {
                        const auto y = render (resonance, slope, septum::FilterType::Lpf,
                                               ratio, level);
                        const auto base = render (resonance, slope,
                                                  septum::FilterType::Bypass, ratio, level);
                        // This reference is specifically the production, fixed
                        // second-stage model. Candidate deviations are expected.
                        const double k = septum::mapping::resonanceDamping (resonance);
                        double h = 1 / std::hypot (1 - ratio * ratio, k * ratio);
                        if (slope == 24)
                            h /= std::hypot (1 - ratio * ratio, 1.2 * ratio);
                        const double db = 20 * std::log10 (y.amplitude / base.amplitude);
                        const double theory = 20 * std::log10 (h);
                        std::printf ("%d,%d,%.2f,%.3f,%.9f,%.9f,%.9f,%.9f,%llu,%llu\n",
                                     resonance, slope, ratio, level, db, theory, db - theory,
                                     y.peak, y.limitHits[0], y.limitHits[1]);
                    }
        return 0;
    }
    std::puts ("type,slope,resonance,input_amplitude,rms,early_rms,output_peak,fundamental_amplitude,finite,stage1_limit_hits,stage2_limit_hits,stage1_max_prelimit,stage2_max_prelimit");
    for (auto type : { septum::FilterType::Lpf, septum::FilterType::Hpf,
                       septum::FilterType::Bpf })
        for (int slope : { 12, 24 })
            for (double level : { 0.001, 1.0 })
                for (int resonance = 0; resonance < 128; ++resonance)
                {
                    const auto y = render (resonance, slope, type, 1.0, level);
                    const char* name = type == septum::FilterType::Lpf ? "LPF"
                                       : type == septum::FilterType::Hpf ? "HPF" : "BPF";
                    std::printf ("%s,%d,%d,%.3f,%.12g,%.12g,%.12g,%.12g,%d,%llu,%llu,%.12g,%.12g\n",
                                 name, slope, resonance, level, y.rms, y.earlyRms, y.peak,
                                 y.amplitude, y.finite ? 1 : 0, y.limitHits[0], y.limitHits[1],
                                 y.largestState[0], y.largestState[1]);
                }
}
