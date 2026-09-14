// Deterministic malformed-parameter and audio-input stress. Run this executable
// under ASan/UBSan as well as in the ordinary test suite.
#include "DSP/SeptumEngine.h"

#include <algorithm>
#include <array>
#include <bit>
#include <chrono>
#include <climits>
#include <cmath>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <new>
#include <limits>

namespace allocationAudit
{
bool active = false;
std::size_t count = 0;
}

// Engine vectors use ordinary alignment. Audit render/note/patch operations
// after preparation without adding instrumentation to production DSP.
void* operator new (std::size_t size)
{
    if (allocationAudit::active) ++allocationAudit::count;
    if (void* memory = std::malloc (std::max (std::size_t { 1 }, size))) return memory;
    throw std::bad_alloc {};
}
void* operator new[] (std::size_t size) { return ::operator new (size); }
void operator delete (void* p) noexcept { std::free (p); }
void operator delete[] (void* p) noexcept { std::free (p); }
void operator delete (void* p, std::size_t) noexcept { std::free (p); }
void operator delete[] (void* p, std::size_t) noexcept { std::free (p); }

namespace
{
int failures = 0;
void expect (bool ok, const char* message)
{
    if (! ok) { ++failures; std::fprintf (stderr, "FAIL: %s\n", message); }
}

struct Random
{
    std::uint32_t state { 0x71f3a2b9u };
    std::uint32_t next() noexcept
    {
        state ^= state << 13; state ^= state >> 17; state ^= state << 5;
        return state;
    }
    int raw() noexcept
    {
        const auto choice = next();
        if ((choice & 15u) == 0) return INT_MIN;
        if ((choice & 15u) == 1) return INT_MAX;
        return static_cast<int> (choice % 512u) - 192;
    }
    template <typename T> T enumeration (int count) noexcept
    {
        return static_cast<T> ((next() & 7u) == 0 ? raw()
                                                    : static_cast<int> (next() % count));
    }
    bool flag() noexcept { return (next() & 1u) != 0; }
};

void randomise (septum::TonePatch& t, Random& r)
{
    for (auto* o : { &t.osc1, &t.osc2 })
    {
        o->wave = r.enumeration<septum::Waveform> (9); o->pitchWide = r.flag();
        for (auto member : { &septum::OscParams::coarse, &septum::OscParams::fine,
                            &septum::OscParams::pulseWidth, &septum::OscParams::pitchEnvDepth })
            o->*member = r.raw();
    }
    for (auto* lfo : { &t.lfo1, &t.lfo2 })
    {
        lfo->shape = r.enumeration<septum::LfoShape> (7);
        lfo->destination1 = r.enumeration<septum::LfoDest1> (4);
        lfo->destination2 = r.enumeration<septum::LfoDest2> (3);
        lfo->tempoSync = r.flag(); lfo->keyTrigger = r.flag();
        for (auto member : { &septum::LfoParams::rate, &septum::LfoParams::tempoSyncNote,
                            &septum::LfoParams::fadeTime, &septum::LfoParams::depth1,
                            &septum::LfoParams::depth2 })
            lfo->*member = r.raw();
    }
    t.mixType = r.enumeration<septum::MixModType> (3);
    t.lowFreq = r.enumeration<septum::LowFreqMode> (3);
    t.filterType = r.enumeration<septum::FilterType> (4);
    t.filterSlope = r.enumeration<septum::FilterSlope> (2);
    t.mono = r.enumeration<septum::MonoMode> (3);
    t.overdrive = r.flag(); t.portamento = r.flag();
    for (auto member : { &septum::TonePatch::pitchEnvAttack, &septum::TonePatch::pitchEnvDecay,
        &septum::TonePatch::balance, &septum::TonePatch::cutoff, &septum::TonePatch::keyFollow,
        &septum::TonePatch::cutoffVelocitySens, &septum::TonePatch::resonance,
        &septum::TonePatch::filterEnvAttack, &septum::TonePatch::filterEnvDecay,
        &septum::TonePatch::filterEnvSustain, &septum::TonePatch::filterEnvRelease,
        &septum::TonePatch::filterEnvDepth, &septum::TonePatch::drive, &septum::TonePatch::level,
        &septum::TonePatch::levelVelocitySens, &septum::TonePatch::pan,
        &septum::TonePatch::ampEnvAttack, &septum::TonePatch::ampEnvDecay,
        &septum::TonePatch::ampEnvSustain, &septum::TonePatch::ampEnvRelease,
        &septum::TonePatch::delayDepth, &septum::TonePatch::reverbDepth,
        &septum::TonePatch::bendRange, &septum::TonePatch::octaveShift,
        &septum::TonePatch::portamentoTime })
        t.*member = r.raw();
}

septum::Patch randomPatch (Random& r)
{
    septum::Patch p;
    randomise (p.upper, r); randomise (p.lower, r);
    p.keyboardMode = r.enumeration<septum::KeyboardMode> (3);
    p.keyboardPart = r.enumeration<septum::KeyboardPart> (2);
    p.modulationAssign = r.enumeration<septum::ModulationAssign> (8);
    for (auto* d : { &p.modulationDestination, &p.pitchBendDestination,
                     &p.expressionDestination, &p.dBeamDestination })
        *d = r.enumeration<septum::ToneDestination> (3);
    p.dBeamAssign = r.enumeration<septum::DBeamAssign> (septum::dBeamAssignCount);
    p.dBeamPolarity = r.enumeration<septum::DBeamPolarity> (2);
    p.delayOn = r.flag(); p.reverbOn = r.flag();
    for (auto* value : { &p.patchLevel, &p.toneBalance, &p.tempo, &p.splitPoint,
        &p.delay.time, &p.delay.feedback, &p.delay.hfDamp, &p.delay.modulationRate,
        &p.delay.modulationDepth, &p.reverb.time, &p.reverb.preDelay, &p.reverb.size,
        &p.reverb.highCut, &p.reverb.density, &p.reverb.diffusion,
        &p.reverb.lfDampFrequency, &p.reverb.lfDampGain, &p.reverb.hfDampFrequency,
        &p.reverb.hfDampGain, &p.arpeggio.styleIndex, &p.arpeggio.endStep,
        &p.arpeggio.octaveRange, &p.arpeggio.accent, &p.arpeggio.velocity,
        &p.arpeggio.style.endStep })
        *value = r.raw();
    p.arpeggio.on = r.flag(); p.arpeggio.hold = r.flag();
    p.arpeggio.splitArpeggio = r.enumeration<septum::SplitArpeggio> (3);
    p.arpeggio.grid = r.enumeration<septum::ArpeggioGrid> (9);
    p.arpeggio.duration = r.enumeration<septum::ArpeggioDuration> (10);
    p.arpeggio.motif = r.enumeration<septum::ArpeggioMotif> (12);
    for (auto& n : p.arpeggio.style.originalNote) n = r.raw();
    for (auto& step : p.arpeggio.style.cells)
        for (auto& cell : step)
            cell = static_cast<signed char> (static_cast<int> (r.next() % 256u) - 128);
    return p;
}

void lifecycle()
{
    septum::Engine engine;
    std::array<float, 33> left {}, right {};
    left.fill (1); right.fill (1);
    engine.noteOn (60, 100);
    engine.process (left.data(), right.data(), 33);
    expect (std::all_of (left.begin(), left.end(), [] (float x) { return x == 0; }),
            "processing before prepare is silent");
    const double nan = std::numeric_limits<double>::quiet_NaN();
    const double inf = std::numeric_limits<double>::infinity();
    for (const double rate : { nan, inf, -inf, -1.0, 0.0, 8000.0, 44100.0,
                               192000.0, 768000.0, 1.0e300 })
    {
        engine.prepare (rate, INT_MAX);
        expect (std::isfinite (engine.sampleRate()) && engine.sampleRate() >= 8000
                && engine.sampleRate() <= 768000, "preparation bounds hostile sample rates");
        engine.noteOn (60, 100);
        engine.process (left.data(), right.data(), 33);
        expect (std::all_of (left.begin(), left.end(), [] (float x) { return std::isfinite (x); }),
                "hostile preparation renders finite audio");
    }
    engine.prepare (44100, INT_MIN);
    engine.process (nullptr, nullptr, 16);
    engine.process (left.data(), nullptr, 16);
    engine.process (nullptr, right.data(), 16);
    left.fill (7); right.fill (7);
    engine.process (left.data(), right.data(), INT_MIN);
    engine.process (left.data(), right.data(), 0);
    expect (left.front() == 7 && right.back() == 7, "nonpositive blocks leave buffers untouched");
    auto calibration = septum::Engine::defaultTimbreCalibration();
    expect (septum::TimbreCalibration::lookup (calibration.cutoffHz, nan)
            == calibration.cutoffHz.front(), "nonfinite table index is bounded");
    calibration.filterEnabled = true;
    calibration.cutoffHz[90] = nan;
    expect (! engine.setTimbreCalibration (calibration), "invalid calibration is rejected");
}

void nonfiniteControllersAndInput()
{
    septum::Engine subject, reference;
    for (auto* e : { &subject, &reference })
    {
        e->prepare (44100, 64);
        e->setMasterTuneHz (443); e->setPitchBend (.25); e->setModulation (.4);
        e->setExpression (.8); e->setPartLevel (.9); e->setPartPan (.3);
        e->noteOn (60, 100);
    }
    for (const double invalid : { std::numeric_limits<double>::quiet_NaN(),
                                 std::numeric_limits<double>::infinity(),
                                 -std::numeric_limits<double>::infinity() })
    {
        subject.setMasterTuneHz (invalid); subject.setPitchBend (invalid);
        subject.setModulation (invalid); subject.setExpression (invalid);
        subject.setPartLevel (invalid); subject.setPartPan (invalid);
    }
    std::array<float, 257> bad {}, clean {}, actualL {}, actualR {}, expectedL {}, expectedR {};
    const std::array<float, 8> inputs { 0, .5f, -1.0f, std::numeric_limits<float>::quiet_NaN(),
        std::numeric_limits<float>::infinity(), -std::numeric_limits<float>::infinity(),
        std::numeric_limits<float>::max(), -std::numeric_limits<float>::max() };
    for (std::size_t i = 0; i < bad.size(); ++i)
    {
        bad[i] = inputs[i % inputs.size()];
        clean[i] = std::isfinite (bad[i]) ? std::clamp (bad[i], -64.0f, 64.0f) : 0;
    }
    for (int repeat = 0; repeat < 16; ++repeat)
    {
        subject.process (actualL.data(), actualR.data(), 257, bad.data(), bad.data());
        reference.process (expectedL.data(), expectedR.data(), 257, clean.data(), clean.data());
        expect (actualL == expectedL && actualR == expectedR,
                "invalid controls preserve last value and bad input equals sanitized input");
        bad.fill (0); clean.fill (0);
    }
}

void parameterStress()
{
    Random r;
    std::uint64_t frames = 0;
    for (double rate : { 8000., 44100., 192000. })
    {
        septum::Engine engine;
        engine.prepare (rate, 1);
        std::array<float, 258> left {}, right {}, inputL {}, inputR {};
        allocationAudit::active = true;
        for (int iteration = 0; iteration < 2048; ++iteration)
        {
            if (iteration % 4 == 0)
            {
                engine.changePatch (randomPatch (r), r.flag());
                septum::ExternalInput input;
                input.inputVolume = r.raw(); input.cutoff = r.raw(); input.resonance = r.raw();
                input.centerCancel = r.flag(); input.filterOn = r.flag();
                input.type = r.enumeration<septum::AudioFilterType> (4);
                input.slope = r.enumeration<septum::FilterSlope> (2);
                engine.setExternalInput (input);
            }
            for (int event = 0; event < 8; ++event)
            {
                const int note = static_cast<int> (r.next() % 160u) - 16;
                switch (r.next() % 16u)
                {
                    case 0: engine.noteOff (note); break;
                    case 1: engine.noteOffDirect (note); break;
                    case 2: engine.setHold (r.flag()); break;
                    case 3: engine.setSostenuto (r.flag()); break;
                    case 4: engine.allNotesOff(); break;
                    case 5: engine.setPortamentoControl (r.raw()); break;
                    case 6: engine.setPitchBend (r.raw() / 127.0); break;
                    case 7: engine.setModulation (r.raw() / 127.0); break;
                    case 8: engine.setTempoClock (r.raw(), r.flag()); break;
                    case 9: engine.setPartPan (r.raw() / 127.0); break;
                    case 10: engine.setMasterKeyShift (r.raw()); break;
                    case 11: engine.setTranspose (r.raw()); break;
                    case 12: engine.setPartEnabled (r.flag(), r.flag()); break;
                    case 13: engine.noteOnDirect (note, r.raw()); break;
                    default: engine.noteOn (note, r.raw()); break;
                }
            }
            const int count = static_cast<int> (r.next() % 257u) + 1;
            for (int i = 0; i < count; ++i)
            {
                inputL[static_cast<std::size_t> (i)] = r.raw() / 127.0f;
                inputR[static_cast<std::size_t> (i)] = r.raw() / 127.0f;
            }
            left.fill (1234); right.fill (1234);
            engine.process (left.data(), right.data(), count, inputL.data(), inputR.data());
            expect (left[static_cast<std::size_t> (count)] == 1234
                    && right[static_cast<std::size_t> (count)] == 1234,
                    "irregular render block preserves buffer canary");
            for (int i = 0; i < count; ++i)
                if (! std::isfinite (left[static_cast<std::size_t> (i)])
                    || ! std::isfinite (right[static_cast<std::size_t> (i)])
                    || std::abs (left[static_cast<std::size_t> (i)]) > 1.3f
                    || std::abs (right[static_cast<std::size_t> (i)]) > 1.3f)
                {
                    allocationAudit::active = false;
                    expect (false, "random parameters and extreme input remain finite and limited");
                    return;
                }
            expect (engine.activeVoiceCount() <= septum::maxPolyphony,
                    "stress never exceeds voice pool");
            if (iteration % 127 == 0) engine.allSoundOff();
            frames += static_cast<unsigned> (count);
        }
        allocationAudit::active = false;
    }
    expect (allocationAudit::count == 0, "render, note events, panic and patch edits allocate no memory");
    std::printf ("Stress rendered %llu frames and 49152 control/note events\n",
                 static_cast<unsigned long long> (frames));
}

void performanceBenchmark()
{
    for (const int voices : { 0, 1, 10 })
        for (const double rate : { 44100., 96000. })
        {
            double best = std::numeric_limits<double>::max();
            std::uint64_t result = 0;
            for (int repeat = 0; repeat < 3; ++repeat)
            {
                septum::Engine engine;
                engine.prepare (rate, 256);
                septum::Patch patch;
                patch.upper.osc1.wave = patch.upper.osc2.wave = septum::Waveform::SuperSaw;
                patch.upper.osc1.pulseWidth = patch.upper.osc2.pulseWidth = 70;
                patch.upper.balance = 0;
                patch.upper.cutoff = 93;
                patch.upper.resonance = 65;
                patch.upper.level = 40;
                patch.delayOn = patch.reverbOn = true;
                patch.upper.delayDepth = patch.upper.reverbDepth = 35;
                engine.setPatch (patch);
                for (int n = 0; n < voices; ++n) engine.noteOn (48 + n, 100);
                std::array<float, 256> left {}, right {};
                std::uint64_t hash = 14695981039346656037ull;
                const auto start = std::chrono::steady_clock::now();
                for (int n = 0; n < static_cast<int> (rate * 2); n += 256)
                {
                    const int count = std::min (256, static_cast<int> (rate * 2) - n);
                    engine.process (left.data(), right.data(), count);
                    for (int i = 0; i < count; ++i)
                    {
                        hash ^= std::bit_cast<std::uint32_t> (left[static_cast<std::size_t> (i)]);
                        hash *= 1099511628211ull;
                        hash ^= std::bit_cast<std::uint32_t> (right[static_cast<std::size_t> (i)]);
                        hash *= 1099511628211ull;
                    }
                }
                const double elapsed = std::chrono::duration<double> (
                    std::chrono::steady_clock::now() - start).count();
                best = std::min (best, elapsed);
                result = hash;
            }
            std::printf ("voices=%d rate=%.0f realtime=%.5f hash=%016llx\n",
                         voices, rate, best / 2, static_cast<unsigned long long> (result));
        }
}

}

int main (int argc, char** argv)
{
    if (argc == 2 && std::strcmp (argv[1], "--benchmark") == 0)
    {
        performanceBenchmark();
        return 0;
    }
    lifecycle();
    nonfiniteControllersAndInput();
    parameterStress();
    std::printf ("Engine robustness: %d failure(s)\n", failures);
    return failures == 0 ? 0 : 1;
}
