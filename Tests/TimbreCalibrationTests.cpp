#include "DSP/SeptumEngine.h"
#include <algorithm>
#include <cmath>
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
} // namespace
int main()
{
    filterTests();
    envelopeTests();
    std::printf ("Timbre calibration: %d checks, %d failures\n", checks, failures);
    return failures != 0;
}
