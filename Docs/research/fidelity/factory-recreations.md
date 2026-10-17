# SH-201 factory sound recreations

Created 2026-09-14. [Open the comparison player](http://127.0.0.1:8918/).

**17 approximate software presets, 17 estimated MIDI files, 619 note events, 122.19 seconds of paired excerpts. Exact factory presets: 0. Exact original performance MIDI files: 0.**

Each target uses an official Roland demo identified in the [factory reference catalog](factory-recordings.json). The software patch is independently authored from INIT PATCH using Septum's current engine. The exported SysEx contains our approximate settings; it is not a recovered Roland factory dump. All patch names start with `APX `, and every player card labels the preset APPROXIMATE and MIDI ESTIMATED.

## Contents

The local dataset is `build-fidelity/hardware-benchmark/factory-recreations-700f4ee/`. Its [download archive](http://127.0.0.1:8918/sh201-factory-recreations.zip) contains all audio, MIDI, individual SysEx patches, an approximate 17-sound bank, parameter recipes and provenance manifests. The bank is a separate importable collection; the software's default bank is still awaiting authentic factory data.

| Factory target | Name | Excerpt seconds | Estimated notes |
|---|---|---:|---:|
| A-1 | Reso Bass | 6.20 | 15 |
| A-2 | Fat Saw Lead | 6.85 | 20 |
| A-3 | SilkyStrings | 7.75 | 10 |
| A-5 | OSC SyncLead | 6.00 | 20 |
| A-6 | SuperSawBrs | 8.00 | 59 |
| A-7 | Electro Seq | 6.30 | 48 |
| B-1 | Fat Bass | 6.85 | 14 |
| B-4 | SuperSawKey | 8.06 | 72 |
| B-5 | FB OSC Lead | 6.50 | 7 |
| B-6 | Poly Synth | 7.15 | 98 |
| B-7 | Sweep Arp | 6.30 | 48 |
| C-4 | SH-201 EP | 7.98 | 22 |
| C-5 | Sweep Up | 8.80 | 6 |
| C-6 | Trancy 201 | 6.40 | 36 |
| C-7 | Sliced Pd/Bs | 6.50 | 126 |
| D-5 | JP-8SweepPad | 8.15 | 6 |
| D-7 | S&H FX 2 | 8.40 | 12 |

## Reconstruction and comparison limits

The [case JSON files](reconstructions/factory/) retain each note, timing estimate, method, uncertainty and native parameter recipe. Pitch hypotheses use source spectra, harmonic spacing and attack analysis. Dense chords, overlapping effects and modulated sounds remain ambiguous. Every note-on velocity is the explicit placeholder 100. Note-offs, controller behavior and recording processing were not recovered.

Electro Seq, Sweep Arp and Sliced Pd/Bs use estimated audible output events with the software arpeggiator disabled. These files do not reconstruct the performer's held keys or the factory arpeggio pattern. Sweep and effect cases use stated held-note hypotheses. Each recipe explains its assumptions and any subsequent manual voicing revisions against a preview render.

Listening copies use independent scalar gains to match whole-excerpt RMS at −20 dBFS, followed by shared peak attenuation where needed. There is no EQ, compression or time warping. Raw float renders retain engine latency. Sequential A/B files play hardware first, a half-second gap, then software; only these sequential files add 5 ms edge fades. The player switches sources at the current playback position.

The source MP3s are lossy stereo demos with unknown live controls and recording processing. Differences in patches, estimated performances and recording chains prevent these examples from isolating DSP fidelity. Spectral review guided approximate voicing; it does not establish perceptual or hardware equivalence.

## Rebuild

With the hash-verified source MP3s, `build-fidelity/libSeptumDSP.a`, `build-fidelity/SeptumRenderMidi`, FFmpeg, NumPy and SciPy available:

```sh
python3 Tools/recreate_factory_demos.py --output build-fidelity/hardware-benchmark/factory-recreations-new
python3 -m http.server 8918 --bind 127.0.0.1 --directory build-fidelity/hardware-benchmark/factory-recreations-new
```

The output directory must be new. The builder compiles the numeric patch recipes against Septum's native codec, rejects clamped or unpreserved assignments, validates all 22 SysEx blocks, and renders the emitted MIDI/SysEx using the existing renderer. All 17 final renders passed finite-audio, non-silence, sample-rate, duration and note-count checks. Source, tool, library, renderer and artifact hashes are retained in `dataset-manifest.json`. The task changes no shipping DSP code or default preset programs.

An independent artifact review verified all 619 emitted note-on/off events, bank payloads and checksums, and the scalar-only listening transforms. All 242 manifest file hashes and ZIP contents matched after the final player fix. All 156 local player links resolved. Browser playback, Stop and active-card state were checked. The [validation record](source-audits/factory-recreations-validation.json) retains the final archive and manifest hashes.

The remaining authentic-bank acquisition work and the official MIDI bank-selection discrepancy are documented in [factory preset references](factory-preset-references.md).
