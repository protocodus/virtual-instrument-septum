# Ten SH-201 fidelity corrections

Research date: 2026-09-12. Audited baseline: `0b80652324c5c8ad79cec38433173013bc45440e`.
This round corrects observable synthesis, audio-input and performance behavior.
It does not establish a bit-exact WSP DSP emulation. No firmware, ROM image,
factory patch bank or captured audio is embedded in these changes.

## Evidence and changes

| # | Correction | Baseline problem | Evidence and boundary |
| --- | --- | --- | --- |
| 1 | Independent key-triggered LFOs for each voice | A new note restarted the tone's shared LFO, changing modulation on already-held notes. | Roland's [key-trigger parameter, p.62](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf#page=62), corroborated by Jim Aikin's firsthand [SH-201 review, printed p.93 / PDF p.101](https://www.worldradiohistory.com/Archive-All-Music/Electronic-Musician/2007/EM-Electronic-Musician-2007-03.pdf#page=101), explicitly identifying polyphonic operation. The shared external audio filter still needs one modulation source. |
| 2 | A separate LFO fade for each note | Later notes in a held chord inherited an earlier note's completed fade. | Roland's [FADE TIME key-on diagram, p.62](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf#page=62). Fade duration mapping remains the existing approximation. |
| 3 | One-octave pitch-envelope depth | Maximum depth swept two octaves. | Aikin's [firsthand hardware review, printed p.92 / PDF p.100](https://www.worldradiohistory.com/Archive-All-Music/Electronic-Musician/2007/EM-Electronic-Musician-2007-03.pdf#page=100) reports the one-octave limit. The symmetric negative endpoint follows Roland's signed depth control; intermediate scaling remains unmeasured. |
| 4 | External-input codec DC filtering | External audio entered the engine without the codec's DC-removal response. | [Service Notes, printed pp.36-37 / PDF p.30](https://www.synthxl.com/wp-content/uploads/2020/01/Roland-SH-201-Service-Manual.pdf#page=30) identifies IC22 as AK4552. The [AKM datasheet, pp.5,10](https://static6.arrow.com/aropdfconversion/4b652a51de1d9eab252cb9f94d4747bd82ff56a5/ek4552.pdf#page=5) gives its ADC high-pass corner as 3.4 Hz at 44.1 kHz. A first-order response models that published characteristic, not unpublished codec coefficients or the whole input circuit. |
| 5 | Linear signed delay feedback | An invented cubic clipper compressed every delay-buffer write, changing repeat levels and adding distortion even at zero feedback. | Roland's [delay FEEDBACK parameter, p.63](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf#page=63) specifies a signed percentage and negative-polarity inversion. Removing the unsupported loop nonlinearity makes this ratio consistent at normal operating levels. Hardware overload behavior remains unknown. |
| 6 | Arpeggio onsets and gates scheduled on the sample grid | Processing ticks could postpone events and make timing depend on host buffer boundaries. | Roland's [GRID and DURATION definitions, p.66](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf#page=66) provide the musical timing target. Scheduling accuracy is an implementation correction, not a measurement of hardware clock jitter or its undocumented shuffle amounts. |
| 7 | Configurable MIDI receive channel | Every incoming channel played and controlled the instrument. | Roland's [RX/TX CHANNEL, p.68](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf#page=68), specifies channels 1-16. The plug-in compatibility option accepts all channels; this plug-in does not transmit MIDI. |
| 8 | Program-change receive switch | Incoming Program Change always replaced the sound. | Roland's [PROGRAM CHANGE receive switch, p.68](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf#page=68). This setting governs MIDI reception, independently of manually choosing a preset. |
| 9 | SysEx device identity | Live patch writes accepted a different unit's device address. | Roland's [DEVICE ID, p.70](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf#page=70), and [MIDI Implementation, pp.2-3](https://cdn.roland.com/assets/media/pdf/SH-201_MI.pdf#page=2), define device matching. Explicit file import remains distinct from live reception. |
| 10 | Active Sensing watchdog | Losing an active MIDI connection could leave sustained notes/controllers active indefinitely. | Roland's [MIDI Implementation, p.2](https://cdn.roland.com/assets/media/pdf/SH-201_MI.pdf#page=2), specifies monitoring after FE, a message gap exceeding 420 ms, sound/note/controller reset, then disarming. |

The original hardware is a digital modeling synth. Its schematic cannot reveal
its oscillator code, filter coefficient tables or envelope curves. A search for
SH-201 firmware/DSP reverse engineering did not supply verified WSP synthesis
source for this work. Existing Super Saw, FB OSC, filter and effect voicings
remain explicitly provisional where no new evidence resolved them. The project's
official wet-recording references are useful listening context; they are not dry,
sample-aligned measurements of these changes.

The sample-and-hold source also draws a new value at a restarted cycle as part
of correction 1. That follows the cycle interpretation of the control; neither
the pseudo-random generator nor its exact sequence is claimed to match Roland.

## Source provenance

The manuals and AKM datasheet are manufacturer documents. The service schematic
and AKM document are hosted by third-party mirrors. The Electronic Musician review
is a firsthand evaluation by Jim Aikin, March 2007, rather than a Roland engineering
specification. The relevant schematic and review pages were inspected visually.
Third-party documents remain outside the repository.

SHA-256 of the retrieved documents:

| Document | SHA-256 |
| --- | --- |
| Roland Owner's Manual | `b4a2968d429c7f3e907a6243723d5e803ae2e0014e8e9107c85bd966deea8e79` |
| Roland MIDI Implementation | `71a8fe00a8d232c494a5aba6885756d99e6650fc14671115260d9446c3009546` |
| Roland Service Notes | `b66d0e976d69860d542620ff2248e6c95f77157a6f1cb2037ff07fe0e582b76b` |
| AKM AK4552, [retrieved mirror](https://www.micro-semiconductor.com/datasheet/61-AK4552VT.pdf) | `79a2c76d56749492b311a5dbccc06b69a5db72328f8803da81cbb4e8ee86bbe2` |
| Electronic Musician, March 2007 | `704e78de8835901986529848cf405cb1dddfe2b97cdb573c21b4f97e176f24dc` |

## Regression measurements

Final integrated Release verification passed all 11 CTest suites. Standalone,
VST3 and Audio Unit built successfully for the local macOS architecture. All
11 demonstration WAVs were regenerated and their README peak table refreshed;
the quick fidelity renderer produced 32 raw fixture/rate measurements with
finite, audible output and patch/MIDI manifests.

The voice suite passes 138 checks, including audible modulation, staggered-note
superposition, both LFO slots, free and synchronized rates, fades, both oscillators'
pitch-envelope endpoints, and the shared AUDIO FILTER path. The initial 134-check
suite produced 50 failures when compiled against the unchanged baseline. The four
later checks protect the shared filter's existing behavior.

The performance suite passes 853 checks covering the codec response, signed delay
ratios, high-feedback modulation decay, arpeggio note/gate boundaries, ties across
pattern wrap, 120% overlap and tempo edits. Compiling it against the baseline
produced 417 failures. These baseline comparisons use the same test code and do
not compare two independently tuned presets.

| Render-path probe | Baseline | Corrected |
| --- | ---: | ---: |
| Maximum staggered-note LFO superposition error | About 0.013092 full scale | Below 0.0000002 |
| Late output of DC input ring-modulated by a sine | 0.0379701 peak | 0.00000000000465 peak |
| Relative first-echo error when input level increases tenfold | 0.000701 | 0.0000000649 |
| Measured +98% feedback repeat ratio | 0.97936815 | 0.98000002 |

The first-order codec model measures -0.12373 dB at 20 Hz at 44.1, 48, 96 and
192 kHz host rates. Maximum positive/negative delay feedback and maximum modulation
decay to below 0.000000054 peak in the final second of the stress fixture. The
arpeggio tests place deadlines on the first sample at or after the calculated
musical time, carrying fractional residuals to avoid accumulated period error.

The processor suite passes 3,977 checks, including all four MIDI corrections and
native-preset/DAW-state migration. Nine editor snapshots were generated; full and
compact layouts were inspected, and all 225 labels fit without condensation.
The system controls are appended to the host parameter list, preserving earlier
AU parameter ordering. Native preset format 2 stores the new controls; version 1
files and older DAW states receive explicit compatibility defaults.

A local Release cost check at 44.1 kHz, ten sustained voices, 256-sample blocks,
and the best of three ten-second renders used about 3.63% of one CPU core before
and 3.70% after with keyed LFOs; free-running LFOs used 3.58% and 3.49%. This is a
local smoke benchmark under concurrent work, not a precise speed comparison or a
portable performance promise. The new per-voice state and deadline scheduling
introduce no dynamic allocation in the render path.

## Reproduce

```sh
cmake -S . -B build-fidelity -DCMAKE_BUILD_TYPE=Release -DSEPTUM_BUILD_PLUGIN=OFF -DBUILD_TESTING=ON
cmake --build build-fidelity --parallel
ctest --test-dir build-fidelity --output-on-failure
```

Enable `SEPTUM_BUILD_PLUGIN` to also run the processor's MIDI reception,
serialization, UI and timestamp regressions. Tests verify the implementation
against explicit behavioral and numerical targets, not hardware audio identity.
