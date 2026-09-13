#include "PluginProcessor.h"
#include <cmath>
#include <cstdio>

namespace
{
int checks = 0, failures = 0;
void expect (bool value, const char* text)
{ ++checks; if (! value) { ++failures; std::fprintf (stderr, "FAIL: %s\n", text); } }
void set (SeptumAudioProcessor& p, const char* id, float value)
{ auto* parameter = p.parameters.getParameter (id); parameter->setValueNotifyingHost (parameter->convertTo0to1 (value)); }
void send (SeptumAudioProcessor& p, std::initializer_list<juce::MidiMessage> events)
{
    juce::AudioBuffer<float> audio (2, 128);
    juce::MidiBuffer midi;
    for (const auto& message : events) midi.addEvent (message, 32);
    p.processBlock (audio, midi);
}
juce::MidiMessage cc (int n, int v, int channel = 1)
{ return juce::MidiMessage::controllerEvent (channel, n, v); }
juce::MidiMessage pc (int n, int channel = 1)
{ return juce::MidiMessage::programChange (channel, n); }
void testBank()
{
    SeptumAudioProcessor p;
    p.prepareToPlay (48000, 128);
    send (p, {pc (41)});
    expect (p.getCurrentProgram() == 41, "bare PCs preserve the existing flat plug-in map");
    send (p, {cc (0, 87), cc (32, 20)});
    expect (p.getCurrentProgram() == 41, "bank selection does not change sound before PC");
    for (int i = 0; i < 32; ++i)
    {
        send (p, {pc (i)});
        expect (p.getCurrentProgram() == i + 32, "USER bank uses decimal LSB20 and 32 slots");
    }
    send (p, {cc (32, 0), pc (9)});
    expect (p.getCurrentProgram() == 9, "PRESET bank selects the authored preset slots");
    send (p, {cc (32, 32), pc (1)});
    expect (p.getCurrentProgram() == 9, "hexadecimal misreading of LSB20 does not select a bank");
    send (p, {cc (0, 1), cc (32, 20), pc (1)});
    expect (p.getCurrentProgram() == 9, "unknown bank MSB is ignored on program selection");
    send (p, {cc (0, 87), cc (32, 0), pc (32)});
    expect (p.getCurrentProgram() == 9, "hardware bank programs above31 are rejected");
    set (p, "system_receive_bank", 0);
    send (p, {cc (32, 20), pc (2)});
    expect (p.getCurrentProgram() == 2, "RX BANK off preserves the previous bank latch");
    set (p, "system_receive_bank", 1);
    set (p, "system_receive_program", 0);
    send (p, {cc (32, 20), pc (3)});
    expect (p.getCurrentProgram() == 2, "RX PROGRAM off rejects PC independently");
    set (p, "system_receive_program", 1);
    send (p, {pc (3)});
    expect (p.getCurrentProgram() == 35, "bank can be prepared while program receive is off");
    set (p, "system_midi_channel", 0);
    send (p, {cc (0, 87, 2), cc (32, 0, 2), pc (4, 2)});
    expect (p.getCurrentProgram() == 4, "ALL mode supports independent channel bank latches");
    send (p, {pc (4, 1)});
    expect (p.getCurrentProgram() == 36, "another channel does not overwrite bank selection");
    // Bank and PC arrive before the note in one render block. Compare the
    // resulting waveform with an explicitly selected identical user slot.
    SeptumAudioProcessor reference, actual;
    reference.setCurrentProgram (34);
    reference.prepareToPlay (48000, 128);
    actual.prepareToPlay (48000, 128);
    juce::AudioBuffer<float> a (2, 2048), b (2, 2048);
    juce::MidiBuffer ma, mb;
    ma.addEvent (cc (0, 87), 0); ma.addEvent (cc (32, 20), 0); ma.addEvent (pc (2), 0);
    const auto note = juce::MidiMessage::noteOn (1, 60, (juce::uint8) 100);
    ma.addEvent (note, 64); mb.addEvent (note, 64);
    actual.processBlock (a, ma); reference.processBlock (b, mb);
    double error = 0, peak = 0;
    for (int i = 0; i < 2048; ++i)
    { error = std::max (error, std::abs (double (a.getSample (0, i)) - b.getSample (0, i))); peak = std::max (peak, std::abs (double (b.getSample (0, i)))); }
    expect (error < 1e-7 && peak > .01, "sample-position bank selection plays the requested sound");
    set (p, "system_receive_bank", 0);
    juce::MemoryBlock state; p.getStateInformation (state);
    reference.setStateInformation (state.getData(), int (state.getSize()));
    expect (reference.parameters.getRawParameterValue ("system_receive_bank")->load() < .5f,
            "receive bank setting survives session restore");
    auto tree = juce::ValueTree::fromXml (*juce::AudioProcessor::getXmlFromBinary (state.getData(), int (state.getSize())));
    tree.removeChild (tree.getChildWithProperty ("id", "system_receive_bank"), nullptr);
    tree.setProperty ("preset_format_version", 3, nullptr);
    juce::AudioProcessor::copyXmlToBinary (*tree.createXml(), state);
    juce::TemporaryFile file (".septum"); file.getFile().replaceWithData (state.getData(), state.getSize());
    expect (reference.loadPresetFromFile (file.getFile()).wasOk()
                && reference.parameters.getRawParameterValue ("system_receive_bank")->load() > .5f,
            "version3 native presets migrate the bank receive default");
}
}
int main()
{
    juce::ScopedJuceInitialiser_GUI gui; testBank();
    std::printf ("MIDI bank processor: %d checks, %d failures\n", checks, failures);
    return failures != 0;
}
