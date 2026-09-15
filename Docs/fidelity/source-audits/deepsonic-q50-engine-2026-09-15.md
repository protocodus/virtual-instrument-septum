# Nominal 50% resonance: complete-engine replay

## Decision

**Keep the shipping midpoint resonance curve unchanged.** The stronger
resonance diagnostics improve almost every long isolated note under the
Q0-derived envelope reconstruction, but worsen the complete held-out musical
sequence. A nominal one-second envelope reverses those isolated-note gains.
This is evidence of unresolved interaction with the reconstructed envelope and
performance; it does not identify a replacement damping curve or LP24 topology.
No shipping DSP changes were made in this experiment.

The [complete record](deepsonic-q50-engine-2026-09-15.json) preserves all raw,
training-gain and fixed-baseline-gain audio metrics, input/output hashes,
decoder/source provenance, and isolated-note summaries. It supplements the
[earlier Q50 response-estimator audit](deepsonic-q50-audit-2026-09-15.md) with
actual engine output. No stationary harmonic estimator is used here.

## Primary held-out sequence

The primary patch retains the Q0 reconstruction: raw cutoff **47**, key follow
**74** (+100%), filter depth **80** (+16; 3.0476 octaves), decay **53**
(0.55197 s in the current linear envelope). These values were learned only from
note 36 at 1.5 s in the Q0 recording. There is no Q50 recipe refit.

The table evaluates hardware time **2.0 s to the end** using a single training
gain per complete render. Lower error is better. Spectral distance is an
unweighted mean of three STFT magnitude distances; it is not a perceptual score
or percentage of similarity. The last column instead uses the exact baseline
raw-64 gain, exposing effects of nuisance refitting.

| Slope / diagnostic | k1 / k2 | Spectral distance | Log spectral, dB | Envelope P95, dB | Spectral, baseline gain |
| --- | ---: | ---: | ---: | ---: | ---: |
| LP12 current raw63 | 0.298862 / inactive | 0.51453 | 5.463 | 25.656 | 0.51076 |
| LP12 current raw64 | 0.289866 / inactive | 0.51720 | 5.439 | 25.580 | 0.51720 |
| LP12 stronger diagnostic | 0.16628 / inactive | 0.64519 | 5.173 | 25.091 | 0.81083 |
| LP24 current raw63 | 0.298862 / 0.5 | 0.64488 | 5.833 | 19.381 | 0.63618 |
| LP24 current raw64 | 0.289866 / 0.5 | 0.64835 | 5.793 | 19.442 | 0.64835 |
| LP24 equal sections | 0.29379 / 0.29379 | 0.67402 | 6.178 | 20.739 | 1.00167 |
| LP24 split sections | 0.17533 / 0.42962 | 0.68279 | 6.338 | 20.548 | 1.06764 |

The LP12 diagnostic improves the average log-spectrum error while increasing
the energy-weighted spectral distance. Those measures weight differences
differently; neither establishes an audible overall improvement. Quiet tails
contribute to the large envelope P95 errors.

An independent [common-mask check](q50-common-mask-2026-09-15.json) recomputes
LP12 log errors using exactly the same union of active bins across all three
models. It reproduces the original pairwise metrics and gives **5.50028 /
5.47364 / 5.12836 dB** for raw63, raw64 and stronger respectively. The stronger
model's log-error improvement therefore survives the identical-bin comparison
(−0.34528 dB against raw64); it is not an artifact of admitting different bins.
The check is reproducible with
[analyze_q50_common_mask.py](../../../Tools/analyze_q50_common_mask.py).

The separate early held-out segment, **0–1.45 s**, behaves differently:
spectral distance improves from 0.50051 → 0.44705 for LP12 and from
0.52045 → 0.44590 / 0.44092 for the two LP24 diagnostics. Both intervals are
reported rather than averaging away their opposing behavior.

## Isolated-note localization and envelope sensitivity

An exploratory follow-up uses the eight isolated holdout notes already named
in the committed Q0 protocol. It measures each original note-on to note-off
interval separately, preserving the same full-file training gain and lag.
No new parameters or notes are selected to improve the result.

With the primary envelope, the LP12 diagnostic improves **7/8** isolated-note
spectral distances; MIDI 91 changes slightly from 0.2825 to 0.2832. Both LP24
diagnostics improve **8/8**. At MIDI 57, the distances change 0.2522 → 0.1523
for LP12 and 0.2772 → 0.1699 / 0.1770 for LP24. Thus the whole-sequence
regression cannot be explained simply as failure at high notes. The remaining
passages contain short notes, transitions, chords and tails, which this
isolated-note test does not separate. Identifying their causes needs further
time-dependent engine measurements.

The fixed nominal sensitivity changes only filter decay to raw **63**
(1.01387 s), retaining the same recording lag. It does not fit the Q50 recording.

| Slope / diagnostic | Nominal-one-second post-training spectral distance |
| --- | ---: |
| LP12 current raw63 / raw64 | 0.62955 / 0.63278 |
| LP12 stronger diagnostic | 0.70746 |
| LP24 current raw63 / raw64 | 0.83547 / 0.83941 |
| LP24 equal / split diagnostic | 0.91680 / 0.93179 |

Under this nominal envelope, each stronger diagnostic worsens **all eight**
isolated-note distances as well. The conditional success of the primary
isolated notes therefore cannot justify promoting damping independently of the
envelope and raw-patch uncertainty.

## Controls and fixed nuisance policy

All five renderers are built from one frozen **b0f6c03** shipping-source
checkpoint. The profile tool starts with `Engine::defaultTimbreCalibration()`;
only the declared damping tables change. Explicit LP24 second-stage tables set
`secondStageIndependent=true`. Constant tables are diagnostic fixtures used at
fixed raw resonance 64, not suggested global production curves.

Two byte-identity checks pass for both slopes:

1. Enabling the calibration path with unchanged defaults produces the same raw
   WAV as the uncalibrated checkpoint at raw64.
2. Reconstructing the active Q0 common/Upper bytes on engine-generated INIT
   produces the same raw Q0 WAV as the committed earlier dry candidate. No
   ignored SysEx or published preset container is needed to reproduce this run.

The first setup accidentally used **17094f9**, the preceding evidence-only
commit. The required Q0 identity guard rejected it before Q50 metrics were
emitted. That setup is retained as rejected; it contributes no measurements.

The original author MIDI is hash-pinned and contains 124 positive note-ons and
124 velocity-zero note-offs, all on channel 1; it contains no channel controller
events that could move a flat diagnostic table. Timing, velocity and notes are
unchanged. The renderer omits only FF20=00 channel-prefix metadata and records
degraded replay explicitly. Other MIDI metadata remains audited.

Only note 36 at **1.5–1.9375057 s** calibrates recording alignment and gain.
First sample-difference crossings at 0.001 times local peak give shared
candidate lags of **−1303 samples (LP12)** and **−1414 samples (LP24)**. Each lag
is derived from the baseline and applied unchanged to every model, raw63
sensitivity and nominal-one-second run. Hardware[t] pairs with renderer[t+lag].
The 0.003 threshold changes relative lag by 4 / 1 samples; the 0.01 sensitivity
changes it by −219 / +204 samples, showing that higher thresholds can follow a
later waveform cycle. Those alternative crossings are recorded, not optimized
against validation audio.

One positive RMS gain is fitted over those aligned training samples per entire
render. Primary baseline64 gains are +6.383 dB / +2.114 dB (LP12 / LP24);
diagnostic gains are +4.787 dB for LP12 and −0.596 / −0.923 dB for LP24. Every
remaining note uses those same gains. Both raw-level and fixed-baseline-gain
measurements are also retained. There is no EQ, per-note gain, per-event timing
fit, time stretching, transposition or waveform-phase optimization.

The two held-out segments are measured separately with boundary guards; no STFT
window spans the excluded training interval. Harmonic-estimator validity does
not control admission to this audio comparison. The multiresolution STFT,
10/50 ms RMS envelope and raw-level measurements are preserved in full.

## Limits and reproduction

The author labels the physical knob **50%**, without SysEx or a raw rounding
rule. Raw63 and raw64 are hypotheses, not known original values. The Q0-derived
cutoff/envelope may differ from the physical Q050 setup; the author describes
setting controls by ear. MP3 encoding, an unknown capture chain, oscillator
phase and unmeasured output behavior remain confounds. No registered perceptual
margins or blinded listening acceptance test is provided. Output equivalence
remains **not_established**.

All renders are finite and end with zero active voices. The primary LP24 equal
and split diagnostic float WAVs exceed full scale: peaks **1.04780 / 1.04930**,
with **10,090 / 13,054** samples across both channels at absolute value ≥1.
The float files retain these values; the analysis does not hard-clip them.
Every other primary render and all nominal-sensitivity renders stay below full
scale. Gains used for analysis may also require common attenuation for listening.

The [replay tool](../../../Tools/compare_deepsonic_q50_engine.py) requires only
the original hash-pinned MIDI/Q050 MP3 cache, repository history, C++20, ffmpeg,
NumPy and SciPy. It privately decodes WAVs and records decoder version/binary
hash, source/decoded hashes and commands. Choose fresh output directories:

```sh
OPENBLAS_NUM_THREADS=1 python3 -B Tools/compare_deepsonic_q50_engine.py \
  --sources build-fidelity/deepsonic \
  --output build-fidelity/hardware-benchmark/q50-reproduction

OPENBLAS_NUM_THREADS=1 python3 -B Tools/compare_deepsonic_q50_engine.py \
  --sources build-fidelity/deepsonic \
  --output build-fidelity/hardware-benchmark/q50-nominal-reproduction \
  --nominal-one-second \
  --alignment-from build-fidelity/hardware-benchmark/q50-reproduction/results.json

OPENBLAS_NUM_THREADS=1 python3 -B Tools/analyze_q50_note_holdouts.py \
  --experiment-dir build-fidelity/hardware-benchmark/q50-reproduction \
  --output build-fidelity/hardware-benchmark/q50-reproduction/note-holdouts.json
```

The [isolated-note tool](../../../Tools/analyze_q50_note_holdouts.py) verifies
the raw render and decoded hardware identities and imports the frozen assessor.
Its localization was motivated by the opposing segment rankings and is labeled
exploratory, not an independent acceptance test.
