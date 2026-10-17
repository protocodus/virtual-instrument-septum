# Saw alias frequency-offset sensitivity

**Small pitch/capture-clock offsets do not explain the disputed 14–17 dB alias-level errors through the existing estimator.** The detector already follows a local peak within ±6 Hz. Replacing nominal harmonic-subtraction frequencies with source-measured H1 changes the primary LP12 alias levels by at most **0.000021 dB**. Known-amplitude pitch/clock controls shifted by ±100 ppm recover within **0.002123 dB**. No kernel coefficients, model phases/gains, raw parameters or DSP were refitted.

This rules out the tested measurement-frequency confound, not the existence of a small capture-clock offset. It does not authenticate the learned asymmetric kernel or identify the original oscillator, filtering, encoding or recording path.

## What the earlier tools actually use

- `fit_high_note_saw_asymmetric_kernels.py` generates every waveform at equal-tempered MIDI f0 (`440 × 2^((note−69)/12)`) and 44.1 kHz. The single training window fits phase, gain and kernel coefficients; later windows fit phase/DC only. It does **not** use the independently reported H1 refinement.
- `analyze_deepsonic_saw_aliases.measure` subtracts main harmonics at that nominal f0, allowing independent quadratic complex-amplitude variation across the 80 ms window. Descending alias locations are `44100 − h × f0`. After subtraction, the Hann residual spectrum is searched within **±6 Hz** for an actual interior peak. Zero padding gives a 0.168 Hz grid, not that resolving power.
- `assess_saw_asymmetric_codec.py` freezes the candidate, phases, indices and hardware eligibility mask. Its gapless codec check applies no lag. That codec control bounds a tested encoder, but did not itself test pitch/capture-clock offsets.
- The earlier harmonic-invariance audit refined H1 from the first LP12 window and compared nominal/refined carrier conventions. Its explicit +3-cent planted control concerned main harmonics. The present alias test closes that narrower remaining measurement gap.

## Original-only checks

The same five previously frozen 80 ms passages are retained: note 91 at +100/+160 ms and notes 93/88/86 at +100 ms. Both Q0 LP12 and LP24 original MP3s are hash checked and privately decoded; no source is downloaded. LP12 passage sample hashes and all original nominal alias levels reproduce exactly to the declared 1e−8 dB numerical guard. Source identities and every observation are in the [receipt](saw-alias-frequency-sensitivity-2026-09-15.json).

| LP12 passage | Local H1 offset | H1 offset in ppm | Largest alias-level change after H1-basis refinement |
|---|---:|---:|---:|
| 91 +100 ms | +0.024287 Hz | +15.489 | 0.00000945 dB |
| 91 +160 ms | −0.012794 Hz | −8.160 | 0.00001551 dB |
| 93 +100 ms | +0.031835 Hz | +18.088 | 0.00001257 dB |
| 88 +100 ms | +0.015529 Hz | +11.778 | 0.00001502 dB |
| 86 +100 ms | −0.045412 Hz | −38.660 | 0.00002063 dB |

Independent H2/H3 local peak offsets per harmonic broadly agree in the early high-note windows. Later/lower windows show more variation, consistent with moving-filter phase. These are local Hann peak measurements, not a calibrated tuning or clock estimate. Across both slopes and all five passages, the largest alias-level change is **0.000681 dB**, in LP24 note 91's later window.

The disputed original LP12 lines are already interior peaks:

| Note / alias | Nominal frequency | Measured peak offset | Existing W4 minus hardware | Change after refined harmonic subtraction |
|---|---:|---:|---:|---:|
| 93 / h19 | 10660.000 Hz | +0.281 Hz | +16.741 dB | +0.00000118 dB |
| 88 / h28 | 7181.714 Hz | +0.283 Hz | +13.885 dB | −0.00001298 dB |
| 88 / h27 | 8500.224 Hz | +0.681 Hz | −11.518 dB | −0.00001502 dB |

Even a hypothetical measurement at the exact nominal frequency, instead of the implemented peak search, would lose only **0.00156 / 0.00266 / 0.01573 dB** at these three source lines. That diagnostic uses continuous Fourier peak refinement on the same residual; it does not select a new scoring frequency or hardware mask. The 10660 Hz line lies only 100 Hz from H6, yet changing the subtraction carrier still has a negligible effect on its measured level.

## Planted fractional-frequency controls

The synthetic signals retain the original-window harmonic magnitudes and all LP12-qualified descending alias amplitudes. Two fixed phase patterns (0.137/0.713 cycles with declared per-harmonic offsets) and five fixed offsets (**−100, −50, 0, +50, +100 ppm**) test each passage. These exceed the primary LP12 H1 shifts. LP24 note 86 reaches −100.3 ppm locally, so this grid is not claimed to bracket every secondary slope's phase motion.

The two mechanisms are deliberately distinct:

1. **Oscillator pitch:** main harmonics become `h × f0 × alpha`, while aliases become `44100 − h × f0 × alpha`.
2. **Capture clock:** every main-harmonic and alias frequency is multiplied by `alpha`.

Here `alpha = 1 + ppm/1e6`. Every amplitude remains fixed. The same nominal-frequency subtraction and ±6 Hz search measure each positive control; alias-free counterparts measure spurious residual leakage. No oscillator kernel or hardware candidate is fitted in these controls.

| Control | Qualified line observations | RMS amplitude-recovery error | Maximum absolute error |
|---|---:|---:|---:|
| Oscillator pitch offsets | 500 | 0.000534 dB | 0.002123 dB |
| Capture-clock offsets | 500 | 0.000431 dB | 0.000802 dB |

All **1000** positive-control line peaks remain interior. For the disputed 10660/7182 Hz pair, maximum absolute error is **0.001497 dB** across both mechanisms. All corresponding alias-free residual levels remain at least **94.25 dB below** the planted line amplitudes; the strongest negative-control residual anywhere is −146.57 dB/H1. These are arithmetic leakage controls, not a physical noise-floor prediction. No new MP3 roundtrip is needed to repeat the already frozen codec experiment.

## Scope and reproduction

The result supports retaining the observed alias notch mismatch as a real mismatch of the frozen prediction under this measurement. It does not prove that a kernel trained at nominal f0 is uniquely identified: frequency/phase origin, source nonstationarity, filter contribution and capture response remain model limitations. No hardware frequency refit, sample-rate selection, new oscillator family or shipping correction follows from this audit.

```sh
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
/Library/Frameworks/Python.framework/Versions/3.11/bin/python3 \
Tools/audit_saw_alias_frequency_sensitivity.py \
  --sources build-fidelity/deepsonic \
  --output build-fidelity/high-note-shape/frequency-sensitivity-reproduction
```

Use a new output directory. The tool verifies the tracked asymmetric baseline/helper hashes and original LP12/LP24 MP3/MIDI hashes, records the actual decoder version/hash, and retains every source window and planted line result. Durable data come from `frequency-sensitivity-v2`; v1 completed the same calculations but failed JSON serialization of a NumPy boolean and produced no result JSON. The v2 change is only the explicit boolean conversion.
