# High-note Saw smoothing models

## Result

An exploratory short linear filter can reproduce much of the high-note
recording's main waveform shape. **It does not reproduce the alias pattern.**
Reducing the polyBLEP correction brings several alias levels closer, but moves
or misses important spectral notches and gives mixed results on other pitches.
No oscillator model or DSP correction is selected.

This is mathematical source identification, not a render of the full engine
with an original preset. The fitted filter could absorb an oscillator,
instrument filter, output circuit, or recording response. The available
[source documentation](sh201-high-note-source-feasibility-2026-09-15.md) does
not identify which stage is responsible.

## Fixed data and exploratory protocol

The original deep!sonic [LP12 Q0 recording](https://www.deepsonic.ch/deep/audio_filter/roland_sh-201_-_filter_demo_-_lpf12_q000.mp3)
and [performance MIDI](https://www.deepsonic.ch/deep/audio_midi/deepsonic_-_filter_demo_-_comparsion_sequence.mid)
are hash-checked against the acquisition catalog. The tool privately decodes
the mono MP3 to 44.1 kHz float PCM and verifies all note identities, velocity
127, and window coverage against the original MIDI.

The training window is 80 ms centered 100 ms after note 91 at MIDI time
18.75 s. Diagnostic evaluation uses its later 160 ms window and notes 93,
88 and 86 at 100 ms. The same-note windows overlap by **20 ms / 882 samples
(25%)**; they are not independent observations. All these passages had already
been examined during exploratory research. They are excluded from coefficient
fitting, but are not an untouched or blind validation set.

The sampled saw is `2*frac(phase + increment*n)-1`, with a fraction of the
existing two-sample polyBLEP residual subtracted. The correction fractions
are 0.5, 0.75, 0.8125, 0.875, 0.9375 and 1.0. Each is followed by a signed
1-, 4-, 8- or 13-tap finite impulse response (FIR) filter. A FIR computes a
weighted sum of nearby samples; negative time offsets here allow identification
without assuming a physical processing delay.

For every one of the 24 models, the first note alone fits the complete FIR
(including gain), DC and waveform origin. Phase search uses a 256-point
full-cycle grid plus bounded local refinement. The exact same coefficients
and gain then predict the other passages, fitting only their unknown waveform
origin and removing DC. No frequency, per-note gain, filter or time warp is
fitted there. These phase fits are more permissive than the full-engine
benchmark and are explicitly part of this diagnostic protocol.

Signed coefficients, delay/phase interchange and the missing capture transfer
make the physical interpretation nonunique even when the numerical design
matrix has full rank. A **one-tap, full-BLEP row is an oscillator-only fitted
reference, not a production-engine baseline**: it contains no engine filter,
envelope, gain staging or output processing.

## Waveform residuals

Numbers below are residual power divided by observed centered signal power.
They are not audible-error percentages or whole-instrument fidelity scores.
Rows illustrate the retained grid; no combined waveform/alias loss selects a
winner.

| FIR taps | BLEP correction | Training note 91 | Later same note | Note 93 | Note 88 | Note 86 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1.0 | 0.062831 | 0.062670 | 0.078864 | 0.051721 | 0.049021 |
| 4 | 1.0 | 0.000724 | 0.000793 | 0.001336 | 0.000505 | 0.000763 |
| 13 | 0.875 | 0.000588 | 0.000702 | 0.001903 | 0.000465 | 0.000975 |
| 13 | 0.9375 | 0.000509 | 0.000616 | 0.001649 | 0.000387 | 0.000816 |
| 13 | 1.0 | 0.000522 | 0.000623 | 0.001494 | 0.000382 | 0.000721 |

The full grid and exact values are in the [waveform result](high-note-saw-fir-2026-09-15.json).
The training waveform minimum occurs with 13 taps and correction 0.9375.
Other pitches do not uniformly prefer that fraction. A small power residual
can still hide a badly wrong weak alias line.

## Independent alias constraint

The [alias detector](deepsonic-saw-aliases-2026-09-15.md) is applied separately
to the observed and predicted samples in each exact window. Eligibility uses
hardware only, with the same interior-peak, local-background and −75 dB/H1
thresholds. The assessment fits no additional coefficient or phase. Every
hardware-qualified bin remains present even when a model suppresses it;
unresolved model peaks are residual-level upper-bound proxies.

The 13-tap / 0.875 example brings the median alias-level difference near zero,
yet retains fixed-bin RMS differences of **13.22, 3.68, 14.03 and 9.55 dB** on
the first windows of notes 91, 93, 88 and 86. On note 91:

| Predicted alias frequency | Hardware level, dB/H1 | Model level, dB/H1 |
|---:|---:|---:|
| 11,172 Hz | −46.7 | −80.0 |
| 8,036 Hz | −68.6 | −51.3 |
| 1,764 Hz | −45.8 | −46.4 |

Matching the last line cannot compensate for the first two. Full BLEP with
the same 13-tap family underestimates the median aliases by approximately
14–17 dB in these passages. The [complete alias result](high-note-saw-fir-aliases-2026-09-15.json)
retains all 24 models, eligibility, background resolution, and every measured
line rather than ranking only selected examples.

## Verification and limits

A planted four-tap / 0.875 synthetic waveform recovers predicted samples with
relative error power `1.39e-18`. This verifies the fitter, not unique physical
tap recovery. All 24 hardware training designs have full rank; maximum
condition number is 16.98. An [independent implementation review](high-note-fir-review-2026-09-15.json)
reconstructs all 120 stored residuals with a separate tap-wise BLEP expression,
with maximum discrepancy `1.39e-17`. All source, MIDI, window and script hashes
are retained.

The first alias-assessment attempt stopped on a mismatched field name before
writing results; the corrected helper key is used in the retained output.
Earlier local pilot grids remain exploratory. No shipping source was changed,
and these short waveform fits do not establish output equivalence.

## Reproduction

```sh
OPENBLAS_NUM_THREADS=1 python3 Tools/fit_high_note_saw_models.py \
  --sources build-fidelity/deepsonic \
  --output build-fidelity/high-note-shape/NEW_RUN
OPENBLAS_NUM_THREADS=1 python3 Tools/assess_saw_fir_aliases.py \
  --experiment build-fidelity/high-note-shape/NEW_RUN \
  --output build-fidelity/high-note-shape/NEW_RUN/aliases.json
```

Use new output paths. The retained run is
`build-fidelity/high-note-shape/fir-model-audit-v2`. Both tools pin the exact
implementations, original source identities and decoded waveform. The next
useful evidence is the filter-slope/time comparison and an oscillator model
that predicts both main harmonics and alias locations/levels across pitches.
