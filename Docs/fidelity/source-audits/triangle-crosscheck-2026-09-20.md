# Triangle polarity and level: cross-preset check

Reversing the triangle polarity and multiplying its amplitude by 1.5 improves
the broad spectrum metric for all five relevant named demos. It does **not**
establish a global waveform correction: Moogie's odd-harmonic error increases
consistently, and Sexy Back contains a local regression. Production DSP stays
unchanged. The [listening page](http://127.0.0.1:8920/triangle-listen/) retains
hardware, current engine and this isolated candidate.

## Evidence and design

The public sources are Roland's [BASS demos and presets](https://www.rolandus.com/go/sh-201_patches/patch_bass.html)
and [LEAD demos and presets](https://www.rolandus.com/go/sh-201_patches/patch_lead.html).
All published preset bytes remain unchanged. Performance MIDI is reconstructed;
the exact recorded patch revision, velocities, controls, processing and prior
oscillator phase history are unknown.

Seven discrete triangle interventions test gains +0.5, +1.5, −0.5, −1, −1.5,
and quarter-/three-quarter-cycle phase offsets at unity gain. Current gain is
+1. Every candidate uses the existing calibration API with identical frozen
DSP sources. This is exploratory comparison, not an untouched confirmation set:
Dist motivated the hypotheses, but all candidates were inspected on the same
five previously studied triangle presets. The other eight cases are isolation
controls, with byte-identical renders for every intervention.

The −1.5 candidate gives the following 32-band spectral residuals. These measure
normalized power, not perceptual fidelity, timing or waveform authenticity.

| Preset | Current | Triangle −1.5 |
| --- | ---: | ---: |
| Moogie 1 | 4.738 dB | 4.200 dB |
| Dist Bs 1 | 5.709 dB | 2.286 dB |
| Club Bass | 7.734 dB | 6.914 dB |
| Air Lead 1 | 13.404 dB | 12.359 dB |
| Sexy Back | 5.680 dB | 5.460 dB |

Sexy Back's triangle fundamental is about 19 Hz, below this metric's 25 Hz
floor. The numerical gains cannot be interpreted as overall fidelity gains.

## Harmonic checks reveal the tradeoff

Joint least-squares fits measure 12 harmonic amplitudes with a constant and
linear trend. Frequencies are estimated separately in each audio; no spectral
offsets, time alignment or EQ are fitted. Dist's physical tuning is −12
semitones for raw coarse −36 with WIDE off. The historical diagnostic's −36
semitone assumption is not reused.

Dist uses early and late 80 ms windows for each of three notes. Moogie uses
60 ms windows from 60–290 ms after three low-note onsets. Both also test
left/right/mid and ±10 ms window shifts. These overlapping observations are
sensitivity checks, not independent recordings. Errors below are nominal
mid-channel values by note.
The shifts move both audio windows together and test window position, not
relative onset alignment; actual MIDI gate variations are evaluated separately.

| Metric | Current | Triangle −1.5 |
| --- | --- | --- |
| Dist H2–H8/H1 RMSE | 8.206 / 7.503 / 7.772 dB | 2.719 / 2.631 / 3.116 dB |
| Dist odd H3/H5/H7 relative to H1 | 11.570 / 10.590 / 10.495 dB | 2.122 / 2.152 / 2.041 dB |
| Moogie H2–H8/H1 RMSE | 6.135 / 6.416 / 5.952 dB | 5.946 / 6.327 / 5.867 dB |
| Moogie odd H3/H5/H7 relative to H1 | 3.506 / 3.856 / 3.873 dB | 4.055 / 4.684 / 4.600 dB |

Dist's H2–H8 error improves in all 27 note/channel/shift combinations by
4.64–5.49 dB. Moogie's odd-harmonic error worsens in all 27 by 0.49–0.86 dB.
Its even-harmonic error stays effectively unchanged, about 6.7–7.5 dB. This
experiment cannot explain the previously documented even-family mismatch.

The [paired note-gate check](candidate-gate-robustness-2026-09-20.md) preserves
the whole-excerpt improvements for Sexy Back, Club Bass and Air Lead under all
tested timing changes. However, Sexy Back's second note gets worse by up to
0.967 dB in a fixed short-window spectrum check.

Classic oscillators start from zero phase for a new voice and continue only
while that voice is active. The unknown hardware history can change relative
phase; a fixed polarity winner on one recording is not proof of Roland's
oscillator convention. See the [input audit](benchmark-input-audit-2026-09-20.md).

## Reproduction and verification

The [compact JSON](triangle-crosscheck-2026-09-20.json) retains all seven
candidates' 13-case metrics, render identities and detailed harmonic errors,
and hashes the full ignored measurements. All 91 renders reproduced
byte-for-byte through the tracked sweep command. Maximum sample peak was
0.7251, all samples were finite, and replay retained the expected 93-sample
latency. A synthetic 12-harmonic signal's recovered amplitude error was below
5e−16; hardware-versus-itself harmonic comparisons returned zero error.

```sh
python3 Tools/sweep_triangle_candidates.py \
  --baseline build-fidelity/public-match-2026-09-20/baseline/SeptumRenderMidi \
  --comparison build-fidelity/public-match-2026-09-20/baseline-comparison \
  --comparison build-fidelity/public-match-2026-09-20/class-a-comparison \
  --comparison build-fidelity/public-match-2026-09-20/sexy-back-baseline \
  --comparison build-fidelity/public-match-2026-09-20/trancefloor-baseline \
  --output /path/to/new-triangle-sweep
python3 Tools/analyze_waveform_crosscheck.py \
  --baseline-comparison build-fidelity/public-match-2026-09-20/baseline-comparison \
  --sweep /path/to/new-triangle-sweep \
  --output /path/to/new-harmonics.json
```

Use Python with `Tools/requirements-hardware.txt`. Media, binaries, source
snapshots and full observations stay under ignored `build-fidelity/` folders.
Both candidate players were checked for playback in the browser; this is
functional QA, not a subjective listening verdict.
