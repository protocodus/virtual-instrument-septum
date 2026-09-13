#include "PluginProcessor.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <vector>

namespace
{
int checks = 0, failures = 0;
void expect (bool value, const char* text)
{
    ++checks;
    if (! value) { ++failures; std::fprintf (stderr, "FAIL: %s\n", text); }
}
void block (SeptumAudioProcessor& p, juce::MidiBuffer midi = {})
{
    juce::AudioBuffer<float> audio (2, 128);
    p.processBlock (audio, midi);
}
void testMode (septum::KeyboardMode keyboard, int channels)
{
    SeptumAudioProcessor p;
    auto patch = septum::initPatch();
    patch.keyboardMode = keyboard;
    patch.upper.ampEnvSustain = patch.lower.ampEnvSustain = 127;
    patch.delayOn = patch.reverbOn = true;
    p.loadPatch (patch);
    p.prepareToPlay (48000, 128);
    juce::MidiBuffer notes;
    for (int note : {60, 64, 67})
        notes.addEvent (juce::MidiMessage::noteOn (1, note, (juce::uint8) 100), 0);
    block (p, notes);
    const int layers = keyboard == septum::KeyboardMode::Dual ? 2 : 1;
    expect (p.getActiveVoiceCount() == 3 * layers, "initial chord is polyphonic");
    juce::MidiBuffer mode;
    mode.addEvent (juce::MidiMessage::controllerEvent (2, 126, channels), 64);
    block (p, mode);
    expect (p.getActiveVoiceCount() == 3 * layers, "foreign-channel mode message is ignored");
    mode.clear();
    mode.addEvent (juce::MidiMessage::controllerEvent (1, 126, channels), 64);
    juce::AudioBuffer<float> audio (2, 128);
    p.processBlock (audio, mode);
    expect (p.getActiveVoiceCount() == 0, "mono mode terminates all old voices");
    for (int i = 64; i < 128; ++i)
        expect (audio.getSample (0, i) == 0 && audio.getSample (1, i) == 0,
                "mono mode clears sound and effect history at its timestamp");
    expect (p.snapshotPatch().upper.mono == septum::MonoMode::SoloLegato
                && p.snapshotPatch().lower.mono == septum::MonoMode::SoloLegato,
            "mono follows the general MIDI mono-legato recommendation");
    block (p, notes);
    expect (p.getActiveVoiceCount() == layers, "CC126 forces one note per tone for every M");
    mode.clear();
    mode.addEvent (juce::MidiMessage::controllerEvent (1, 127, 0), 32);
    for (const auto metadata : notes)
        mode.addEvent (metadata.getMessage(), 64);
    block (p, mode);
    expect (p.getActiveVoiceCount() == 3 * layers, "poly mode and subsequent chord apply in one block");
    expect (p.snapshotPatch().upper.mono == septum::MonoMode::Poly
                && p.snapshotPatch().lower.mono == septum::MonoMode::Poly,
            "poly mode is reflected in patch parameters");
}
std::vector<float> overlap (bool midiMode, bool legato)
{
    SeptumAudioProcessor p; auto patch = septum::initPatch();
    patch.upper.mono = midiMode ? septum::MonoMode::Poly
        : legato ? septum::MonoMode::SoloLegato : septum::MonoMode::Solo;
    patch.upper.ampEnvAttack = 70;
    patch.upper.ampEnvDecay = 35;
    patch.upper.ampEnvSustain = 40;
    patch.upper.filterType = septum::FilterType::Bypass;
    patch.upper.osc1.wave = septum::Waveform::Sine;
    p.loadPatch (patch); p.prepareToPlay (48000, 256);
    std::vector<float> result (16384);
    for (int at = 0; at < int (result.size()); at += 256)
    {
        juce::AudioBuffer<float> audio (2, 256); juce::MidiBuffer midi;
        if (at == 0)
        {
            if (midiMode) midi.addEvent (juce::MidiMessage::controllerEvent (1, 126, 1), 0);
            midi.addEvent (juce::MidiMessage::noteOn (1, 60, (juce::uint8) 100), 0);
        }
        if (at == 8192) midi.addEvent (juce::MidiMessage::noteOn (1, 64, (juce::uint8) 100), 0);
        p.processBlock (audio, midi);
        std::copy_n (audio.getReadPointer (0), 256, result.begin() + at);
    }
    return result;
}
void testLegato()
{
    const auto actual = overlap (true, true), reference = overlap (false, true), retriggered = overlap (false, false);
    double error = 0, contrast = 0;
    for (std::size_t i = 0; i < actual.size(); ++i)
    {
        error = std::max (error, std::abs (double (actual[i]) - reference[i]));
        contrast = std::max (contrast, std::abs (double (actual[i]) - retriggered[i]));
    }
    expect (error < 1e-7, "CC126 overlapping notes preserve the slow attack like SOLO+LEGATO");
    expect (contrast > .001, "slow-attack fixture detects an unintended mono envelope retrigger");
}
}
int main()
{
    juce::ScopedJuceInitialiser_GUI gui;
    for (auto mode : {septum::KeyboardMode::Single, septum::KeyboardMode::Dual})
        for (int channels : {0, 1, 16, 127}) testMode (mode, channels);
    testLegato();
    std::printf ("MIDI mode processor: %d checks, %d failures\n", checks, failures);
    return failures != 0;
}
