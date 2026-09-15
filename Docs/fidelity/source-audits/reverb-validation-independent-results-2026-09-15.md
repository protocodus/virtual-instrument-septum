# Prospective reverb validation: independent completed-run verification

**All 36 render receipts and hashes passed.** Independent calculations from
the WAVs reproduced 108 measurements with maximum absolute difference
`4.479971948967432e-12`. All 48 listening arrays matched their prescribed
float32 samples exactly. No evaluator or DSP changes were made.

The [pre-score review](reverb-validation-independent-review-2026-09-15.md),
including the synthetic delay/gain and poisoned-evaluation checks, was saved
before inspecting this run. Source-only reconstruction inputs were frozen in
Git `b483c45`. The [complete verification receipt](reverb-validation-independent-results-2026-09-15.json)
retains each case, model, audio/receipt hash, summary and numerical difference.

## What was checked

- All three frozen source trees and binaries were checked against their
  manifests. Original source bytes were independently anchored to Git
  `b0f6c03`; the only candidate DSP differences were the specified final
  equal-channel reverb-return gains. This closes the source-anchor gap noted
  in the earlier evaluator review.
- All twelve case JSON files matched both pre-render protocol pins and
  pre-score Git `b483c45`. Original audio/preset identity, MIDI bytes and
  native MIDI replay events matched every render receipt.
- Prefix-only lag/gain, common evaluation supports and disjoint calibration
  supports were recomputed. Every primary measurement, candidate-prefix-gain
  sensitivity, and the four predeclared Class A region measurements was
  recomputed from raw WAV samples.
- Independent STFT, stereo and level formulas and FFT-convolution RMS
  envelopes reproduced the reported metrics. All 48 hardware/model listening
  files matched the common lag, primary gain, slice and shared listening
  scalar exactly.

## Interpretation limits

Six Ambient early/nominal cases reached the **−50 ms lag bound**; the three
late-gate variants used approximately −37.53 ms. This is a recorded protocol
limitation, not evidence for a new capture delay or a reason to select gates.
No gates or gain candidate were selected by this review.

Log-spectrum and envelope activity masks remain pair-dependent. Their
verification does not make them identical-bin comparisons; unmasked spectral
convergence retains common support. These checks establish correct provenance
and calculation for conditional reconstructed performances, not original MIDI,
hardware equivalence or a universally correct reverb gain.

## Reproduction

Run from the repository root, choosing a new output directory:

```sh
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 python3 Tools/verify_reverb_validation_run.py --run build-fidelity/hardware-benchmark/reverb-new-preset-validation/run-01 --out build-fidelity/hardware-benchmark/reverb-new-preset-validation/independent-verify-02
```

The [verifier](../../../Tools/verify_reverb_validation_run.py) consumes only the
frozen source/inputs, completed manifests, receipts and WAVs. It does not render,
change the performance, select a model, or run another alignment search range.
