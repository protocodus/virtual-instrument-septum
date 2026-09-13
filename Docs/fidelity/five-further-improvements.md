# Five further improvements to SH-201 fidelity

Septum benefits most from correcting audible behavior that can be specified and tested independently of unknown Roland DSP code. The selected changes are clock-source synchronization, continuous SOLO portamento, correct reverb damping gains, feedback-oscillator synchronization, and MIDI Portamento Control. Each has a separate implementation commit and regression coverage. The changes improve specific behaviors; they do not establish overall hardware audio identity.

The audited starting point is commit `850bddf`. That version already contains substantial oscillator, envelope, filter, external-input, MIDI and output-circuit work. No new physical SH-201 recording was available for this investigation. Existing public-recording analyses were reviewed as evidence with their original performance and recording uncertainties preserved.

## Candidate ranking

The scores below are engineering judgments, not listening-panel results. Audible impact measures the size and relevance of the expected change in affected patches. Grounding measures confidence in the behavioral target, including direct manufacturer documentation and reproducible code defects. Complexity measures implementation and regression risk, including interactions with existing sessions.

Each dimension uses a 1–5 scale. Higher impact and grounding are better; higher complexity is harder. The comparison score is `0.45 × impact + 0.35 × grounding + 0.20 × (6 − complexity)`. Small score differences are not significant; the table makes the tradeoffs explicit rather than presenting them as measured probabilities.

| Rank | Candidate | Impact | Grounding | Complexity | Score | Decision |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | System, incoming MIDI and host tempo sources | 5 | 5 | 4 | 4.40 | Implement |
| 2 | Continuous pitch when another SOLO note interrupts a glide | 4 | 4 | 1 | 4.20 | Implement |
| 3 | Reverb HF/LF damping shelf endpoints | 4 | 4 | 2 | 4.00 | Implement |
| 4 | FB OSC source phase responds to oscillator SYNC | 4 | 3 | 1 | 3.85 | Implement with explicit inference boundary |
| 5 | MIDI CC84 one-shot glide and source-voice continuation | 4 | 4 | 3 | 3.80 | Implement |
| 6 | Replace Super Saw mix and tracked high-pass laws | 5 | 2 | 4 | 3.35 | Defer for isolated SH-201 captures |
| 7 | Replace FB OSC excitation waveform/topology | 5 | 1 | 3 | 3.20 | Defer for direct evidence |
| 8 | Reproduce hardware cutoff stepping | 3 | 3 | 2 | 3.20 | Defer until update cadence is measured |
| 9 | Broader filter resonance/cutoff recalibration | 5 | 2 | 5 | 3.15 | Defer; existing recordings do not uniquely identify it |
| 10 | Promote the fixed-rate engine prototype | 4 | 2 | 5 | 2.70 | Defer; internal hardware rate and integration costs unresolved |
| 11 | Global triangle polarity change | 3 | 2 | 3 | 2.65 | Reject current evidence; cross-preset conflict |
| 12 | Reconstruct proprietary reverb geometry | 4 | 1 | 5 | 2.35 | Defer for impulse/burst recordings |
| 13 | Invent noise or external-input slave SYNC | 2 | 1 | 4 | 1.65 | Reject unsupported mechanism |

Clock-source support receives the highest impact score because a wrong rhythmic rate affects an entire performance, including both arpeggiation and synchronized modulation. SOLO continuity is a smaller code change with a direct audible failure case. Reverb damping affects only wet sound, but errors accumulate through successive feedback passes. FB synchronization has modest implementation cost and clear functional relevance, while its exact internal topology remains the least certain selected item.

CC84 is relevant principally to external MIDI sequencing and legato performances. Its narrower use does not diminish the size of the defect when it is used: allocating another note or ignoring the glide changes articulation, pitch trajectory and polyphony. It is separate from ordinary SOLO continuity because it defines an explicit MIDI command with different voice-allocation and note-off semantics.

## Evidence quality

Roland's Owner's Manual and MIDI Implementation establish the instrument's exposed controls and supported messages.[^1][^2] They are strongest for behavior and parameter meaning. They generally do not disclose coefficient tables, smoothing, random-number generation or the synthesis program running on the custom DSP. A documented control is therefore a suitable target for a behavioral correction, but not a license to claim recovered firmware.

The MIDI 1.0 specification supplies the detailed CC84 contract, while the SH-201 documentation establishes that the instrument receives that controller.[^3] Roland's JP-8080 manual independently gives compatible worked examples, but remains corroboration from another instrument.[^4] MIDI Timing Clock's quarter-note relationship is also directly documented by the MIDI Association.[^5]

Roland's downloadable patches provide additional evidence that FB OSC and SYNC are intentionally exposed together. Two independently decoded examples are `ReverseMetal` in the PAD bank and `FB Harmonics` in the BASS bank.[^6][^7] Both have equal nominal oscillator pitches in the relevant tone. Their settings support the existence of the combination; they do not establish that a particular recording needs a nontrivial phase reset or identify the feedback buffer's reset behavior.

Original DSP research is useful for selecting sound mathematical realizations. Smith's shelf-filter treatment provides a numerical foundation for the damping correction.[^8] Szabo's Super Saw measurements concern the JP-8000/JP-8080, so they cannot by themselves resolve the SH-201-specific mix or high-pass choices.[^9] The distinction between same-device behavior, related-device measurements and a numerical model is retained throughout the implementation.

## Clock-source synchronization

The previous engine used the saved patch tempo at every arpeggio and tempo-synchronized LFO calculation. Incoming timing clocks and the host's BPM could not change those rates. A patch intended for a sequence at 120 BPM would continue at its own 60 BPM setting, even with a valid external clock stream.

The new control offers PATCH, SYSTEM, MIDI and HOST. PATCH preserves the existing saved-tempo behavior. SYSTEM uses a common tempo independent of program selection. MIDI consumes the incoming event stream, including USB MIDI delivered by the host. HOST is explicitly a plug-in extension using the DAW's BPM; it is not an assertion that Roland's USB setting means host playhead data. Roland's source-selection behavior is documented on Owner's Manual p. 68.[^1]

The engine receives an effective tempo without rewriting `Patch::tempo` or exported patch bytes. Both shared and voice-local LFOs use it, as do arpeggio step lengths and tied-gate calculations. Host tempo retains fractional precision. On external tempo changes, outstanding arpeggio deadlines scale with the tempo ratio, preserving the remaining musical duration instead of leaving a previously scheduled gate at the old rate.

MIDI timing is measured in rendered samples, making offline processing and live audio use the same timebase. The estimator averages up to six inter-clock intervals and can acquire after the second valid pulse. Its interval bounds allow the difference between two rounded absolute timestamps; a stricter half-sample tolerance incorrectly rejected valid 300 BPM streams at 22.05 and 32 kHz.

No-clock handling is explicit. Selecting MIDI pauses tempo-driven motion until a rate is available. A gap longer than the greater of 500 ms and three estimated intervals retires the estimate; new valid pulses reacquire it. That timeout and estimator are engineering choices rather than measured Roland firmware behavior. Free-running LFOs, voice envelopes and release handling continue independently.

HOST falls back to patch tempo if the playhead, optional BPM, or a finite positive value is unavailable. The implementation reads the playhead only inside the audio callback, as required by JUCE.[^10] It follows tempo rather than snapping arpeggio or LFO phase to a DAW bar, loop boundary, or transport start. MIDI Start/Continue/Stop and song-position reconstruction are outside this change; the SH-201 implementation chart does not establish support for those commands.[^2]

Clock source and system tempo are appended host parameters. Native preset format 3 carries them; versions 1 and 2 and older DAW sessions receive explicit PATCH/120 defaults. Existing parameter identifiers and patch SysEx structures retain their meaning. The editor exposes CLOCK, PATCH BPM and SYS BPM in the performance section.

## Continuous SOLO portamento

A three-note lead phrase exposes the original defect. Play a note, start a long glide to a second note, then press a third before the second pitch is reached. In SOLO mode, the engine jumped to the second note's target pitch before beginning the third glide. SOLO+LEGATO already preserved the current pitch, which showed that continuity had accidentally become dependent on envelope articulation.

The correction preserves the sounding pitch of a reused mono voice, while retaining the normal SOLO envelope attack. Fresh polyphonic voices still use the part's preceding pitch as their ordinary glide source. This separates the two observable requirements without changing the unmeasured time-control curve. Roland describes smooth portamento and the SOLO/LEGATO articulation distinction on p. 19.[^1]

The regression compares interrupted and return-to-held-key phrases with an independent continuous-pitch reference. It covers both parts, both oscillators, ascending and descending intervals, several sample rates and two block sizes. A positive test verifies that SOLO still retriggers its amplitude attack. The maximum waveform error in the distinguishing fixtures changed from approximately 0.024309 full scale to zero. Detailed reasoning and reproduction are in [the continuity audit](source-audits/portamento-continuity.md).

This correction is most relevant to quickly played leads and bass lines with long glide settings. It does not claim to calibrate Roland's exponential or linear glide law, exact duration table, velocity treatment, or every voice-stealing case.

## Reverb damping

The original damping filters combined a direct signal with a recursive low-pass smoother. Its high-frequency endpoint was not zero. Consequently, requesting HF −36 dB at a 4 kHz corner produced only about −10.989 dB at Nyquist at 44.1 kHz. Conversely, LF damping at −36 dB and 4 kHz also reduced the high-frequency endpoint by 2.690 dB. The defect changed the spectral balance of repeated reverb circulation.

The replacement realizes first-order complementary shelves with the requested endpoint gain and a unity opposite endpoint. Roland supplies the independent damping controls and ranges; the chosen order and transition shape remain a model.[^1][^8] Direct sound, delay routing, reverb line geometry and HIGH CUT keep their existing roles. Neutral damping remains exact unity.

A full-engine 12 kHz burst probe illustrates the effect below Nyquist. With 4 kHz damping corners and the same neutral reference, LF −36 dB tail energy rises from 0.030617 to 0.628444 of neutral, while HF −6 dB falls from 0.015525 to 0.003286. Those are changes of +13.12 dB and −6.74 dB respectively in the measured 0.3–0.6 second window. They demonstrate a material change in the intended frequency region, not a measured reduction in distance to hardware.

The tests inspect endpoints, complex response, passive gain, neutral behavior, full-engine tails, block partitioning and live frequency changes. The implementation also handles published corners that cannot be represented below Nyquist at a low host sample rate. See [the damping audit](source-audits/reverb-damping-shelves.md) for formulas, exact fixtures, automation handling and limitations.

## Feedback-oscillator synchronization

The previous SYNC branch explicitly excluded FB OSC as the slave oscillator. With OSC2 inaudible in the mix, switching between MIX and SYNC could therefore produce identical output even when the oscillator pitches differed. Classic slave oscillators and Super Saw already responded to sync.

The correction applies the existing fractional OSC2-wrap position to the feedback oscillator's excitation phase. It keeps the feedback delay and damping history. This is the smallest local interpretation of the generic oscillator-reset behavior, supported by the documented SYNC function and published patch combinations.[^1][^6][^7] It avoids adding a new excitation waveform, clearing a resonator on every period, or changing unrelated oscillators.

Tests isolate zero-feedback phase behavior, then check that nonzero feedback remains active and that MIX/SYNC become distinguishable. The fractional-ramp reference error is below `7.4e-8` at 44.1, 48 and 96 kHz. Seven of ten focused checks fail against the original implementation; all pass with the correction. The full existing engine suite also passes.

This is the selected change with the largest remaining topology uncertainty. It restores a missing behavioral response, but the exact SH-201 feedback-oscillator reset has not been measured. An isolated FB OSC capture at unequal oscillator pitches would be the best next check. [The FB SYNC audit](source-audits/feedback-sync.md) records that boundary and the decoded preset evidence.

## MIDI Portamento Control

Previously CC84 merely overwrote the part's remembered pitch. The portamento switch could still suppress the following glide, and a polyphonic source note could receive an additional voice instead of continuing its existing sound. Those failures are distinct from normal keyboard SOLO behavior.

The MIDI contract makes the command a source designation for one following note. A sounding source continues without a fresh attack; otherwise the supplied note specifies the starting pitch. The command overrides the ordinary portamento switch for that transition.[^3] The implementation consumes the pending designation once, distributes it to both directly played tones in Dual, and preserves the target note's release ownership.

Voice lookup is bounded by the existing voice pool and introduces no allocation. Pending control state is cleared by reset and panic paths, including the processor's controller-reset handling. Zero glide time remains immediate. The interaction between arpeggiator-transformed input and hardware MIDI remote-keyboard settings is not established by this work; generated arpeggio notes do not inherit a stale designation.

Regression coverage includes switch-off operation, existing-source continuation, source and target note-off order, one-shot routing in Split and Dual, unrelated polyphonic voices, zero time, and reset behavior. See [the CC84 audit](source-audits/midi-portamento.md) for the exact source contract and final measurements.

## Why larger timbre changes remain deferred

Changing more oscillator or filter constants would be easy to hear, but that alone does not make it a fidelity improvement. The existing [Moogie waveform investigation](source-audits/moogie-oscillator-shape.md) shows why: fitting a small subset of harmonics produces plausible-looking models that fail additional harmonics. The recordings cannot yet separate oscillator shape, phase, filter behavior and recording processing uniquely.

Likewise, a global triangle inversion improves several Dist Bs 1 measurements but worsens some Moogie odd-harmonic ratios. Promoting it would encode one recording's ambiguity as a universal oscillator rule. The existing [distortion/phase audit](source-audits/dist-overdrive-phase.md) remains the appropriate record of that hypothesis.

A new Super Saw mix or high-pass law has a stronger related-instrument foundation than an arbitrary guess, but the existing implementation already incorporates that literature.[^9] Additional reuse of JP-8000 evidence does not increase confidence that a specific SH-201 setting is correct. The next useful evidence is a dry SH-201 spread sweep with oscillator isolation, not another fit to a different model.

The isolated fixed-rate prototype addresses host-rate consistency, yet the documented USB stream rate alone does not establish the internal clock of every synthesis block. Its existing cost and event/input integration questions remain relevant. Similarly, generic modern hard-sync antialiasing can improve numerical quality without matching a digital instrument's alias spectrum; the original DAFx work is algorithmic evidence rather than a hardware identification.[^11]

The next hardware session should prioritize short discriminating captures: FB OSC MIX/SYNC at unequal pitches; Super Saw spread at several notes; wet noise bursts for independent LF/HF damping controls; and rapid SOLO/CC84 glide sequences. Keep MIDI, patch bytes, system settings, sample rate, gain and capture path fixed and archived. Hold back at least one note or setting from any fit, then test it before changing a global model.

## Validation and reproduction

The starting DSP build passed all 11 existing CTest suites. The new focused suites exercise the actual audio path where possible, with analytic or independently scheduled references and explicit cases that distinguish the previous behavior. Passing them demonstrates those contracts, not a null match with a physical instrument.

For the DSP suites:

```sh
cmake -S . -B build-fidelity -DCMAKE_BUILD_TYPE=Release -DSEPTUM_BUILD_PLUGIN=OFF -DBUILD_TESTING=ON
cmake --build build-fidelity --parallel
ctest --test-dir build-fidelity --output-on-failure
```

Enable `SEPTUM_BUILD_PLUGIN` to include the processor's host/MIDI timing, session migration and native preset tests. `SeptumPluginProcessorTests --editor-snapshots <directory>` produces editor views for visual inspection. The final integrated validation record is maintained in [the results file](five-further-validation.md).

## Sources

[^1]: Roland Corporation. [SH-201 Owner's Manual](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf), 2006. Printed pp. 19, 32, 62–63, 68 and 72. Primary behavioral source.
[^2]: Roland Corporation. [SH-201 MIDI Implementation](https://cdn.roland.com/assets/media/pdf/SH-201_MI.pdf), March 1, 2006, version 1.00. Printed pp. 1, 4 and 9. Primary message/address contract.
[^3]: MIDI Manufacturers Association / Japan MIDI Standards Committee. [MIDI 1.0 Detailed Specification](https://www.seriesten.org/docs/protocols/MIDI_1.0_Detailed_Specification.pdf#page=21), document version 4.2.1, February 1996, printed pp. 16–17; public mirror of the original specification.
[^4]: Roland Corporation. [JP-8080 Owner's Manual](https://cdn.roland.com/assets/media/pdf/JP-8080_OM.pdf#page=192), printed p. 192, Portamento Control examples. Related-instrument corroboration.
[^5]: MIDI Association. [About MIDI—Part 3: MIDI Messages](https://midi.org/about-midi-part-3midi-messages), System Real Time section. Primary explanation of Timing Clock.
[^6]: Roland. [SH-201 Additional Patch Download—100 PAD](https://www.rolandus.com/go/sh-201_patches/patch_pad.html), undated official archive; linked bank includes `ReverseMetal`. Decoded data are detailed in the FB SYNC audit.
[^7]: Roland. [SH-201 Additional Patch Download—100 BASS](https://www.rolandus.com/go/sh-201_patches/patch_bass.html), undated official archive; linked bank includes `FB Harmonics`.
[^8]: Julius O. Smith III. [Low and High Shelving Filters](https://www.dsprelated.com/freebooks/filters/Low_High_Shelving_Filters.html), *Introduction to Digital Filters with Audio Applications*, W3K Publishing, 2007. Mathematical realization, not Roland coefficients.
[^9]: Adam Szabo. [How to Emulate the Super Saw](https://www.adamszabo.com/internet/adam_szabo_how_to_emulate_the_super_saw.pdf), Royal Institute of Technology, 2010. Original JP-8000/JP-8080 measurements.
[^10]: JUCE. [AudioPlayHead::PositionInfo](https://docs.juce.com/master/classjuce_1_1AudioPlayHead_1_1PositionInfo.html) and [AudioProcessor::getPlayHead](https://docs.juce.com/master/classjuce_1_1AudioProcessor.html), official API documentation; implementation checked against the repository's JUCE 8.0.14 dependency.
[^11]: [Virtual Analog Oscillator Hard Synchronisation: Fourier series and an efficient implementation](https://www.dafx.de/paper-archive/details/C3p4ljTQMk9GMtSpRIU8-A), DAFx 2012. Primary algorithm research considered for the antialiasing alternative.
