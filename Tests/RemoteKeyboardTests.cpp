// OM pp. 22 and 69: remote keyboard input reaches the arpeggiator; ordinary
// MIDI notes reach the sound generator directly. The two sources may coexist.
#include "DSP/SeptumEngine.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>

namespace {
int checks = 0, failures = 0;
void expect (bool pass, const char* label)
{
    ++checks;
    if (! pass) { ++failures; std::fprintf (stderr, "FAIL: %s\n", label); }
}
void directOn (septum::Engine& engine, int note)
{
#if defined(SEPTUM_REMOTE_BASELINE)
    engine.noteOn (note, 100);
#else
    engine.noteOnDirect (note, 100);
#endif
}
void directOff (septum::Engine& engine, int note)
{
#if defined(SEPTUM_REMOTE_BASELINE)
    engine.noteOff (note);
#else
    engine.noteOffDirect (note);
#endif
}
septum::Patch patchFor (bool arp, septum::KeyboardMode mode = septum::KeyboardMode::Single)
{
    septum::Patch patch;
    patch.keyboardMode = mode;
    patch.splitPoint = 60;
    patch.upper.osc1.wave = septum::Waveform::Sine;
    patch.upper.balance = -63;
    patch.upper.filterType = septum::FilterType::Bypass;
    patch.upper.ampEnvAttack = patch.upper.ampEnvDecay = 0;
    patch.upper.ampEnvSustain = 127;
    patch.upper.ampEnvRelease = 0;
    patch.upper.levelVelocitySens = 0;
    patch.lower = patch.upper;
    patch.delayOn = patch.reverbOn = false;
    patch.tempo = 120;
    patch.arpeggio.on = arp;
    patch.arpeggio.grid = septum::ArpeggioGrid::Quarter;
    patch.arpeggio.duration = septum::ArpeggioDuration::P30;
    patch.arpeggio.motif = septum::ArpeggioMotif::UpL;
    patch.arpeggio.style = septum::ArpeggioStyle {};
    patch.arpeggio.style.endStep = 1;
    patch.arpeggio.style.cells[0][0] = 100;
    return patch;
}
double render (septum::Engine& engine, double seconds)
{
    std::array<float, 128> left {}, right {};
    const int samples = static_cast<int> (seconds * engine.sampleRate());
    double energy = 0.0;
    bool finite = true;
    for (int position = 0; position < samples; position += 128)
    {
        const int count = std::min (128, samples - position);
        engine.process (left.data(), right.data(), count);
        for (int i = 0; i < count; ++i)
        {
            finite = finite && std::isfinite (left[i]) && std::isfinite (right[i]);
            energy += left[i] * static_cast<double> (left[i]);
        }
    }
    expect (finite, "direct and keyboard audio remains finite");
    return energy;
}
void initialise (septum::Engine& engine, double rate, const septum::Patch& patch)
{
    engine.prepare (rate, 128);
    engine.setPatch (patch);
    engine.reset();
}
int held (const septum::Engine& engine)
{
    return engine.heldVoiceCount (true) + engine.heldVoiceCount (false);
}
}

int main()
{
    for (double rate : {44100.0, 48000.0, 96000.0})
    {
        for (auto mode : {septum::KeyboardMode::Single, septum::KeyboardMode::Dual,
                          septum::KeyboardMode::Split})
        {
            septum::Engine engine;
            initialise (engine, rate, patchFor (true, mode));
            directOn (engine, 60);
            render (engine, 0.22);
            expect (held (engine) == (mode == septum::KeyboardMode::Dual ? 2 : 1),
                    "ordinary MIDI sustains through the keyboard arp's gate gap");
            expect (render (engine, 0.10) > 0.001,
                    "ordinary MIDI stays audible with the arpeggiator enabled");
            directOff (engine, 60);
            render (engine, 0.03);
            expect (held (engine) == 0, "ordinary MIDI note-off releases its routed parts");
        }

        // Both sources play exactly the same pitch; each release belongs to
        // its own source, including the arpeggiator's internally scheduled off.
        for (bool directFirst : {false, true})
        {
            septum::Engine engine;
            initialise (engine, rate, patchFor (true));
            engine.noteOn (60, 100);
            directOn (engine, 60);
            render (engine, 0.05);
            expect (held (engine) == 2, "same-pitch keyboard and direct MIDI start independent voices");
            if (directFirst)
            {
                directOff (engine, 60);
                expect (held (engine) == 1, "direct release preserves a same-pitch keyboard arp gate");
                render (engine, 0.17);
                expect (held (engine) == 0, "keyboard arp gate still owns its scheduled release");
                engine.noteOff (60);
            }
            else
            {
                render (engine, 0.17);
                expect (held (engine) == 1, "arp gate-off leaves same-pitch direct MIDI sounding");
                engine.noteOff (60);
                expect (held (engine) == 1, "keyboard release leaves same-pitch direct MIDI sounding");
                directOff (engine, 60);
            }
            render (engine, 0.03);
            expect (held (engine) == 0, "both sources finish without a stuck key");
        }

        // Source ownership also matters before arpeggiation is enabled and
        // across live switch edits: direct notes must never enter its chord.
        {
            septum::Engine engine;
            auto patch = patchFor (false);
            initialise (engine, rate, patch);
            directOn (engine, 60);
            patch.arpeggio.on = true;
            engine.setPatch (patch);
            render (engine, 0.22);
            expect (held (engine) == 1, "turning on the arp does not absorb direct MIDI keys");
            patch.arpeggio.on = false;
            engine.setPatch (patch);
            render (engine, 0.02);
            expect (held (engine) == 1, "turning off the arp does not duplicate direct MIDI keys");
            directOff (engine, 60);
            expect (held (engine) == 0, "direct key ownership survives arp switch edits");
        }

        for (bool directFirst : {false, true})
        {
            septum::Engine engine;
            initialise (engine, rate, patchFor (false));
            directOn (engine, 60);
            engine.noteOn (60, 100);
            if (directFirst) directOff (engine, 60); else engine.noteOff (60);
            expect (held (engine) == 1, "same-pitch ordinary keys have separate source ownership");
            if (directFirst) engine.noteOff (60); else directOff (engine, 60);
            expect (held (engine) == 0, "the remaining source releases independently");
        }

        for (auto mono : {septum::MonoMode::Solo, septum::MonoMode::SoloLegato})
        {
            septum::Engine engine;
            auto patch = patchFor (false);
            patch.upper.mono = mono;
            initialise (engine, rate, patch);
            directOn (engine, 60);
            engine.noteOn (72, 100);
            engine.noteOff (72);
            expect (held (engine) == 1, "solo returns to a still-held direct MIDI source");
            directOff (engine, 60);
            expect (held (engine) == 0, "solo return restores the direct source's note-off ownership");
        }

        // Independent sostenuto latches survive a new press of the same pitch
        // from the other source, and All Notes Off releases direct input even
        // when an ARP HOLD chord is playing that pitch.
        {
            septum::Engine engine;
            initialise (engine, rate, patchFor (false));
            directOn (engine, 60);
            engine.setSostenuto (true);
            directOff (engine, 60);
            engine.noteOn (60, 100);
            engine.noteOff (60);
            expect (held (engine) == 1, "a new keyboard key cannot erase direct MIDI's sostenuto latch");
            engine.setSostenuto (false);
            expect (held (engine) == 0, "sostenuto lift releases its direct source");
        }
        {
            septum::Engine engine;
            auto patch = patchFor (true);
            patch.arpeggio.hold = true;
            initialise (engine, rate, patch);
            engine.noteOn (60, 100);
            directOn (engine, 60);
            render (engine, 0.05);
            engine.allNotesOff();
            expect (held (engine) == 1, "All Notes Off releases direct MIDI while ARP HOLD owns its gate");
            engine.allSoundOff();
            expect (engine.activeVoiceCount() == 0, "panic clears both keyboard and direct input");
        }
    }
    std::printf ("%d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
