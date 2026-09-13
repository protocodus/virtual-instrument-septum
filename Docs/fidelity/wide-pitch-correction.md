# WIDE pitch correction and the remaining timbre gap

2026-09-13. **The importer treated the normal PITCH range as three octaves instead of one.** Cotton Wool, Pedal Bs 1 and SupaJuce 1 recordings support a one-octave interval where the previous implementation produced three octaves. This correction applies to both oscillators in both tones, SysEx import/export, live fragmented messages and panel MIDI CCs. It does not add EQ or modify the published preset bytes.

## Evidence and correction of the earlier conclusion

The [Owner's Manual, p. 29](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf) describes semitone steps over ±1 octave, expanded to ±3 octaves by WIDE. Page 60 says the parameter table gives Editor display values. The [MIDI Implementation, p. 5](https://static.roland.com/assets/media/pdf/SH-201_MI.pdf) lists raw coarse 28–100, displayed −36…+36, and a separate WIDE switch. Unlike Master Coarse Tune, that oscillator row does not explicitly give a semitone unit. The official Editor XML binds the display to raw minus 64; it does not establish the subsequent DSP conversion.

**Our earlier conclusion that dividing normal-range coarse by three contradicted the documentation was wrong.** The resources establish the stored and displayed values, not that those values remain physical semitones with WIDE off. The corrected interpretation is supported by independent oscillator intervals:

| Original published preset | Stored oscillator controls | Hardware recording |
|---|---|---|
| Cotton Wool, PAD 01 | Super Saw coarse 0; sine signed raw −36/fine −7; both WIDE off | Isolated low sine near 65.15 Hz with a Super Saw family near 130.8 Hz |
| Pedal Bs 1, BASS 04 | Same oscillator setup | Pairs around 32.22/65.06, 38.44/77.76 and 57.83/116.83 Hz |
| SupaJuce 1, LEAD 06 | Two squares; signed raw +36 and 0; both WIDE off | Lower fundamental near 329.48 Hz and upper square at twice that frequency; strong lower H2/H6/H10/H14, weak H4/H8 |

The [Cotton/Pedal audit](source-audits/cotton-tuning-audit.md) includes repeated notes, both channels and a scan of all 32 named demos. The [SupaJuce audit](source-audits/supajuce-pitch-audit.md) independently tests a classic waveform. Sources are Roland's [PAD](https://www.rolandus.com/go/sh-201_patches/patch_pad.html), [BASS](https://www.rolandus.com/go/sh-201_patches/patch_bass.html) and [LEAD](https://www.rolandus.com/go/sh-201_patches/patch_lead.html) banks and demos; exact download URLs, bank members and SHA-256 identities are in the [source catalog](hardware-reference-catalog.json). The endpoint conclusion does not depend on the unknown original keyboard octave or recording gain.

Normal-range signed raw ±36 now maps to physical ±12 semitones. WIDE on retains ±36. Interior normal values use nearest-integer division by three, consistent with documented semitone steps, **but the exact interior quantization table remains unmeasured**. The polyphonic Soundtrack demo did not resolve it. Public editor resources were inspected; no DSP ROM code was obtained.

## Implementation and compatibility

`OscParams::coarse`, native preset files and host automation continue to store physical semitones. This avoids retuning existing native sessions. Hardware values are converted at the wire boundary. Normal export multiplies physical semitones by three; pitches beyond ±12 export with WIDE enabled even if an older native patch has its switch off. Export does not alter that native patch. Noncanonical normal raw positions can export as equivalent canonical positions, so this is pitch-preserving rather than byte-preserving export.

The live decoder retains original raw WIDE/coarse pairs across fragmented messages. Either byte rebases as a pair after a host edit. Panel CC20/21/78/85 also update this raw cache: two consecutive normal values can round to the same semitone while needing different pitches after a later WIDE message. These writes use fixed stack storage and the existing patch-replacement revision handling. Unrelated DT1 writes leave legacy native WIDE/pitch values alone.

**Re-import original hardware SysEx to correct a patch previously saved with the old interpretation.** Existing native sessions deliberately retain their saved sounding pitches; there is no reliable way to infer whether a saved pitch was intentional or came from the earlier importer.

## Paired production renders

The [new comparison player](http://127.0.0.1:8898/player/) contains hardware, corrected Septum and previous Septum for four excerpts. Both Septum versions receive **identical MIDI bytes and identical original preset bytes** within each new comparison. The original hardware MIDI is unavailable: every reconstruction remains explicitly labeled. All audio uses 44.1 kHz; the 93-sample engine latency remains in place. Listening copies use whole-excerpt scalar level matching, without EQ, compression, time stretching or velocity fitting.

The tuning discovery also corrects the inferred keyboard notes. Cotton's notes are raised 12 semitones from the historical estimate; Moogie and Dist's notes are lowered 24. SupaJuce's reconstruction accounts for its stored tone octave shift −1. Current cases live under `reconstructions/current/`. Historical reconstructions retain their original paths and are also copied under `reconstructions/historical-before-wide/`; the revised 16-note historical Moogie reconstruction is retained in `source-audits/moogie-1-octave-revision.json`. These revisions are disclosed, not presented as recovered original MIDI.

| Cotton Wool, first 5 seconds | Previous decoder, revised MIDI | Corrected decoder, same MIDI | Hardware |
|---|---:|---:|---:|
| 20–40 Hz power relative to 40 Hz–16 kHz | −1.79 dB | **−39.08 dB** | −50.75 dB |
| Power spectral centroid, 20 Hz–16 kHz | 100.6 Hz | **188.4 Hz** | 316.3 Hz |

The earlier historical render with different MIDI measured 74.6 Hz and +6.00 dB; it is not the controlled baseline in this table. The corrected production Cotton WAV is byte-identical to the prior one-octave diagnostic, now reached through the original unmodified preset.

SupaJuce's upper square family is restored from the incorrect H8 position to H2/H6/H10. Its overall brightness still falls short: the corrected centroid is 697 Hz versus hardware 1,642 Hz. The old render's 1,711 Hz centroid was coincidentally close while containing the wrong oscillator interval. A single brightness score is not a fidelity score.

Moogie and Dist correct their played-note mapping; with the compensating MIDI revisions their production WAVs are byte-identical to the earlier accepted filter-decay renders. **This round does not claim a further bass-timbre improvement for those two patches.** Verified pairs, binary and audio hashes, raw measurements and the historical equality checks are retained in [production-pitch-comparison.json](source-audits/production-pitch-comparison.json).

The subsequent [resonance investigation](resonance-investigation.md) uses the corrected oscillator intervals to calibrate moderate resonance. The results above remain the historical pitch-correction stage.

## Why we did not adopt the other candidates

The [Dist oscillator/overdrive audit](source-audits/dist-overdrive-phase.md) identifies relative pulse/triangle cancellation as a stronger residual than overdrive gain. Inverting triangle polarity improves H2–H8 error across six Dist notes from roughly 7–8 dB to 3–3.5 dB and brings third-harmonic phase closer. However, it worsens Moogie's odd harmonic ratios. This is useful evidence about relative waveform phase, not proof of a global polarity rule.

The [Moogie oscillator audit](source-audits/moogie-oscillator-shape.md) shows that pulse width alone cannot reproduce the even-harmonic pattern under a monotone low-pass. A resonant-filter fit can match selected lower harmonics but misses withheld H10/H12 by roughly 11–14 dB. Expanding the fit changes its inferred cutoff trajectory substantially. Neither result identifies a unique new resonance or pulse-width law. These candidates remain diagnostic, and the earlier production linear filter-decay correction is retained.

## Reproduction and validation

Build the current renderer, acquire the catalog's hash-verified sources using the existing benchmark workflow, then run:

```sh
python3 Tools/compare_hardware.py \
  --sources build-fidelity/hardware-benchmark/sources \
  --renderer build-fidelity/SeptumRenderMidi \
  --output build-fidelity/hardware-benchmark/new-pitch-run
```

The default four JSON cases now use the corrected pitch interpretation. For a paired run, preserve the previous renderer before rebuilding, render both binaries into fresh `before/` and `after/` directories, then run:

```sh
python3 Tools/summarize_pitch_comparison.py \
  --root build-fidelity/hardware-benchmark/wide-pitch-implementation \
  --historical-filter-after build-fidelity/hardware-benchmark/filter-implementation/after
```

The summarizer verifies MIDI/preset identity and input/output hashes before producing the player. Renderer hashes identify the executed binaries; a source snapshot collected while executing a preserved older binary is not a claim about that binary's original source. Raw third-party audio/preset payloads remain in ignored build directories.

Core tests cover endpoints, provisional interior rounding, physical pitch round trips, noncanonical raw retention, both fragment orders, host edits and native high-pitch audio preservation. Processor tests exercise all four pitch CCs, same/separate-block WIDE writes, reconciler ordering, patch/program replacement and native session restoration. All 12 CTest suites pass (including 4,599 engine and 4,122 processor checks). Release arm64 AU, VST3 and Standalone bundles build and pass strict ad hoc signature verification. The comparison player was checked for playback and source switching. Bundle hashes and verification details are recorded with the production artifact manifest.
