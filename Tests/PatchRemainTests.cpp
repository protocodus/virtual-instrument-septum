// Roland SH-201 Owner's Manual p. 68: PATCH REMAIN maintains the sound of
// the currently sounding patch when a different patch is selected.
#include "DSP/SeptumEngine.h"

#include <algorithm>
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

septum::Patch sourcePatch()
{
    septum::Patch patch;
    patch.patchLevel = 83;
    patch.toneBalance = 21;
    patch.tempo = 173;
    patch.upper.osc1.wave = septum::Waveform::Sine;
    patch.upper.balance = -63;
    patch.upper.filterType = septum::FilterType::Bypass;
    patch.upper.level = 32;
    patch.upper.ampEnvAttack = 4;
    patch.upper.ampEnvDecay = 21;
    patch.upper.ampEnvSustain = 103;
    patch.upper.ampEnvRelease = 0;
    patch.lower = patch.upper;
    return patch;
}

septum::Patch nextPatch()
{
    auto patch = sourcePatch();
    patch.patchLevel = 0;
    patch.toneBalance = -63;
    patch.tempo = 39;
    patch.keyboardMode = septum::KeyboardMode::Single;
    patch.keyboardPart = septum::KeyboardPart::Lower;
    patch.upper.osc1.wave = septum::Waveform::Saw;
    patch.upper.osc1.coarse = 12;
    patch.upper.filterType = septum::FilterType::Lpf;
    patch.upper.cutoff = 25;
    patch.upper.ampEnvRelease = 127;
    patch.upper.mono = septum::MonoMode::SoloLegato;
    patch.modulationDestination = septum::ToneDestination::Lower;
    patch.pitchBendDestination = septum::ToneDestination::Lower;
    patch.expressionDestination = septum::ToneDestination::Lower;
    patch.modulationAssign = septum::ModulationAssign::Amp;
    patch.lower = patch.upper;
    return patch;
}

void select (septum::Engine& engine, const septum::Patch& patch, bool remain = true)
{
#ifdef SEPTUM_PATCH_REMAIN_BASELINE
    if (! remain)
        engine.allSoundOff();
    engine.setPatch (patch);
#else
    engine.changePatch (patch, remain);
#endif
}

void prepare (septum::Engine& engine, const septum::Patch& patch, double rate = 48000)
{
    engine.prepare (rate, 256);
    engine.setPatch (patch);
    engine.reset();
}

std::vector<float> render (septum::Engine& engine, int count, int block = 37)
{
    std::vector<float> left (static_cast<std::size_t> (count)), right (left.size());
    for (int pos = 0; pos < count; pos += block)
        engine.process (left.data() + pos, right.data() + pos, std::min (block, count - pos));
    return left;
}

double relativeError (const std::vector<float>& a, const std::vector<float>& b)
{
    double error = 0.0, energy = 0.0;
    for (std::size_t i = 0; i < a.size(); ++i)
    {
        error += std::pow (static_cast<double> (a[i]) - b[i], 2.0);
        energy += static_cast<double> (a[i]) * a[i];
    }
    return std::sqrt (error / std::max (1.0e-30, energy));
}

void testSoundSnapshot()
{
    for (bool keyTrigger : { false, true })
        for (auto wave : { septum::LfoShape::Tri, septum::LfoShape::SampleHold,
                           septum::LfoShape::Random })
            for (bool tempoSync : { false, true })
            {
                auto patch = sourcePatch();
                patch.upper.lfo1.shape = wave;
                patch.upper.lfo1.keyTrigger = keyTrigger;
                patch.upper.lfo1.tempoSync = tempoSync;
                patch.upper.lfo1.tempoSyncNote = 0;
                patch.upper.lfo1.rate = 112;
                patch.upper.lfo1.fadeTime = 37;
                patch.upper.lfo1.destination1 = septum::LfoDest1::Pitch1;
                patch.upper.lfo1.depth1 = 24;
                patch.upper.lfo2.shape = wave;
                patch.upper.lfo2.rate = 107;
                septum::Engine actual, reference;
                prepare (actual, patch);
                prepare (reference, patch);
                actual.noteOn (69, 100);
                reference.noteOn (69, 100);
                render (actual, 8192);
                render (reference, 8192);
                select (actual, nextPatch());
                actual.setPitchBend (0.3);
                reference.setPitchBend (0.3);
                actual.setModulation (0.4);
                reference.setModulation (0.4);
                actual.setExpression (0.6);
                reference.setExpression (0.6);
                const double error = relativeError (render (reference, 16384), render (actual, 16384));
                expect (error < 1.0e-6, "old tone, level, balance, controller destinations and LFO remain: "
                    + std::to_string (keyTrigger) + "/" + std::to_string (static_cast<int> (wave))
                    + "/" + std::to_string (tempoSync) + " error=" + std::to_string (error));
                // A second selection and ordinary parameter editing must not
                // replace a snapshot from the first selection.
                auto third = nextPatch();
                third.upper.osc1.wave = septum::Waveform::Square;
                third.keyboardMode = septum::KeyboardMode::Dual;
                select (actual, third);
                third.upper.ampEnvSustain = 0;
                actual.setPatch (third);
                expect (relativeError (render (reference, 1024), render (actual, 1024)) < 1.0e-6,
                        "multiple changes and edits preserve original voice");
                actual.noteOff (69);
                reference.noteOff (69);
                expect (relativeError (render (reference, 4096), render (actual, 4096)) < 1.0e-6,
                        "original release remains after keyboard routing changes");
                expect (actual.activeVoiceCount() == 0, "retained voice finishes its original release");
            }
}

void testAssignmentAndRelease()
{
    auto first = sourcePatch();
    first.upper.mono = septum::MonoMode::SoloLegato;
    septum::Engine engine;
    prepare (engine, first);
    engine.noteOn (60, 100);
    render (engine, 1024);
    auto next = first;
    next.upper.osc1.wave = septum::Waveform::Square;
    select (engine, next);
    engine.noteOn (64, 100);
    expect (engine.activeVoiceCount() == 2, "new solo voice does not reuse retained solo voice");
    engine.noteOn (67, 100);
    expect (engine.activeVoiceCount() == 2, "new solo program retains its own one-voice allocation");
    engine.noteOff (67);
    engine.noteOff (64);
    render (engine, 4096);
    expect (engine.activeVoiceCount() == 1, "new solo stack cannot steal or retarget old held note");
    engine.noteOff (60);
    render (engine, 4096);
    expect (engine.activeVoiceCount() == 0, "old solo note responds to its own release");

    for (bool direct : { false, true })
    {
        prepare (engine, first);
        if (direct) engine.noteOnDirect (60, 100); else engine.noteOn (60, 100);
        render (engine, 1024);
        auto arp = nextPatch();
        arp.arpeggio.on = true;
        select (engine, arp);
        if (direct) engine.noteOff (60); else engine.noteOffDirect (60);
        render (engine, 1024);
        expect (engine.heldVoiceCount (true) == 1, "opposite source cannot release retained note");
        if (direct) engine.noteOffDirect (60); else engine.noteOff (60);
        render (engine, 4096);
        expect (engine.activeVoiceCount() == 0, "new arp routing cannot strand retained note");
    }

    for (bool pedalBefore : { false, true })
    {
        prepare (engine, first);
        engine.noteOn (60, 100);
        if (pedalBefore) engine.setSostenuto (true);
        select (engine, nextPatch());
        if (! pedalBefore) engine.setSostenuto (true);
        engine.noteOff (60);
        render (engine, 4096);
        expect (engine.activeVoiceCount() == 1, "sostenuto catches retained key before or after selection");
        engine.setSostenuto (false);
        render (engine, 4096);
        expect (engine.activeVoiceCount() == 0, "sostenuto lift releases retained note");
    }
    prepare (engine, first);
    engine.noteOn (60, 100);
    engine.setHold (true);
    select (engine, nextPatch());
    engine.allNotesOff();
    render (engine, 4096);
    expect (engine.activeVoiceCount() == 1, "all notes off honors hold on retained note");
    engine.setHold (false);
    render (engine, 4096);
    expect (engine.activeVoiceCount() == 0, "hold lift releases retained note after all notes off");

    prepare (engine, first);
    engine.noteOn (60, 100);
    render (engine, 1024);
    select (engine, nextPatch(), false);
    expect (engine.activeVoiceCount() == 0, "PATCH REMAIN off stops old voices");
    const auto silent = render (engine, 1024);
    expect (std::all_of (silent.begin(), silent.end(), [] (float x) { return x == 0.0f; }),
            "PATCH REMAIN off also clears buffered sound");
}

void testPolyphonyAndLiveEdits()
{
    septum::Engine engine;
    auto patch = sourcePatch();
    prepare (engine, patch);
    for (int i = 0; i < 10; ++i) engine.noteOn (48 + i, 100);
    render (engine, 1024);
    patch.keyboardMode = septum::KeyboardMode::Dual;
    select (engine, patch);
    for (int i = 0; i < 5; ++i)
    {
        engine.noteOn (72 + i, 100);
        expect (engine.activeVoiceCount() == 10, "retained programs share the ten physical voices");
    }
    for (int i = 0; i < 10; ++i) engine.noteOff (48 + i);
    render (engine, 4096);
    expect (engine.activeVoiceCount (true) == 5 && engine.activeVoiceCount (false) == 5,
            "new dual program gets five complete pairs while replacing retained voices");
    engine.allSoundOff();
    expect (engine.activeVoiceCount() == 0, "panic stops every retained generation");

    patch = sourcePatch();
    prepare (engine, patch);
    engine.noteOn (69, 100);
    render (engine, 1024);
    patch.upper.level = 0;
    engine.setPatch (patch);
    const auto edited = render (engine, 8192);
    double tail = 0.0;
    for (std::size_t i = edited.size() - 1024; i < edited.size(); ++i) tail += edited[i] * edited[i];
    std::printf ("Live edit tail energy %.12g\n", tail);
    expect (tail < 1.0e-8, "routine setPatch still edits current sounding voices: tail=" + std::to_string (tail));
}

void testReleaseAndPortamento()
{
    septum::Engine actual, reference;
    auto first = sourcePatch();
    first.upper.ampEnvRelease = 42;
    prepare (actual, first);
    prepare (reference, first);
    actual.noteOn (69, 100);
    reference.noteOn (69, 100);
    render (actual, 8192);
    render (reference, 8192);
    actual.noteOff (69);
    reference.noteOff (69);
    render (actual, 256);
    render (reference, 256);
    select (actual, nextPatch());
    expect (relativeError (render (reference, 8192), render (actual, 8192)) < 1.0e-6,
            "release already in progress continues with original sound and timing");

    first = sourcePatch();
    prepare (actual, first);
    actual.noteOn (60, 100);
    render (actual, 1024);
    select (actual, first);
    actual.setPortamentoControl (60);
    actual.noteOn (67, 100);
    expect (actual.activeVoiceCount() == 2, "CC84 cannot transfer a retained program's voice");
    actual.noteOff (67);
    render (actual, 4096);
    expect (actual.activeVoiceCount() == 1, "CC84 new note does not take retained note release ownership");
    actual.noteOff (60);
    render (actual, 4096);
    expect (actual.activeVoiceCount() == 0, "retained CC84 source remains independently releasable");

    first.arpeggio.on = true;
    first.arpeggio.style.endStep = 1;
    first.arpeggio.style.cells[0][0] = 100;
    prepare (actual, first);
    actual.noteOn (60, 100);
    render (actual, 32);
    expect (actual.activeVoiceCount() > 0, "arpeggiator starts a voice before patch selection");
    select (actual, nextPatch());
    render (actual, 4096);
    expect (actual.activeVoiceCount() == 0, "last old arpeggio gate decays instead of becoming stuck");
}
}

int main()
{
    testSoundSnapshot();
    testAssignmentAndRelease();
    testPolyphonyAndLiveEdits();
    testReleaseAndPortamento();
    std::printf ("Patch remain: %d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
