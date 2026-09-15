# Independent production Saw review — 2026-09-15

**No actionable blocker found in the final Sync-guarded source.** The focused test passes **8,364 checks**. The [durable receipt](saw-w4-production-source-independent-review-2026-09-15.json) pins the final header, engine, test and CMake files, preserves the independent SciPy oracle/generator, and incorporates the prototype comparison and its retained failed exact-double check.

## Source and rate checks

`Tests/ClassicSawFidelityTests.cpp` is registered as `Septum.ClassicSawFidelity`. It requires no Python dependencies to run.

- Forty-two frozen values from an independent SciPy B-spline evaluator agree within `2.16e-15`, including overlapping support at the legal maximum increment.
- Phase-domain H2–H8 at 1,760 Hz agree with the independent oracle across 44.1/48/96 kHz within `7.82e-14 dB`.
- Piecewise Gaussian integration gives continuous-phase mean magnitude below `5.21e-16` across the rate/increment cases.
- Legal host rates from 8 to 768 kHz, small through maximum native increments, finite output, defensive input handling, and the maximum **63 periodic copies** are exercised.

The harmonic test samples a common set of waveform phases. It verifies the correction's fixed physical duration; it does **not** assert identical aliased host-rate spectra or provide new hardware validation. Likewise, the zero-mean result concerns the continuous waveform, not an arbitrary finite sampled window.

The retained compiled prototype comparison covers 140,014 source samples. Exact double equality initially failed at a `3.47e-18` difference. The completed comparison reports 979 double differences, a maximum absolute difference of `3.55e-15`, and **zero float-cast differences**. Both the failed exact-double receipt and the completed numerical receipt are preserved; no source adjustment was made to force bitwise double equality.

## Final code scope

The 32 coefficients match the frozen hardware-training selection. The paired basis integrals are computed once. The evaluator uses four active control points, has no allocation, rejects non-finite/out-of-range inputs before integer conversion, and bounds the periodized sum.

The engine supplies `nativeIncrement * (sampleRate / 44100)`. This retains four reference-sample widths in physical time and preserves the reference-rate arithmetic. Canonical phase advance, natural-wrap flags, fractional wrap offsets, and the existing waveform phase offset remain unchanged. Non-44.1 kHz hardware folding has not been measured.

The first production integration preserved the forced-reset sample but changed subsequent hard-sync samples through the wider correction support. An existing full-engine naive-sync waveform test caught that regression. The final guard keeps **OSC1 Saw under Sync** on the existing naive-reset/polyBLEP path; the test was not relaxed. OSC2 and ordinary Mix/Ring Saw still use W4. The guard is evaluated only inside the Saw waveform branch, so it does not change other waveforms.

## Performance and validation limits

Scalar timing is diagnostic: the separate 250,000-call batches measured about 3.7 ns/call at 440 Hz / 44.1 kHz and about 602 ns/call at the extreme 768 kHz / maximum native increment. These are single-process source-function timings, **not plugin capacity or real-time guarantees**. Typical reference-rate support requires at most four copies.

The focused source tests do not replace the existing full-engine Sync test, complete CTest suite, or raw 12-case production replay. The [final production replay](saw-w4-production-integration-2026-09-15.md), run-02 after the Sync fallback, reports all 12 complete WAVs byte-identical to the frozen experimental renders, including tails. Its replay was independently performed by the benchmark reviewer. This review made no production Source changes, new hardware fits, commits, or test-threshold relaxations.
