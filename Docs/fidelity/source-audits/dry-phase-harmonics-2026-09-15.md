# Dry saw phase: independent harmonic self-control

## Finding

Joint sinusoid/ramp measurements are substantially more stable than arbitrary
short-window waveform comparisons, but **they are not perfectly phase invariant
for the moving-filter renders**. The fundamental is very stable. Weak LP24
harmonics can differ by several dB even though every synthesis parameter other
than global saw origin is identical. A one-percent total residual-power guard
does not establish the accuracy of every weak harmonic.

This is a self-control of the production model and estimator, not a measurement
of Roland's phase, a phase optimization, or evidence of hardware equivalence.

## Fixed protocol and provenance

- Source checkpoint `b0f6c03`; global saw phases 0, .25, .5 and .75 cycles.
- LP12 and LP24 use the same original deepsonic MIDI and frozen Q0 reconstructed
  patch as the phase experiment. Both phase-zero WAVs pass the pinned production
  byte-identity guards. All eight WAVs, MIDI, recipes, render receipts, renderer
  binaries, build inputs and frozen files were hash checked.
- Training note: MIDI36, `[66150,85444)` at 44.1 kHz. One whole-note RMS gain per
  phase and slope; also report fixed gain 1. No delay, tuning, cutoff or phase
  fitting. All renders retain the same 93-sample renderer latency.
- Validation notes `(onset seconds, MIDI pitch)`: `(0,24)`, `(.75,24)`, `(2,29)`,
  `(4.75,24)`, `(6,31)`, `(17.25,57)`, `(18.75,91)`, `(20.25,84)`.
  Original MIDI independently confirms the pitches, velocity 127, gate lengths
  and lack of simultaneous held notes in these gates.
- Every note, including training, uses centers +100, +180, +260, +340 ms and an
  80-ms width. MIDI24 is 32.7032 Hz: only **2.616 fundamental cycles per window**.
- Simultaneously fit DC, a DC ramp, and independent sine/cosine coefficients and
  their linear ramps for H1 through `min(30,floor(8000/f0))`. Report center
  amplitudes. This uses four right sides of the same least-squares system; it
  does not share fitted amplitude or phase between renders. The implementation
  agrees with the frozen single-render filter estimator to below 1e-12 absolute
  amplitude on the lowest note at both slopes.
- Summarize H1–H16, with H2–H8 and H9–H16 separately. Eligible harmonics are
  selected **only from phase zero**: above −45 dB relative to H1 and absolute
  amplitude at least 1e-8. Every phase uses exactly the same bins. No candidate
  activity mask or removal of individually disagreeing harmonics.
- Common validity requires all four phase fits to have full rank, condition
  number ≤100, variance ≥1e-12, H1 amplitude ≥1e-8 and unexplained power ≤1%.
  Every requested window and rejection reason remains in the JSON.

## Results

71 of 72 common windows pass (284 of 288 individual render-windows). All eight
training windows pass. The single rejected window is LP12, MIDI91 at 18.75 s,
center +100 ms: all four phases have 1.026–1.029% unexplained power. Thus
validation coverage is 31/32 LP12 and 32/32 LP24 windows. The maximum condition
number is 4.356; none failed conditioning or power guards.

RMS differences against phase zero, in dB, on the common valid validation
windows and identical phase-zero-selected harmonics:

| Slope / metric | Phase .25 | Phase .50 | Phase .75 |
|---|---:|---:|---:|
| LP12 H1 amplitude, fixed gain | .0052 | .0098 | .0079 |
| LP12 H1–H16 amplitude, fixed gain | .0885 | .1015 | .0970 |
| LP12 H1–H16 amplitude, training gain | .0883 | .1114 | .1112 |
| LP12 H1–H16 relative-to-H1 ratios | .0893 | .1030 | .0984 |
| LP24 H1 amplitude, fixed gain | .0215 | .0292 | .0244 |
| LP24 H1–H16 amplitude, fixed gain | .3457 | .2857 | .2622 |
| LP24 H1–H16 amplitude, training gain | .3459 | .2890 | .2634 |
| LP24 H1–H16 relative-to-H1 ratios | .3468 | .2873 | .2647 |

These pooled H1–H16 rows contain 343 LP12 and 231 LP24 harmonic observations
per phase. They weight observations equally; counts and separate harmonic
groups are explicit in the JSON. Phase zero against itself is exactly zero.

All 12 MIDI24 windows pass at both slopes. For MIDI24, H2–H8 ratio RMS differences
are .090/.121/.085 dB for LP12 and .445/.458/.385 dB for LP24. The largest MIDI24
LP24 ratio difference is 1.969 dB, H5 at +340 ms of the first note, whose
phase-zero H5 is −39.03 dB relative to H1. Across all validation notes the largest
LP24 difference is 3.069 dB, H7 at +260 ms of MIDI29 (2 s), with phase-zero H7 at
−44.11 dB. These observations remain included; no tighter threshold was chosen
after seeing them.

## Interpretation and reproduction

The frozen engine shifts both classic waveform evaluation and its BLEP edge;
it does not shift the canonical oscillator clock or MIDI events. A fresh voice
clears filter state, so a different initial waveform can produce a different
filter/attack transient. A short local linear-ramp model also has approximation
error for changing filter amplitude and phase. This experiment does not separate
those two effects. It therefore supports using harmonic magnitudes as a useful
diagnostic with measured uncertainty, while rejecting the assumption that all
weak harmonic estimates are immune to unknown oscillator origin. No late
chords are passed through this single-fundamental estimator.

From a completed `Tools/measure_dry_phase_sensitivity.py` experiment:

```sh
OPENBLAS_NUM_THREADS=1 python3 Tools/analyze_dry_phase_harmonics.py \
  --experiment-dir build-fidelity/hardware-benchmark/dry-phase-control/run-01 \
  --output NEW_RESULT.json
```

The complete durable result is
`Docs/fidelity/source-audits/dry-phase-harmonics-2026-09-15.json`; the original
identical result is `build-fidelity/hardware-benchmark/dry-phase-control/run-01/harmonics.json`.
The JSON pins the analyzer, frozen estimator, source manifest and eight renders.
