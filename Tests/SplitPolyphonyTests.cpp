// SH-201 OM pp. 46-47, 74: DUAL layers two tones and halves note count;
// SPLIT selects one tone per key within the ten-voice physical pool.
// Per-part reservation is not specified; shared allocation is an inference.
#include "DSP/SeptumEngine.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>

namespace {
int checks = 0, failures = 0;
void expect (bool condition, const char* description)
{
    ++checks;
    if (! condition) { ++failures; std::fprintf (stderr, "FAIL: %s\n", description); }
}

septum::Patch patchFor (septum::KeyboardMode mode)
{
    septum::Patch patch;
    patch.keyboardMode = mode;
    patch.splitPoint = 60;
    patch.upper.osc1.wave = septum::Waveform::Sine;
    patch.upper.balance = -63;
    patch.upper.filterType = septum::FilterType::Bypass;
    patch.upper.ampEnvAttack = patch.upper.ampEnvDecay = 0;
    patch.upper.ampEnvSustain = 127;
    patch.upper.ampEnvRelease = 127;
    patch.upper.levelVelocitySens = 0;
    patch.lower = patch.upper;
    patch.delayOn = patch.reverbOn = false;
    return patch;
}

void process (septum::Engine& engine)
{
    std::array<float, 128> left {}, right {};
    engine.process (left.data(), right.data(), 128);
    expect (std::all_of (left.begin(), left.end(), [] (float value) {
                return std::isfinite (value); }), "split rendering is finite");
}
}

int main()
{
    for (double rate : {44100.0, 48000.0, 96000.0})
    {
        for (bool upper : {false, true})
        {
            septum::Engine engine;
            engine.prepare (rate, 128);
            engine.setPatch (patchFor (septum::KeyboardMode::Split));
            engine.reset();
            const int first = upper ? 60 : 40;
            for (int n = 0; n < 10; ++n)
                engine.noteOn (first + n, 100);
            process (engine);
            expect (engine.activeVoiceCount (upper) == 10,
                    "either SPLIT side can fill the ten-voice pool");
            expect (engine.activeVoiceCount (! upper) == 0,
                    "single-side SPLIT does not sound the opposite tone");
            engine.noteOn (first + 10, 100);
            expect (engine.activeVoiceCount() == 10,
                    "eleventh SPLIT note steals within the physical limit");

            // A released tail must give way to a new note on the other side.
            engine.noteOff (first + 1);
            engine.noteOn (upper ? 48 : 72, 100);
            expect (engine.activeVoiceCount (upper) == 9
                        && engine.activeVoiceCount (! upper) == 1,
                    "the other SPLIT side can reclaim a full shared pool");
            process (engine);
        }

        for (int lowerCount = 1; lowerCount < 10; ++lowerCount)
        {
            septum::Engine engine;
            engine.prepare (rate, 128);
            engine.setPatch (patchFor (septum::KeyboardMode::Split));
            engine.reset();
            for (int n = 0; n < lowerCount; ++n) engine.noteOn (40 + n, 100);
            for (int n = 0; n < 10 - lowerCount; ++n) engine.noteOn (60 + n, 100);
            expect (engine.activeVoiceCount (false) == lowerCount
                        && engine.activeVoiceCount (true) == 10 - lowerCount,
                    "unequal SPLIT chords share all ten physical voices");
        }

        septum::Engine dual;
        dual.prepare (rate, 128);
        dual.setPatch (patchFor (septum::KeyboardMode::Dual));
        dual.reset();
        for (int n = 0; n < 10; ++n) dual.noteOn (60 + n, 100);
        expect (dual.activeVoiceCount (true) == 5 && dual.activeVoiceCount (false) == 5,
                "DUAL keeps the documented five layered notes");
    }
    std::printf ("%d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
