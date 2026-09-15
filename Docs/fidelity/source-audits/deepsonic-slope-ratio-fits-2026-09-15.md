# Paired Q0 filter-slope ratios

2026-09-15. **An ordinary extra low-pass section explains the low-note slope difference well. The nearly flat high-note H2–H8 ratios require a much higher effective cutoff than the frozen low-note trajectory predicts, under the shared-source assumptions.** Near-flat ratios give broad cutoff bounds, not a precise endpoint. Later ratios retain discrepancies even when damping is free. No production DSP, raw parameter law or bypass rule changed.

## What cancels, and what remains assumed

For each harmonic, this diagnostic subtracts normalized LP12 magnitude from normalized LP24 magnitude:

`R_h = 20log10(Ah_24/A1_24) − 20log10(Ah_12/A1_12)`.

A shared oscillator/capture frequency response and a constant recording gain cancel; no ideal-saw `1/h` spectrum is assumed. Interpreting the remainder as **one extra section** additionally assumes the same oscillator spectrum, common capture response, identical first filter section and identical cutoff in both recordings. The [owner's procedural recipe](https://www.deepsonic.ch/deep/htm/deepsonic_analytics_filter_comparison.php) does not authenticate identical raw patches or these equalities. The 40 ms windows can also contain moving-filter effects.

Inputs are the [independent invariance audit's](deepsonic-high-note-invariance-2026-09-15.md) hash-verified Q0 amplitudes: MIDI69/84/86/88/91/93, 40 ms windows at +80/+120/+160/+200 ms, extended through +400 ms for the two long gates. Nominal MIDI frequency and the existing frozen LP12 H1 refinement are both retained. Per-time H2–H8 eligibility is shared across both slopes and both frequency policies: above −55 dB/H1 and at least 20 dB coefficient-SNR proxy. Fixed H2–H4 is a separate sensitivity group. Weak higher harmonics later in the gate are explicitly excluded from the variable group; that group is not compared as though its membership stayed constant.

Source harmonic-model residual power is retained as a diagnostic, rather than an additional rejection threshold. Its maximum is 0.0027% of signal variance here. A small residual verifies the local amplitude representation; it does not make a moving filter stationary.

## Conditional model and tolerance ranges

The extra TPT low-pass response is `H(f)=1/(1−r²+jkr)`, with `r=tan(πf/44100)/tan(πfc/44100)`, normalized to `H(f0)`. Cutoff spans 5–22000 Hz. The first fit fixes damping `k=1.2`; the second permits `0.05≤k≤4`. Cutoff/damping fits use bounded multi-start searches. No per-harmonic gain or new raw-control curve is fitted.

Profiles use 1201 logarithmic cutoff samples, with damping profiled when free. Reported ranges allow the best RMSE plus 0.10, 0.25 or 0.50 dB. These are explicit sensitivity tolerances, **not statistical confidence intervals**. Flat profiles reaching 22000 Hz do not identify a finite cutoff; the grid brackets their lower edges. The upper bound is the search limit, not a measured hardware endpoint.

## Representative results

All rows below use nominal frequency and qualified H2–H8. Errors are RMS over harmonic ratios, in dB. The final column is a rounded conservative lower edge for the **free-damping** best+0.25 dB tolerance region; every listed high-note region extends to the 22 kHz search ceiling.

| Note / center | Frozen low-note fc | Error at that fc, fixed / free k | Best fixed-k fc / error | Best free-k error | Free-k tolerance lower edge |
|---|---:|---:|---:|---:|---:|
| 69 / +80 ms | 2983 Hz | 0.804 / 0.401 | 3443 Hz / 0.027 | 0.020 | 3085 Hz; bounded above |
| 84 / +80 ms | 7096 Hz | 1.578 / 1.099 | 22000 Hz / 0.100 | 0.018 | ≈9.12 kHz |
| 86 / +80 ms | 7965 Hz | 1.723 / 1.233 | 22000 Hz / 0.008 | 0.006 | ≈10.63 kHz |
| 88 / +120 ms | 7626 Hz | 3.382 / 2.621 | 19740 Hz / 0.012 | 0.007 | ≈11.73 kHz |
| 91 / +160 ms | 7772 Hz | 5.724 / 4.983 | 21185 Hz / 0.035 | 0.024 | ≈13.49 kHz |
| 93 / +160 ms | 8724 Hz | 6.348 / 5.695 | 21307 Hz / 0.015 | 0.014 | ≈15.08 kHz |

Low69's four windows fit the fixed-damping extra section with 0.027–0.053 dB RMS error. Their fitted cutoffs decline from 3443 to 2050 Hz, while the frozen extrapolation gives 2983 to 1879 Hz. This is a conditional paired-response measurement, not a replacement cutoff law.

The high-note fixed-damping optima lie near the top of the search, but free damping reduces some optimum cutoffs considerably. For example note91/+160 ms has a free optimum near 16.96 kHz, `k=1.343`; its tolerance region spans approximately 13.49–22 kHz. At +160 ms on note93, the optimum is about 19.22 kHz, `k=1.370`, with a 15.08–22 kHz tolerance region. **Neither observation determines a precise Nyquist-adjacent cutoff.**

The high harmonics carry this constraint. Fixed H2–H4 alone allows substantially more freedom: at the frozen cutoffs, free-damping errors for note91/+160 ms and note93/+160 ms are only 0.223 and 0.203 dB. Their best+0.25 dB lower edges fall to approximately 7.50 and 8.33 kHz. Those lower harmonics alone cannot strongly reject the frozen trajectory. All H2–H8 in the earlier table remain eligible under both source frequency conventions.

The simple extra-section model is also incomplete later. At note91/+240 ms it retains 0.341 dB RMS and 0.489 dB maximum error with free damping over H2–H8. At +400 ms, qualified H2–H6 retain 0.487 dB RMS / 0.660 dB maximum error. Fixed H2–H4 reduces that late error to 0.125 dB RMS, showing that the broader shape matters. These discrepancies can arise from unequal source/first-stage settings, a moving response, or an inadequate extra-section model; they do not uniquely locate the cause.

Changing to the frozen refined-frequency convention changes fitted RMS errors by at most 0.00080 dB for fixed damping and 0.00065 dB for free damping across the complete set.

## Actual recurrence control

A compiled fixture extracts the shipping SVF state recurrence and runs it at fixed cutoff/damping, with amplitudes kept below its nonlinear state limiter. It processes an arbitrary eight-harmonic source with deep H5/H6 notches, a common signed FIR capture response, and an independent 0.83 gain on the two-stage output. The control therefore tests cancellation without a `1/h` assumption or identical output gain.

All **54 cases** pass: six pitches × cutoffs 2500/7000/18000 Hz × damping 0.8/1.2/2.0. After one second of state settling, the final 40 ms ratio recovers the analytic transfer with maximum RMS error **8.0×10⁻¹⁰ dB**. Maximum relative cutoff recovery error is **5.7×10⁻¹¹**, and damping error **4.5×10⁻¹⁰**. These are numerical fixture accuracies, not hardware-measurement uncertainty. The fixture checks the extracted scalar recurrence, not the complete plugin signal path.

## Reproduction and decision

[The durable JSON](deepsonic-slope-ratio-fits-2026-09-15.json) retains every fit, mask, profile range, source receipt and the full-result hash. The full measurements and generated C++ fixture remain in ignored `build-fidelity/deepsonic/slope-ratio-v1/`.

```sh
OPENBLAS_NUM_THREADS=1 python3 Tools/fit_deepsonic_slope_ratios.py \
  --input build-fidelity/deepsonic/high-note-invariance-v3/results.json \
  --output build-fidelity/deepsonic/slope-ratio-new
```

Use a new output directory. This test supports a Q0 high-note response that is effectively more open than the ordinary section at the frozen low-note cutoff predicts. It does not distinguish clamping, switching, a changed cutoff mapping, or undocumented recipe differences. The separate Q50 evidence rejects extending Q0 invariance to an unconditional cutoff-only bypass. No engine correction is selected here.

The large errors at the frozen cutoff reject that **extrapolation plus extra-section model together** under the stated assumptions. They do not independently measure a 7 kHz transition or another hardware switching threshold.
