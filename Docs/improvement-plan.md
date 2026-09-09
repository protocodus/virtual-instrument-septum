# Septum improvement plan

Source audit: 2026-09-09. Source line references below refer to the audited baseline.
Constraint: no access to a physical SH-201 for new recordings.

UI implementation update: the hardware-inspired editor, prominent
part tabs, independent ON/OFF mutes, real per-part activity, and consolidated header
routing are now implemented. The complete dark background follows the edited part
with coral Upper or cyan Lower fills at different opacities. Only the selected
part tab glows; repeated part badges and decorative tab borders are removed.
Selection remains visible when muted, with its sound controls disabled and dimmed.
ON/OFF sits beside each part title. Mutes use a 7.5 ms ramp. Streamed SysEx parameter
edits preserve mutes; explicit native file imports/program loads reset them.

Audio implementation update: A1 now has deterministic raw float-WAV renders,
exact patch/MIDI manifests, numerical comparisons and an official-bank extractor.
A2 is implemented as an isolated reference-rate prototype and remains outside
the plug-in because of its control-cadence, CPU and input/event timing tradeoffs.
The shipping output circuit now uses the schematic's active Sallen-Key topology
with component-derived coefficients and 8x evaluation; the previous independent
RC approximation was incorrect. The native-rate oscillator, voice-filter and
envelope voicings remain unchanged pending stronger calibration evidence.
The next A5 increment fixes SysEx audio gaps, smooths gain and pan changes,
keeps bypassed effects decaying and improves fractional-delay reconstruction.
See [five additional quality improvements](fidelity/quality-round2.md) and
[circuit measurements, limitations and reproduction](fidelity/README.md).

## Recommended direction

Make Upper and Lower persistent, prominent parts of the interface. Each needs an
unambiguous edit target, a separate ON/OFF control, its keyboard routing, and
activity measured by the engine. Keep the warm Upper / cool Lower identity.

For audio, first make the current sound consistent across host sample rates and
build reproducible comparison tools. Then improve the filter/envelopes, Super Saw,
FB OSC and effects using the strongest available references. The current engine
already implements most synthesis features; its main fidelity gaps are the
undetermined mappings and algorithms behind those features.

Without matched hardware captures, distinguish a verified implementation fix,
a match to a public recording, and a preferred sound. These are different claims.

## Findings in the current source

| Finding | Evidence | Consequence |
| --- | --- | --- |
| Small Upper/Lower edit tabs already exist in the header. | `Source/PluginEditor.cpp:744`, `:1524` | Enlarge and consolidate the existing concept rather than introduce another selector. |
| Selecting an edit tab rebinds per-tone controls and saves `editingUpperTone` without changing sound. | `Source/PluginEditor.cpp:940`, `:1212` | Preserve this consistent editing behavior. |
| The separate bottom `PART` selector controls which tone receives new notes in Single. | `Source/PluginEditor.cpp:710`; `Source/DSP/SeptumEngine.cpp:666` | Move routing into the same top area and rename it to explain its purpose. |
| `toneAudibility()` infers “sounds” and “IS SILENT” from routing parameters. | `Source/PluginEditor.cpp:887` | It is not audio activity; the wording can be false. |
| Changing Single's playing part does not clear previously active voices. | `Source/DSP/SeptumEngine.cpp:593`, `:3123` | A tone labelled silent can still be held or releasing. |
| Telemetry exposes master output and total voices, not each tone. | `Source/PluginProcessor.h:54`; `Source/PluginEditor.cpp:2053` | True per-part activity needs engine/processor work. |
| Color intensity currently also means edited or eligible to sound. | `Source/PluginEditor.cpp:1737`, `:1889` | Give editing, enable, routing and activity distinct visual signals. |
| Host rate drives oscillator phase increments and naive discontinuities. | `Source/DSP/SeptumEngine.cpp:434`, `:1711`, `:1737`, `:1863` | Aliasing, and therefore timbre, changes with host sample rate. |
| Cutoff, resonance and ADSR mappings are explicitly voiced. | `Source/DSP/SeptumEngine.h:41`, `:65` | The controls are implemented, but not calibrated to the instrument. |
| Super Saw combines related JP-8000 measurements with assumed mix and HPF. | `Source/DSP/SeptumEngine.h:121`; `Source/DSP/SeptumEngine.cpp:1475` | Similar architecture does not establish SH-201 identity. |
| FB OSC and effect algorithms contain substantial original choices. | `Source/DSP/SeptumEngine.cpp:1733`, `:2993`; `Source/DSP/SeptumPresets.cpp:24` | These deserve reference comparisons before further output-stage detail. |

## UI behavior to implement

### Top part strip

Move patch name/program selection and keyboard routing to the header. Directly
under it, place two large Upper and Lower tabs above the tone editor. Retain the
existing signal-path organization and make shared sections a clearly
labelled area. Keep per-tone delay/reverb sends with the tone's amp controls.

| Signal | Meaning | Presentation |
| --- | --- | --- |
| Part identity | Upper or Lower | Stable warm/cool accent and text, even when off. |
| Editing | All tone controls below affect this part. | Illuminate the selected tab and tint the complete dark instrument background coral for Upper or cyan for Lower. Group controls with translucent fills, without repeating part names on each section. |
| ON/OFF | This part's contribution is enabled or muted. | Separate labelled button; clicking it never selects another editor. |
| Keyboard routing | Which new keys reach the part. | `All keys`, `Below C4`, `C4 and above`, or `No keys in Single`. |
| Activity | What the engine is currently rendering. | Per-part voice count and level meter; status such as `Ready`, `Playing`, `Releasing`, `Off`. |

An OFF part remains selectable for inspection, with its sound controls disabled
until re-enabled. Selecting a part never changes routing or turns it on. Shared
controls remain available. Do not make the other tab unavailable just because it
is not selected.
Use text and shape as well as color; support keyboard focus and clear tooltips.

Show `Single / Layer (Dual) / Split` beside the tabs. In Single, expose `Play:
Upper / Lower` there; in Split, expose the split point. An enabled but unrouted
part must explicitly say `No keys in Single`. A previous release can still show
activity even though that part no longer receives new keys.

Keep keyboard zone colors independent of which part is edited. Highlight actual
note activity separately. Move system tuning and uncommon controller assignments
to a secondary area so they do not compete with part identity and patch selection.
Avoid globally shrinking every control to fit a larger header; assess the actual
plugin window at realistic laptop sizes.

### ON/OFF semantics

Recommend a reversible audio mute with a short gain ramp (prototype 5–10 ms):

- Apply it after each tone's level, expression and balance contribution and before
  dry summing and new delay/reverb sends.
- Preserve note, pedal, arpeggiator and envelope processing while muted. Held notes
  can resume at their current envelope state when re-enabled; notes released while
  muted must not return. The mute does not save CPU or reclaim voices.
- Preserve mode and polyphony: muting one tone in Dual does not turn the other
  into a ten-voice Single tone. Split boundaries remain unchanged.
- Let existing shared delay/reverb tails decay. A single tone cannot be extracted
  from a shared effect buffer; show shared effect activity separately.
- Do not implement OFF by writing AMP LEVEL, TONE BALANCE or KEYBOARD MODE.

Publish per-part aggregate audio levels and voice/gate counts from the audio
thread. The UI must not inspect mutable voices. Measure the summed tone signal
after its gains/mute and before shared effects; label it as part contribution,
since the master output can still be zero. Use a short visual hold/decay so brief
notes are visible at the current 24 Hz editor refresh. Voice allocation alone
does not prove audible output; e.g. a running envelope can have level zero.

### State and compatibility

Add stable, plugin-specific automatable enable parameters, default ON/ON. Preserve
all existing parameter IDs, enum values and the non-automatable edit preference.
Keep enable state outside the SH-201-compatible patch/SysEx contract.

Old DAW sessions without the extension migrate explicitly to ON/ON; newer session
restores preserve both enables. Recommended native program/SysEx load policy:
restore ON/ON, while keeping the chosen edit target. A future native plugin preset
format may include the extension. SysEx export cannot represent independent mutes.

Review the existing parameter-publication concurrency limits before extending state
load paths (`README.md`, Known concurrency limits). Also audit the hidden use of
`keyboardPart` for external audio-filter LFO selection
(`Source/DSP/SeptumEngine.cpp:2690`); the existing UI's dimming does not prove a
parameter has no effect outside Single.

## Audio work without hardware access

| Order | Work | Deliverable and acceptance |
| --- | --- | --- |
| A1 | Build comparable dry renders and a reference manifest. | Exact raw patch, MIDI, initial random state, rate, gain, output path and source provenance. Add raw unnormalised renders for measurements and separate level-matched listening copies. |
| A2 | Prototype a fixed internal synthesis rate and a resampling boundary. | Same intended alias spectrum across 44.1/48/88.2/96 kHz hosts; preserved note/control timing, correctly reported latency, safe external-input conversion and acceptable CPU. Treat 44.1 kHz as a provisional reference choice. |
| A3 | Characterize filter and envelope behavior. | Response/envelope plots over raw values 0/32/64/96/127, all filter modes/slopes, resonant onset and sustain/retrigger cases. Use public dry demonstrations where controls can be established; retain existing voicing when evidence is insufficient. |
| A4 | Compare Super Saw and FB OSC candidates. | Match spread trajectory, bass removal, centre/side levels, spectral evolution and feedback partial structure. Evaluate several notes/registers, not one appealing patch. |
| A5 | Improve effects and performance behavior. | Delay timing/modulation, reverb decay/early reflections/stereo behavior, overdrive curve, LFO retrigger/fade, glide and stealing comparisons. Keep uncertain hardware behavior explicitly open. |

A2 should begin with an isolated prototype before moving the entire engine behind
a rate converter. Assess oscillator-only versus whole-voice processing, existing
overdrive latency/oversampling, event scheduling, external input and effects.
Upsampling naive waveforms at every host rate would change their alias pattern;
ordinary “more oversampling” is not itself a fidelity criterion.

The repository's driver documentation supports a 44.1 kHz device audio stream.
That alone does not prove the internal rate of every hardware synthesis block.
Consistent plugin output is directly testable now; choosing the closest hardware
alias model remains a separate evidence question.

Use Roland's public recordings as character references where patches/mastering are
unknown. Seek official parameter documents and publicly available matching patch
data, recording uncertainty in the manifest. Public wet demos cannot determine a
unique oscillator/filter model. Preserve the existing blind-listening convention
in `Docs/decisions.md`: preferences may guide sound design but do not close a
hardware calibration question. Do not require new hardware recordings to start A1
or A2, or claim exact calibration from unpaired public demonstrations.

### Verified rate inconsistency

A temporary source-only probe rendered one A6 (1,760 Hz) through Super Saw at spread
zero, one oscillator, filter bypass, no overdrive/delay/reverb, velocity 127 and a
two-second hold. The final one second was measured with a Hann window; levels are
relative to the fundamental. The probe did not change repository source.

| Host sample rate | Component at 15,940 Hz | Component at 19,840 Hz |
| --- | ---: | ---: |
| 44.1 kHz | −33.38 dBc | −57.21 dBc |
| 48 kHz | −67.70 dBc | −33.95 dBc |
| 96 kHz | −83.90 dBc | −55.17 dBc |

The 16th harmonic at 28,160 Hz folds to different frequencies. This establishes
host-dependent model output, not which output is closer to an SH-201.

## Delivery sequence and checks

1. **UI state clarity and telemetry:** replace inferred silence wording, add
   per-part contribution/activity, enlarge tabs, consolidate routing, maintain
   shared/per-tone boundaries. Can proceed independently of audio calibration.
2. **Part ON/OFF:** add the real mute/state behavior, smooth gains, migrations and
   explicit shared-tail semantics.
3. **Audio comparison tools and rate prototype:** establish a repeatable baseline,
   compare candidate rate boundaries, then integrate a chosen design.
4. **Reference-led sound tuning:** filter/ADSR, Super Saw/FB OSC, then effects and
   performance. Record changed assumptions and patch-compatibility impact.

Meaningful UI checks: switch the edit target and move an actual rebound control;
verify only that tone changes. Cover both edit targets, all three modes, all four
enable combinations, Single part changes with active/releasing voices, split
boundaries, automation, pedal holds, arpeggio HOLD and re-enabling sustained notes.
Verify old/new state restore, editor reopening, program/SysEx load policy and
unchanged SysEx layout. Inspect default and compact windows and both tone colors.

Meaningful audio checks: retain finite-output, polyphony and codec tests; add
cross-rate spectral/time-domain comparisons with explicit tolerances, event timing
and block-size checks, latency alignment and CPU measurements. Use envelope timing
and spectral features for free-running oscillators, rather than requiring a
pointwise waveform null. Passing stability tests is not proof of sonic equivalence.

Baseline validation during this audit: `cmake --build build-dsp -j 4` succeeded;
`ctest --test-dir build-dsp --output-on-failure` passed **2/2** (`Septum.Engine`
and `Septum.RenderDemos`). This build has the plugin disabled; JUCE processor/UI
tests and live plugin inspection were not run. UI analysis used source and the
committed screenshot.

## Primary reference boundary

[Roland's SH-201 manual](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf#page=46)
documents Single choosing one tone and Dual/Split playing both with a separate
editing indication. On hardware, Upper/Lower also chooses playback in Single;
the proposed consistent edit-only tabs and independent mutes are deliberate plugin
usability choices. The documented mode/part/balance parameters do not include
independent Upper/Lower enables. Effect settings are shared with separate tone
send depths (pp. 63–64).

[Roland specifications](https://www.roland.com/jp/products/sh-201/) describe ten
voices and two tones within one MIDI part. The manual explicitly gives five
simultaneous layered notes in Dual. Septum also imposes five voices per tone in
Split; fixed 5+5 Split allocation was not confirmed from the primary manual in
this audit, so preserve current behavior pending stronger evidence.
