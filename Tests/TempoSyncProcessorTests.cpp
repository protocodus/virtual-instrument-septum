#include "PluginProcessor.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <limits>
#include <vector>

namespace
{
int checks = 0, failures = 0;
void expect (bool condition, const char* label)
{
    ++checks;
    if (! condition) { ++failures; std::fprintf (stderr, "FAIL: %s\n", label); }
}
void set (SeptumAudioProcessor& processor, const char* id, float value)
{
    auto* parameter = processor.parameters.getParameter (id);
    parameter->setValueNotifyingHost (parameter->convertTo0to1 (value));
}
struct PlayHead final : juce::AudioPlayHead
{
    juce::Optional<double> bpm;
    bool positionAvailable = true;
    juce::Optional<PositionInfo> getPosition() const override
    {
        if (! positionAvailable) return {};
        PositionInfo info;
        info.setBpm (bpm);
        return info;
    }
};

std::vector<float> render (int source, int patchTempo, int systemTempo,
                           juce::Optional<double> hostTempo, int blockSize,
                           bool clocks, bool arpeggio, bool freeLfo = false,
                           bool hostAvailable = true)
{
    SeptumAudioProcessor processor;
    auto patch = septum::initPatch();
    septum::applyArpeggioStyle (patch, 0);
    patch.tempo = patchTempo;
    patch.delayOn = patch.reverbOn = false;
    patch.upper.osc1.wave = septum::Waveform::Sine;
    patch.upper.filterType = septum::FilterType::Bypass;
    patch.upper.ampEnvAttack = 0;
    patch.upper.ampEnvSustain = 127;
    patch.upper.lfo1.keyTrigger = true;
    patch.upper.lfo1.tempoSync = ! freeLfo;
    patch.upper.lfo1.tempoSyncNote = 11; // quarter note
    patch.upper.lfo1.destination1 = septum::LfoDest1::Pitch1;
    patch.upper.lfo1.depth1 = 30;
    patch.arpeggio.on = arpeggio;
    processor.loadPatch (patch);
    set (processor, "system_clock_source", static_cast<float> (source));
    set (processor, "system_tempo", static_cast<float> (systemTempo));
    PlayHead playHead;
    playHead.bpm = hostTempo;
    playHead.positionAvailable = hostAvailable;
    processor.setPlayHead (&playHead);
    processor.prepareToPlay (48000.0, blockSize);
    std::vector<float> result (48000);
    for (int at = 0; at < static_cast<int> (result.size()); at += blockSize)
    {
        const int count = std::min (blockSize, static_cast<int> (result.size()) - at);
        juce::AudioBuffer<float> block (2, count);
        juce::MidiBuffer midi;
        // Identical event segmentation on reference and actual paths.
        if (clocks)
            for (int pulse = ((at + 999) / 1000) * 1000; pulse < at + count; pulse += 1000)
                midi.addEvent (juce::MidiMessage::midiClock(), pulse - at);
        if (at <= 5000 && at + count > 5000)
            midi.addEvent (juce::MidiMessage::noteOn (1, 60, (juce::uint8) 100), 5000 - at);
        processor.processBlock (block, midi);
        std::copy_n (block.getReadPointer (0), count, result.begin() + at);
    }
    expect (processor.snapshotPatch().tempo == patchTempo,
            "external tempo never changes the stored patch tempo");
    return result;
}
double difference (const std::vector<float>& a, const std::vector<float>& b)
{
    double peak = 0.0;
    for (std::size_t i = 0; i < a.size(); ++i)
        peak = std::max (peak, std::abs (static_cast<double> (a[i]) - b[i]));
    return peak;
}

void testAudio()
{
    for (const int block : { 37, 256 })
        for (const bool arp : { false, true })
        {
            const auto reference = render (0, 120, 90, 75.0, block, true, arp);
            expect (difference (reference, render (1, 60, 120, 75.0, block, true, arp)) < 2e-6,
                    "SYSTEM clock audio matches the selected tempo for LFO and arpeggio");
            expect (difference (reference, render (2, 60, 90, 75.0, block, true, arp)) < 2e-6,
                    "MIDI clock drives LFO and arpeggio at 24 pulses per quarter");
            expect (difference (reference, render (3, 60, 90, 120.0, block, true, arp)) < 2e-6,
                    "HOST clock audio matches the host tempo for LFO and arpeggio");
            expect (difference (reference, render (0, 60, 90, 120.0, block, true, arp)) > 1e-3,
                    "tempo fixtures distinguish a wrong rate audibly");
        }
    const auto reference = render (0, 120, 90, {}, 256, false, false);
    for (const auto invalid : { 0.0, -10.0, std::numeric_limits<double>::quiet_NaN(),
                                std::numeric_limits<double>::infinity() })
        expect (difference (reference, render (3, 120, 90, invalid, 256, false, false)) == 0.0,
                "invalid host BPM falls back to patch tempo");
    expect (difference (reference, render (3, 120, 90, {}, 256, false, false)) == 0.0,
            "missing optional BPM falls back to patch tempo");
    expect (difference (reference, render (3, 120, 90, 90.0, 256, false, false, false, false)) == 0.0,
            "missing playhead position falls back to patch tempo");
    expect (difference (reference, render (3, 60, 90, 120.5, 256, false, false)) > 1e-5,
            "fractional host BPM is not rounded to an integer");
    expect (difference (render (0, 60, 90, {}, 256, false, false, true),
                        render (3, 60, 90, 120.0, 256, false, false, true)) == 0.0,
            "free-running LFO is independent of clock source");
    const auto waiting = render (2, 120, 90, {}, 256, false, true);
    expect (*std::max_element (waiting.begin(), waiting.end()) == 0.0f
                && *std::min_element (waiting.begin(), waiting.end()) == 0.0f,
            "MIDI source waits for clock before starting the arpeggio");
}

void testState()
{
    SeptumAudioProcessor processor;
    set (processor, "system_clock_source", 1);
    set (processor, "system_tempo", 137);
    processor.setCurrentProgram (1);
    expect (processor.parameters.getRawParameterValue ("system_tempo")->load() == 137.0f,
            "SYSTEM tempo survives program changes");
    juce::MemoryBlock data;
    processor.getStateInformation (data);
    SeptumAudioProcessor restored;
    restored.setStateInformation (data.getData(), static_cast<int> (data.getSize()));
    expect (restored.parameters.getRawParameterValue ("system_tempo")->load() == 137.0f
                && restored.parameters.getRawParameterValue ("system_clock_source")->load() == 1.0f,
            "clock source and system BPM round-trip through DAW state");
    const auto xml = juce::AudioProcessor::getXmlFromBinary (data.getData(), static_cast<int> (data.getSize()));
    auto legacy = juce::ValueTree::fromXml (*xml);
    for (const auto* id : { "system_tempo", "system_clock_source" })
        legacy.removeChild (legacy.getChildWithProperty ("id", id), nullptr);
    legacy.setProperty ("preset_format_version", 2, nullptr);
    juce::AudioProcessor::copyXmlToBinary (*legacy.createXml(), data);
    restored.setStateInformation (data.getData(), static_cast<int> (data.getSize()));
    expect (restored.parameters.getRawParameterValue ("system_clock_source")->load() == 0.0f
                && restored.parameters.getRawParameterValue ("system_tempo")->load() == 120.0f,
            "legacy DAW state restores explicit patch-clock defaults over current settings");
    juce::TemporaryFile preset (".septum");
    expect (preset.getFile().replaceWithData (data.getData(), data.getSize())
                && restored.loadPresetFromFile (preset.getFile()).wasOk(),
            "version 2 preset files migrate missing clock parameters");
    expect (restored.savePresetToFile (preset.getFile()).wasOk()
                && processor.loadPresetFromFile (preset.getFile()).wasOk(),
            "version 3 native presets save and load");
}
} // namespace

int main()
{
    juce::ScopedJuceInitialiser_GUI gui;
    testAudio();
    testState();
    std::printf ("Tempo sync processor: %d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
