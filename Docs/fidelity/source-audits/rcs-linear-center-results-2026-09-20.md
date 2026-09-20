# Linear-center overdrive diagnostics — 2026-09-20

**Neither fixed shaper supports a global calibration change.** The A02 training screen fails combined trajectory and harmonic checks. Prospective tests then find systematic dry-harmonic regression on A01 and missing A03/A05 closure. No shipping candidate was selected and production DSP is unchanged.

## Scope and fixed comparisons

The 16-cell A02 screen crosses hard clipping at ±1 or tanh shoulders outside a linear ±0.5 center, original/zero-mean Pulse, current/100 ms filter attack, and original depth −22/temporary depth −32. Existing tanh and linearized ADAA supply 16 matched control records. All other patch bytes, reconstructed MIDI, timing and measurement windows stay fixed.

Both **uncentered shapers with current attack** were separately frozen for prospective testing before A02 results were read. They were not selected because A02 passed. The 34 comparisons cover two models ×17 original-preset cases, including the already used A02. Different-patch baselines were previously characterized; this is prospective validation of fixed models, not untouched recordings. Public recordings identify presets, but exact performance MIDI, phase, live edits and capture gain remain unavailable. The RCS video and SoundCloud are two encodes of one performance.

## A02 measurements

| Fixed late fourth-note ratio | Hardware range | All 16 cells / eight windows |
|---|---:|---:|
| H3/H2 | −15.894…−15.189 dB | −10.527…+1.667 dB |
| H4/H2 | −24.687…−23.840 dB | −16.153…−2.428 dB |

Neither range overlaps. These channel/window/encode observations are sensitivity checks, not independent trials. H2-reference interpretation assumes a clean Lower sine and linear output summation.

All candidate fourth-note sustained 10/20/30 dB closures are censored, versus hardware 27/27 settings at each threshold. At 100 ms attack/depth −32, first-note high-band power drops only 10.46–12.72 dB versus hardware 30.71 dB; observed 10 dB crossings are 18.80–27.78 ms late. All crossings remain censored under the separate shorter common guard; its hardware 30 dB landmark is also censored, so guards must not be mixed.

The new late signals do **not** converge to the matched linearized controls: H2 amplitudes remain 10.93–15.02 dB lower. At depth −32, H3/H2 differs by +15.34…+19.01 dB and H4/H2 by +6.81…+20.53 dB. Raw band/harmonic powers, RMS, fit residuals and every matched window remain pinned in the JSON.

## Why a linear center still receives a large signal

Independent source review confirms both oscillator legs have gain 1 at BALANCE 0 and are [summed without division by two](../../../Source/DSP/SeptumEngine.cpp#L2397). Each stationary LP stage has unity DC response below its state limiter. [Drive 33 gives pregain 2.604642](../../../Source/DSP/SeptumEngine.h#L229), so the shaper's unit and half-unit boundaries correspond to filtered-input magnitudes 0.383930 and 0.191965.

At temporary depth −32, the current model's terminal cutoff is 204.4365 Hz. A stationary estimate for the 103.8262 Hz Upper square fundamental is 1.05407 after the LP24 filter, 2.74548 after pregain, or approximately 2.78519 including interpolator baseband gain. The octave-higher Pulse cannot cancel that stationary fundamental; subtracting its mean removes DC, not the square fundamental. These are Fourier-component estimates, **not tapped sample peaks or hardware measurements**. Dynamic settling, state limiting and interpolation images are outside the estimate.

The [AMP envelope follows overdrive](../../../Source/DSP/SeptumEngine.cpp#L2533), as do level/velocity/pan and [voice headroom 0.22](../../../Source/DSP/SeptumEngine.cpp#L3780). Quiet output therefore does not establish a small shaper input. This identifies an operating-level issue to investigate in the software; it does not establish Roland's gain law or a replacement threshold.

## Prospective component checks

| Dry harmonic error, median dB | Baseline | Hard clip | Tanh shoulders |
|---|---:|---:|---:|
| A01: H2–H8/H1 | 2.503 | 3.814 | 3.366 |
| A01: odd H3/H5/H7/H1 | 2.466 | 4.726 | 3.922 |
| Dist Bs 1: H2–H8/H1 | 7.888 | 7.874 | 7.877 |

Both A01 total and odd-harmonic errors worsen in all 27 note/channel/onset settings. Dist's small total improvement accompanies a small even-harmonic regression; neither supplies a general success. A03 and A05 have zero candidate 10/20/30 dB closures in all 27 settings. Hardware counts are 27/27/27 for A03 and 27/27/26 for A05. A05 loses the baseline's three observed 10 dB crossings. Both references include delay, and A05's late high band reaches the recording floor.

Broad spectral error improves for A02, A05 and Dist but worsens for A01, A03, Club Bass and Sexy Back. That secondary score does not override the dry-harmonic and trajectory failures. All ten overdrive-off cases remain byte-identical for each shaper: 20 identity controls passed.

## Reproduction and limits

The [machine-readable audit](rcs-linear-center-results-2026-09-20.json) retains exact protocols, frozen binaries/source hashes, all 16 training rows and 34 prospective comparisons, analytic calculations, raw-level artifacts and reproduction commands. All retained hardware metrics reproduce exactly, including 66 A02 harmonic fits. No new windows, fitted gain, phase, alignment or aggregate winner were introduced. One runner status-string compatibility fix occurred before candidate measurement; the superseded runner and correction remain pinned. Candidate transfer arithmetic passed independent pre-build numerical checks. A later unintended `--help` invocation reran the validation analyzer: every compact numerical result was verified unchanged and hashes were reconciled transparently. The original raw report was not retained, so old/new raw-fit byte identity is not claimed.

The source-labelled reference provenance remains conditional, and 27 overlapping settings are not 27 independent performances. All conclusions concern these declared models and patches; they neither identify the hardware shaper nor exclude other gain structures.
