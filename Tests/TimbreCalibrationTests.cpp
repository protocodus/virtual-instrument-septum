#include "DSP/SeptumEngine.h"
#include <algorithm>
#include <cmath>
#include <complex>
#include <cstdio>
#include <limits>
#include <vector>

namespace {
int checks = 0, failures = 0;
void expect (bool pass, const char* message)
{ ++checks; if (! pass) { ++failures; std::fprintf (stderr, "FAIL: %s\n", message); } }
septum::Patch patch()
{
    septum::Patch p;
    p.upper.osc1.wave = septum::Waveform::Saw;
    p.upper.balance = -63; p.upper.cutoff = 58; p.upper.resonance = 40;
    p.upper.filterEnvDepth = 0; p.upper.levelVelocitySens = 0;
    p.upper.ampEnvAttack = p.upper.ampEnvDecay = 0; p.upper.ampEnvSustain = 127;
    p.delayOn = p.reverbOn = false;
    return p;
}
std::vector<float> render (septum::Engine& engine, int count = 8192)
{
    std::vector<float> l (static_cast<std::size_t> (count)), r (l.size());
    engine.process (l.data(), r.data(), count);
    expect (std::all_of (l.begin(), l.end(), [] (float x) { return std::isfinite (x); }), "finite audio");
    return l;
}
double difference (const std::vector<float>& a, const std::vector<float>& b)
{
    double error = 0;
    for (std::size_t i = 0; i < a.size(); ++i) error = std::max (error, std::abs (double (a[i]) - b[i]));
    return error;
}
void prepare (septum::Engine& e, double rate, const septum::Patch& p)
{ e.prepare (rate, 256); e.setPatch (p); e.reset(); e.noteOn (57, 100); }
void filterTests()
{
    for (double rate : { 44100., 48000., 96000. })
        for (auto slope : { septum::FilterSlope::Db12, septum::FilterSlope::Db24 })
        {
            auto p = patch(); p.upper.filterSlope = slope;
            septum::Engine base, identity, candidate, reference;
            auto c = septum::Engine::defaultTimbreCalibration(); c.filterEnabled = true;
            expect (identity.setTimbreCalibration (c), "valid default filter model");
            prepare (base, rate, p); prepare (identity, rate, p);
            expect (difference (render (base), render (identity)) == 0, "static default filter table equals production equations");
            p.upper.resonance = 100; base.setPatch (p); identity.setPatch (p);
            expect (difference (render (base), render (identity)) == 0, "cutoff-only model retains original resonance coupling during automation");
            p.upper.resonance = 40;
            // Shift the full cutoff and damping curves by twelve control steps.
            // Compare actual audio against independently selecting those controls.
            for (std::size_t i = 0; i < 128; ++i)
            {
                const int raw = std::min (127, static_cast<int> (i) + 12);
                c.cutoffHz[i] = septum::mapping::cutoffHz (raw);
                c.resonanceDamping[i] = std::max (-0.04, septum::mapping::voiceResonanceDamping (raw));
                c.secondStageDamping[i] = septum::mapping::voiceSecondStageDamping (c.resonanceDamping[i]);
            }
            expect (candidate.setTimbreCalibration (c), "valid shifted model");
            prepare (candidate, rate, p);
            p.upper.cutoff += 12; p.upper.resonance += 12;
            prepare (reference, rate, p);
            expect (difference (render (candidate), render (reference)) < 1e-8, "calibrated poles and cutoff match independently changed patch");
            auto bad = c; bad.cutoffHz[64] = std::numeric_limits<double>::quiet_NaN();
            expect (! candidate.setTimbreCalibration (bad), "reject nonfinite without clearing active voice");
            expect (candidate.activeVoiceCount() == 1, "invalid installation is atomic");
            expect (difference (render (candidate), render (reference)) < 1e-8, "invalid profile leaves state and audio unchanged");
            expect (candidate.setTimbreCalibration (c) && candidate.activeVoiceCount() == 0, "valid model switch clears old voices");
            bad = c; bad.cutoffHz[64] = 4; expect (! bad.valid(), "reject unsafe cutoff");
            bad = c; bad.resonanceDamping[64] = -1; expect (! bad.valid(), "reject unsafe feedback");
            bad = c; bad.secondStageDamping[64] = 0; expect (! bad.valid(), "reject autonomous second pole oscillation");
            // An explicitly supplied second-stage table is independently
            // active. Copy the shifted reference's k2 to verify that route too.
            c.secondStageIndependent = true;
            expect (candidate.setTimbreCalibration (c), "explicit second-pole table accepted");
            p.upper.cutoff -= 12; p.upper.resonance -= 12; prepare (candidate, rate, p);
            p.upper.cutoff += 12; p.upper.resonance += 12; prepare (reference, rate, p);
            expect (difference (render (candidate), render (reference)) < 1e-8, "independent second-pole table reaches reference response");
        }
}
void envelopeTests()
{
    for (double rate : { 44100., 48000., 96000. })
    {
        auto p = patch();
        p.upper.filterEnvAttack = 50; p.upper.filterEnvDecay = 61;
        p.upper.filterEnvSustain = 74; p.upper.filterEnvRelease = 61;
        p.upper.filterEnvDepth = 24; p.upper.ampEnvRelease = 100;
        septum::Engine base, identity, candidate, reference;
        auto c = septum::Engine::defaultTimbreCalibration(); c.envelopeEnabled = true;
        expect (identity.setTimbreCalibration (c), "valid envelope tables");
        prepare (base, rate, p); prepare (identity, rate, p);
        expect (difference (render (base), render (identity)) == 0, "default envelope tables preserve transient audio");
        base.noteOff (57); identity.noteOff (57);
        expect (difference (render (base), render (identity)) == 0, "default envelope tables preserve release audio");
        for (std::size_t i = 0; i < 128; ++i)
        {
            const int raw = std::min (127, static_cast<int> (i) + 10);
            c.attackSeconds[i] = septum::mapping::attackSeconds (raw);
            c.decaySeconds[i] = septum::mapping::filterDecaySeconds (raw);
            c.releaseSeconds[i] = septum::mapping::decaySeconds (raw);
            c.sustainLevel[i] = i == 0 ? 0 : raw / 127.0;
        }
        expect (candidate.setTimbreCalibration (c), "valid independent envelope timing and sustain curves");
        prepare (candidate, rate, p);
        p.upper.filterEnvAttack += 10; p.upper.filterEnvDecay += 10;
        p.upper.filterEnvSustain += 10; p.upper.filterEnvRelease += 10;
        prepare (reference, rate, p);
        expect (difference (render (candidate, 65536), render (reference, 65536)) == 0,
                "mapped attack, decay and sustain match independently edited patch");
        candidate.noteOff (57); reference.noteOff (57);
        expect (difference (render (candidate), render (reference)) == 0, "mapped release matches reference, amp timing unchanged");
        auto bad = c; bad.attackSeconds[50] = 0; expect (! bad.valid(), "reject zero time");
        bad = c; bad.sustainLevel[0] = 0.1; expect (! bad.valid(), "retain zero sustain endpoint");
        bad = c; bad.releaseSeconds[61] = 121; expect (! bad.valid(), "reject excessive release");
    }
}
void waveformTests()
{
    for (double rate : { 44100., 48000., 96000. })
        for (int wave = 0; wave < 5; ++wave)
        {
            auto p = patch(); p.upper.filterType = septum::FilterType::Bypass;
            p.upper.osc1.wave = static_cast<septum::Waveform> (wave);
            septum::Engine base, identity, inverted, shifted;
            auto c = septum::Engine::defaultTimbreCalibration(); c.wavesEnabled = true;
            expect (identity.setTimbreCalibration (c), "valid waveform identity");
            prepare (base, rate, p); prepare (identity, rate, p);
            const auto original = render (base);
            expect (difference (original, render (identity)) == 0, "default wave convention preserves all five waveforms");
            c.waveGain[static_cast<std::size_t> (wave)] = -1;
            expect (inverted.setTimbreCalibration (c), "valid waveform polarity diagnostic");
            prepare (inverted, rate, p);
            auto negative = render (inverted);
            for (auto& x : negative) x = -x;
            expect (difference (original, negative) < 1e-8, "whole waveform including correction inverts exactly");
            c.waveGain[static_cast<std::size_t> (wave)] = 1;
            c.phaseCycles[static_cast<std::size_t> (wave)] = 0.5;
            expect (shifted.setTimbreCalibration (c), "valid half-cycle convention");
            prepare (shifted, rate, p);
            auto half = render (shifted);
            if (wave == 1 || wave == 3 || wave == 4)
            {
                for (auto& x : half) x = -x;
                expect (difference (original, half) < 1e-7, "symmetric waveform phase shift agrees with independent polarity control");
            }
            auto bad = c; bad.phaseCycles[0] = 1; expect (! bad.valid(), "reject unwrapped phase");
            bad = c; bad.pulseDuty[0] = 0; expect (! bad.valid(), "reject zero-width pulse");
        }
    auto p = patch(); p.upper.osc1.wave = septum::Waveform::PulseSquare; p.upper.osc1.pulseWidth = 40;
    septum::Engine custom, reference;
    auto c = septum::Engine::defaultTimbreCalibration(); c.wavesEnabled = true;
    for (std::size_t i = 0; i < 128; ++i) c.pulseDuty[i] = septum::mapping::pulseDuty (std::min (127, static_cast<int> (i) + 20));
    expect (custom.setTimbreCalibration (c), "valid PW curve");
    prepare (custom, 48000, p); p.upper.osc1.pulseWidth += 20; prepare (reference, 48000, p);
    expect (difference (render (custom), render (reference)) == 0, "PW table matches independently shifted control");
}
void superSawTests()
{
    for (double rate : { 44100., 48000., 96000. })
        for (auto mix : { septum::MixModType::Mix, septum::MixModType::Sync })
            for (int spread : { 0, 41, 115 })
            {
                auto p = patch(); p.upper.osc1.wave = septum::Waveform::SuperSaw;
                p.upper.osc2.wave = septum::Waveform::Sine; p.upper.osc2.coarse = 7;
                p.upper.mixType = mix; p.upper.osc1.pulseWidth = spread;
                septum::Engine base, identity, custom, reference;
                auto c = septum::Engine::defaultTimbreCalibration(); c.superSawEnabled = true;
                expect (identity.setTimbreCalibration (c), "valid default Super Saw including polynomial wiggle");
                prepare (base, rate, p); prepare (identity, rate, p);
                expect (difference (render (base), render (identity)) == 0, "default Super Saw preserves phase, gain, filter and sync");
                auto modulated = p;
                modulated.upper.lfo1.destination1 = septum::LfoDest1::Pw1;
                modulated.upper.lfo1.depth1 = 45; modulated.upper.lfo1.rate = 81;
                base.setPatch (modulated); identity.setPatch (modulated);
                expect (difference (render (base), render (identity)) == 0, "mix-only Super Saw profile retains fractional detune polynomial");
                for (std::size_t i = 0; i < 128; ++i)
                    c.superDetune[i] = septum::mapping::superSawDetuneAmount (std::min (127, static_cast<int> (i) + 12) / 127.0);
                c.superDetuneTableEnabled = true;
                expect (custom.setTimbreCalibration (c), "valid alternative detune curve");
                prepare (custom, rate, p); p.upper.osc1.pulseWidth += 12; prepare (reference, rate, p);
                expect (difference (render (custom), render (reference)) == 0, "detune table matches independent patch control including slave reset");
            }
    auto p = patch(); p.upper.osc1.wave = septum::Waveform::SuperSaw;
    p.upper.filterType = septum::FilterType::Bypass;
    septum::Engine low, high, silent;
    auto c = septum::Engine::defaultTimbreCalibration(); c.superSawEnabled = true;
    c.superSideGain.fill (0); c.superCenterGain.fill (1); c.superDetune.fill (0);
    c.superDetuneTableEnabled = true;
    expect (low.setTimbreCalibration (c), "isolated center saw");
    c.superHpfRatio = 2;
    expect (high.setTimbreCalibration (c), "pitch-tracked filter calibration");
    prepare (low, 48000, p); prepare (high, 48000, p);
    render (low, 48000); render (high, 48000);
    const auto a = render (low, 48000), b = render (high, 48000);
    const auto fundamental = [] (const std::vector<float>& values)
    {
        std::complex<double> sum {};
        for (std::size_t i = 0; i < values.size(); ++i)
            sum += double (values[i]) * std::polar (1.0, -2 * septum::mapping::pi * 220 * i / 48000.0);
        return std::abs (sum);
    };
    const double x = std::tan (septum::mapping::pi * 220 / 48000) / std::tan (septum::mapping::pi * 440 / 48000);
    const double predicted = (x * x / std::sqrt (1 + x * x * x * x)) * std::sqrt (2.0);
    expect (std::abs (fundamental (b) / fundamental (a) - predicted) < 1e-5,
            "tracked high-pass obeys independent Butterworth magnitude ratio");
    c.superCenterGain.fill (0); expect (silent.setTimbreCalibration (c), "zero center and side gains");
    prepare (silent, 48000, p);
    const auto zero = render (silent);
    expect (std::all_of (zero.begin(), zero.end(), [] (float v) { return v == 0; }), "independent center/side gains reach silence");
    auto bad = c; bad.superOffsets[3] = 0.1; expect (! bad.valid(), "keep sync center at nominal pitch");
    bad = c; bad.superHpfQ = 0; expect (! bad.valid(), "reject singular tracked filter");
    bad = c; bad.superOffsets[0] = -1; expect (! bad.valid(), "reject reverse/out-of-range oscillator offsets");
}
} // namespace
int main()
{
    filterTests();
    envelopeTests();
    waveformTests();
    superSawTests();
    std::printf ("Timbre calibration: %d checks, %d failures\n", checks, failures);
    return failures != 0;
}
