# Ten additional SH-201 fidelity improvements

The strongest remaining changes improve how documented sounds respond to notes, program selection and live controls. They do not justify another global change to the oscillator spectrum, filter curve or envelope time tables. This round therefore combines seven performance or timing corrections with three corrections to audio transitions. The starting point is commit `fdd6c75`, which already includes the previous five improvements: SOLO glide continuity, feedback-oscillator sync, reverb damping shelves, CC84 portamento and external tempo sources.

All ten changes are implemented separately. The evidence distinguishes manufacturer specifications, inferences from the instrument’s architecture, and numerical policies used to remove defects introduced by the plug-in. No new recordings from an SH-201 were available. Synthetic before/after renders demonstrate implementation differences; they are not hardware null tests.

## Selection

Scores are engineering judgments on a five-point scale. Audible impact considers both the size of the defect and the situations in which it occurs. Grounding considers the strength of evidence for the specific correction, rather than confidence that all surrounding sound synthesis is hardware-identical. Complexity includes implementation cost, compatibility and regression risk. The priority score is `2 × impact + 2 × grounding − complexity`; equal scores are not meaningfully distinct.

| Priority | Implemented candidate | Impact | Grounding | Complexity | Score | Evidence class |
|---:|---|---:|---:|---:|---:|---|
| 1 | Align AMP ENV with voice processing latency | 5 | 5 | 2 | 18 | Numerical defect with independent audio reference |
| 2 | Direct MIDI versus Remote Keyboard routing | 5 | 5 | 4 | 16 | Explicit SH-201 input behavior; bounded integration choices |
| 3 | Hardware bank selection and RX BANK | 4 | 5 | 2 | 16 | Exact manufacturer MIDI address mapping |
| 4 | PATCH REMAIN | 5 | 5 | 5 | 15 | Explicit feature; shared-effects and repeated-note boundaries |
| 5 | Direct MIDI bypasses keyboard transpose/octave | 4 | 4 | 1 | 15 | Manufacturer distinction plus MIDI transposition guidance |
| 6 | Shared ten-voice pool in SPLIT | 4 | 4 | 1 | 15 | Strong architectural inference; no allocation capture |
| 7 | Fractional SMF tempo in offline replay | 3 | 5 | 1 | 15 | Exact MIDI-file time representation and numeric counterexample |
| 8 | MIDI mono/poly mode reception | 3 | 4 | 1 | 13 | SH-201 chart; articulation choice informed by MIDI guidance |
| 9 | Smooth tone balance and effect sends | 4 | 3 | 2 | 12 | Documented controls; implementation smoothing policy |
| 10 | Crossfade reverb PRE DELAY and SIZE edits | 4 | 3 | 3 | 11 | Documented controls; published delay-transition method |

The ranking favors identifiable defects over broad feature counts. For example, a fixed processing delay that consumes a large part of a fast attack has stronger evidence than changing the attack table to make one recording resemble another. PATCH REMAIN ranks below several smaller corrections because it affects voice ownership, controllers and shared effects, despite its large performance benefit.

## Articulation and voice allocation

The oversampled overdrive implementation already delays the clean voice path to match its processed path. Its AMP envelope was evaluated after that transport without receiving equivalent delay. At 44.1 kHz, the 19-sample offset consumed approximately 43% of the existing fastest attack before the first oscillator sample arrived. The correction transports the existing envelope alongside the audio and keeps the voice alive until its delayed release samples drain. It changes neither envelope curvature nor the chosen time tables. This follows the documented AMP role and removes a numerical mismatch introduced by oversampling. [1][4]

An independent sine/envelope reference reduces full-transient relative RMS error from 0.371 to less than 4 × 10⁻⁸ at 44.1 kHz, and from 0.349 to the same numerical range at 48 kHz. A 192 kHz control, where the matched integer delay is zero, stays unchanged. Tests also exercise single-sample blocks, fresh voices, release completion and panic. These measurements establish alignment within Septum, not Roland envelope calibration. The [AMP audit](source-audits/amp-envelope-latency.md) gives the equations, rates and limits.

SPLIT previously assigned five voices to each part even if the other part was idle. Roland explicitly associates the polyphony reduction with DUAL’s two simultaneous tones; SPLIT plays one tone per key and the instrument specification gives ten voices. The implementation now reserves five per part only in DUAL, and lets SPLIT share the existing ten physical voices. A six-note chord in one split zone therefore keeps all six notes. This is a strong inference, while the exact hardware stealing priority remains unmeasured. [1]

The [SPLIT tests](source-audits/split-polyphony.md) cover both sides, ten-note capacity, overflow, DUAL’s unchanged limit, and SINGLE’s unchanged capacity. The old implementation fails 42 of 66 focused checks; the correction passes all 66. This fixes wasted capacity without increasing the overall voice budget or introducing a new voice-stealing model.

## Input and MIDI performance

Remote Keyboard requires separating an external sequencer’s sound-generator input from a keyboard driving the arpeggiator. The SH-201 manual says that external MIDI requires Remote Keyboard to drive the arpeggiator, and that the remote keyboard may transmit on any channel. Septum previously sent every accepted note through the keyboard route while rejecting foreign-channel notes. [1]

Two engine entry points now distinguish direct MIDI notes from keyboard notes. Voice and held-key ownership includes this source distinction, so a generated arpeggio note-off cannot terminate a sustained direct note at the same pitch. Pedals, SOLO return priority and live arpeggiator routing changes preserve it. The plug-in exposes MIDI NOTES as DIRECT, REMOTE and CHANNEL. DIRECT and REMOTE correspond to the documented off/on behaviors; CHANNEL is the compatibility default that preserves Septum’s former selected-channel arpeggiator input. Existing presets migrate to CHANNEL.

REMOTE exempts keyboard performance messages from receive-channel filtering. Program selection, panel edits and channel-mode commands retain that filter. The manual does not provide a message-by-message exemption list, so this boundary is an explicit integration choice. Changing input mode releases current keys and pedals while ordinary tails decay; ARPEGGIO HOLD keeps its chord as after physical key release. The [Remote Keyboard audit](source-audits/remote-keyboard.md) describes these boundaries and source-overlap tests.

The related transposition correction is independently useful. Keyboard OCTAVE SHIFT and TRANSPOSE previously retuned direct incoming MIDI, even though MASTER KEY SHIFT exists separately for global tuning. Direct notes now bypass the two keyboard shifts while retaining master shift, master tuning and per-tone octave/pitch settings. Manufacturer control definitions and the MIDI specification’s separate-transposition recommendation support that distinction, but no SH-201 direct-input capture establishes every live-edit detail. [1][3] Across 384 checks, the [direct-transposition fixture](source-audits/direct-midi-transpose.md) reduces its worst waveform error from 0.152 to zero.

Hardware bank selection is exact rather than inferred. MIDI Implementation p. 1 specifies decimal MSB 87, LSB 0 for PRESET and LSB 20 for USER, followed by program bytes 0–31. The printed LSB 020 is not hexadecimal 20. Previously CC0 and CC32 were ignored, so a sequence requesting a USER slot recalled a PRESET sound. The receiver now latches the bank until Program Change, rejects unsupported banks and respects an independent RX BANK switch. [2]

The plug-in keeps its existing flat program numbers until a channel explicitly selects a bank. ALL-channel compatibility mode maintains independent latches. These latches reset on audio preparation and are not session-persistent controller state. The mapped sounds remain Septum’s 32 authored presets and 32 initial user slots; the change does not supply Roland’s factory data. The [bank audit](source-audits/midi-bank-selection.md) includes full-slot, timestamp, audio and migration checks.

CC126 and CC127 were also absent. The SH-201 chart recognizes mono/poly modes and lists these messages as stopping existing sound. Reception now updates both tone modes and handles notes later in the same buffer under the new setting. CC126 selects SOLO+LEGATO, following the general MIDI mono articulation recommendation; its Mode 4 text leaves overlap behavior unspecified, so the precise SH-201 envelope response is still unmeasured. CC127 selects POLY. [1][3] The [mode audit](source-audits/midi-channel-modes.md) separates these two levels of evidence. The implementation keeps the existing instrument-wide panic scope for mode changes and the per-tone interpretation of mono in SPLIT.

## Program continuity

PATCH REMAIN preserves the current sound when selecting another patch. Septum previously replaced the tone parameters used by every sounding voice, so a held saw could turn immediately into the new oscillator/filter/envelope combination. A separate program-selection operation now retains each old voice’s tone and relevant common controls. Routine automation continues to edit the current program. [1]

Retained voices keep envelope state, LFO phase/random state, modulation and bend destinations, expression routing, balance and patch level. They can finish even after the new patch selects another keyboard part or has level zero. They still share the fixed ten-voice budget, and new SOLO/CC84 assignment cannot accidentally reuse an old program’s voice. The processor applies this operation once per selection revision, including MIDI changes inside an audio buffer, and publishes retained release length for host tail reporting.

Preserving patch level required moving it into the voice dry/send path. This also prevents a new patch’s level from rescaling an already-written effect tail and avoids applying a patch level to the independent external-input monitor. Delay and reverb remain one shared network and adopt the newly selected settings. The old arpeggiator stops and its final gate releases; a second independent sequencer/effects engine is not created. Same-pitch notes from the same input source retain the existing release-all policy across generations. These are implementation boundaries, not manufacturer promises about undocumented corner cases. The [PATCH REMAIN audit](source-audits/patch-remain.md) records the exact tested scope.

## Clock and live-control transitions

The offline MIDI renderer converted exact SMF microseconds-per-quarter tempos into an integer patch BPM. MIDI note timestamps remained exact, so a synced LFO or arpeggio could gradually diverge from those notes. The renderer now uses the existing fractional external-clock API without rewriting stored patch tempo. Range validation checks the exact value before replay, preventing an out-of-range tempo from becoming apparently valid through rounding. [3][6] The [fractional-tempo audit](source-audits/fractional-smf-tempo.md) includes tests for nonintegral tempos, invalid endpoints and identical output from different stored patch tempos under the same external clock.

Tone balance and delay/reverb send depths were additional abrupt gain paths. Other level controls already smooth live edits, but these controls multiplied running audio by a new value immediately. The new per-voice gain states walk to the existing targets at audio rate. Fresh voices start at their chosen gains, while steals, legato and retained voices preserve continuity. The smoothing duration is a project policy; the existing endpoint gains and mappings remain authoritative. This prevents an instantaneous send discontinuity from reappearing later as an echo or wet-tail click. [1]

The [send/balance audit](source-audits/effect-send-smoothing.md) records 807 passing checks at 44.1, 48 and 96 kHz; the isolated old path fails 42. The largest first-sample full-scale gain step falls from 1 to 0.00903, and irregular block partitions produce identical output. The 2.5 ms time constant reuses the engine's existing control-smoothing policy, without claiming a measured Roland response.

Reverb PRE DELAY and SIZE previously jumped integer read positions in filled buffers. Crossfading among fixed read positions avoids a discontinuity without introducing continuous delay glides. Nonnegative weights sum to one, and rapid retargeting preserves the current mixture. The original settled pre-delay positions, room geometries and damping/decay mappings remain in use. The 10 ms transition is a numerical quality choice informed by published delay methods, not an identified SH-201 firmware constant. [5]

The [reverb-transition tests](source-audits/reverb-geometry-transitions.md) check all 126 pre-delay positions, all eight sizes, repeated retargeting, panic, block fragmentation and six sample rates. In the 48 kHz fixture, the first-return transient measure improves by 21.7 dB for both controls. Ninety-six settled configurations produce identical complete-audio hashes before and after this isolated change. Stress tails remain finite and decay, although this is not a formal proof for every possible time-varying feedback schedule. Worst-case mixing work and memory are bounded.

## Alternatives not selected

| Candidate | Decision and evidence still needed |
|---|---|
| Complete SYSTEM COMMON DT1 reception | Valuable, but broader state, byte-fragment and routing work than the direct-note tuning correction. Existing universal master controls and patch DT1 remain available. |
| Different FB-OSC excitation or feedback law | No decisive SH-201 waveform/feedback sweep; a different excitation would globally change patches on weak evidence. |
| Another Super Saw spread, side mix or high-pass change | Existing choices include related-hardware measurements and listening decisions. Need SH-201 dry spectra at controlled spread values. |
| Global filter/envelope recalibration | Existing conditional fits disagree on withheld harmonics and lack a sufficient parameter grid. Need identifiable dry captures and repeated notes. |
| Always-on fixed internal synthesis rate | Prior prototype still has timing, CPU and conversion-latency tradeoffs; the codec’s USB rate does not prove every DSP block’s internal rate. |
| Bandlimited hard-sync redesign | May improve aliasing quality but could remove hardware character; compare isolated hardware sync spectra first. |
| Recorder, D Beam or local pedal assignment | Larger control-surface scope, with less immediate benefit to the current plug-in sound path. |
| Persist every MIDI bank/controller latch | Useful deterministic replay extension, but separate from the documented bank-number correction and existing transient controller policy. |

The next substantial timbre improvements should be driven by a small, repeatable hardware capture set: dry oscillator sweeps, pulse-width endpoints, feedback amount/pitch sweeps, filter responses at fixed cutoff/resonance points, and complete attack/decay/release traces. That evidence could justify changing physical mappings without fitting incidental recording conditions.

## Validation and delivery

Every candidate has its own conventional commit and focused regression evidence. The combined build, test totals, commit list and compatibility observations are recorded in [ten-more-validation.md](ten-more-validation.md). Audition artifacts use original procedural notes/input signals and one shared normalization gain per before/after pair. They retain event timelines and source revisions so differences can be reproduced.

## Sources

1. Roland Corporation. [SH-201 Owner’s Manual](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf), 2006. Printed pp. 18–19, 22, 27, 38–39, 46–47, 63–64, 68–69, 73–74. Control semantics, architecture, remote input, program continuity and MIDI chart.
2. Roland Corporation. [SH-201 MIDI Implementation, version 1.00](https://cdn.roland.com/assets/media/pdf/SH-201_MI.pdf), March 1, 2006. Printed pp. 1, 4–5. Bank map, system parameters and tone-mode enumeration.
3. MIDI Manufacturers Association and Japan MIDI Standards Committee. [MIDI 1.0 Detailed Specification, version 4.2.1](https://www.seriesten.org/docs/protocols/MIDI_1.0_Detailed_Specification.pdf), revised February 1996, archival specification copy. Printed p. 22 and Appendix A-6. General mono articulation and separate transposition guidance; Mode 4 overlap latitude is retained in the analysis.
4. Martin Holters. [Antiderivative Antialiasing for Stateful Systems](https://www.mdpi.com/2076-3417/10/1/20), *Applied Sciences* 10(1), 20, 2020, section 2. Numerical antialiasing/oversampling context; not evidence of Roland’s implementation.
5. Julius O. Smith III. [Physical Audio Signal Processing: Large Delay Changes](https://dsprelated.com/freebooks/pasp/Large_Delay_Changes.html), author-published DSP text, accessed September 13, 2026. Crossfading fixed delay positions.
6. Mido project. [Standard MIDI Files—MIDI Tempo vs. BPM](https://mido.github.io/mido/files/midi.html#midi-tempo-vs-bpm), official MIDI-file library documentation, accessed September 13, 2026. Microseconds per quarter note. See the fractional-tempo audit for exact representation and replay policy.
