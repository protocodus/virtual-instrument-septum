#pragma once

#include <JuceHeader.h>
#include "DSP/MidiBankSelect.h"

#include "DSP/SeptumEngine.h"
#include "DSP/MidiTempoClock.h"
#include "DSP/SeptumPresets.h"
#include "DSP/SeptumSysEx.h"

#include <array>
#include <atomic>
#include <memory>
#include <mutex>
#include <optional>
#include <thread>

namespace septum::parameters
{
// Parameter IDs mirror the modelled instrument's parameter contract: one
// complete tone block per part ("up_"/"lo_" prefix), the shared patch-common
// block, and the shared delay/reverb blocks.
[[nodiscard]] inline juce::String toneId (bool upper, const char* name)
{
    return juce::String (upper ? "up_" : "lo_") + name;
}
} // namespace septum::parameters

class SeptumAudioProcessor final : public juce::AudioProcessor
{
public:
    SeptumAudioProcessor();
    ~SeptumAudioProcessor() override;

    void prepareToPlay (double sampleRate, int samplesPerBlock) override;
    void releaseResources() override;
    bool isBusesLayoutSupported (const BusesLayout& layouts) const override;
    void processBlock (juce::AudioBuffer<float>&, juce::MidiBuffer&) override;

    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override { return true; }

    const juce::String getName() const override { return JucePlugin_Name; }
    bool acceptsMidi() const override { return true; }
    bool producesMidi() const override { return false; }
    bool isMidiEffect() const override { return false; }
    // Computed from the current patch: amp release plus delay repeats down to
    // -60 dB plus reverb RT60, capped — see the implementation.
    double getTailLengthSeconds() const override;

    int getNumPrograms() override;
    int getCurrentProgram() override;
    void setCurrentProgram (int index) override;
    const juce::String getProgramName (int index) override;
    void changeProgramName (int, const juce::String&) override {}

    void getStateInformation (juce::MemoryBlock& destinationData) override;
    void setStateInformation (const void* data, int sizeInBytes) override;

    // Native presets carry the complete plug-in state, including both parts,
    // shared/system settings and any imported arpeggio pattern. File access
    // belongs on the message thread; a failed load leaves the sound intact.
    [[nodiscard]] juce::Result savePresetToFile (const juce::File& file);
    [[nodiscard]] juce::Result loadPresetFromFile (const juce::File& file);
    [[nodiscard]] juce::String getCurrentPresetName() const;

    // Editor helpers.
    [[nodiscard]] float getOutputLevel (int channel) const noexcept
    {
        return engine.getOutputLevel (channel);
    }
    [[nodiscard]] int getActiveVoiceCount() const noexcept
    {
        return activeVoices.load (std::memory_order_relaxed);
    }
    [[nodiscard]] float getPartOutputLevel (bool upper) const noexcept
    {
        return engine.getPartOutputLevel (upper);
    }
    [[nodiscard]] int getPartActiveVoiceCount (bool upper) const noexcept
    {
        return partActiveVoices[upper ? 0u : 1u].load (std::memory_order_relaxed);
    }
    [[nodiscard]] int getPartHeldVoiceCount (bool upper) const noexcept
    {
        return partHeldVoices[upper ? 0u : 1u].load (std::memory_order_relaxed);
    }
    void triggerFromUi (int note, int velocity) noexcept;
    void releaseFromUi (int note) noexcept;
    // The on-screen bend/modulation lever, mirroring the hardware's lever
    // left of the keys. Applied on the audio thread each block.
    void setLeverFromUi (float bendMinus1to1, float mod0to1) noexcept
    {
        uiBend.store (bendMinus1to1, std::memory_order_relaxed);
        uiMod.store (mod0to1, std::memory_order_relaxed);
        uiLeverDirty.store (true, std::memory_order_release);
    }

    // Reads the current parameter values into an engine patch. Shared by the
    // audio thread and tests, so the two can never disagree.
    [[nodiscard]] septum::Patch snapshotPatch() const;

    // The external-input path's settings, read the same way. Kept out of the
    // patch because the instrument keeps them out of it (OM pp. 49-51).
    [[nodiscard]] septum::ExternalInput snapshotExternalInput() const;

    // The message-thread half of a MIDI program change: repeats the values
    // the audio path already wrote, with host/UI notification, skipping any
    // parameter edited since. Normally reached via the queued message-loop
    // callback; public so the harness can stand in for that loop.
    void reconcileProgram (int index);

    // The message-thread half of a received panel CC: republishes the raw
    // values the audio path wrote, with host and UI notification. Public so
    // the harness can stand in for the message loop.
    void reconcileControlChanges();

    // Loads an entire structured patch into the processor and APVTS.
    void loadPatch (const septum::Patch& patch);

    // The two halves of that, split so a patch arriving on the audio thread
    // (a received SysEx dump) writes only atomics there and is republished to
    // the host and the UI from the message loop. Public so the harness can
    // stand in for that loop.
    // `publishGrid` puts the arpeggio grid into the same guarded write
    // window as the parameters, so a concurrent state save cannot pair one
    // patch revision's parameters with another's grid.
    void writePatchToParameters (const septum::Patch& patch,
                                 bool publishGrid = false) noexcept;
    void republishPatchParameters();
    // Point the shadows back at whatever the parameters now hold and drop any
    // pending republish. Called by the writers that run on the message thread,
    // so a program change or a preset load that lands between a dump and its
    // republish is not undone by it: last writer wins.
    void syncPatchShadows() noexcept;

    // Everything a queued republish could still put back, dropped. A state
    // restore replaces the whole parameter tree, so a CC, a dump or a
    // device-control message whose republish has not run yet must not land on
    // top of the session that was just loaded.
    void cancelPendingRepublishes() noexcept;

    // The same half for the three Universal Realtime device-control messages.
    // Public so the harness can stand in for the message loop.
    void republishSystemParameters();

    // Parses and loads SysEx .syx bytes into the active patch.
    void loadSysExData (const void* data, std::size_t sizeInBytes);

    // Encodes the current patch into a Roland SH-201 SysEx .syx byte buffer.
    [[nodiscard]] std::vector<std::uint8_t> createSysExDataForCurrentPatch() const;

    juce::AudioProcessorValueTreeState parameters;

    static juce::AudioProcessorValueTreeState::ParameterLayout
        createParameterLayout();

private:
    void loadPatchUnderWriteAccess (const septum::Patch& patch);

    // Explicit host patch loads supersede MIDI parameter edits that overlap
    // them. Notification-only collisions defer those edits instead of losing
    // them. Audio makes a bounded atomic try;
    // notes, releases and performance controllers do not use this gate.
    // Only host/control callers take the mutex or wait for an audio writer.
    std::recursive_mutex hostParameterMutex;
    // 0 = none, 1 = explicit host transaction, 2 = notification only.
    std::atomic<int> hostParameterWritePending { 0 };
    std::atomic<std::uint64_t> hostParameterTransaction { 0 };
    std::atomic<bool> audioParameterWriteActive { false };
    struct ParameterWriteAccess
    {
        enum class Mode { Host, Audio, Notification };
        ParameterWriteAccess (SeptumAudioProcessor& processor, Mode requested)
            : owner (processor), mode (requested), hostLock (processor.hostParameterMutex,
                                                            std::defer_lock)
        {
            transaction = owner.hostParameterTransaction.load();
            // A notification may reenter the processor. Nested audio helpers
            // share an acquired audio gate; a host notification cannot start
            // another host transaction, or inject a MIDI patch into its own
            // half-written state. The outer transaction wins in both cases.
            for (auto* previous = current; previous != nullptr; previous = previous->parent)
                if (&previous->owner == &owner)
                {
                    if (mode == Mode::Audio && previous->mode == Mode::Audio)
                        enter (false);
                    else if (mode == Mode::Audio && previous->mode == Mode::Notification)
                        deferred = true;
                    return;
                }
            if (mode != Mode::Audio)
            {
                hostLock.lock();
                owner.hostParameterWritePending.store (mode == Mode::Host ? 1 : 2);
                while (owner.audioParameterWriteActive.load())
                    std::this_thread::yield();
                if (mode == Mode::Host)
                    owner.hostParameterTransaction.fetch_add (1);
                enter (true);
            }
            else
            {
                const int pending = owner.hostParameterWritePending.load();
                if (pending != 0) { deferred = pending == 2; return; }
                bool available = false;
                if (! owner.audioParameterWriteActive.compare_exchange_strong (available, true))
                    return;
                const int pendingAfterClaim = owner.hostParameterWritePending.load();
                if (pendingAfterClaim != 0)
                {
                    deferred = pendingAfterClaim == 2;
                    owner.audioParameterWriteActive.store (false);
                    return;
                }
                enter (true);
            }
        }
        ~ParameterWriteAccess()
        {
            if (! acquired) return;
            current = parent;
            if (! ownsGate) return;
            if (mode != Mode::Audio) owner.hostParameterWritePending.store (0);
            else owner.audioParameterWriteActive.store (false);
        }
        explicit operator bool() const noexcept { return acquired; }
        bool shouldDefer() const noexcept { return deferred; }
        std::uint64_t transactionAtEntry() const noexcept { return transaction; }
        ParameterWriteAccess (const ParameterWriteAccess&) = delete;
        ParameterWriteAccess& operator= (const ParameterWriteAccess&) = delete;
    private:
        void enter (bool owns) noexcept
        {
            acquired = true;
            ownsGate = owns;
            parent = current;
            current = this;
        }
        SeptumAudioProcessor& owner;
        Mode mode;
        std::unique_lock<std::recursive_mutex> hostLock;
        bool acquired { false }, ownsGate { false };
        bool deferred { false };
        std::uint64_t transaction {};
        ParameterWriteAccess* parent { nullptr };
        inline static thread_local ParameterWriteAccess* current { nullptr };
    };

    // Notification collisions are replayed by the audio thread in FIFO order
    // at the next available boundary. Explicit host transactions invalidate
    // older queued edits. Overflow retains the newest parameter edits; notes
    // and pedals never enter this queue and always keep their original timing.
    struct DeferredParameterMidi
    {
        std::array<std::uint8_t, 79> data {};
        int size {};
    };
    static constexpr std::size_t deferredParameterCapacity = 256;
    std::array<DeferredParameterMidi, deferredParameterCapacity> deferredParameterMidi {};
    std::size_t deferredParameterRead { 0 }, deferredParameterCount { 0 };
    std::uint64_t deferredParameterTransaction { 0 };
    void deferParameterMidi (const std::uint8_t* data, int size,
                             std::uint64_t transaction) noexcept;
    bool drainDeferredParameterMidi();
    // Both return true when the event edited a patch parameter, so the audio
    // path can refresh the engine patch before rendering the next segment.
    bool handleMidiMessage (const juce::MidiMessage& message);
    bool handleController (int controller, int value, int channel);
    septum::MidiBankSelect midiBankSelect;
    std::atomic<float>* receiveBankValue { nullptr };
    std::atomic<float>* remoteKeyboardValue { nullptr };
    int appliedRemoteKeyboard { 2 };
    std::atomic<float>* patchRemainValue { nullptr };
    std::atomic<std::uint64_t> patchSelectionRevision { 0 };
    std::uint64_t appliedPatchSelectionRevision { 0 };
    std::atomic<double> retainedReleaseSeconds { 0.0 };
    [[nodiscard]] bool acceptsLiveSysEx (const std::uint8_t* data,
                                         std::size_t size) const noexcept;
    bool decodeLivePatchMessage (const std::uint8_t* data, std::size_t size,
                                 septum::Patch& patch) noexcept;
    // Only the audio thread touches the raw-byte decoder. Other patch writers
    // advance a revision, so even a replacement by identical parameter values
    // retires any unfinished multi-byte MIDI write without a data race.
    septum::sysex::PatchDataDecoder liveSysExDecoder;
    std::atomic<std::uint64_t> liveSysExRevision { 0 };
    std::uint64_t appliedLiveSysExRevision { 0 };
    void resetPerformanceControllers() noexcept;
    void observeMidiActivity (const juce::MidiMessage&) noexcept;
    void applyTempoSource() noexcept;
    septum::MidiTempoClock midiTempoClock;
    std::atomic<float>* clockSourceValue { nullptr };
    std::atomic<float>* systemTempoValue { nullptr };
    int appliedClockSource { 0 };
    double hostTempoBpm { 0.0 };
    void applyProgram (int index);
    void applyProgramAsync (int index);
    void setCurrentPresetName (const juce::String& name, std::uint64_t identityRevision);
    [[nodiscard]] juce::Result validatePresetState (const juce::ValueTree& state) const;
    // Writes a factory program straight into the cached raw-value atomics.
    // Allocation-free, so the audio thread can land a MIDI program change
    // without depending on the message loop ever running; the queued
    // reconcileProgram then repeats the untouched values with host/UI
    // notification.
    void writeProgramToParameters (int index) noexcept;
    void cacheParameterPointers();
    void resetPartEnablesToParameters() noexcept;
    // Pushes the SYSTEM COMMON settings at the engine. Allocation-free.
    void applySystemSettings() noexcept;

    // Audio-thread lookups resolved once at construction: raw-value atomics
    // aligned with the binding tables, and ranged parameters for the CC map.
    // processBlock must never build a juce::String.
    std::vector<std::atomic<float>*> upperValues, lowerValues, patchValues;
    // Plug-in-only controls: intentionally absent from Patch and SysEx maps.
    // Streamed native parameter writes leave these independent mutes intact.
    std::array<std::atomic<float>*, 2> partEnableValues {};
    // The audio thread's own copy of everything a received SysEx dump writes,
    // and which of those it has written since the message thread last looked.
    //
    // The vectors above are the parameter objects' own storage, and
    // setValueNotifyingHost writes it — so republishing a value read a moment
    // earlier put that older value back over whatever a later packet of the
    // same dump had stored in between. A dump is 22 packets and a whole block
    // of them could be lost that way. The shadows are what the republish
    // reads, and the mask keeps it from touching anything the audio thread has
    // not written, so a program change or a preset load on the message thread
    // is never republished over.
    std::unique_ptr<std::atomic<float>[]> upperShadow, lowerShadow, patchShadow;
    std::atomic<bool> patchDirty { false };

    // The arpeggio grid a received patch dump carried.
    //
    // It is the one piece of documented patch data with no plug-in parameter
    // to live in: a 32 x 16 grid of cells with one Original Note per row,
    // sixteen SysEx blocks of it. Without somewhere to keep it, every decoded
    // row was thrown away by the next `snapshotPatch()` — which rebuilds the
    // style from the selector — so a pattern imported from real hardware
    // neither played nor survived a re-export. It is kept here and used in
    // place of the selected template while the selector stays where it was
    // when the dump arrived; moving the selector picks a template, which is
    // what the hardware's panel does too.
    //
    // Readers pin a slot before copying its ordinary payload. A writer only
    // claims an unpinned, unpublished slot, so a suspended state-save thread
    // remains safe even after arbitrarily many subsequent MIDI dumps.
    struct ImportedArpeggioStyle
    {
        static constexpr std::size_t slotCount = 32;
        struct Slot
        {
            // -1: writer owns this slot; >= 0: number of pinned readers.
            mutable std::atomic<int> users { 0 };
            septum::ArpeggioStyle style {};
            // The selector this grid belongs to travels *in* the slot. Held
            // in an atomic of its own it could be observed a moment ahead of
            // its payload — a reader passing the selector check and then
            // copying the previous slot as though it were the new one.
            int selector { -1 };
        };
        std::array<Slot, slotCount> slots {};
        // Handed out to writers, so two of them never pick the same slot.
        std::atomic<std::uint64_t> reserved { 0 };
        // How many publishes have completed; the newest is slot
        // (published - 1) % slotCount, and zero means nothing is published.
        // This one store publishes the grid and its selector together.
        std::atomic<std::uint64_t> published { 0 };
        std::atomic<bool> valid { false };
    };
    // Mutable because `snapshotPatch()` is const and retires the grid when it
    // finds the selector has moved: the store is two atomics, and the object
    // is a cache in front of the parameters rather than part of them.
    mutable ImportedArpeggioStyle importedArpeggio;

    void publishImportedArpeggioStyle (const septum::ArpeggioStyle& style,
                                       int selector) noexcept;
    // Drop it. A factory program carries its own style, and the selector is
    // only a key: without this, a program whose style index happened to match
    // the one an imported grid arrived under played the imported grid instead
    // of its own template.
    void invalidateImportedArpeggioStyle() const noexcept;
    // Reports through `selectorMoved` that the grid on file was filed under a
    // different selector than the one asked for. Moving the selector chooses a
    // template, so that mismatch is normally the grid's cue to retire — but a
    // snapshot taken while a patch is being written holds a selector from one
    // revision and can meet a slot from the next, and retiring on *that*
    // mismatch throws away a grid nobody moved away from. Only a caller that
    // can show its selector and the slot came from the same revision may act
    // on the flag, and it can only show that after the read, never before it.
    // So the read itself never retires: it reports, and the caller decides.
    [[nodiscard]] bool readImportedArpeggioStyle (
        int selector, septum::ArpeggioStyle& out,
        bool* selectorMoved = nullptr, int* storedSelector = nullptr,
        std::uint64_t* observedTicket = nullptr) const noexcept;
    void writeImportedArpeggioToState (juce::ValueTree& state) const;
    void readImportedArpeggioFromState (const juce::ValueTree& state);
    std::atomic<float>* masterValue { nullptr };
    // SYSTEM COMMON: master tune in Hz, then key shift, keyboard octave and
    // transpose in the order systemParameterIds() lists them.
    std::atomic<float>* systemTuneValue { nullptr };
    std::atomic<float>* midiChannelValue { nullptr };
    std::atomic<float>* receiveProgramValue { nullptr };
    std::atomic<float>* deviceIdValue { nullptr };
    std::atomic<float>* activeSensingValue { nullptr };
    // Active Sensing starts only after FE. Count rendered samples so offline
    // hosts and arbitrary buffer sizes share the documented 420 ms timeout.
    std::uint64_t activeSensingTimeoutSamples { 0 };
    std::uint64_t activeSensingSamplesRemaining { 0 };
    bool activeSensingArmed { false };
    int appliedMidiChannel { 1 };
    std::vector<std::atomic<float>*> systemValues;
    std::vector<std::atomic<float>*> externalValues;
    // The input bus arrives in the same buffer the output is written to, so
    // it is copied out before that buffer is cleared.
    std::vector<float> externalInputL, externalInputR;
    struct CachedCc
    {
        int controller { -1 };
        juce::RangedAudioParameter* parameter { nullptr };
        // The parameter's own raw value, which is what the engine snapshots.
        // The audio thread writes this and nothing else; the parameter object
        // and the host are caught up on the message thread.
        std::atomic<float>* raw { nullptr };
        bool signedValue { false };
        bool keyFollow { false };
        std::atomic<float>* pitchWide { nullptr }; // Coarse pitch CC wire scaling.
        std::uint32_t pitchAddress { 0 }; // Address of this oscillator's WIDE/coarse pair.
    };
    std::vector<CachedCc> ccCache;
    // The value the audio thread last wrote, kept where only it writes.
    //
    // `CachedCc::raw` is the parameter object's own storage, and
    // setValueNotifyingHost writes it: publishing a value read a moment
    // earlier put that older value back over anything a CC had stored in
    // between, and the dirty bit the newer CC had set then made the next pass
    // republish the stale value it had just been overwritten with. The
    // controller's value was lost outright, not merely delayed. The shadow is
    // what the message-thread pass reads, so the newest value always wins.
    std::unique_ptr<std::atomic<float>[]> ccShadow;
    // Which cached CCs the audio thread has written since the message thread
    // last looked. One bit per entry in ccCache.
    std::array<std::atomic<std::uint64_t>, 2> ccDirty { 0u, 0u };
    // Catches the parameter objects and the host up with the raw values a
    // received CC wrote on the audio thread. Coalescing, so a knob sweep of
    // 128 messages a second costs one message-thread pass per frame rather
    // than 128.
    // Requesting host/UI publication from the callback must not allocate or
    // post an OS message. One message-thread timer polls these atomic flags.
    struct CcReconciler final
    {
        explicit CcReconciler (SeptumAudioProcessor& o) : owner (o) {}
        void triggerAsyncUpdate() noexcept { pending.store (true, std::memory_order_release); }
        void poll() { if (pending.exchange (false, std::memory_order_acquire)) owner.reconcileControlChanges(); }
        std::atomic<bool> pending { false };
        SeptumAudioProcessor& owner;
    };
    CcReconciler ccReconciler { *this };
    // The same shape for a whole patch, after a SysEx dump lands on the audio
    // path.
    struct PatchReconciler final
    {
        explicit PatchReconciler (SeptumAudioProcessor& o) : owner (o) {}
        void triggerAsyncUpdate() noexcept { pending.store (true, std::memory_order_release); }
        void poll() { if (pending.exchange (false, std::memory_order_acquire)) owner.republishPatchParameters(); }
        std::atomic<bool> pending { false };
        SeptumAudioProcessor& owner;
    };
    PatchReconciler patchReconciler { *this };

    // [settled] Universal Realtime device control: "the Universal Realtime
    // messages ... will be set automatically" (MIDI Implementation v1.00
    // p. 2). Three of them name SYSTEM COMMON parameters this replica
    // publishes -- Master Volume, Master Fine Tuning, Master Coarse Tuning --
    // so they are received onto those parameters. They arrive on the audio
    // thread and take the same split every other received message does: raw
    // atomics here, host and UI notification from the queued pass.
    bool handleDeviceControlSysEx (const std::uint8_t* data,
                                   std::size_t size) noexcept;
    // MASTER LEVEL, MASTER TUNE, MASTER KEY SHIFT, in that order.
    static constexpr std::size_t deviceControlCount = 3;
    std::array<juce::RangedAudioParameter*, deviceControlCount>
        deviceControlParameters { nullptr, nullptr, nullptr };
    std::array<std::atomic<float>*, deviceControlCount>
        deviceControlValues { nullptr, nullptr, nullptr };
    // The audio thread's own copy, for the reason `ccShadow` exists: the
    // pointers above are the parameter objects' storage and
    // setValueNotifyingHost writes it, so publishing a value read a moment
    // earlier put it back over a message that had arrived in between.
    std::array<std::atomic<float>, deviceControlCount> deviceControlShadow {};
    std::atomic<unsigned> deviceControlDirty { 0u };
    struct SystemReconciler final
    {
        explicit SystemReconciler (SeptumAudioProcessor& o) : owner (o) {}
        void triggerAsyncUpdate() noexcept { pending.store (true, std::memory_order_release); }
        void poll() { if (pending.exchange (false, std::memory_order_acquire)) owner.republishSystemParameters(); }
        std::atomic<bool> pending { false };
        SeptumAudioProcessor& owner;
    };
    SystemReconciler systemReconciler { *this };
    std::vector<float> monoScratch;
    bool prepared { false };

    septum::Engine engine;
    std::atomic<int> activeVoices { 0 };
    std::array<std::atomic<int>, 2> partActiveVoices { 0, 0 };
    std::array<std::atomic<int>, 2> partHeldVoices { 0, 0 };
    std::atomic<int> currentProgram { 0 };
    // A MIDI program change only advances this atomic revision. An in-flight
    // file save cannot attach its older name to a subsequently loaded sound.
    // The string/lock are used by editor and host callbacks, never by audio.
    std::atomic<std::uint64_t> presetIdentityRevision { 0 };
    mutable juce::CriticalSection presetNameLock;
    juce::String currentPresetName;
    std::uint64_t currentPresetNameRevision { 0 };

    struct UiNoteEvent
    {
        int note { -1 };
        int velocity { 0 };  // 0 = note-off
    };
    static constexpr unsigned uiQueueCapacity = 64;
    std::array<UiNoteEvent, uiQueueCapacity> uiQueue {};
    std::atomic<unsigned> uiWrite { 0 };
    std::atomic<unsigned> uiRead { 0 };
    std::atomic<float> uiBend { 0.0f };
    std::atomic<float> uiMod { 0.0f };
    std::atomic<bool> uiLeverDirty { false };
    // Overflow coalesces to the latest requested state per note. Retaining
    // presses as well as releases avoids clearing a release for a retrigger
    // whose note-on did not fit in the FIFO.
    std::array<std::atomic<std::uint64_t>, 2> forcedRelease { 0u, 0u };
    std::array<std::atomic<int>, 128> overflowUiVelocity {};
    // Set only while applyProgram sprays a program into the APVTS on the
    // message thread: the audio path then renders that factory patch
    // atomically instead of a half-updated parameter snapshot. MIDI program
    // changes do not stage — they write the raw values directly.
    // Program index+1 in the low seven bits, its selection revision above.
    // One atomic prevents a later MIDI selection from consuming an older
    // message-thread staged program under the later revision.
    std::atomic<std::uint64_t> stagedProgram { 0 };
    // A revision plus active-writer count guards complete snapshot reads.
    // Generation parity alone is insufficient: two concurrent parameter
    // sprays make an even generation while both are still writing. Readers
    // reject every active writer without making the audio thread wait.
    // ParameterWriteAccess serializes complete writes; this revision guard
    // also protects readers that do not take that gate, including state save.
    std::atomic<std::uint32_t> patchGeneration { 0 };
    std::atomic<std::uint32_t> activePatchWriters { 0 };

    struct PatchWriteScope
    {
        explicit PatchWriteScope (SeptumAudioProcessor& processor) noexcept
            : owner (processor)
        {
            owner.activePatchWriters.fetch_add (1, std::memory_order_acq_rel);
            generation = owner.patchGeneration.fetch_add (1, std::memory_order_acq_rel) + 1u;
        }
        ~PatchWriteScope() { finish(); }
        void finish() noexcept
        {
            if (! active) return;
            owner.patchGeneration.fetch_add (1, std::memory_order_acq_rel);
            owner.activePatchWriters.fetch_sub (1, std::memory_order_acq_rel);
            active = false;
        }
        SeptumAudioProcessor& owner;
        std::uint32_t generation {};
        bool active { true };
        PatchWriteScope (const PatchWriteScope&) = delete;
        PatchWriteScope& operator= (const PatchWriteScope&) = delete;
    };

    [[nodiscard]] bool patchSnapshotStable (std::uint32_t generation) const noexcept
    {
        return activePatchWriters.load (std::memory_order_acquire) == 0u
            && patchGeneration.load (std::memory_order_acquire) == generation;
    }

    std::atomic<int> pendingProgram { -1 };
    struct ReconciliationState
    {
        explicit ReconciliationState (SeptumAudioProcessor& o) : owner (&o) {}
        juce::CriticalSection lock;
        SeptumAudioProcessor* owner;
    };
    // Timer ownership stays on the message thread. Destruction on a host
    // worker detaches under the state lock; the next tick disposes the timer.
    // DeletedAtShutdown also covers hosts that never pump their message loop.
    struct ReconciliationTimer final : private juce::Timer, private juce::DeletedAtShutdown
    {
        explicit ReconciliationTimer (std::shared_ptr<ReconciliationState> s) : state (std::move (s))
        {
            startTimerHz (30);
        }
        ~ReconciliationTimer() override { stopTimer(); }
        void timerCallback() override
        {
            // Keep the state alive if this callback disposes the timer.
            const auto keepAlive = state;
            const juce::ScopedLock guard (keepAlive->lock);
            if (auto* owner = keepAlive->owner)
            {
                const int program = owner->pendingProgram.exchange (-1, std::memory_order_acquire);
                if (program >= 0 && owner->getCurrentProgram() == program)
                    owner->reconcileProgram (program);
                owner->ccReconciler.poll();
                owner->patchReconciler.poll();
                owner->systemReconciler.poll();
            }
            else
                delete this;
        }
        std::shared_ptr<ReconciliationState> state;
    };
    std::shared_ptr<ReconciliationState> reconciliationState;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (SeptumAudioProcessor)
};
