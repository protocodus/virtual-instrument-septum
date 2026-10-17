# PATCH REMAIN

The [Roland SH-201 Owner's Manual](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf), printed p. 68, defines PATCH REMAIN as a system switch that maintains the sound of the currently sounding patch when another patch is selected. This is a direct behavioral requirement. Merely leaving voices allocated while replacing their oscillator, envelope and modulation parameters does not satisfy it: the old held note becomes the newly selected sound.

`Engine::changePatch(patch, remain)` now separates program selection from ordinary `setPatch()` parameter editing. With REMAIN enabled, active voices retain their tone parameters, patch level, tone balance, controller assignments/destinations and internal patch tempo. Oscillator, filter, envelope, overdrive and glide state continue. A free-running LFO copies the original tone's entire waveform/random state while preserving its individual note fade; it then runs independently of the newly selected tone. External/system tempo and performance controller values remain shared controls. Ordinary edits continue to affect current-program voices.

Retained voices form a separate assignment generation. New SOLO or CC84 notes cannot repurpose them through legato ownership, and the new program's mono held-key stack cannot retarget an old note. Physical note-offs keep their keyboard-versus-direct-MIDI ownership even if the new program changes its keyboard mode, selected part, split or arpeggiator routing. Hold, sostenuto and All Notes Off still release retained notes correctly. All generations share the existing ten physical voices and voice-stealing priority; repeated program changes allocate no extra voices. Disabling REMAIN stops existing audio at selection.

Patch level now scales each program's voice signal before the shared effects, with an audio-rate slew. Keeping it solely on the final output made preservation impossible when the new patch selected level zero. This also lets an existing effect tail keep the level with which it entered the effects. The numerical gain placement and smoothing policy are implementation choices rather than recovered hardware circuitry.

## Scope and evidence limits

The manual establishes preservation of the sounding patch; it does not disclose voice snapshots, allocation details across program changes or the treatment of all concurrent controller combinations. The per-voice implementation is a bounded realization of that audible contract, not a claim about Roland's firmware layout. The new program uses the existing shared delay, reverb and external-input processing, so changes to those settings can alter old voices or tails. The previous arpeggiator sequence stops at selection and its final sounding gate enters the original release; maintaining an independent old sequencer is outside this implementation. These are explicit boundaries, not documented hardware exceptions to PATCH REMAIN.

## Validation

`Tests/PatchRemainTests.cpp` compares retained dry audio with an unchanged reference engine. The test varies keyed/free-running triangle, sample-and-hold and random LFOs, rate and tempo synchronization, controller values/destinations, patch level, balance, waveform, filtering and release. It covers multiple selections, later live edits, old releases already in progress, new SOLO and CC84 ownership, keyboard/direct note-off separation, hold, sostenuto, All Notes Off, panic, arpeggiator replacement and ten-voice allocation across Single-to-Dual selection.

The pre-change path is compiled with `SEPTUM_PATCH_REMAIN_BASELINE`, which uses the former `setPatch()` behavior. Its first 72 checks failed 43 assertions; retained dry comparisons had approximately 0.993–0.995 relative RMS error. The corrected path passes those checks with retained audio within a relative RMS tolerance of 1e-6, plus six release/CC84/arpeggiator checks. The existing engine suite also passes all 4,599 checks. These tests verify documented behavior and internal continuity; hardware recordings would still be needed to compare effect transitions and exact program-change scheduling.

The processor exposes REMAIN as an appended system parameter, saved in
format-6 native presets and host state. Earlier formats migrate it to OFF.
UI/host program selection, incoming MIDI Program Change and explicit patch
loads mark a selection revision; ordinary parameter automation and streamed
DT1 edits do not. The audio thread calls `changePatch` once per selection and
uses `setPatch` for edits. A staged factory program carries its revision and
index in one atomic value, preventing a newer MIDI selection from consuming
an older staged program under the wrong revision.

The host tail estimate includes the longest active retained voice's original
release, published atomically from the audio thread. A new short-release
patch therefore cannot make the host truncate a retained long-release pad.
Processor tests compare old-tone audio across UI, MIDI and explicit loads,
REMAIN OFF termination, live edits, tail reporting and state migration.

Repeated notes with the same pitch and input source retain Septum's existing
release-all policy: one note-off releases matching voices across both old and
current patches. The note-off carries no patch-generation identifier. This
is an implementation boundary, not a recovered SH-201 repeated-note policy.
