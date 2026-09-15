# Output path: code and headroom audit

**Finding:** the current output path does not compress any of the 12 complete benchmark takes. The modeled analog circuit is linear, and all takes remain below the final safety limiter. This rules out that limiter as the cause of their perceived lack of impact. It does not rule out missing hardware coloration or other oscillator, filter, envelope, effect, phase or performance differences.

Scope: read-only audit of production `4b9f1bfc609910154066708d2cf03e119c7d7b71`; no new hardware fit or Source change. [Numerical receipt](output-path-code-audit-2026-09-15.json) includes source hashes, the compiled probe source, reproduction commands and all 12 WAV hashes. These are the unchanged complete outputs from [Saw integration verification](saw-w4-production-integration-2026-09-15.md).

## Gain and nonlinear stages

| Stage | Current behavior | Consequence |
|---|---|---|
| Oscillator and tone balance | Each leg has unity gain at center; opposite leg fades linearly toward its endpoint | Two oscillators/layers can reinforce or cancel; no automatic sum normalization or voice-count compressor |
| Voice filter | Integrator-state soft knee at magnitude 8, asymptote 9 | A possible nonlinear source at high resonance; separate from output/preamp behavior |
| AMP overdrive | Only when enabled: oversampled ADAA tanh, drive up to +32 dB, compensation `preGain^-0.4` | Explicit per-voice saturation and level compensation; when disabled the path is a pure transport delay |
| AMP envelope and level | Envelope multiplies voice; level is `(raw/127)^2`, with velocity sensitivity, tremolo and equal-power tone pan | Static level is a gain, while envelope/LFO/velocity deliberately change dynamics; center pan is −3.0103 dB per channel |
| Voice headroom | Constant 0.22 (−13.1515 dB), before dry/send accumulation | Reduces absolute level, not crest factor or dynamics by itself |
| Patch/expression/tone controls | Patch level and expression are linear; same per-voice signal feeds dry and sends | No extra DUAL-only attenuation or compression appears in this accumulation |
| Effects | Dry plus delay plus reverb; reverb injection 0.35 and current return 0.4 | Wet level/phase can alter perceived impact; there is no post-sum automatic gain compensation |
| Master | Linear `master/127 * partLevel`; output pan normalized to unity at center | Ten-millisecond control slew acts on changes, not every note. Reset primes master and patch gain, so it does not apply a fresh master fade to each note |
| AnalogOutput | Linear 0.329 Hz coupling and active reconstruction response, implemented at 8× with 74-sample transport | Frequency/phase shaping, no amplitude-dependent gain, noise, DAC quantization or saturation |
| Final safety limiter | Exact identity through magnitude 0.9; smooth static saturation toward 1.05 above it | No detector, attack/release or AGC. It compresses large instantaneous samples only |
| Plug-in output | Stereo is handed directly to the host. Mono output is `0.5*(L+R)` | No hidden stereo gain, clipper or compressor; mono can lose out-of-phase content |

Source locations: [AnalogOutput](../../../Source/DSP/AnalogOutput.h), [engine mappings](../../../Source/DSP/SeptumEngine.h), [engine accumulation/output](../../../Source/DSP/SeptumEngine.cpp), [plug-in processor](../../../Source/PluginProcessor.cpp).

## What “gain 2.5 normalized out” means

The reconstruction circuit's closed-loop gain 2.5 remains in the pole/feedback calculation. The final small-signal voltage gain is divided out; this is not a unity-gain replacement for the circuit topology. Restoring the factor is **+7.9588 dB**. In a linear path it changes only level. If it pushes the existing safety limiter, any resulting distortion belongs to that current limiter model; it is not evidence of the hardware preamp transfer.

The implementation places master gain before `AnalogOutput`; the modeled hardware volume control belongs downstream of the DAC/reconstruction path. Constant gain commutes with the present linear circuit. That simplification must be revisited before adding level-dependent preamp behavior: physical DAC scaling, the saturation stage and the master-pot position must be distinguished. Public recordings and fitted calibration gains do not establish volts per digital full scale or the recording's master-pot setting.

## Measurements

The actual compiled circuit, driven by a three-tone signal with a level transition, scales linearly at gains 0.01, 0.1, 2.5 and 10. The worst relative RMS scaling error is **2.14e−14**. This is a numerical implementation check, not a measured hardware distortion limit.

Its continuous reference response is −0.00118 dB at 20 Hz, −0.00977 dB at 1 kHz, −0.238 dB at 5 kHz, −0.887 dB at 10 kHz and −2.841 dB at 20 kHz. Thus this model cannot be removing substantial bass/midrange level. Linear phase shaping can still change waveform crest factor; that differs from amplitude-dependent compression.

All 12 full float32 WAVs were hash-verified and remeasured. Their largest absolute sample is **0.735546** (Moogie 1), below the limiter knee 0.9. Since the implemented limiter is monotone and any input at or above 0.9 produces output at or above 0.9, these complete sampled outputs establish that it was inactive throughout. Float rounding is immaterial to this margin. This statement does not cover other patches, controller states or higher polyphony.

| Take | Peak |
|---|---:|
| Dry LP12 / LP24 | 0.213373 / 0.231865 |
| Air Lead 1 / Brassy Ld 1 | 0.256107 / 0.269957 |
| Club Bass / Cotton Wool | 0.231546 / 0.190178 |
| Dist Bs 1 / Moogie 1 | 0.570786 / 0.735546 |
| Pedal Bs 1 / So Juno 1 | 0.215299 / 0.239537 |
| Supa Juce 1 / Vangelead | 0.509688 / 0.334932 |

## Existing test coverage and next useful distinction

`AnalogOutputTests` independently solves the circuit nodes, checks gain/phase over four sample rates, unity gain and 74-sample transport of the numerical resampler, reset and finite defensive rates. `AmpEnvelopeLatencyTests` checks short attacks/releases against an independently transported envelope. `ControlSmoothingTests` checks gain automation, and the main engine tests cover clean zero-resonance filtering and bounded high-resonance behavior. These are implementation checks; they do not authenticate omitted line/phones stages or op-amp distortion.

A useful output experiment should separate a fixed linear frequency/phase correction from level-dependent coloration and from simple loudness. It should retain the current matched-preset gains or explicitly report a gain-only sensitivity. No output-stage production change follows from this audit alone. Absolute gain, omitted loaded master/line circuitry, nonlinear transfer and capture chain remain source/calibration questions.

## Reproduction

At the recorded source revision, recover `probe_source` from the JSON receipt into `build-fidelity/output-path-audit/run-01/probe.cpp`, then run the recorded compile/run command from the repository root. It includes the actual production `outputLimit` implementation and `AnalogOutput`, rather than a copied limiter formula. The WAV peak rows can be reproduced directly from each pinned float32 stereo WAV; compare the largest absolute sample with 0.9. No render or parameter fit is needed.
