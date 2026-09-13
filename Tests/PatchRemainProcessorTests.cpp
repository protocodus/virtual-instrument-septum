#include "PluginProcessor.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <vector>
namespace
{
int checks = 0, failures = 0;
void expect (bool value, const char* label)
{ ++checks; if (! value) { ++failures; std::fprintf (stderr, "FAIL: %s\n", label); } }
void set (SeptumAudioProcessor& p, const char* id, float v)
{ auto* a = p.parameters.getParameter (id); a->setValueNotifyingHost (a->convertTo0to1 (v)); }
septum::Patch sound()
{
    auto p = septum::initPatch(); p.patchLevel = 91;
    p.upper.osc1.wave = septum::Waveform::Sine; p.upper.filterType = septum::FilterType::Bypass;
    p.upper.ampEnvSustain = 127; p.upper.ampEnvAttack = 0; p.upper.ampEnvRelease = 100;
    return p;
}
std::vector<float> render (bool remain, int selection)
{
    SeptumAudioProcessor p; p.loadPatch (sound()); set (p, "system_patch_remain", remain ? 1.0f : 0.0f);
    p.prepareToPlay (48000, 256); std::vector<float> out (16384);
    for (int at = 0; at < int (out.size()); at += 256)
    {
        juce::AudioBuffer<float> audio (2, 256); juce::MidiBuffer midi;
        if (at == 0) midi.addEvent (juce::MidiMessage::noteOn (1, 60, (juce::uint8) 100), 0);
        if (at == 8192)
        {
            if (selection == 1) p.setCurrentProgram (32);
            if (selection == 2) midi.addEvent (juce::MidiMessage::programChange (1, 32), 0);
            if (selection == 3)
            {
                auto next = sound(); next.patchLevel = 0; next.keyboardPart = septum::KeyboardPart::Lower;
                next.upper.osc1.wave = septum::Waveform::Saw; next.upper.ampEnvRelease = 0;
                next.lower.ampEnvRelease = 0; p.loadPatch (next);
            }
            if (selection == 4) set (p, "up_osc1_wave", 0); // ordinary live edit
        }
        p.processBlock (audio, midi);
        std::copy_n (audio.getReadPointer (0), 256, out.begin() + at);
    }
    if (remain && selection == 3)
        expect (p.getTailLengthSeconds() >= septum::mapping::decaySeconds (100),
                "host tail includes the retained voice's longer release");
    return out;
}
double error (const std::vector<float>& a, const std::vector<float>& b, int from)
{ double e = 0; for (std::size_t i = std::size_t (from); i < a.size(); ++i) e = std::max (e, std::abs (double (a[i]) - b[i])); return e; }
void testAudio()
{
    const auto reference = render (true, 0);
    for (int selection : {1, 2, 3})
    {
        const auto retained = render (true, selection), stopped = render (false, selection);
        expect (error (reference, retained, 0) < 1e-6, "REMAIN keeps old dry tone across UI, MIDI and explicit patch loads");
        expect (error (reference, stopped, 8192) > .01, "OFF switches away from the old sound");
        expect (std::all_of (stopped.begin() + 8192, stopped.end(), [] (float v) { return std::abs (v) < 1e-12f; }),
                "OFF terminates old voices at selection");
    }
    expect (error (reference, render (true, 4), 8192) > .01,
            "REMAIN does not freeze ordinary live oscillator edits");
}
void testState()
{
    SeptumAudioProcessor p; set (p, "system_patch_remain", 1);
    p.setCurrentProgram (2);
    expect (p.parameters.getRawParameterValue ("system_patch_remain")->load() > .5f,
            "patch selection retains the system REMAIN switch");
    juce::MemoryBlock data; p.getStateInformation (data);
    SeptumAudioProcessor restored; restored.setStateInformation (data.getData(), int (data.getSize()));
    expect (restored.parameters.getRawParameterValue ("system_patch_remain")->load() > .5f,
            "host state stores REMAIN");
    auto tree = juce::ValueTree::fromXml (*juce::AudioProcessor::getXmlFromBinary (data.getData(), int (data.getSize())));
    tree.removeChild (tree.getChildWithProperty ("id", "system_patch_remain"), nullptr);
    tree.setProperty ("preset_format_version", 5, nullptr);
    juce::AudioProcessor::copyXmlToBinary (*tree.createXml(), data);
    juce::TemporaryFile file (".septum"); file.getFile().replaceWithData (data.getData(), data.getSize());
    expect (restored.loadPresetFromFile (file.getFile()).wasOk()
                && restored.parameters.getRawParameterValue ("system_patch_remain")->load() < .5f,
            "version5 presets migrate REMAIN to OFF");
}
}
int main()
{
    juce::ScopedJuceInitialiser_GUI gui; testAudio(); testState();
    std::printf ("Patch remain processor: %d checks, %d failures\n", checks, failures); return failures != 0;
}
