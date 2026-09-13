#include "PluginProcessor.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <vector>

namespace
{
int checks = 0, failures = 0;
void expect (bool condition, const char* label)
{ ++checks; if (! condition) { ++failures; std::fprintf (stderr, "FAIL: %s\n", label); } }
void set (SeptumAudioProcessor& p, const char* id, float value)
{ auto* parameter = p.parameters.getParameter (id); parameter->setValueNotifyingHost (parameter->convertTo0to1 (value)); }
septum::Patch sound (bool arp)
{
    auto patch = septum::initPatch();
    septum::applyArpeggioStyle (patch, 0);
    patch.arpeggio.on = arp;
    patch.upper.osc1.wave = septum::Waveform::Sine;
    patch.upper.filterType = septum::FilterType::Bypass;
    patch.upper.ampEnvAttack = patch.upper.ampEnvRelease = 0;
    patch.upper.ampEnvSustain = 127;
    return patch;
}
std::vector<float> render (int mode, int channel, bool arp, bool ui = false)
{
    SeptumAudioProcessor p;
    p.loadPatch (sound (arp)); set (p, "system_remote_keyboard", float (mode));
    p.prepareToPlay (48000, 256);
    if (ui) for (int n : {60, 64, 67}) p.triggerFromUi (n, 100);
    std::vector<float> result (24000);
    for (int at = 0; at < int (result.size()); at += 256)
    {
        const int count = std::min (256, int (result.size()) - at);
        juce::AudioBuffer<float> audio (2, count); juce::MidiBuffer midi;
        if (at == 0 && ! ui)
            for (int n : {60, 64, 67})
                midi.addEvent (juce::MidiMessage::noteOn (channel, n, (juce::uint8) 100), 0);
        p.processBlock (audio, midi);
        std::copy_n (audio.getReadPointer (0), count, result.begin() + at);
    }
    return result;
}
double difference (const std::vector<float>& a, const std::vector<float>& b)
{ double peak = 0; for (std::size_t i = 0; i < a.size(); ++i) peak = std::max (peak, std::abs (double (a[i]) - b[i])); return peak; }
void testAudio()
{
    const auto direct = render (0, 1, true);
    expect (difference (direct, render (0, 1, false)) < 1e-7, "DIRECT bypasses arpeggio despite its ON switch");
    const auto arp = render (2, 1, true);
    expect (difference (arp, direct) > .01, "fixture distinguishes chord from arpeggio");
    expect (difference (arp, render (1, 9, true)) < 1e-7, "REMOTE accepts keyboard notes from any channel");
    expect (difference (arp, render (0, 1, true, true)) < 1e-7, "UI keyboard continues to play arpeggios in DIRECT mode");
    for (int mode : {0, 2})
    {
        const auto rejected = render (mode, 9, true);
        expect (std::all_of (rejected.begin(), rejected.end(), [] (float x) { return std::abs (x) < 1e-12f; }),
                "DIRECT and CHANNEL respect the configured receive channel");
    }
    SeptumAudioProcessor p;
    p.loadPatch (sound (false)); set (p, "system_remote_keyboard", 1);
    p.prepareToPlay (48000, 256);
    juce::AudioBuffer<float> audio (2, 256); juce::MidiBuffer midi;
    const auto current = p.getCurrentProgram(); const auto cutoff = p.snapshotPatch().upper.cutoff;
    midi.addEvent (juce::MidiMessage::programChange (9, 3), 0);
    midi.addEvent (juce::MidiMessage::controllerEvent (9, 74, 5), 0);
    midi.addEvent (juce::MidiMessage::noteOn (9, 60, (juce::uint8) 100), 0);
    midi.addEvent (juce::MidiMessage::controllerEvent (9, 64, 127), 32);
    midi.addEvent (juce::MidiMessage::noteOff (9, 60), 64);
    p.processBlock (audio, midi);
    expect (p.getCurrentProgram() == current && p.snapshotPatch().upper.cutoff == cutoff,
            "remote keyboard does not exempt foreign-channel program or panel edits");
    expect (p.getActiveVoiceCount() == 1, "remote sustain reaches the keyboard note");
    set (p, "system_remote_keyboard", 0);
    midi.clear(); for (int i = 0; i < 30; ++i) p.processBlock (audio, midi);
    expect (p.getActiveVoiceCount() == 0, "mode changes release current notes and pedals without stuck voices");
    // Applying a newly loaded patch precedes queued UI note routing.
    auto changed = sound (false); changed.keyboardPart = septum::KeyboardPart::Lower;
    p.loadPatch (changed); p.triggerFromUi (60, 100); p.processBlock (audio, midi);
    expect (p.getPartActiveVoiceCount (false) == 1 && p.getPartActiveVoiceCount (true) == 0,
            "UI notes use the newly selected patch's keyboard routing");
}
void testState()
{
    SeptumAudioProcessor p; set (p, "system_remote_keyboard", 0);
    juce::MemoryBlock bytes; p.getStateInformation (bytes);
    SeptumAudioProcessor restored; restored.setStateInformation (bytes.getData(), int (bytes.getSize()));
    expect (restored.parameters.getRawParameterValue ("system_remote_keyboard")->load() < .5f,
            "remote mode survives session restore");
    auto tree = juce::ValueTree::fromXml (*juce::AudioProcessor::getXmlFromBinary (bytes.getData(), int (bytes.getSize())));
    tree.removeChild (tree.getChildWithProperty ("id", "system_remote_keyboard"), nullptr);
    tree.setProperty ("preset_format_version", 4, nullptr);
    juce::AudioProcessor::copyXmlToBinary (*tree.createXml(), bytes);
    juce::TemporaryFile file (".septum"); file.getFile().replaceWithData (bytes.getData(), bytes.getSize());
    expect (restored.loadPresetFromFile (file.getFile()).wasOk()
                && restored.parameters.getRawParameterValue ("system_remote_keyboard")->load() > 1.5f,
            "version4 native presets migrate to CHANNEL compatibility mode");
}
}
int main()
{
    juce::ScopedJuceInitialiser_GUI gui; testAudio(); testState();
    std::printf ("Remote keyboard processor: %d checks, %d failures\n", checks, failures);
    return failures != 0;
}
