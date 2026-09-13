// The keyboard's octave/transpose controls and the tone generator's tuning
// are distinct paths (SH-201 OM pp. 18, 68-69; MIDI 1.0 Appendix A-6).
#include "DSP/SeptumEngine.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <vector>

namespace {
int checks = 0, failures = 0;
double worstDirectDifference = 0.0;
void expect (bool pass, const char* text)
{ ++checks; if (! pass) { ++failures; std::fprintf (stderr, "FAIL: %s\n", text); } }
septum::Patch patchFor (bool lower, bool osc2)
{
    septum::Patch patch;
    patch.keyboardPart = lower ? septum::KeyboardPart::Lower : septum::KeyboardPart::Upper;
    auto& tone = lower ? patch.lower : patch.upper;
    tone.osc1.wave = tone.osc2.wave = septum::Waveform::Sine;
    tone.osc1.coarse = tone.osc2.coarse = 0;
    tone.osc1.fine = tone.osc2.fine = 0;
    tone.balance = osc2 ? 63 : -63;
    tone.filterType = septum::FilterType::Bypass;
    tone.ampEnvAttack = tone.ampEnvDecay = 0;
    tone.ampEnvSustain = 127;
    tone.levelVelocitySens = 0;
    patch.delayOn = patch.reverbOn = false;
    return patch;
}
void initialise (septum::Engine& engine, double rate, const septum::Patch& patch,
                 int octave, int transpose, int masterShift = 0)
{
    engine.prepare (rate, 256);
    engine.setPatch (patch);
    engine.setKeyboardOctaveShift (octave);
    engine.setTranspose (transpose);
    engine.setMasterKeyShift (masterShift);
    engine.reset();
}
std::vector<float> render (septum::Engine& engine)
{
    std::vector<float> left (4096), right (4096);
    engine.process (left.data(), right.data(), static_cast<int> (left.size()));
    expect (std::all_of (left.begin(), left.end(), [] (float x) { return std::isfinite (x); }),
            "transpose fixture audio is finite");
    return left;
}
double difference (const std::vector<float>& a, const std::vector<float>& b)
{
    double result = 0;
    for (std::size_t i = 0; i < a.size(); ++i)
        result = std::max (result, std::abs (double (a[i]) - b[i]));
    return result;
}
double peak (const std::vector<float>& a)
{
    double result = 0;
    for (float x : a) result = std::max (result, std::abs (double (x)));
    return result;
}
}

int main()
{
    for (double rate : {44100.0, 48000.0, 96000.0})
        for (bool lower : {false, true})
            for (bool osc2 : {false, true})
            {
                const auto patch = patchFor (lower, osc2);
                for (auto shifts : {std::array<int, 2>{-3, -5}, {3, 6}, {1, -5}, {-1, 6}})
                {
                    septum::Engine direct, reference;
                    initialise (direct, rate, patch, shifts[0], shifts[1]);
                    initialise (reference, rate, patch, 0, 0);
                    direct.noteOnDirect (60, 100);
                    reference.noteOnDirect (60, 100);
                    const auto actual = render (direct), expected = render (reference);
                    const double error = difference (actual, expected);
                    worstDirectDifference = std::max (worstDirectDifference, error);
                    expect (error < 1e-8 && peak (expected) > .001,
                            "direct MIDI ignores only the keyboard's octave and transpose");

                    // The ordinary/remote keyboard path still follows both
                    // controls, and matches the explicitly shifted note.
                    initialise (direct, rate, patch, shifts[0], shifts[1]);
                    initialise (reference, rate, patch, 0, 0);
                    direct.noteOn (60, 100);
                    reference.noteOn (60 + 12 * shifts[0] + shifts[1], 100);
                    expect (difference (render (direct), render (reference)) < 1e-8,
                            "keyboard and remote-keyboard notes keep their pitch shifts");
                }

                // Master tuning and native tone octave belong to the sound
                // generator, so direct MIDI must continue to follow them.
                septum::Engine direct, reference;
                auto tuned = patch;
                (lower ? tuned.lower : tuned.upper).octaveShift = -1;
                initialise (direct, rate, tuned, 3, 6, 7);
                initialise (reference, rate, patch, 0, 0);
                direct.noteOnDirect (65, 100); // 65 - 12 + 7 = 60
                reference.noteOnDirect (60, 100);
                expect (difference (render (direct), render (reference)) < 1e-8,
                        "direct MIDI preserves MASTER KEY SHIFT and native tone octave");

                initialise (direct, rate, patch, 0, 0);
                initialise (reference, rate, patch, 0, 0);
                direct.noteOnDirect (60, 100);
                reference.noteOnDirect (60, 100);
                (void) render (direct); (void) render (reference);
                direct.setKeyboardOctaveShift (2); direct.setTranspose (-5);
                expect (difference (render (direct), render (reference)) < 1e-8,
                        "live keyboard transposition does not retune a held direct MIDI voice");
            }
    std::printf ("%d checks, %d failures; maximum direct difference %.9g\n",
                 checks, failures, worstDirectDifference);
    return failures == 0 ? 0 : 1;
}
