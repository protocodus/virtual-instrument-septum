// Published SH-201 measurements (one-page table, dated 13 January 2021):
// https://www.deepsonic.ch/deep/docs_misc/deepsonic_analytics_-_envelope_lfo_speed.pdf
// Measure modulation periods in rendered audio, independently of the rate
// mapping implementation. This checks endpoint adoption, not the unpublished
// intermediate control table or the source's measurement accuracy.

#include "DSP/SeptumEngine.h"
#include "DSP/SeptumPresets.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

namespace
{
int checks = 0, failures = 0;

void expect (bool ok, const std::string& label)
{
    ++checks;
    if (! ok)
    {
        ++failures;
        std::fprintf (stderr, "FAIL: %s\n", label.c_str());
    }
}

// A square LFO alternately mutes and opens one clean sine oscillator. The
// periods between audible rising edges survive output-filter/transport delay.
// Energy windows suppress the carrier; no LFO state or mapping helper is read.
double audiblePeriod (double sampleRate, int rawRate, bool second, bool keyed,
                      bool synced, double seconds)
{
    auto patch = septum::initPatch();
    patch.tempo = 120;
    patch.delayOn = patch.reverbOn = false;
    auto& tone = patch.upper;
    tone.osc1.wave = septum::Waveform::Sine;
    tone.balance = -63;
    tone.filterType = septum::FilterType::Bypass;
    tone.ampEnvAttack = tone.ampEnvDecay = tone.ampEnvRelease = 0;
    tone.ampEnvSustain = 127;
    tone.level = 28;
    tone.levelVelocitySens = 0;
    tone.lfo1.depth1 = tone.lfo1.depth2 = 0;
    tone.lfo2.depth1 = tone.lfo2.depth2 = 0;
    auto& lfo = second ? tone.lfo2 : tone.lfo1;
    lfo.shape = septum::LfoShape::Sqr;
    lfo.rate = rawRate;
    lfo.keyTrigger = keyed;
    lfo.fadeTime = 0;
    lfo.tempoSync = synced;
    lfo.tempoSyncNote = 11; // documented quarter note: 0.5 seconds at 120 BPM
    lfo.destination2 = septum::LfoDest2::Amp;
    lfo.depth2 = 63;

    septum::Engine engine;
    engine.prepare (sampleRate, 256);
    engine.setPatch (patch);
    std::array<float, 256> left {}, right {};
    // Exercise a free-running phase that is distinct from key-triggered zero.
    for (int n = static_cast<int> (sampleRate * 0.317); n > 0;)
    {
        const int block = std::min (256, n);
        engine.process (left.data(), right.data(), block);
        n -= block;
    }
    engine.noteOn (93, 100); // A6 carrier, 1760 Hz
    const int windowSamples = static_cast<int> (std::round (sampleRate * 0.001));
    const double windowSeconds = windowSamples / sampleRate;
    std::vector<double> energy;
    double sum = 0.0;
    int inWindow = 0;
    bool finite = true;
    for (int n = static_cast<int> (std::ceil (seconds * sampleRate)); n > 0;)
    {
        const int block = std::min (256, n);
        engine.process (left.data(), right.data(), block);
        for (int i = 0; i < block; ++i)
        {
            const double x = left[static_cast<std::size_t> (i)];
            finite = finite && std::isfinite (x);
            sum += x * x;
            if (++inWindow == windowSamples)
            {
                energy.push_back (sum / windowSamples);
                sum = 0.0;
                inWindow = 0;
            }
        }
        n -= block;
    }
    const double high = *std::max_element (energy.begin(), energy.end());
    expect (finite && high > 1.0e-8, "period probe produces finite audible audio");
    const double threshold = high * 0.3;
    std::vector<double> edges;
    for (std::size_t i = 1; i < energy.size(); ++i)
        if (energy[i - 1] < threshold && energy[i] >= threshold
            && i * windowSeconds > 0.1)
        {
            const double fraction = (threshold - energy[i - 1]) / (energy[i] - energy[i - 1]);
            edges.push_back ((static_cast<double> (i) - 1.0 + fraction) * windowSeconds);
        }
    if (edges.size() < 2)
        return -1.0;
    return (edges.back() - edges.front()) / static_cast<double> (edges.size() - 1);
}
}

int main()
{
    for (const double sr : { 44100.0, 48000.0, 96000.0 })
        for (const bool second : { false, true })
            for (const bool keyed : { false, true })
                for (const int raw : { 0, 127 })
                {
                    const double expected = raw == 0 ? 20.59 : 0.04022;
                    const double actual = audiblePeriod (sr, raw, second, keyed, false,
                                                         raw == 0 ? 48.0 : 0.6);
                    const std::string label = "LFO" + std::to_string (second ? 2 : 1)
                        + " keyed=" + std::to_string (keyed) + " raw=" + std::to_string (raw)
                        + " sr=" + std::to_string (sr);
                    expect (std::abs (actual - expected) < 0.002,
                            label + " measured period=" + std::to_string (actual));
                    std::printf ("%s period=%.8f s\n", label.c_str(), actual);
                }

    // The free-rate endpoint change must not affect tempo-synchronized LFOs.
    for (const bool second : { false, true })
        for (const bool keyed : { false, true })
            for (const int raw : { 0, 127 })
            {
                const double actual = audiblePeriod (48000.0, raw, second, keyed, true, 1.6);
                expect (std::abs (actual - 0.5) < 0.002,
                        "tempo sync retains quarter-note period at both free-rate endpoints");
            }
    std::printf ("%d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
