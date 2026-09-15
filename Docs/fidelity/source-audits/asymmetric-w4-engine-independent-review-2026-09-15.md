# Independent W4 engine prerequisite review — 2026-09-15

**No source-math, clock, or affine-backend blocker found.** This review supports trying the proposed partial oscillator correction through the actual engine. It does not establish a match to the SH-201 or validate a hardware-fitted vector. The independent phase-search recovery gate also passed on retained complete-engine audio.

The [machine-readable receipt](asymmetric-w4-engine-independent-review-2026-09-15.json) preserves reviewed file hashes, all numerical results, and the independent checker source text. No production DSP was changed, and no hardware optimizer was run for this review.

## Source definition

The [proposal](asymmetric-w4-engine-test-proposal-2026-09-15.md) uses 16 retained cubic B-splines on each half of a four-sample wrap neighborhood. Repeated half-sample interior knots give C1 continuity within each half. Omitting the final two basis functions makes the value and first derivative zero at either outer endpoint. The halves remain independent at the natural wrap.

For the positive-distance basis `B_j(t)`, let `n_j` and `p_j` be its negative- and positive-side coefficients. Define `K(d)` from `B_j(-d)` for `-4 < d < 0`, and `B_j(d)` for `0 <= d < 4`. At wrapped phase `u` and positive phase increment `a`, the candidate is

```
y(u,a) = 2u - 1 + sum over integer k of K((u-k)/a)
         - a * sum_j I_j (n_j + p_j)
I_j = integral B_j(t) dt = (knot[j+4] - knot[j]) / 4
```

Here `I = [1/8, 1/8, 1/4, …, 1/4]`. Periodizing first and changing variables in the integral proves zero continuous-phase mean, including overlapping support. At the engine's maximum increment 0.45, wraps `-1, 0, 1, 2` suffice; the implementation uses the general integer bounds. This normalization does not promise zero mean in a finite sampled window. No window-level subtraction should be inserted before nonlinear processing.

The exact existing polyBLEP is nested by

```
b = [1, 2/3, 5/12, 1/12, 0, …, 0]
n = -b; p = b
```

because `sum b_j B_j(t) = max(1-t, 0)^2`. No cross-wrap continuity condition was added: the general waveform's value jump is `-2 + p_0 - n_0`, and its one-sided sample-time slope change is `6*(p_1-p_0+n_1-n_0)`. Those are observable consequences of the proposed family.

## Independent checks

| Check | Result |
|---|---|
| Exact integral formula versus spline integration | Zero numerical difference |
| Continuous-phase quadrature at seven increments, including overlap | Maximum mean magnitude `6.94e-17` |
| Compiled De Boor source versus independent SciPy basis/reference | 55,488 comparisons; maximum error `2.22e-16` |
| Actual `renderClassicWave` clock, wrap offset, and RNG | 2,592 paired cases; all exact |
| Actual hard-sync reset / non-Saw sample identity | 2,376 paired cases; all exact |
| Disabled experiment and enabled nested polyBLEP versus pinned whole production WAVs | LP12 and LP24 byte-identical for both branches |
| Independent complete-vector audio versus cached affine columns | Relative RMS `5.73e-8` and `5.89e-8` at phases 0 and 0.321 |
| Coefficient-plus-DC matrix | Rank 33; conditions 8,967 and 8,866 |

The compiled-source checks cover every isolated coefficient, exact and adjacent knots, phase offsets, other notes, and increments through 0.45. The direct oscillator harness includes the actual copied engine implementation, rather than a replacement clock formula alone. The full-vector controls report no filter-state or output limiting.

## Planted phase-search recovery

All 328 cached operator matrices and their float64-array hashes were rechecked, together with 350 file hashes. The saved best is the lowest valid visited loss, all 256 coarse phases are present, and the fixed full-vector source was recovered at phase `0.3209999893` from planted `0.321`. Recomputed training error power is `3.20e-15`; the retained prediction reconstructs to `5.55e-17` maximum absolute difference.

All 12 canonical-phase comparisons were recomputed directly from the separately rendered WAVs: full performance plus five frozen high-note windows for each slope. The worst relative error power was `2.56e-14` for LP12 and `2.47e-14` for LP24, below the predeclared `1e-8` guard. Both source vectors retained the unit ramp, canonical phase, original MIDI and exact slope-specific patch. No optimizer was rerun, and no hardware recording was opened in this review.

## Fitter and state review

The backend's columns are responses to zero source, unit ramp, and each isolated basis. The correct affine composition is `F(ramp) + sum c_j*(F(basis_j)-F(zero))`, as implemented. Each column is prewarmed through the complete earlier MIDI. It is copied immediately before the exact note-91 event at sample 826875; capture follows the original 256-sample/event call boundaries and crops afterward. The original MIDI contains only one note-91 onset, so the note-specific phase offset does not alter an earlier occurrence in the full-vector control. Latency remains 93 samples.

The fitter fixes gain, lag, unit-ramp amplitude, and downstream DSP, and solves only 32 source coefficients plus output DC at each training phase. It retains invalid rank/condition rows and every valid coarse/refined best. The 256-point grid and at most 16 bounded local refinements are a finite search. Allowed natural-wrap jumps can make its sampled objective discontinuous; there is no global-optimum claim. Independently recovering a planted complete-engine source and transferring it to canonical-phase audio is the appropriate operational guard.

**Later candidate check:** unrestricted fitted coefficients can activate a nonlinear knee even though individual columns and small planted vectors do not. Independently render the fitted vector at the fitted phase, inspect limiter counters, and compare it with the affine prediction using the frozen gain/DC before calling the fitted loss an actual-engine loss. Canonical full-performance validation must use the actual rendered audio.

Fixing the ramp removes one amplitude ambiguity, but a short filtered window can still leave coefficient, phase, and DC directions weakly distinguishable. A consistent improvement on untouched notes and presets can be useful without identifying the manufacturer's unique oscillator architecture or assigning every spectral feature to the oscillator.
