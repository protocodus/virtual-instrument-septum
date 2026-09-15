# Dry envelope curves: actual-engine validation

## Result and scope

Both frozen exponential-envelope hypotheses modestly improve the complete dry
sequence and substantially improve late chord harmonics. Interpolating cutoff
in Hz fits the measured late chords better than the fitted log-cutoff control.
The complete output still differs from the hardware, and this experiment does
not identify a production raw-slider time/depth curve. No shipping DSP is
changed by this audit.

The [measurement record](dry-envelope-engine-2026-09-15.json) contains all
whole-sequence metrics, every declared isolated/chord interval summary, common
harmonic-pool results, and source/render/decoder hashes. Full per-resolution
interval metrics and independent harmonic observations remain in the generated
output and are reproducible with the tracked assessment tool.

## Mathematical integration passed before interpreting scores

The [compiled integration check](dry-envelope-integration-2026-09-15.md) verifies
the actual frozen envelope methods, profile, depth mapping and cutoff target
expression. All seven fixtures pass. Through 2.5 seconds, maximum target errors
are below **4.3e−9 cents**. Later artificial holds expose only the declared
settling threshold: the largest Hz discrepancy is **0.000121 cents** at four
seconds. This checks exact control-target endpoints; the paired audio test also
exercises coefficient interpolation, oscillators, voices and output processing.

The physical Hz model at the primary 35 ms convention uses a 0.214076 s time
constant, base cutoff 0.931883 times the fundamental, and depth 3.128317 octaves.
The log-cutoff control uses its independently fitted 0.907943 s time constant,
base cutoff 0.158908 times the fundamental, and depth 5.693481 octaves. These
generously fitted physical fixtures are compared as frozen hypotheses, not
asserted to be recovered original raw controls. The initial raw patch stays
identical; candidate calibration/mapping changes integrate those physical curves.

## Primary audio comparison, physical delay 35 ms

Every case fits one scalar gain using original note 36 at 1.5–1.9375057 s, then
freezes it for all other events. Lower errors are better. Spectral distance is
the mean of three STFT magnitude distances, not a similarity percentage or a
validated perceptual score.

| Model | Slope | Post-training spectral distance | Log spectral, dB | Envelope P95, dB | Mean isolated-note spectral | Mean late-chord spectral |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Production | LP12 | 0.28616 | 4.549 | 24.464 | 0.26168 | 0.30843 |
| Exponential, Hz cutoff | LP12 | 0.27790 | 4.475 | 24.063 | 0.25966 | 0.24687 |
| Exponential, log cutoff | LP12 | 0.27839 | 4.491 | 24.567 | 0.25975 | 0.24949 |
| Production | LP24 | 0.29660 | 5.163 | 23.079 | 0.20031 | 0.35425 |
| Exponential, Hz cutoff | LP24 | 0.27617 | 5.038 | 23.329 | 0.19378 | 0.24390 |
| Exponential, log cutoff | LP24 | 0.27852 | 5.057 | 23.975 | 0.19403 | 0.25184 |

The post-training segment is original hardware time 2.0 s to the end. The
separate 0–1.45 s segment changes 0.39955 → 0.39940 / 0.40012 for LP12 and
0.32665 → 0.32385 / 0.32388 for LP24 (production → Hz / log). Thus even the Hz
fixture does not improve every statistic: LP24 envelope P95 becomes slightly
worse, and early LP12 spectral change is tiny.

Isolated-note means describe the eight previously declared note-on to note-off
intervals. Late-chord means describe seven original chords, each at
0.41–0.67 s after its MIDI onset; full chord intervals are also recorded. These
unweighted interval means are descriptive, not independent statistical samples.

## Harmonics measured independently in hardware and engine audio

The harmonic comparison does not fit cutoff, gain, phase or any curve to each
window. It measures hardware and renderer amplitudes independently with local
quadrature/ramp estimators, applies the fixed full-file gain, and compares both
harmonic ratios and absolute amplitudes.

Only windows valid for **hardware and all three primary models** enter the
comparative RMS errors below. Validity requires condition number ≤100 and ≤1%
unexplained signal power. Chord targets additionally require isolated H1/H2/H3
above the existing noise-proxy thresholds. Retained partials use the same
hardware-defined −45 dB floor; chord partials also require hardware noise-proxy
SNR ≥20 dB. Nearby chord partials are modeled as nuisance clusters, never
mistaken for independent target harmonics.

| Held-out group | Slope | Common windows | Partial observations | Production H2–H8 ratio RMS | Hz | Log |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Isolated notes | LP12 | 31 / 32 | 204 | 1.002 dB | 0.942 dB | 0.941 dB |
| Isolated notes | LP24 | 31 / 32 | 185 | 1.152 dB | 0.882 dB | 0.884 dB |
| Late chords | LP12 | 12 / 21 | 45 | 3.573 dB | 0.415 dB | 0.777 dB |
| Late chords | LP24 | 4 / 21 | 8 | 4.958 dB | 0.551 dB | 1.037 dB |

Absolute late-chord H2–H8 errors agree with the ratio result:
**4.517 → 0.387 / 0.975 dB** for LP12 and **5.308 → 0.652 / 1.175 dB** for
LP24. These use the one training-note gain, so per-window normalization cannot
conceal loudness errors.

Held-out isolated-note H9–H16 ratios change **0.535 → 0.500 / 0.497 dB** for
LP12 (127 partial observations), but **0.776 → 0.847 / 0.829 dB** for LP24
(30 observations). No late-chord H9–H16 partials meet the declared floor. The
late LP24 result consequently rests on only eight eligible low-harmonic
observations; it cannot support a broad upper-spectrum agreement claim.

Nine chord windows per slope are excluded because H3 is not isolated. Eight
more LP24 baseline windows have inadequate H3 noise-proxy SNR, with one also
below the relative floor. One isolated-note window per slope fails the
baseline residual-power rule. All observations, failed-window reasons and
per-model eligibility counts are retained alongside the common-pool result.

## Fixed physical timing and sensitivity

The primary lag is computed, not optimized:

```
candidate lag = round(93 + 0.001 * 44100 - 0.035 * 44100)
              = -1406 samples
```

Hardware[t] pairs with renderer[t+lag]. The same lag is applied to production,
Hz35 and log35. Their LP12 training gains are respectively **12.334 / 12.311 /
12.314 dB**; LP24 gains are **11.755 / 11.732 / 11.735 dB**. No other event is
used to select a gain or timing value. The integer lag is 0.4 samples from the
nominal continuous value. The engine's actual attack takes 45 samples rather
than nominal 44.1; the integration audit records that additional quantization,
and the predeclared lag is kept unchanged.

The 30/35/40 ms fixtures pair each physical delay with its corresponding depth.
Their target cutoff remains the same function of original MIDI time once
aligned; note onsets, gates and other audio behavior can still differ under
the alternate recording-delay assumptions. These are sensitivity cases, not a
delay search used to select a winner.

| Paired delay | Hz LP12 / LP24 post-training spectral | Log LP12 / LP24 |
| --- | ---: | ---: |
| 30 ms, lag −1186 | 0.30633 / 0.30286 | 0.30657 / 0.30456 |
| **35 ms, lag −1406, primary** | **0.27790 / 0.27617** | **0.27839 / 0.27852** |
| 40 ms, lag −1627 | 0.27700 / 0.27423 | 0.27777 / 0.27703 |

The old onset-derived lags (−1375 LP12 / −1438 LP24) are retained solely as
separate sensitivity. They give production → Hz / log spectral distances
0.28778 → 0.27949 / 0.27994 and 0.29495 → 0.27475 / 0.27711. These analyses use
float64 hardware arrays; tiny differences from older float32 audit metrics do
not represent altered audio or inputs.

## Provenance, limits and reproduction

All sources are the pinned original Q000 MP3 recordings and original performance
MIDI. The patch is a documented-recipe reconstruction, not recording-specific
hardware SysEx. All 124 note-ons and note-offs are preserved. Only FF20=00
channel-prefix metadata is omitted, with degraded replay recorded. Both channels
of each dry renderer agree within float32 peak-relative epsilon; the comparison
selects the left channel against mono hardware. All 14 renders are finite,
remain below full scale, and finish with zero active voices. Production raw WAVs
are byte-identical to the previously validated dry Q0 outputs.

The fixtures deliberately integrate already fitted curves. Their raw controls
do not identify the original slider calibration, and the recordings are held
out only from this nuisance fitting—not from all prior source analysis or DSP
development. MP3 encoding, unknown capture response, phase, estimator bias and
the small valid LP24 chord set remain limitations. Whole-sequence spectral and
envelope discrepancies remain material. There is no registered perceptual
acceptance margin or blinded equivalence result; status remains
**not_established**.

Build dry renderers with [build_envelope_experiment.py](../../../Tools/build_envelope_experiment.py)
and verify them with [verify_dry_envelope_integration.py](../../../Tools/verify_dry_envelope_integration.py).
Then run the [audio/harmonic assessment](../../../Tools/assess_dry_envelope_candidates.py)
into a new directory:

```sh
OPENBLAS_NUM_THREADS=1 python3 -B Tools/assess_dry_envelope_candidates.py \
  --renders build-fidelity/envelope-hypothesis/dry-v2/renders.json \
  --sources build-fidelity/deepsonic \
  --output build-fidelity/envelope-hypothesis/dry-v2/evaluation-new
```

The tool verifies original media and raw-render hashes, decodes private WAVs,
freezes the exact analysis scripts, and records decoder version/hash/commands.
`audio-results.json` has every interval's full measurements;
`harmonic-observations.json` has independent measured/rejected windows;
`harmonic-summary.json` uses the common valid pool. No downloaded media enters
the repository.
