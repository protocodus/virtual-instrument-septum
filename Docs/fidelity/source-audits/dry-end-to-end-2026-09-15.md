# Dry original-MIDI replay: zero resonance

## Result

The actual Septum engine improves on both dry SH-201 filter recordings when the
reconstructed cutoff trajectory is fitted using one training note. Held-out
spectral distance decreases from **0.34231 to 0.28779** for LP12 and **0.34903 to
0.29495** for LP24. This supports the zero-resonance damping correction, but
does **not** establish equivalent output. The envelope reconstruction matters:
the nominal one-second setting produces worse results after the same correction.

All measurements and input/output hashes are in the
[measurement record](dry-end-to-end-2026-09-15.json). The comparison uses the
author's original MIDI and a documented patch recipe; no recording-specific
SysEx was available. Source identities and acquisition links are in the
[deepsonic manifest](deepsonic-acquisition-2026-09-15.json).

## Held-out measurements

Every arrow is LFO-only control → zero-resonance k=1.2 candidate. Lower is better.
Spectral distance is the mean of three STFT magnitude distances, not a percentage
of perceived similarity. Harmonic values are RMS errors in dB.

| Reconstructed envelope | Slope | Spectral distance, after training | H2–H8 ratios | H9–H16 ratios | Absolute H2–H8 | Absolute H9–H16 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Onset-corrected trajectory | LP12 | 0.34231 → 0.28779 | 2.690 → 1.184 | 1.647 → 0.552 | 2.151 → 1.231 | 0.975 → 0.609 |
| Onset-corrected trajectory | LP24 | 0.34903 → 0.29495 | 3.011 → 1.313 | 2.564 → 0.833 | 2.505 → 1.332 | 1.555 → 0.944 |
| Nominal one second | LP12 | 0.29559 → 0.31231 | 2.940 → 4.583 | 3.629 → 5.039 | See JSON | See JSON |
| Nominal one second | LP24 | 0.30137 → 0.32853 | 4.952 → 7.138 | 2.767 → 5.241 | See JSON | See JSON |

The onset-corrected candidate's post-training log spectral errors are still
**4.675 dB / 5.101 dB**, and its 10/50 ms envelope P95 errors are
**20.392 dB / 18.826 dB** (LP12 / LP24). Quiet tails contribute to those envelope
statistics. Before-training spectral distances also improve, from
0.42837 → 0.40520 and 0.36302 → 0.32874; LP12 log spectral error in that segment
increases 7.330 → 7.551 dB. Improvements are therefore neither uniform across
all measurements nor evidence that the whole waveform now matches.

The harmonic check uses eight isolated validation notes and four 80 ms windows
per note. LP12 retains 208 H2–H8 and 127 H9–H16 observations; LP24 retains 189 and
30. Each retained hardware harmonic exceeds −45 dB relative to its fundamental.
The windows overlap and are not independent statistical replicates. Absolute
harmonic errors use the same single file gain as the audio, so the ratio
diagnostic cannot conceal a separate per-note loudness adjustment.

## What was fixed before validation

- Both renderers use the same frozen 18 DSP/renderer source files. The baseline
  includes the measured LFO correction; only the global damping profile differs.
  At resonance zero the quadratic experiment and final linear bridge are
  identical: stage one changes from k=2 to 1.2; LP24 stage two remains k=1.2.
- The original 124 note-ons, velocities (all 127), 124 note-offs and SMF timing
  are preserved. Replay uses MIDI channel 1, 120 BPM from the SMF, 44.1 kHz,
  master level 100, a two-second tail, and retains 93 renderer latency samples.
- The single Upper tone is an ordinary saw, OSC1 only, low-pass filter, key
  follow +100%, resonance zero, no effects/overdrive/LFO depths, and neutral
  velocity sensitivities. Raw cutoff 47 is the nearest current mapping to the
  fundamental: 260.063 Hz at MIDI note 60. Key-follow raw is 74.
- Only note 36 at MIDI time **1.5–1.9375057 s** calibrates the reconstructed
  envelope, gain and timing. Eight cutoff targets (both slopes, offsets
  0.10/0.18/0.26/0.34 s) come from the previously measured dry response fit.
  Searching depth +14…+19 and decay raw 45…66 selects **depth +16 (raw 80,
  3.0476 octaves), decay raw 53 (0.55197 s in the existing linear envelope)**.
  The training trajectory residual is 0.0410 octaves. This raw value is a
  reconstruction proxy; it is not evidence of the original hardware slider
  position or its true decay duration.
- The nominal sensitivity retains depth +16 and the nearest current one-second
  decay, raw 63 (1.01387 s). The shorter reconstruction follows the measured
  early trajectory; the counterexample exposes the separate envelope-law issue.

### Fixed delay and gain policy

The first waveform difference above 0.001 times local peak identifies the
training-note onset in the declared 1.49–1.56 s search interval. The 0.003
sensitivity changes the relative result by less than 0.3 ms. Hardware onset
samples are 67636 / 67716; preliminary candidate onset samples are 66261 /
66278. Their differences give **lag −1375 / −1438 samples** (−31.179 / −32.608 ms)
for LP12 / LP24. The same lag is then used for both renderers and both envelope
recipes. Comparisons pair hardware[t] with renderer[t + lag].

One positive scalar RMS gain is fitted to the training note for each complete
render and held fixed for every remaining event. The onset-corrected gains are
control/candidate **+13.658/+12.324 dB** for LP12 and **+13.052/+11.764 dB** for
LP24. There is no per-note gain, event retiming, EQ, time stretching or waveform
phase matching. The initial full-note envelope-correlation lag experiment is
retained locally as sensitivity only: its model-dependent timing confused the
decaying envelope and recording onset.

Audio is evaluated separately before training [0,1.45 s] and after training
[2.0 s,end of decoded hardware], with the required boundary guard for the
negative lag. The segments are not concatenated. Harmonic validation uses
isolated original notes at 0, 0.75, 2.0, 4.75, 6.0, 17.25, 18.75 and 20.25 s.
Those observations are held out from this nuisance fit, not from all prior DSP
development or later research in this session.

## Replay and measurement qualifications

The renderer explicitly reports degraded replay because **FF20=00 channel-prefix
metadata alone is omitted**; all notes already carry channel 1. The FF54
SMPTE-offset event remains recorded metadata. The preliminary captured script's
descriptive omission list incorrectly also names FF54; the authoritative render
receipts and this audit correct that description. No original MIDI bytes change.

Both channels of each dry render agree within float32 peak-relative epsilon
(maximum observed difference about 1.5e−11); analysis explicitly selects the
left channel to compare with the mono hardware source. All eight raw renders
are finite, have no full-scale samples, and end with zero active voices.

The sources are lossy MP3 recordings with an unknown capture chain and no
hardware patch dump. Free oscillator phase prevents waveform nulls from serving
as a general acceptance test. Finite-window harmonic estimators can have bias;
the audio STFT and absolute harmonic checks are retained alongside ratios.
There are no independently validated perceptual acceptance margins, repeated
hardware captures or blinded listening results here. The result remains
**not_established** for output equivalence.

## Reproduction

The [tracked reproduction tool](../../../Tools/reproduce_zero_resonance_benchmark.py)
and [pinned source/profile/recipe bundle](zero-resonance-reproduction-2026-09-15.json)
reconstruct the experiment without the ignored frozen-source directory or scripts.
See [the reproduction instructions](zero-resonance-reproduction-2026-09-15.md).
Raw media and generated SysEx remain in the private output directory.
