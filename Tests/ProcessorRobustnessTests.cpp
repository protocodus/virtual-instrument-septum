#include "PluginProcessor.h"

#include <array>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <new>
#include <random>
#include <thread>
#include <vector>

namespace
{
thread_local bool countAllocations = false;
thread_local std::size_t allocations = 0;
int checks = 0, failures = 0;
void expect (bool condition, const char* message)
{
    ++checks;
    if (! condition)
    {
        ++failures;
        std::fprintf (stderr, "FAIL: %s\n", message);
    }
}
void finite (const juce::AudioBuffer<float>& audio)
{
    bool okay = true;
    for (int channel = 0; channel < audio.getNumChannels(); ++channel)
        for (int sample = 0; sample < audio.getNumSamples(); ++sample)
            okay = okay && std::isfinite (audio.getSample (channel, sample));
    expect (okay, "rendered output remains finite");
}
void render (SeptumAudioProcessor& processor, juce::MidiBuffer& midi,
             int channels = 2, int samples = 128)
{
    juce::AudioBuffer<float> audio (channels, samples);
    processor.processBlock (audio, midi);
    finite (audio);
    expect (midi.isEmpty(), "the instrument consumes its MIDI input");
}
void testOrdering()
{
    for (const bool releaseFirst : { false, true })
    {
        SeptumAudioProcessor processor;
        processor.prepareToPlay (48000, 16);
        juce::MidiBuffer midi;
        const auto on = juce::MidiMessage::noteOn (1, 60, juce::uint8 (100));
        const auto off = juce::MidiMessage::noteOff (1, 60);
        midi.addEvent (releaseFirst ? off : on, 12);
        midi.addEvent (releaseFirst ? on : off, 12);
        render (processor, midi);
        expect (processor.getPartHeldVoiceCount (true) == (releaseFirst ? 1 : 0),
                "equal-timestamp note events retain host insertion order");
    }
    for (const bool programFirst : { false, true })
    {
        SeptumAudioProcessor processor;
        processor.prepareToPlay (48000, 16);
        juce::MidiBuffer midi;
        const auto program = juce::MidiMessage::programChange (1, 3);
        const auto cutoff = juce::MidiMessage::controllerEvent (1, 74, 23);
        midi.addEvent (programFirst ? program : cutoff, 6);
        midi.addEvent (programFirst ? cutoff : program, 6);
        render (processor, midi);
        expect (processor.snapshotPatch().upper.cutoff == (programFirst ? 23 : septum::factoryPatches()[3].patch.upper.cutoff),
                "equal-timestamp program and panel CC retain host insertion order");
    }
    SeptumAudioProcessor processor;
    processor.prepareToPlay (48000, 16);
    juce::MidiBuffer midi;
    midi.addEvent (juce::MidiMessage::noteOn (1, 60, juce::uint8 (100)), -5);
    midi.addEvent (juce::MidiMessage::noteOff (1, 60), 10000);
    render (processor, midi, 2, 64);
    expect (processor.getPartHeldVoiceCount (true) == 0,
            "out-of-block timestamps clamp predictably while preserving note release");
}
void testMalformedMidi()
{
    SeptumAudioProcessor processor;
    processor.prepareToPlay (48000, 16);
    juce::MidiBuffer midi;
    const std::uint8_t truncatedNote[] { 0x90, 60 };
    const std::uint8_t truncatedCc[] { 0xb0, 74 };
    const std::uint8_t invalidNote[] { 0x90, 0xff, 100 };
    const std::uint8_t invalidCc[] { 0xb0, 74, 0xff };
    const std::uint8_t unterminatedSysEx[] { 0xf0, 0x41, 0x10, 0, 0, 0x16, 0x12 };
    const auto before = processor.snapshotPatch().upper.cutoff;
    midi.addEvent (truncatedNote, sizeof (truncatedNote), 0);
    midi.addEvent (truncatedCc, sizeof (truncatedCc), 0);
    midi.addEvent (invalidNote, sizeof (invalidNote), 0);
    midi.addEvent (invalidCc, sizeof (invalidCc), 0);
    midi.addEvent (unterminatedSysEx, sizeof (unterminatedSysEx), 0);
    std::vector<std::uint8_t> hugeSysEx (60000, 1);
    hugeSysEx.front() = 0xf0; hugeSysEx.back() = 0xf7;
    midi.addEvent (hugeSysEx.data(), static_cast<int> (hugeSysEx.size()), 0);
    render (processor, midi);
    expect (processor.getPartHeldVoiceCount (true) == 0, "malformed note messages create no held voice");
    expect (processor.snapshotPatch().upper.cutoff == before, "malformed CC messages do not change parameters");
}
void testCallbackHasNoAllocations()
{
    SeptumAudioProcessor processor;
    auto layout = processor.getBusesLayout();
    layout.inputBuses.set (0, juce::AudioChannelSet::stereo());
    expect (processor.setBusesLayout (layout), "external input bus enables for allocation regression");
    processor.prepareToPlay (48000, 16);
    juce::AudioBuffer<float> audio (2, 8193);
    audio.clear();
    juce::MidiBuffer midi;
    for (int program = 0; program < 12; ++program)
        midi.addEvent (juce::MidiMessage::programChange (1, program), program * 19);
    const auto packets = septum::sysex::encodePatchToSysExPackets (septum::initPatch());
    for (const auto& packet : packets)
        midi.addEvent (packet.data(), static_cast<int> (packet.size()), 256);
    midi.addEvent (juce::MidiMessage::controllerEvent (1, 74, 85), 258);
    midi.addEvent (juce::MidiMessage::noteOn (1, 67, juce::uint8 (100)), 259);
    const std::uint8_t universal[] { 0xf0, 0x7f, 0x7f, 0x04, 0x01, 0x00, 100, 0xf7 };
    midi.addEvent (universal, sizeof (universal), 260);
    allocations = 0;
    countAllocations = true;
    processor.processBlock (audio, midi);
    countAllocations = false;
    if (allocations != 0)
        std::fprintf (stderr, "callback allocations: %zu\n", allocations);
    expect (allocations == 0, "oversized block with programs, CCs and complete SysEx dump performs no C++ allocations");
    finite (audio);
    expect (processor.snapshotPatch().upper.cutoff == 85, "later CC composes on the decoded dump");
    expect (processor.getPartHeldVoiceCount (true) == 1, "note after dump plays the final patch");
}
void testLifecycleAndChannels()
{
    SeptumAudioProcessor processor;
    juce::MidiBuffer midi;
    midi.addEvent (juce::MidiMessage::noteOn (1, 60, juce::uint8 (100)), 0);
    render (processor, midi); // before prepare: bounded silence, no engine access
    for (double rate : { 0.0, -48000.0, std::numeric_limits<double>::quiet_NaN(),
                          std::numeric_limits<double>::infinity(), 48000.0 })
    {
        processor.prepareToPlay (rate, -1);
        for (int channels : { 0, 1, 2, 4 })
            for (int samples : { 0, 1, 31, 257 })
            {
                midi.addEvent (juce::MidiMessage::noteOn (1, 60, juce::uint8 (100)), 0);
                midi.addEvent (juce::MidiMessage::noteOff (1, 60), samples);
                render (processor, midi, channels, samples);
                expect (processor.getPartHeldVoiceCount (true) == 0, "empty and unusual buffers still process note releases");
            }
        processor.triggerFromUi (60, 100);
        processor.releaseResources();
        expect (processor.getActiveVoiceCount() == 0, "releaseResources resets voice meters");
        render (processor, midi);
    }
    processor.prepareToPlay (48000, 16);
    render (processor, midi);
    expect (processor.getPartHeldVoiceCount (true) == 0, "reprepare cannot resurrect queued UI notes from a stopped stream");
}

void testUiOverflow()
{
    SeptumAudioProcessor processor;
    processor.prepareToPlay (48000, 16);
    // Fill the queue with irrelevant releases. A brand-new press arriving
    // while full must reach the instrument through the overflow mailbox.
    for (int i = 0; i < 64; ++i) processor.releaseFromUi (61);
    processor.triggerFromUi (60, 100);
    juce::MidiBuffer midi;
    render (processor, midi);
    expect (processor.getPartHeldVoiceCount (true) == 1, "an overflowed new UI press is retained");
    for (int i = 0; i < 64; ++i) processor.releaseFromUi (61);
    processor.releaseFromUi (60);
    processor.triggerFromUi (60, 70);
    processor.releaseFromUi (60);
    render (processor, midi);
    expect (processor.getPartHeldVoiceCount (true) == 0, "the last overflowed release wins after repeated retriggers");
}

void testOversizedInputMatchesPreparedBuffer()
{
    const auto take = [] (int maximumBlock)
    {
        SeptumAudioProcessor processor;
        auto layout = processor.getBusesLayout();
        layout.inputBuses.set (0, juce::AudioChannelSet::stereo());
        processor.setBusesLayout (layout);
        processor.prepareToPlay (48000, maximumBlock);
        juce::AudioBuffer<float> audio (2, 4097);
        for (int i = 0; i < audio.getNumSamples(); ++i)
        {
            audio.setSample (0, i, 0.1f * static_cast<float> (std::sin (i * 0.17)));
            audio.setSample (1, i, 0.1f * static_cast<float> (std::cos (i * 0.13)));
        }
        juce::MidiBuffer midi;
        midi.addEvent (juce::MidiMessage::noteOn (1, 60, juce::uint8 (100)), 17);
        midi.addEvent (juce::MidiMessage::noteOff (1, 60), 2053);
        processor.processBlock (audio, midi);
        return audio;
    };
    const auto small = take (16), large = take (4097);
    double error = 0;
    for (int channel = 0; channel < 2; ++channel)
        for (int i = 0; i < small.getNumSamples(); ++i)
            error = std::max (error, std::abs (double (small.getSample (channel, i)) - large.getSample (channel, i)));
    expect (error < 1.0e-6, "chunked oversized input preserves both input samples and MIDI timing");
}
void testInvalidHostState()
{
    SeptumAudioProcessor processor;
    processor.prepareToPlay (48000, 16);
    processor.parameters.getRawParameterValue ("up_cutoff")->store (47);
    juce::MemoryBlock valid;
    processor.getStateInformation (valid);
    const auto xml = juce::AudioProcessor::getXmlFromBinary (valid.getData(), static_cast<int> (valid.getSize()));
    expect (xml != nullptr, "fixture state is readable");
    const auto original = juce::ValueTree::fromXml (*xml);
    const auto reject = [&] (juce::ValueTree state)
    {
        juce::MemoryBlock bytes;
        juce::AudioProcessor::copyXmlToBinary (*state.createXml(), bytes);
        processor.setStateInformation (bytes.getData(), static_cast<int> (bytes.getSize()));
        expect (processor.snapshotPatch().upper.cutoff == 47, "invalid host state preserves the previous patch");
    };
    reject (juce::ValueTree ("OtherPlugin"));
    for (const juce::var& bad : { juce::var ("NaN"), juce::var ("inf"), juce::var ("garbage"), juce::var (1.0e38), juce::var (-1.0e38) })
    {
        auto state = original.createCopy();
        state.getChildWithProperty ("id", "up_cutoff").setProperty ("value", bad, nullptr);
        reject (state);
    }
    {
        auto state = original.createCopy();
        state.setProperty ("program", std::numeric_limits<int>::max(), nullptr);
        reject (state);
    }
    {
        auto state = original.createCopy();
        state.addChild (state.getChild (0).createCopy(), -1, nullptr);
        reject (state);
    }
    processor.setStateInformation (nullptr, 16);
    processor.setStateInformation (valid.getData(), -1);
    processor.setStateInformation (valid.getData(), std::numeric_limits<int>::max());
    const auto rejectXml = [&] (const std::string& body)
    {
        juce::MemoryBlock malicious;
        juce::MemoryOutputStream stream (malicious, false);
        stream.write (valid.getData(), 4); // valid JUCE binary XML magic
        stream.writeInt (static_cast<int> (body.size()));
        stream.write (body.data(), body.size());
        stream.writeByte (0);
        processor.setStateInformation (malicious.getData(), static_cast<int> (malicious.getSize()));
        expect (processor.snapshotPatch().upper.cutoff == 47, "hostile XML is rejected before recursive parsing");
    };
    std::string nested;
    for (int i = 0; i < 10000; ++i) nested += "<node>";
    for (int i = 0; i < 10000; ++i) nested += "</node>";
    rejectXml (nested);
    rejectXml ("<!DOCTYPE Septum [<!ENTITY a 'expanded'>]><Septum name='&a;'/>");
    std::mt19937 random (0x53455054);
    std::array<std::uint8_t, 128> bytes {};
    for (int iteration = 0; iteration < 200; ++iteration)
    {
        for (auto& byte : bytes) byte = static_cast<std::uint8_t> (random());
        processor.setStateInformation (bytes.data(), static_cast<int> (random() % bytes.size()));
    }
    expect (processor.snapshotPatch().upper.cutoff == 47, "fuzzed binary state preserves the previous patch");
}

void testBooleanStateRestoration()
{
    SeptumAudioProcessor processor;
    juce::MemoryBlock state;
    processor.getStateInformation (state);
    std::vector<std::pair<juce::AudioProcessorParameter*, float>> booleans;
    for (auto* parameter : processor.getParameters())
        if (auto* boolean = dynamic_cast<juce::AudioParameterBool*> (parameter))
        {
            booleans.emplace_back (parameter, parameter->getValue());
            // Different underlying normalized value, same canonical raw
            // bool: APVTS replaceState alone may incorrectly skip this.
            boolean->setValueNotifyingHost (boolean->get() ? 0.7f : 0.4f);
        }
    processor.setStateInformation (state.getData(), static_cast<int> (state.getSize()));
    for (const auto& [boolean, value] : booleans)
        expect (boolean->getValue() == value, "host state restores the canonical normalized bool even when raw bool was unchanged");
}

void testHostTransactionWins()
{
    SeptumAudioProcessor processor;
    processor.parameters.getRawParameterValue ("system_midi_channel")->store (1);
    processor.prepareToPlay (48000, 16);
    juce::MidiBuffer note;
    note.addEvent (juce::MidiMessage::noteOn (1, 60, juce::uint8 (100)), 0);
    render (processor, note);
    struct DuringWrite final : juce::AudioProcessorParameter::Listener
    {
        SeptumAudioProcessor& processor;
        bool invoked { false }, notesHandled { false };
        explicit DuringWrite (SeptumAudioProcessor& p) : processor (p) {}
        void parameterValueChanged (int, float) override
        {
            if (invoked) return;
            invoked = true;
            juce::AudioBuffer<float> audio (2, 16);
            juce::MidiBuffer midi;
            midi.addEvent (juce::MidiMessage::noteOff (1, 60), 0);
            midi.addEvent (juce::MidiMessage::controllerEvent (1, 64, 0), 0);
            midi.addEvent (juce::MidiMessage::noteOn (1, 62, juce::uint8 (100)), 1);
            midi.addEvent (juce::MidiMessage::controllerEvent (2, 126, 0), 2);
            midi.addEvent (juce::MidiMessage::programChange (1, 4), 2);
            midi.addEvent (juce::MidiMessage::controllerEvent (1, 74, 98), 3);
            const std::uint8_t value = 79;
            const auto packet = septum::sysex::makeDt1Message (0x10000113, &value, 1);
            midi.addEvent (packet.data(), static_cast<int> (packet.size()), 4);
            processor.processBlock (audio, midi);
            notesHandled = processor.getPartHeldVoiceCount (true) == 1;
        }
        void parameterGestureChanged (int, bool) override {}
    } listener (processor);
    auto* cutoff = processor.parameters.getParameter ("up_cutoff");
    cutoff->addListener (&listener);
    auto hostPatch = septum::initPatch();
    hostPatch.upper.cutoff = 29;
    hostPatch.upper.resonance = 41;
    hostPatch.lower.cutoff = 67;
    processor.loadPatch (hostPatch);
    cutoff->removeListener (&listener);
    expect (listener.invoked, "regression injects MIDI while the host write is active");
    expect (listener.notesHandled, "notes and pedal releases continue through an active host transaction");
    const auto actual = processor.snapshotPatch();
    expect (actual.upper.cutoff == hostPatch.upper.cutoff && actual.upper.resonance == hostPatch.upper.resonance
                && actual.lower.cutoff == hostPatch.lower.cutoff,
            "a whole host patch wins over colliding MIDI program, CC and SysEx edits");
    juce::MidiBuffer midi;
    midi.addEvent (juce::MidiMessage::controllerEvent (1, 74, 42), 0);
    render (processor, midi);
    expect (processor.snapshotPatch().upper.cutoff == 42, "MIDI parameter changes resume after the host transaction completes");
}

void testPublicationDoesNotLoseMidi()
{
    for (const int messages : { 1, 300 })
    for (const bool restoreAfter : { false, true })
    {
    SeptumAudioProcessor processor;
    processor.prepareToPlay (48000, 16);
    juce::MidiBuffer first;
    first.addEvent (juce::MidiMessage::controllerEvent (1, 74, 97), 0);
    render (processor, first);
    struct DuringNotification final : juce::AudioProcessorParameter::Listener
    {
        SeptumAudioProcessor& processor;
        int messages;
        bool invoked { false };
        explicit DuringNotification (SeptumAudioProcessor& p, int n) : processor (p), messages (n) {}
        void parameterValueChanged (int, float) override
        {
            if (invoked) return;
            invoked = true;
            juce::AudioBuffer<float> audio (2, 16);
            juce::MidiBuffer midi;
            for (int i = 1; i < messages; ++i)
                midi.addEvent (juce::MidiMessage::controllerEvent (1, 74, i % 128), 0);
            midi.addEvent (juce::MidiMessage::controllerEvent (1, 74, 23), 0);
            midi.addEvent (juce::MidiMessage::noteOn (1, 60, juce::uint8 (100)), 1);
            midi.addEvent (juce::MidiMessage::noteOff (1, 60), 2);
            processor.processBlock (audio, midi);
        }
        void parameterGestureChanged (int, bool) override {}
    } listener (processor, messages);
    auto* cutoff = processor.parameters.getParameter ("up_cutoff");
    cutoff->addListener (&listener);
    processor.reconcileControlChanges();
    cutoff->removeListener (&listener);
    if (restoreAfter)
    {
        auto hostPatch = septum::initPatch();
        hostPatch.upper.cutoff = 66;
        processor.loadPatch (hostPatch);
    }
    juce::MidiBuffer empty;
    render (processor, empty);
    expect (listener.invoked, "regression injects final CC during notification publication");
    expect (processor.snapshotPatch().upper.cutoff == (restoreAfter ? 66 : 23),
            restoreAfter ? "a later explicit host patch invalidates older deferred MIDI edits"
                         : "the final CC overlapping notification survives even after bounded FIFO overflow");
    expect (processor.getPartHeldVoiceCount (true) == 0, "deferred control overflow never drops note releases");
    }
}
void testParameterAndMidiFuzz()
{
    SeptumAudioProcessor processor;
    processor.prepareToPlay (48000, 16);
    std::vector<std::atomic<float>*> values;
    for (const auto* parameter : processor.getParameters())
        if (const auto* identified = dynamic_cast<const juce::AudioProcessorParameterWithID*> (parameter))
            values.push_back (processor.parameters.getRawParameterValue (identified->paramID));
    std::mt19937 random (0x52454c45);
    constexpr std::array<float, 8> extremes { -std::numeric_limits<float>::max(),
        std::numeric_limits<float>::max(), std::numeric_limits<float>::quiet_NaN(),
        std::numeric_limits<float>::infinity(), -std::numeric_limits<float>::infinity(), 0, -1, 127 };
    juce::AudioBuffer<float> audio (2, 97);
    juce::MidiBuffer midi;
    for (int iteration = 0; iteration < 250; ++iteration)
    {
        values[random() % values.size()]->store (extremes[random() % extremes.size()]);
        for (int event = 0; event < 8; ++event)
        {
            std::array<std::uint8_t, 3> raw { static_cast<std::uint8_t> (0x80 + random() % 0x70),
                static_cast<std::uint8_t> (random()), static_cast<std::uint8_t> (random()) };
            midi.addEvent (raw.data(), 1 + static_cast<int> (random() % 3),
                           static_cast<int> (random() % 125) - 12);
        }
        audio.clear();
        processor.processBlock (audio, midi);
        finite (audio);
    }
    expect (std::isfinite (processor.getTailLengthSeconds()), "invalid raw automation cannot poison tail reporting");
}

void testBackgroundDestruction()
{
    std::atomic<bool> finished { false };
    std::thread host ([&]
    {
        for (int i = 0; i < 24; ++i)
        {
            auto processor = std::make_unique<SeptumAudioProcessor>();
            processor->prepareToPlay (48000, 16);
            juce::AudioBuffer<float> audio (2, 16);
            juce::MidiBuffer midi;
            midi.addEvent (juce::MidiMessage::programChange (1, i % 16), 0);
            processor->processBlock (audio, midi);
            std::this_thread::yield();
            processor.reset();
        }
        finished.store (true);
    });
    while (! finished.load())
    {
        juce::Timer::callPendingTimersSynchronously();
        std::this_thread::yield();
    }
    host.join();
    juce::Timer::callPendingTimersSynchronously();
    expect (true, "host background destruction safely detaches queued parameter publication");
}

void testArpeggioRetirementCannotEraseNewImport()
{
    SeptumAudioProcessor processor;
    auto patch = septum::initPatch();
    patch.arpeggio.styleIndex = 1;
    patch.arpeggio.style.cells[0][0] = 37;
    processor.loadPatch (patch);
    std::atomic<bool> running { true };
    std::thread snapshots ([&]
    {
        while (running.load (std::memory_order_relaxed))
            (void) processor.snapshotPatch();
    });
    bool preserved = true;
    for (int iteration = 0; iteration < 400; ++iteration)
    {
        // Retiring the old imported style is legitimate after this selector
        // move. A reader completing that retirement late must not clear the
        // new import published by the immediately following host patch load.
        processor.parameters.getRawParameterValue ("arp_style")->store (2);
        patch.arpeggio.style.cells[0][0] = static_cast<signed char> (1 + iteration % 100);
        processor.loadPatch (patch);
        preserved = preserved && processor.snapshotPatch().arpeggio.style.cells[0][0]
                                      == patch.arpeggio.style.cells[0][0];
    }
    running.store (false, std::memory_order_relaxed);
    snapshots.join();
    preserved = preserved && processor.snapshotPatch().arpeggio.style.cells[0][0]
                                  == patch.arpeggio.style.cells[0][0];
    expect (preserved, "concurrent retirement of an old selector never erases a newly imported pattern");
}
}

// Count allocations on the calling audio thread only. JUCE's timer thread may
// allocate independently; that is unrelated to real-time callback safety.
void* operator new (std::size_t size)
{
    if (countAllocations) ++allocations;
    if (void* result = std::malloc (size == 0 ? 1 : size)) return result;
    throw std::bad_alloc();
}
void* operator new[] (std::size_t size) { return ::operator new (size); }
void operator delete (void* p) noexcept { std::free (p); }
void operator delete[] (void* p) noexcept { std::free (p); }

int main()
{
    juce::ScopedJuceInitialiser_GUI gui;
    testOrdering();
    testMalformedMidi();
    testCallbackHasNoAllocations();
    testLifecycleAndChannels();
    testUiOverflow();
    testOversizedInputMatchesPreparedBuffer();
    testInvalidHostState();
    testBooleanStateRestoration();
    testHostTransactionWins();
    testPublicationDoesNotLoseMidi();
    testParameterAndMidiFuzz();
    testBackgroundDestruction();
    testArpeggioRetirementCannotEraseNewImport();
    std::printf ("Processor robustness: %d checks, %d failures\n", checks, failures);
    return failures != 0;
}
