# Frozen W4 alias transfer across eight original pitches

**The wider original-mask check supports a provisional classic-Saw correction.** The selected vector improves the complete-mask alias proxy RMS in every one of32 original note/offset/slope windows. This includes additional pitches69,76,81 and84, beyond the five windows used in earlier W4 comparisons. The check changes no coefficient, waveform family, phase, timing, gain or eligibility mask.

The [complete receipt](saw-w4-alias-transfer-2026-09-15.json) pins the original MP3/MIDI, selected vector, actual full-engine WAVs, source measurement helper, premeasurement protocol and every original/modeled line. Tool: `Tools/assess_saw_w4_alias_transfer.py`; run: `build-fidelity/saw-w4-engine/alias-transfer-01`.

## Unchanged reference and timing conventions

The [earlier alias audit](deepsonic-saw-aliases-2026-09-15.json) already supplied eight pitches,80ms windows at offsets100/160ms and separate original-only LP12/LP24 masks of200/168 line-windows. Those masks are retained exactly. Note91 is excluded from coefficient-transfer aggregates. All these recordings have previously been examined; this is exploratory transfer testing.

The earlier audit used stereo-mean engine audio and `onset−.035+93/44100` timing. Its hardware and old-timing production levels reproduce with **zero discrepancy**. The present comparison then applies the established−1406-sample offset to both production and W4 left-channel audio. Thus the masks are inherited without silently treating the two historical timing conventions as identical.

## Results excluding trained note91

| Filter | Original line-windows | Production → W4 proxy RMS | Resolved model lines | Individual absolute errors improved |
|---|---:|---:|---:|---:|
| LP12 | 182 | 23.690 → 7.911dB | 98 → 158 | 147 /182 |
| LP24 | 150 | 27.309 → 11.435dB | 60 → 117 | 123 /150 |

All32 per-window RMS comparisons improve; individual contrary bins remain in the JSON. Representative100ms windows:

| MIDI | LP12 production → W4 | LP24 production → W4 |
|---|---:|---:|
| 69 | 34.830 → 3.800dB | 40.027 → 3.565dB |
| 76 | 25.976 → 9.144dB | 33.893 → 6.079dB |
| 81 | 15.183 → 12.099dB | 19.407 → 16.807dB |
| 84 | 19.340 → 6.119dB | 23.427 → 12.688dB |
| 86 | 22.265 → 6.035dB | 25.707 → 12.714dB |
| 88 | 23.364 → 5.752dB | 25.144 → 9.934dB |
| 93 | 16.550 → 7.722dB | 16.825 → 7.198dB |

These are complete-mask **search-maximum proxies**, not precise physical-line errors when a candidate peak fails the retained interior-peak/prominence/−75dBc threshold. Failed candidate lines remain in the denominator. The same original source/codec/background limitations as the earlier audit apply. The results do not prove that every DSP block runs at44.1kHz.

## Independent promotion judgment

I support a provisional adoption of the frozen W4 source vector. Its benefit now extends across register and both filter slopes. Combined with the previously verified LP12 upper-harmonic improvement, held-note84 energy improvement and independent AirLead gain, this is enough to justify a partial correction without requiring uniform success or identifying Roland's exact implementation.

The LP24 harmonic-ratio regressions, broad dry log-spectral regressions and SoJuno/Vangelead wet log-error regressions must remain explicit. Small full-sequence energy changes do not erase those counterexamples, and no listening-based inaudibility claim is made here.

One concrete integration gate remains: **sample-rate convention**. The experiment defines four source samples at44.1kHz, while the shipping engine runs at the host rate. Reusing four host samples changes the support from90.70µs to83.33µs at48kHz and41.67µs at96kHz. The production implementation must state its convention and check its main-harmonic/source behavior at48/96kHz while reproducing the validated44.1kHz output. This is a bounded integration check, not a request for another parameter fit or new hardware acquisition.

No production DSP change is part of this receipt. Whole-instrument equivalence remains unestablished.
