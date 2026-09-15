// Conditional hardware shape evidence:
// Docs/fidelity/dry-filter-calibration.md
// Render the complete engine and measure sine gain relative to BYPASS. The
// independent transfer expression checks that the fitted filter response
// reaches the audio path. It does not establish the unknown raw cutoff table.
#include "DSP/SeptumEngine.h"
#include "DSP/SeptumPresets.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <complex>
#include <cstdio>

namespace
{
double amplitude (double rate, int note, int resonance, bool fourPole, bool bypass)
{
    auto patch = septum::initPatch();
    patch.delayOn = patch.reverbOn = false;
    auto& tone = patch.upper;
    tone.osc1.wave = septum::Waveform::Sine;
    tone.balance = -63;
    tone.filterType = bypass ? septum::FilterType::Bypass : septum::FilterType::Lpf;
    tone.filterSlope = fourPole ? septum::FilterSlope::Db24 : septum::FilterSlope::Db12;
    tone.cutoff = 64;
    tone.resonance = resonance;
    tone.keyFollow = tone.cutoffVelocitySens = tone.filterEnvDepth = 0;
    tone.ampEnvAttack = tone.ampEnvDecay = tone.ampEnvRelease = 0;
    tone.ampEnvSustain = 127;
    tone.level = 20;
    tone.levelVelocitySens = 0;
    tone.lfo1.depth1 = tone.lfo1.depth2 = 0;
    tone.lfo2.depth1 = tone.lfo2.depth2 = 0;
    septum::Engine engine;
    engine.prepare (rate, 256);
    engine.setPatch (patch);
    engine.noteOn (note, 100);
    std::array<float, 256> left {}, right {};
    const int total = static_cast<int> (rate);
    double power = 0;
    for (int offset = 0; offset < total;)
    {
        const int n = std::min (256, total - offset);
        engine.process (left.data(), right.data(), n);
        for (int i = 0; i < n; ++i)
            if (offset + i >= total / 2)
                power += static_cast<double> (left[i]) * left[i];
        offset += n;
    }
    return std::sqrt (power / (total / 2));
}

double expectedGainDb (double rate, int note, double k, bool fourPole)
{
    const double pi = std::acos (-1.0);
    const double hz = 440.0 * std::exp2 ((note - 69) / 12.0);
    // Existing cutoff law is held fixed; this test targets filter shape.
    const double cutoff = 20.0 * std::exp2 (640.0 / 127.0);
    const double omega = std::tan (pi * hz / rate) / std::tan (pi * cutoff / rate);
    const std::complex<double> denominator (1.0 - omega * omega, k * omega);
    double magnitude = 1.0 / std::abs (denominator);
    if (fourPole)
        magnitude /= std::abs (std::complex<double> (1.0 - omega * omega,
                                                   std::clamp (k, 0.5, 1.2) * omega));
    return 20.0 * std::log10 (magnitude);
}
}

int main()
{
    int checks = 0, failures = 0;
    double worst = 0;
    // These are endpoint/previous-anchor constants, not calls to the mapping
    // under test. Integer-Hz notes give complete carrier cycles in each window.
    for (const double rate : { 44100.0, 48000.0, 96000.0 })
        for (const int note : { 57, 69, 81, 93 })
            for (const bool fourPole : { false, true })
                for (const int raw : { 0, 40 })
                {
                    const double k = raw == 0 ? 1.2 : 0.5591507918157866;
                    const double dry = amplitude (rate, note, raw, fourPole, true);
                    const double wet = amplitude (rate, note, raw, fourPole, false);
                    const double error = std::abs (20 * std::log10 (wet / dry)
                                                  - expectedGainDb (rate, note, k, fourPole));
                    worst = std::max (worst, error);
                    ++checks;
                    if (! std::isfinite (error) || error > 0.015)
                    {
                        ++failures;
                        std::fprintf (stderr, "FAIL: rate %.0f note %d LP%d raw%d: %.6f dB\n",
                                      rate, note, fourPole ? 24 : 12, raw, error);
                    }
                }
    std::printf ("Dry filter response: %d checks, %d failures; maximum error %.8f dB\n",
                 checks, failures, worst);
    return failures == 0 ? 0 : 1;
}
