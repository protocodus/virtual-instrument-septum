# RCS A02 terminal-model diagnosis — 2026-09-20

**No clear implementation bug was found. Slower attack alone does not identify the hardware closure.** The unchanged model has a fixed, relatively bright endpoint followed by harmonic-generating overdrive. Reusing an active SOLO envelope adds a separate gate/history confound. This read-only audit does not fit parameters or alter DSP.

The actual baseline render uses the original A02 SysEx SHA-256 `1d8852b039a22559f388d1af0567c2805b8315b9e76eb8fdc604d6bf16444ac3`. Its frozen renderer is verified, all 18 source inputs match the current checkout, and all calibration sections are disabled. [The JSON](rcs-a02-terminal-model-2026-09-20.json) retains full provenance and calculations.

Upper decodes to LP24 cutoff120/resonance0, filter ADSR24/127/127/127, depth−22, overdrive on/drive33, zero key follow, cutoff velocity and LFO depths. The current formulas give:

| Quantity | Incumbent value |
|---|---:|
| Initial cutoff | 13,976.805 Hz |
| Envelope depth | −4.190476 octaves |
| Sustain envelope level | 1 |
| Terminal cutoff | **765.506 Hz** |
| Attack24 | 5.000552 ms |
| Drive33 pre-gain | 2.604642 (+8.315 dB) |
| Drive compensation | 0.681869 |
| Lower static cutoff64 | 657.706 Hz |

Cutoff is `base × 2^(envelope × depth)`. Sustain127 correctly gives envelope1, so decay127 contributes no further motion after the attack. Negative depth correctly closes the filter. Changing attack to 50/100/150 ms changes travel time while preserving 765.506 Hz. Neither sign, sustain decoding nor byte offsets explain the hardware's much lower late high-frequency floor.

The actual signal path is square+pulse → flat LOW FREQ → two lowpass stages → oversampled ADAA `tanh` overdrive → amp envelope/level → part mix/output. At the endpoint, the **linear filter alone** gives approximately −25.12 dB at 1.5 kHz, −48.35 dB at 3 kHz and −73.80 dB at 6 kHz. These values do not bound the final harmonics: the nonlinear stage comes afterward and can regenerate them. The amp envelope also follows drive, so its decay does not reduce the modeled drive-input excitation.

PW56 currently means duty0.698425. The generated pulse retains DC0.396850, which a lowpass preserves; drive pre-gain makes that a bias of **1.033653** at the shaper. This affects asymmetry and generated harmonics. Later output coupling removes steady DC but cannot undo harmonics already created. Hardware pulse duty/DC behavior, drive gain and transfer, and exact internal placement remain unmeasured; this is not proof that any one of them is wrong. The [Roland manual](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf), pp. 27 and 37–39, describes the high-level stages and distortion's added overtones, without specifying these numeric laws or internal algorithm.

The existing baseline's high/low band ratio at source-aligned 21.840 s is **−13.212 dB**, compared with hardware **−58.714 dB** using the same 1024-sample Hann / 1.5–12 kHz versus 300–1500 Hz measurement. Its baseline plateau remains about −13 dB across 21.70–21.84 s. This endpoint failure explains why a better broad score from a slower transient cannot establish a calibrated attack law.

There is also a reconstruction-sensitive behavior: `Envelope::trigger()` enters Attack **without clearing its current level**. Active SOLO notes reuse their voice. Our adjoining note-off/note-on events advance no release samples, so later filter attacks can restart from level1 and immediately remain at the terminal cutoff. A sufficiently long gap lets the short amplifier release finish; the next fresh voice resets its filter envelope to0. Hardware retrigger semantics and the actual gaps are unknown. This behavior is explicit in the current implementation, and is not an established bug; it also cannot explain the first fresh note's failed closure.

The unresolved combinations are base cutoff with **negative** depth scaling; pulse duty/DC/gain/phase with overdrive; attack shape with the terminal nonlinear spectrum; and retrigger behavior with true note overlap. The existing 12-octave envelope range was inferred from positive-depth material and does not independently calibrate −22. These quantities cannot be identified from broad-score improvement or one spectral crossing. Keep the attack probes experimental until the full note trajectory and independent controls support a specific change.
