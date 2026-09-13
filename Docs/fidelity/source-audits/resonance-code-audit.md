# Resonance implementation audit, 2026-09-13

This audit describes the **fixed-second-stage baseline before the September 13 resonance calibration**, plus two isolated experimental models. The accompanying CSVs are synthetic implementation measurements, not Roland recordings. Production subsequently adopted a more conservative bounded model; the unrestricted two-stage experiment below is not a recommended production setting.

## Finding

The baseline's soft moderate resonance was a calibration/topology question, not an identified SysEx scaling or filter-coefficient bug. The [Roland MIDI Implementation](https://static.roland.com/assets/media/pdf/SH-201_MI.pdf), p. 5, assigns resonance an unsigned byte at tone offset `0x16`, range 0–127. The public [Editor 1.10 resource](https://static.roland.com/assets/media/dmg/SH201_Editor110_osx.dmg), `BufferModel.xml`, names the same address and range; `PatchFilter.xml` binds its knob and numeric display directly. Septum's decoder, host parameter, and panel CC path use that range without an extra signed or normalized conversion.

The [Owner's Manual](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf), pp. 36 and 61, describes increasing the boost near cutoff and possible sustained oscillation at high resonance. It does not establish a numerical Q law, exact oscillation threshold, limiter voltage, or internal filter topology. The old source's claim that both numerical damping endpoints were settled overstated this evidence. The square-root taper and second-stage damping were explicitly choices made by ear elsewhere in the source and [decision log](../../decisions.md).

The baseline uses `k = 2 − 2.04√(raw/127)` in its first TPT state-variable section, and fixed `k2 = 1.2` in the second section for 24 dB operation. The coefficient normalization and LPF/HPF/BPF taps are internally consistent. The band-pass tap is already unnormalized, so the earlier bug that suppressed its peak by multiplying by damping is not present. Resonance smoothing reaches the target rather than applying a persistent attenuation.

## Small-signal and limiter measurements

[Probe source](../../../Tools/AnalyzeResonance.cpp), [runner](../../../Tools/analyze_resonance.py), [56 transfer measurements](resonance-code-audit.csv), and [source/binary hashes and sweep summaries](resonance-code-audit.json).

The probe drives EXT-IN with a known sine at amplitudes 0.001 and 1.0. It disables the separate AUDIO FILTER, effects, drive, filter modulation, and velocity gain; selects one oscillator; sets cutoff 64; and measures at 48 kHz. Tone level 25 attenuates **after** the voice filter, leaving its internal excitation intact. Projection uses seconds 1–2 of a two-second render and is divided by a corresponding BYPASS render. The transfer probe uses frequency ratios 0.75 and 1 relative to the bilinear-warped natural frequency.

For raw resonance up to 100, gain agrees with the analytical transfer to within 0.000164 dB at both input amplitudes. At amplitude 0.001 it agrees across the entire tested range through 120. This rules out a coefficient error or limiter suppression as the explanation for weak resonance around raw 40–44 in this fixture.

The analytical baseline peaks illustrate how mild that region was:

| Raw | First-stage damping | LPF12 peak | LPF24 peak | LPF24 peak frequency / natural frequency |
| --- | ---: | ---: | ---: | ---: |
| 31 | 0.99212 | 1.295 dB | 1.516 dB | 0.6375 |
| 44 | 0.79924 | 2.702 dB | 2.592 dB | 0.7321 |
| 64 | 0.55183 | 5.508 dB | 4.791 dB | 0.8542 |
| 100 | 0.18979 | 14.474 dB | 13.006 dB | 0.9820 |

At the natural frequency itself, raw 44 LPF24 gains only 0.363 dB. The fixed second section attenuates by 1.584 dB at that frequency. It is more accurately described as a fixed, mildly peaked section than as strictly non-resonant: `k2=1.2` gives Q=0.833 and a 0.355 dB peak by itself.

The state limiter does become significant at stronger settings. For a full-amplitude sine at the natural frequency, LPF24 at raw 110 measures 16.706 dB against the linear model's 18.292 dB. At raw 118 it measures 16.912 instead of 27.887 dB; at 120, 16.948 instead of 33.799 dB. Quiet input still follows the linear model. These differences are input-dependent saturation in the current state limiter, not an incorrect conversion of the resonance byte.

## Experimental sweep

Each model has 1,536 independent renders: every resonance integer 0–127, all three filter types, both slopes, and both input amplitudes. The positive first-stage damping transforms as `2*(oldK/2)^power`; zero/negative damping is retained. Only the voice filter changes; AUDIO FILTER retains its original mapping.

| Model | Power | Second-stage damping | First-stage limiter begins, full input | Second-stage limiter begins, full input |
| --- | ---: | --- | ---: | ---: |
| [Historical baseline](resonance-candidate-sweeps/baseline.csv) | 1 | 1.2 | 108 | Never |
| [Stronger first stage](resonance-candidate-sweeps/first-stage-2.7.csv) | 2.7 | 1.2 | 51 | Never |
| [Unrestricted two-stage experiment](resonance-candidate-sweeps/two-stage-1.6.csv) | 1.6 | `min(1.2, k1)` | 83 | 54 |

All 4,608 renders are finite, and every adjacent-setting RMS change is nonnegative. In the two-stage experiment, quiet input first triggers the second-stage limiter at raw 113; the first stage at 123. Negative damping in both sections remains bounded in this static test.

These results do **not** establish safe live automation. Settings use separate reset renders. Very high-Q signals can still be building in the measurement window, so their RMS is not a steady-state Q measurement. The largest quiet-input adjacent rise is 22.12 dB in the baseline, 8.25 dB in the stronger-first-stage model, and 2.69 dB for the two-stage model's 24 dB output. Those are finite-duration level differences, not measured sample discontinuities.

`output_peak` covers the whole file, including the initial EXT-IN direct-monitor handover; its roughly 0.921 maximum is shared by all three models and must not be interpreted as the voice filter's steady peak. RMS and harmonic projection start after that handover. Limiter counters count each integrator-state value above the knee, before limiting. Stage 2 always runs, even with 12 dB output selected; its counts do not then describe selected output saturation.

## Why the unrestricted experiment was rejected

The separate core-suite run of the unrestricted power-1.6 model exposed behavior this static sweep cannot test: HPF24 peak 1.015659 exceeded its normal-patch 0.9 limit, a sample-and-hold filter modulation jump reached 1.303, and a slope-switch jump reached 0.010235 against the existing bound of four times 0.002501. Three further failures merely pinned the old assumption that LPF24 must peak less than LPF12; those assertions were incompatible with the newly observed resonance contrast.

The bounded alternative uses power 1.5 and `k2=clamp(k1, 0.5, 1.2)`. At raw 44 its first-stage damping is about 0.505, so the floor leaves the conditional recording fit near raw 40/44 intact while limiting extrapolation into unmeasured high-resonance settings. The first stage still self-oscillates. The second stage no longer becomes an independently unstable section. The broader core-suite run cleared the independent peak and modulation/transition failures with this guard; only the three old topology assertions remained before their replacement.

The floor is a conservative modeling choice, not a recovered Roland circuit constant. Q=2 can still saturate under strong drive, so boundedness alone would not justify it. Tests should retain independent automation and headroom checks, verify measured small-signal resonance contrast, and verify the separate AUDIO FILTER remains unchanged. The [SupaJuce recording audit](supajuce-resonance-audit.md) supplies the hardware evidence; this audit supplies implementation diagnostics.

## Reproduction

The runner copies source and its support archive into a new output directory and never edits shipping DSP:

```sh
python3 Tools/analyze_resonance.py --output /tmp/septum-resonance-audit
```

`baseline` explicitly recreates the historical square-root/fixed-stage model even if current production uses a calibrated voice helper. For a quick transfer-only check:

```sh
python3 Tools/analyze_resonance.py --output /tmp/septum-resonance-transfer \
  --profiles baseline --modes transfer
```

To reproduce the exact captured inputs later, pass `--source` pointing to the saved `production-source` directory and `--archive` pointing to its accompanying archive. The capture used here is `/tmp/septum-hw-benchmark/resonance-code-audit/profiles-v1`. A second build from that frozen capture reproduced the transfer CSV byte for byte, SHA-256 `64378e00a521da8f140a68fb5f8135e2c414a887d09a9eeaaf661bdb230f38dc`. Hashes of every compiled source, copied header, archive, executable, and CSV are retained in the JSON. Later source changes outside resonance can change results; the hash record makes that distinction visible.
