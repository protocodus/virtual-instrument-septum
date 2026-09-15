# Alignment regression: numerical noise before a late attack

**A nearly silent candidate window could win the old envelope-alignment search through amplified FFT rounding error. The scorer now excludes unsupported variance.** Independent replay of **171 historical fitted transforms** changes only the newly identified `201vsJP8000` C3-release opening. The other **170 retain exactly the same lag and gain**, including every comparison supporting the provisional reverb-return change and both DUAL phase grids.

This is a measurement-tool correction. No instrument DSP, preset, MIDI or audio render changes. Historical results remain intact; the affected 201 release case now has a [separately recorded corrected evaluation](reverb-mode-damping-followup-2026-09-15.md) in `reverb-mode-damping-followup/run-02`.

## Reproduced failure

The 201 C3-release reconstruction has a late first attack in a .4-second calibration prefix. An allowed lag placed the candidate's common correlation support almost entirely before that attack. Its peak RMS envelope was only **5.818 × 10⁻¹⁹**, and centered variance **3.393 × 10⁻³⁷**—**1.442 × 10⁻³⁷** of the largest candidate-window variance.

FFT convolution produces tiny rounding errors even where the ideal numerator is effectively zero. Dividing that error by the near-zero normalization yielded **52.7228**, outside Pearson correlation's possible range. The old code selected this value, then clipped the reported correlation to 1.0. Direct centered dot products at the selected lag give only **.0292765**.

| 201 C3-release prefix | Historical fit | Corrected fit |
|---|---:|---:|
| Candidate lag | −1295 samples / −29.365 ms | **132 samples / +2.993 ms** |
| Prefix gain | 5.056782 | **4.443261** |
| Reported correlation | 1.0 after clipping | **.9917185** |
| Direct Pearson correlation at selected lag | .0292765 | **.9917185** |

The corrected lag equals the held-opening case's lag. The gains need not match because their complete calibration supports contain different key-release histories. This agreement does not recover an authentic hardware latency or validate either reconstructed gate.

## Independent code review

The [assessor](../../../Tools/assess_hardware_equivalence.py) makes two changes inside `fit_transform`:

1. Subtract the candidate envelope's mean before rolling sums, variance and FFT correlation. Adding or removing a common constant leaves Pearson correlation unchanged mathematically; centering improves numerical conditioning for flat envelopes.
2. Admit a lag only when its candidate centered variance exceeds **10⁻¹² times the complete candidate-prefix envelope energy**, alongside the existing nonzero-denominator requirement. This prevents numerical silence from competing with an audible attack. The threshold scales with candidate gain within the supported audible numerical range.

An AST comparison confirms that `fit_transform` is the only changed assessor function. Audio reading, RMS envelope construction, gain calculation, later spectral/envelope/stereo measurements, acceptance rules, allowed ±50 ms bounds and calibration intervals retain their previous implementations. Unchanged lag and gain therefore preserve the prior measurement supports and values; small changes in correlation metadata are ordinary floating-point effects.

This guard is an identifiability check, not an acoustic quality threshold or a guarantee that an envelope alignment is physically correct. It intentionally declines delay identification when candidate variation is too small. Existing search-boundary and transcription limitations still apply.

## Regression controls

The new [tests](../../../Tests/HardwareEquivalenceTests.py) use a late attack, a tiny pre-attack sinusoid, four known shifts **−137, 0, 132, 441 samples**, and three uniform candidate scales **.001, 1, 1000**. An independent focused replay of the same two test methods against the pinned old and new assessors confirms:

- **All 12 late-attack subcases fail with the old assessor**, selecting false negative lags instead of the planted shifts.
- **All 12 pass with the correction**, recovering exact integer shifts and inverse gains; the constant-candidate control also reports an unidentifiable delay.
- Both real 201 recordings preserve their corrected lag of 132 samples under candidate scales **10⁻⁴, .01, 1, 100, 10⁴**. Maximum inverse-gain compensation error is **2.22 × 10⁻¹⁶**.

The root task separately ran the complete 14-test Python measurement suite successfully. This audit independently replays the two relevant regression methods and the actual frozen audio fits; it does not rerun DSP builds or render candidates.

## Historical impact audit

Each historical fit is first reproduced exactly with its pinned old assessor. The updated scorer then receives the identical calibration samples. Reference/model WAV hashes are checked before use. The reverb audit additionally checks **185 complete model WAV/receipt pairs**, including the paired variants whose timing is inherited from the previous-return fit.

| Frozen study | Fitted records checked | Changed lag/gain |
|---|---:|---:|
| Reverb width candidates | 10 | 0 |
| Reverb return candidates | 10 | 0 |
| Class A / Ambient original validation scenarios | 12 | 0 |
| Ambient first-gate extension | 1 | 0 |
| 201 held/release opening hypotheses | 2 | **1: C3 release only** |
| Common classic phase grid | 8 | 0 |
| Independent Upper/Lower phase grid | 32 | 0 |
| Named-preset CLI prefix assessments | 52 | 0 |
| Filter-envelope preset holdouts | 10 | 0 |
| Cutoff-taper candidate baseline fits | 10 | 0 |
| Initial dry note36 fits: original, rejected bypass setup, reproduction | 24 | 0 |
| **Total fitted records** | **171** | **1** |

The 52 named-preset CLI records comprise the original ten-preset baseline, original and reproduced LFO-only/zero-resonance cohorts, and both linear-profile controls. The initial dry replay preserves its historical native float32 reference arithmetic and float64 candidate left-channel adapter; it does not silently change the input math. Ten additional older whole-file assessments used `max_lag_seconds=0` and never entered the correlation branch.

These counts include repeated inputs and reproduction controls; they are not independent hardware observations. Across all corrected selected lags, reported versus independently computed direct Pearson correlation differs by at most **6.37 × 10⁻¹⁴**. The minimum selected-window variance fraction of its search maximum is **.10277**, far above the pathological case's old 10⁻³⁷ fraction.

The previously reported Club and Ambient regressions survive unchanged. In particular, all Ambient phase-grid lags still sit at −50 ms: the numerical guard does not resolve that distinct articulation/alignment uncertainty.

## Other dependency review

The [JSON receipt](alignment-silence-regression-2026-09-15.json) pins the reviewed source files and records why these studies do not inherit the faulty search:

| Study | Timing method / effect of this fix |
|---|---|
| Final dry Q0 engine comparison | Uses explicit training-note onset thresholds; its earlier free-correlation results were also checked above. |
| Dry phase and experimental dry envelope comparisons | Fixed physical delay plus known renderer latency; no `fit_transform` call. |
| Q50 engine and later note holdouts | Training-note onset threshold or pinned inherited lag. |
| Moogie envelope candidate selection | Frozen source onset windows, renderer 93-sample compensation and predeclared timing sensitivity; harmonic scoring. |
| Public LFO clock and step-shape evidence | Periodogram/frequency refinement and source edge-grid fitting; does not call this assessor. |
| Dry filter, chord-envelope and slope-ratio estimators | Local harmonic or transfer fits, without RMS-envelope alignment search. |
| Source stereo/tail reports and reference-mask summaries | Use unchanged readers, RMS, stereo or measurement helpers; no new prefix lag search. |

No production-supporting result found in this dependency review is invalidated by the correction. This statement concerns this specific numerical bug and the enumerated inputs, not all possible measurement errors.

## Reproduce and provenance

The original ignored benchmark runs and their pinned audio are prerequisites. Replaying only these analyses does not build or render instruments, decode replacement audio, or overwrite historical results.

```sh
OPENBLAS_NUM_THREADS=1 python3 Tools/audit_reverb_alignment_variance.py \
  --benchmark-root build-fidelity/hardware-benchmark \
  --output build-fidelity/hardware-benchmark/alignment-silence-regression/reproduction

OPENBLAS_NUM_THREADS=1 python3 Tools/audit_other_alignment_dependencies.py \
  --fidelity-root build-fidelity \
  --alignment-run build-fidelity/hardware-benchmark/alignment-silence-regression/reproduction \
  --output build-fidelity/hardware-benchmark/alignment-silence-regression/reproduction-other
```

Recorded runs: `alignment-silence-regression/run-01` and `other-studies-01`. Historical assessor SHA-256: `b6ca63fa02ff11f3154cf34c1233cfe460fd4447be403fe4c0695646ccb74631`. Corrected assessor SHA-256: `09d43cb55f7b90fe4c06fc7f79b803d809735f2e4c2ee36db6002d17d595f642`.

The durable JSON retains both complete audits, input and tool hashes, exact old/new transforms, direct-correlation checks, dependency inventory, focused test logs and uniform-gain controls. Historical bad scores remain historical; they should not be silently relabeled as corrected measurements.
