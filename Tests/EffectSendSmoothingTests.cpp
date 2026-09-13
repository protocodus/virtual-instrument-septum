// These tests inspect the actual dry/send buses, before the shared effects
// obscure a one-sample control discontinuity. The DSP headers are included
// first so the access shim cannot alter standard-library declarations.
#include "DSP/SeptumPatch.h"
#include "DSP/AnalogInput.h"
#include "DSP/AnalogOutput.h"
#include "DSP/ReverbDamping.h"
#include "DSP/ReverbReadHeads.h"
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <vector>
#if defined (__clang__)
 #pragma clang diagnostic push
 #pragma clang diagnostic ignored "-Wkeyword-macro"
#endif
#define private public
#include "DSP/SeptumEngine.h"
#undef private
#if defined (__clang__)
 #pragma clang diagnostic pop
#endif

namespace {
int checks = 0, failures = 0;
double largestSendStep = 0, largestBalanceStep = 0, largestSplitError = 0;
void expect (bool pass, const char* message)
{
    ++checks;
    if (! pass) { ++failures; std::fprintf (stderr, "FAIL: %s\n", message); }
}
struct Frame { double dry, delay, reverb, output; };
Frame frame (septum::Engine& engine)
{
    float l {}, r {};
    engine.process (&l, &r, 1);
    return {engine.dryL_[0], engine.sendDelayL_[0], engine.sendReverbL_[0], l};
}
void run (septum::Engine& engine, int n)
{
    std::array<float, 256> l {}, r {};
    while (n > 0) { const int k = std::min (n, 256); engine.process (l.data(), r.data(), k); n -= k; }
}
septum::Patch fixture (bool lower = false)
{
    septum::Patch patch;
    patch.keyboardPart = lower ? septum::KeyboardPart::Lower : septum::KeyboardPart::Upper;
    patch.delayOn = patch.reverbOn = false;
    patch.patchLevel = 127;
    for (auto* tone : {&patch.upper, &patch.lower})
    {
        tone->osc1.wave = tone->osc2.wave = septum::Waveform::Sine;
        tone->balance = -63;
        tone->filterType = septum::FilterType::Bypass;
        tone->ampEnvAttack = tone->ampEnvDecay = 0;
        tone->ampEnvSustain = 127;
        tone->ampEnvRelease = 16;
        tone->levelVelocitySens = 0;
        tone->delayDepth = tone->reverbDepth = 0;
    }
    return patch;
}
void init (septum::Engine& engine, const septum::Patch& patch, double rate)
{
    engine.prepare (rate, 256); engine.setPatch (patch); engine.reset(); engine.noteOn (60, 100);
}
double sendRatio (const Frame& f) { return std::abs (f.dry) > 1e-8 ? f.delay / f.dry : 0; }
void testSteps (double rate, bool lower)
{
    auto patch = fixture (lower);
    septum::Engine changed, reference;
    init (changed, patch, rate); init (reference, patch, rate);
    run (changed, 4096); run (reference, 4096);
    auto& tone = lower ? patch.lower : patch.upper;
    tone.delayDepth = tone.reverbDepth = 127;
    changed.setPatch (patch);
    auto a = frame (changed), b = frame (reference);
    const double sendStep = sendRatio (a);
    largestSendStep = std::max (largestSendStep, sendStep);
    expect (std::abs (a.dry) > 1e-4, "send step fixture has an audible nonzero dry sample");
    expect (sendStep > 0 && sendStep < .012, "full send jump begins below 1.2 percent gain");
    expect (a.dry == b.dry && a.delay == a.reverb, "send automation leaves dry audio unchanged and treats both sends equally");
    run (changed, static_cast<int> (rate * .05)); run (reference, static_cast<int> (rate * .05));
    a = frame (changed); (void) frame (reference);
    expect (std::abs (sendRatio (a) - 1) < 2e-6, "send reaches the existing unity endpoint after settling");
    tone.delayDepth = tone.reverbDepth = 0; changed.setPatch (patch);
    a = frame (changed); (void) frame (reference);
    expect (sendRatio (a) > .988 && sendRatio (a) < 1, "send fade to zero has no first-sample discontinuity");
    run (changed, static_cast<int> (rate * .05)); run (reference, static_cast<int> (rate * .05));
    a = frame (changed); (void) frame (reference);
    expect (std::abs (sendRatio (a)) < 2e-6, "send settles to silence");

    patch.toneBalance = lower ? 63 : -63; changed.setPatch (patch);
    a = frame (changed); b = frame (reference);
    const double balanceStep = std::abs (a.dry - b.dry) / std::abs (b.dry);
    largestBalanceStep = std::max (largestBalanceStep, balanceStep);
    expect (std::abs (b.dry) > 1e-4, "tone balance fixture has a nonzero reference sample");
    expect (balanceStep > 0 && balanceStep < .012, "tone balance mute begins below 1.2 percent dry gain change");
    run (changed, static_cast<int> (rate * .05)); run (reference, static_cast<int> (rate * .05));
    a = frame (changed); b = frame (reference);
    expect (std::abs (a.dry / b.dry) < 2e-6, "tone balance reaches its existing mute endpoint");
    patch.toneBalance = 0; changed.setPatch (patch);
    a = frame (changed); b = frame (reference);
    expect (a.dry / b.dry > 0 && a.dry / b.dry < .012, "tone balance unmute starts continuously");
}
void testFreshAndReset (double rate, bool lower)
{
    for (int depth : {0, 1, 63, 127})
        for (int balance : {-63, -31, 0, 31, 63})
        {
            auto patch = fixture (lower), unity = patch;
            auto& tone = lower ? patch.lower : patch.upper;
            tone.delayDepth = depth; tone.reverbDepth = 127 - depth;
            patch.toneBalance = balance;
            septum::Engine actual, reference;
            init (actual, patch, rate); init (reference, unity, rate);
            for (int cycle = 0; cycle < 3; ++cycle)
            {
                if (cycle == 1) { actual.reset(); reference.reset(); actual.noteOn (60, 100); reference.noteOn (60, 100); }
                if (cycle == 2) { actual.allSoundOff(); reference.allSoundOff(); actual.noteOn (60, 100); reference.noteOn (60, 100); }
                double dryError = 0, delayError = 0, reverbError = 0, referencePeak = 0;
                const double gain = septum::mapping::balanceLegGain (balance, lower);
                for (int i = 0; i < 192; ++i)
                {
                    const auto a = frame (actual), b = frame (reference);
                    referencePeak = std::max (referencePeak, std::abs (b.dry));
                    dryError = std::max (dryError, std::abs (a.dry - b.dry * gain));
                    delayError = std::max (delayError, std::abs (a.delay - a.dry * depth / 127.0));
                    reverbError = std::max (reverbError, std::abs (a.reverb - a.dry * (127-depth) / 127.0));
                }
                expect (referencePeak > .001 && dryError < 2e-8, "fresh, reset and panic-reused voices start at exact tone balance without extra attack fade");
                expect (delayError < 2e-8 && reverbError < 2e-8, "static sends preserve their existing raw-value laws including zero and maximum");
            }
        }
}
void testReuseAndRemain (double rate)
{
    for (auto mode : {septum::MonoMode::Poly, septum::MonoMode::Solo, septum::MonoMode::SoloLegato})
    {
        auto patch = fixture(); patch.upper.mono = mode;
        septum::Engine engine, unity; init (engine, patch, rate); init (unity, patch, rate);
        if (mode == septum::MonoMode::Poly)
            for (int note = 61; note < 70; ++note) { engine.noteOn (note, 100); unity.noteOn (note, 100); }
        run (engine, 4096); run (unity, 4096);
        patch.upper.delayDepth = patch.upper.reverbDepth = 127;
        patch.toneBalance = -63; engine.setPatch (patch);
        run (engine, 12); run (unity, 12);
        const auto before = frame (engine), beforeUnity = frame (unity);
        engine.noteOn (72, 100); unity.noteOn (72, 100); // steals a live slot in all three modes
        const auto a = frame (engine), b = frame (unity);
        expect (std::abs (beforeUnity.dry) > 1e-6 && std::abs (b.dry) > 1e-6
                    && a.dry / b.dry > .8
                    && std::abs (a.dry / b.dry - before.dry / beforeUnity.dry) < .012,
                "poly stealing, SOLO retrigger and LEGATO preserve a moving tone balance gain");
        expect (std::abs (a.dry) > 1e-6 && sendRatio (a) > 0 && sendRatio (a) < .15,
                "poly stealing, SOLO retrigger and LEGATO preserve a moving send gain");
    }
    auto patch = fixture();
    septum::Engine retained, reference;
    init (retained, patch, rate); init (reference, patch, rate);
    run (retained, 4096); run (reference, 4096);
    patch.upper.delayDepth = 127; patch.upper.reverbDepth = 99; patch.toneBalance = -31;
    retained.setPatch (patch); reference.setPatch (patch);
    run (retained, 17); run (reference, 17);
    retained.changePatch (fixture(), true);
    double error = 0;
    for (int i = 0; i < 1024; ++i)
    {
        const auto a = frame (retained), b = frame (reference);
        error = std::max ({error, std::abs (a.dry-b.dry), std::abs (a.delay-b.delay), std::abs (a.reverb-b.reverb)});
    }
    expect (error < 2e-8, "Patch Remain preserves both current smoothing states and old-patch targets");
}
void testAutomation (double rate)
{
    auto patch = fixture();
    septum::Engine whole, split;
    init (whole, patch, rate); init (split, patch, rate);
    run (whole, 4096); run (split, 4096);
    std::uint32_t rng = 9419;
    bool bounded = true;
    for (int event = 0; event < 100; ++event)
    {
        rng = rng * 1664525u + 1013904223u;
        patch.upper.delayDepth = static_cast<int> (rng & 127u);
        patch.upper.reverbDepth = static_cast<int> ((rng >> 8) & 127u);
        patch.toneBalance = static_cast<int> ((rng >> 16) % 127u) - 63;
        whole.setPatch (patch); split.setPatch (patch);
        std::array<float, 53> wl {}, wr {}, sl {}, sr {};
        whole.process (wl.data(), wr.data(), 53);
        int offset = 0;
        for (int n : {1, 3, 7, 13, 29})
        { split.process (sl.data() + offset, sr.data() + offset, n); offset += n; }
        for (std::size_t i = 0; i < wl.size(); ++i)
            largestSplitError = std::max ({largestSplitError, std::abs (double(wl[i])-sl[i]), std::abs (double(wr[i])-sr[i])});
    }
    expect (largestSplitError < 2e-7, "send and balance automation output is invariant under irregular block splitting");
    init (whole, fixture(), rate); run (whole, 4096);
    for (int i = 0; i < 3000; ++i)
    {
        patch.upper.delayDepth = (i & 1) ? 0 : 127;
        patch.upper.reverbDepth = (i % 3) ? 0 : 127;
        patch.toneBalance = (i & 1) ? -63 : 63;
        whole.setPatch (patch);
        const auto a = frame (whole);
        bounded = bounded && std::isfinite (a.output) && std::abs (a.output) < 1
            && std::isfinite (a.dry) && std::abs (a.delay) <= std::abs (a.dry) + 1e-8
            && std::abs (a.reverb) <= std::abs (a.dry) + 1e-8;
    }
    expect (bounded, "sample-dense extreme automation remains finite with convex bounded send gains");
}
}
int main()
{
    for (double rate : {44100.0, 48000.0, 96000.0})
    {
        for (bool lower : {false, true}) { testSteps (rate, lower); testFreshAndReset (rate, lower); }
        testReuseAndRemain (rate); testAutomation (rate);
    }
    std::printf ("%d checks, %d failures; max first send step %.9g, balance step %.9g, block split error %.9g\n",
                 checks, failures, largestSendStep, largestBalanceStep, largestSplitError);
    return failures == 0 ? 0 : 1;
}
