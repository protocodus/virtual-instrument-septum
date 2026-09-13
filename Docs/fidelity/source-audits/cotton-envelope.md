# Cotton Wool: temporal output and gate-only diagnostics

2026-09-13. **The current Cotton filter and envelope values match the published preset, but the output's temporal behavior still differs.** Moving reconstructed note-offs affects the release timing and cannot explain the brightness difference before release. The wet hardware tail does not identify a dry amplifier release time. This investigation leaves production DSP, the published SysEx and the current reconstruction unchanged.

The [preset verification](cotton-preset-verification.md) compares every stored block and the native decoder output. Roland associates the named [Cotton Wool recording](https://www.rolandus.com/go/sh-201_patches/mp3/PAD/TOP8_Cotton_Wool.mp3) and downloadable patch on its [PAD page](https://www.rolandus.com/go/sh-201_patches/patch_pad.html). Original performance MIDI, controller state and capture processing are unavailable. Identical published patch values are established; identical conditions during the recording are not.

## Current modeled envelope behavior

The [Owner's Manual, pp. 37–39](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf), distinguishes the filter and amplifier envelopes and their behavior after key release. It does not give the following numerical conversion tables; these are current engine choices, with the filter-decay anchor calibrated conditionally in the earlier investigation.

| Published setting | Current model |
|---|---:|
| Filter attack 10 | 1.9555 ms |
| Filter decay 58 | 757.865 ms linear segment to sustain |
| Filter sustain 87 | Envelope level 87/127 ≈0.6850 |
| Filter release 105 | 2.6589 s to −60 dB of envelope amount |
| Amplifier attack 0 | 1 ms |
| Amplifier decay 0 / sustain 127 | Sustain is unity, so no peak-to-sustain decrease |
| Amplifier release 39 | 28.923 ms to −60 dB; exponential time constant 4.187 ms |

The long filter release cannot sustain audible output after the amplifier closes. None of these mapped times should be presented as a measured Roland value. The [instrumented model audit](cotton-envelope-model.md) separately records the actual cutoff trajectory and Super Saw phase behavior; it is more informative than equating a broad spectral ratio with filter frequency.

## Measurements and interventions

[analyze_cotton_envelope.py](../../../Tools/analyze_cotton_envelope.py) freezes the current renderer and first reproduces the retained production WAV **byte for byte**. Its source comparison is `brightness-investigation/production-after/cotton-wool`. The complete original SysEx hash is:

```text
e7f23e39445895f2158482037b37a19dfe413e536869c0e6f78352de6e49fbef
```

Three first-note interventions change only its note-off from **0.370 s to 0.400, 0.440 or 0.480 s**. A separate long-chord intervention extends notes 16, 17 and 18 by 200 ms, from 3.625/3.625/3.750 to 3.825/3.825/3.950 s. Their onsets, pitches, velocities and all other MIDI events are unchanged. Every gate diagnostic uses the original SysEx and is sample-identical to the control before the first altered note-off. These alternatives are explicitly diagnostic; none is promoted as recovered MIDI.

A further, separate **effects-off diagnostic** changes only the common Delay SW and Reverb SW bytes, offsets 0x1C/0x1D, to zero and recomputes the DT1 checksum. The original patch remains untouched. This diagnostic tests the current effect model, not the unknown hardware effect response.

The approximately 65.15 Hz sine-like component of the first note is measured with Hann-weighted sinusoidal least squares. Constant/linear trend and Super Saw harmonic sinusoids are nuisance terms. Amplitudes use mean squared left/right complex coefficients, normalized to each signal's own 0.20–0.33 s plateau; absolute recording gain is not fitted. Primary windows are 70 ms, with 50/90 ms hardware sensitivity checks. The long chord uses 120 ms windows and three sine-like components around 154.94, 173.91 and 219.11 Hz, referenced to 2.95–3.15 s. These are components of the wet output, not isolated amplifier envelopes.

Brightness uses 700–3000 Hz power relative to 200–700 Hz power, with a Hann periodogram and mean stereo channel power. The known 93-sample render latency is included. Analysis windows overlap and are not independent measurements. Window centers at or beyond 0.465 s can include the next reconstructed onset at 0.500 s; their stored rows must not be treated as isolated first-note render tails. The figure and the main gate comparison stay before this boundary.

## First-note timing and tail

The hardware sine-like component is effectively flat through about 0.37 s, within roughly 0.1 dB over the established plateau. The current reconstructed release starts at 0.370 s and rapidly exposes its lower-level wet return. Moving the note-off delays this transition but cannot independently set its shape.

| Window center | Hardware | Current off 0.370 | Diagnostic off 0.400 | Diagnostic off 0.440 | Diagnostic off 0.480 |
|---|---:|---:|---:|---:|---:|
| 0.390 s | −0.38 dB | −12.77 dB | −0.73 dB | +0.66 dB | +0.66 dB |
| 0.410 s | −1.80 dB | −14.84 dB | −6.86 dB | +0.89 dB | +0.90 dB |
| 0.430 s | −3.98 dB | −15.37 dB | −14.82 dB | −0.67 dB | +0.80 dB |
| 0.450 s | −6.21 dB | −14.94 dB | −14.94 dB | −7.67 dB | +0.59 dB |

Values are relative fitted 65 Hz component amplitudes, not total output dBFS. Later gates can improve one time point while overholding another. This bounded test supports a performance/release discrepancy, but does not choose a correct note-off or a replacement release mapping.

The recording's stereo behavior rules out reading its whole tail as a dry amplifier envelope. Before release, its right channel is about **0.6 dB** stronger and nearly in phase with the left at 65 Hz. By 0.420 s this becomes **+2.12 dB / +7.33°**, and by 0.460 s **+4.77 dB / +23.89°**. The 50/70/90 ms checks give +4.56…4.99 dB and +23.53…24.30° at 0.460 s. That divergence is consistent with a growing wet or capture contribution, not a common scalar amplitude change alone.

The normalized squared complex channel inner product across fitted windows changes from 0.99998 over 0.20–0.35 s to 0.96013 over 0.40–0.48 s. This is a descriptive consistency measure from correlated windows, not an independent statistical coherence estimate. Phase/amplitude divergence is the more directly interpretable result.

The current effects-off diagnostic reaches **−54.06 dB** relative to its sine plateau at 0.410 s, versus **−14.84 dB** with published effects enabled. Thus the current model's tail is itself predominantly wet by then. The hardware could have different wet timing, coloration or amplitude; no dry hardware stem is available. An amplifier release correction cannot be inferred uniquely from this recording.

## Brightness before any changed note-off

The early spectral trajectory differs while the first note is held. At 0.230 s, the hardware high/mid ratio is **−2.50 dB** versus **−7.41 dB** in the current render. By 0.330 s, hardware falls to **−7.55 dB**, while the render is **−7.10 dB**. Both 70 ms windows end before the original 0.370 s note-off. The hardware changes by −5.04 dB; the current render changes by +0.31 dB. Gate-only edits are exactly inactive in this interval.

The initial broader rise from 0.150 to 0.230 s is approximately 6.4 dB, but its earliest window straddles the hardware onset and is **not a clean filter-attack measurement**. Restricting the comparison to centers 0.190–0.230 s gives only a 1.39 dB rise. The source onset and Super Saw interference need to be separated before interpreting that rise as an envelope attack law. The current effects-off trajectory is nearly unchanged over these early windows, showing that its modeled wet path does not produce the observed shape.

The current filter cutoff decreases during this interval, but detuned Super Saw harmonics can strengthen as phases interfere. The [model/phase audit](cotton-envelope-model.md) demonstrates that confound. These measurements establish a temporal output difference; they do not isolate a wrong attack, decay, sustain or oscillator spectrum on their own.

The exact preset adds another concrete alternative: reverb pre-delay raw 125 maps to **100 ms**, with time 104, size 7 and send 35. Adding 100 ms to the reconstructed 0.125 s onset gives 0.225 s, close to the broad hardware brightness peak. This numerical proximity is not causal identification: the hardware onset is uncertain and appears later than the reconstruction, and its wet component has not been separated. In the actual current render, original effects versus FX off first differ at source-aligned **0.25508 s**, or **130.08 ms after the reconstructed onset**; a 10⁻⁵ full-scale sample-difference threshold gives 0.25605 s. The modeled effect network therefore adds about 30 ms of onset delay beyond its explicit pre-delay. Wet arrival timing is a plausible competing mechanism to investigate before recasting the measured rise as filter attack.

## Later held chord

The roughly 219 Hz sine-like component is nearly flat from 2.8 through 3.6 s in both signals. At 3.700 s hardware is −5.14 dB relative to its plateau and current production is −12.23 dB; by 3.800 s hardware is −17.46 dB while production is −11.66 dB. Extending all three chord gates by 200 ms gives −0.18 and −1.51 dB at those times, overholding this component. Hence one blanket gate extension is not supported by both passages.

The current reconstruction includes other note onsets at 3.375, 3.625 and 3.750 s, with wet tails and potentially different original voicings. The later rebound of a fitted component is not a literal amplifier rise. This long-chord check constrains performance interpretations but cannot calibrate release independently.

![Cotton temporal measurements, gate-only interventions and stereo-tail check](cotton-envelope.png)

## Retained evidence

The [JSON](cotton-envelope.json) contains all component amplitudes/phases, band-ratio time courses, window sensitivity, exact gate/preset interventions and hashes. All six renders finish with the same expected latency; the unmodified control reproduces production exactly. Script compilation, hash consistency and figure inspection were completed. The broader [Cotton investigation](../cotton-wool-investigation.md) combines this with the complete preset/decoder audit.

```sh
OPENBLAS_NUM_THREADS=1 python3 Tools/analyze_cotton_envelope.py \
  --comparison build-fidelity/hardware-benchmark/brightness-investigation/production-after/cotton-wool \
  --renderer build-fidelity/SeptumRenderMidi \
  --output /tmp/cotton-envelope-new
```

Session diagnostic audio and MIDI are retained under `build-fidelity/hardware-benchmark/brightness-investigation/cotton-envelope-audit-v3/`. Earlier scratch results remain separately preserved. No baseline artifact was overwritten and no alternative MIDI was substituted into the listening comparison.
