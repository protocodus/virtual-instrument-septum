# SupaJuce 1: filter-envelope depth and remaining motion

The smallest supported change is the filter-envelope depth coefficient from 10 to 12, keeping the existing cutoff map, key tracking and envelope timing. At the published depth of 31, this changes peak modulation from 4.921 to 5.905 octaves. This is an empirical calibration at one positive depth, **not a measured full-scale endpoint or a recovered Roland transfer table**.

The first-note-only fitted coefficient is **12.04195** with the current resonance model and envelope timing. The rounded coefficient 12 substantially improves actual original-preset renders on every early note, while 14 overshoots. The long held note still exposes a faster hardware decline and later harmonic notches. Those residuals are retained below; they do not justify changing sustain or release from this recording.

## Source and input provenance

Roland's [official LEAD patch page](https://www.rolandus.com/go/sh-201_patches/patch_lead.html) associates the [SupaJuce 1 recording](https://www.rolandus.com/go/sh-201_patches/mp3/LEAD/TOP8_SupaJuce1.mp3) with the [downloadable LEAD bank](https://www.rolandus.com/go/sh-201_patches/shl/SH-201_Patch_LEAD.zip). The librarian record is LEAD #6, `SupaJuce 1`; the web heading spells it `SupaJuice 1`. Association by name does not authenticate the exact recorded patch revision. Original performance MIDI and recording/system settings are unavailable.

The [Owner's Manual](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf), filter/key-follow/envelope descriptions on pp. 35–38 and detailed parameters on pp. 60–61, describes the controls qualitatively. The [MIDI implementation](https://static.roland.com/assets/media/pdf/SH-201_MI.pdf) and public [Editor 1.10](https://static.roland.com/assets/media/dmg/SH201_Editor110_osx.dmg) establish raw fields and ranges. They do not supply a cutoff-Hz table, a depth-to-octave table or envelope timing constants. No ROM or measured electrical transfer function is asserted here.

Audited local source copies and SHA-256:

| Local source | SHA-256 |
|---|---|
| `/tmp/septum-hardware-fidelity/owners.pdf` | `b4a2968d429c7f3e907a6243723d5e803ae2e0014e8e9107c85bd966deea8e79` |
| `/tmp/septum-hw-benchmark/research-official/SH-201_MI.pdf` | `71a8fe00a8d232c494a5aba6885756d99e6650fc14671115260d9446c3009546` |
| `/tmp/septum-hw-benchmark/research-official/editor-resources/BufferModel.xml.utf8.txt` (normalized XML reading copy, filter fields around lines 650–735) | `758f8e3ee019eb99678bda29af1d80e2c09353493dc65c659d5ff25f89de085d` |

The [numeric audit](supajuce-brightness.json) records the exact audio, SysEx, reconstructed MIDI, analysis-script and renderer-profile hashes. All three candidate renders use identical SysEx and MIDI; the script verifies their bytes. The original MP3 SHA-256 is `e9c1dbe5cddf241f69b0d7b044201bb18e212345dc080c35a09001cb9afe103f`.

The comparison manifests' source hashes describe the contemporaneous shipping checkout. Each `brightness-investigation/renderers/depth-N/profile.json` records `source_sha256` for its actual modified renderer; use that profile when attributing a candidate's source. None of these candidate files alters a hardware preset.

## Method and control equation

SupaJuce uses an upper square oscillator at twice the lower square's frequency. Harmonics H2, H6, H10, H14, H18, H22, H26 and H30, counted from the lower fundamental, belong only to the upper square in the linear oscillator model. Ratios to H2 remove scalar recording gain and oscillator balance without fitting either. They do not remove capture EQ or wet-effect interference.

All measurements use full-rate 44.1 kHz audio and simultaneous least-squares sine/cosine harmonics, plus a constant and trend. Frequencies are estimated separately from each note's audio. Main windows are 30 ms wide, centered at 40, 55, 70, 85 and 100 ms after reconstructed onset; windows extending beyond a gate are excluded. Renderer measurements account for its declared 93-sample output latency. No EQ, time warp or arbitrary per-harmonic gain is applied.

The inverse filter calculation fixes the current resonance-40 damping at `k1=k2=0.5591507918`. The production second-stage floor of 0.5 is inactive here. It uses the exact TPT frequency warp and ideal-square `1/n` amplitudes, fitting only a cutoff for each diagnostic window. The prior [resonance audit](supajuce-resonance-audit.md) explains why the filter topology, sample-rate warping and source law remain conditional hardware assumptions.

The predictive control-law calculation retains:

```text
base_octave = log2(20) + cutoff*10/127 + (keyfollow/100)*(played_note-60)/12
cutoff_Hz = 2 ** (base_octave + envelope * depth/63 * coefficient)
```

Here cutoff=27, keyfollow=50, depth=31 and velocity sensitivity=0. Filter A/D/S/R are 3/61/74/63. The current linear envelope attacks in 1.223 ms, then declines from 1 to `74/127` in **0.905030 s**. Its decay is linear in envelope level and therefore linear in log-cutoff, until sustain or note-off. The analytic equation is the continuous counterpart of production's sample/control-tick updates, not a substituted audio renderer.

Only first-note windows fit the depth coefficient. The other five notes then use that same coefficient, cutoff equation, timing, sustain and key tracking with **no fitted cutoff or note-specific offset**. Separately reported per-frame cutoff inversions diagnose residuals; they are not the held-out predictions. These are cross-note checks within an already examined recording, not untouched laboratory validation or independent hardware sessions.

## Early peak: coefficient 12 is supported

At 70 ms on the first note, conditional hardware cutoff is **7382 Hz**. The existing equation predicts **3767 Hz**; coefficient 12 predicts **7292 Hz**. This isolates a modulation-depth deficit, rather than requiring a global cutoff shift. A global shift would also alter patches whose filter-envelope depth is zero.

Coefficient-only fitting on the first note returns 12.04195. Keeping the audio unchanged and varying note age by ±15 ms gives 11.957–12.129. Window widths of 20/40 ms and independent left/right measurements give 12.037–12.044. These are sensitivity ranges, not statistical confidence intervals; overlapping windows are correlated.

Actual-render RMS error in H6–H30/H2, over the early windows, in dB:

| Note / sounding lower pitch | Coefficient 10 | Coefficient 12 | Coefficient 14 |
|---|---:|---:|---:|
| 1 / E4, calibration note | 23.90 | **1.91** | 7.02 |
| 2 / A3 | 22.33 | **5.09** | 9.51 |
| 3 / A3 | 21.74 | **4.68** | 9.22 |
| 4 / A3 | 22.08 | **4.00** | 8.96 |
| 5 / D4 | 23.34 | **2.34** | 7.14 |
| 6 / G3 | 18.73 | **1.92** | 6.37 |

These scores cover a particular isolated oscillator family. They are neither whole-preset error nor a percentage of hardware accuracy. The direct renders contain the actual oscillator, filters and enabled effects; their residuals are larger than the idealized predictive filter fits.

Key follow requires no correction from these notes. At 70 ms, the three A3 cutoffs divided by the first E4 cutoff are 0.8140, 0.8242 and 0.8115, versus 0.8170 predicted by keyfollow=50. The D4 ratio is 0.9445 versus 0.9439, and G3 is 0.7844 versus 0.7711. Conditional apparent key-follow values are about 47–52, consistent with the existing value 50 within these spectral/performance uncertainties.

## Decay, sustain and release remain unresolved

The early first-note inferred log-cutoff slope is **−4.200 octaves/s**; the held D note's early slope is **−4.759 octaves/s**. Production predicts −2.269 before this change and **−2.723 octaves/s** with coefficient 12. Thus the early peak correction does not fully reproduce the motion.

On the held D note at 150 ms, inferred cutoff is 5465 Hz versus the coefficient-12 prediction of 5918 Hz. At 200 ms they are 4592 and 5385 Hz. Fitting both coefficient and duration to the first note gives 12.2493 and 0.6006 s, but the two-parameter improvement is modest and inconsistent across the held-out early notes. It also depends on reconstructed onset, the unmeasured sustain response, ideal source law and filter topology. This audit recommends retaining the current decay map in this correction.

Late-note direct-render checks show both the improvement and its limit:

| Time into held D note | Coefficient 10 RMS | Coefficient 12 RMS |
|---|---:|---:|
| 125 ms | 22.15 | 3.50 |
| 150 ms | 21.99 | 4.55 |
| 175 ms | 22.04 | 5.44 |
| 200 ms | 18.21 | 8.58 |
| 225 ms | 15.94 | 12.64 |
| 250 ms | 11.48 | **20.73** |
| 350 ms | 13.20 | **18.56** |
| 450 ms | 17.12 | 15.75 |
| 500 ms | 8.64 | **17.08** |

After roughly 225 ms, hardware develops isolated deep harmonic notches that a smooth resonant LPF cannot reproduce. At 250 ms, even a freely fitted cutoff has 6.76 dB RMS residual. Enabled delay/reverb can mix older bright harmonics with the decayed dry note and produce cancellation; the exact recording path is unknown. Weak late harmonics also approach the recording/noise floor. The worse late scores are not discarded or absorbed into an EQ fit.

The longest reconstructed gate is 0.519 s, shorter than the current 0.906 s attack-plus-decay time to sustain. No observed note reaches a clean sustain plateau. Amp release is zero, whose present mapping drops the dry signal by 60 dB in about 2 ms, preventing useful identification of the much longer filter release independently of wet tails. There is no supported sustain or release correction here.

## Limits of the depth interpretation

Because the cutoff map is exponential, adding raw cutoff units and adding octaves are mathematically equivalent after scaling. Current coefficient 10 is equivalent to adding `depth*(127/63)` raw cutoff units at envelope peak; coefficient 12 adds `depth*(12/10)*(127/63)`. Adding the signed depth value directly as raw cutoff units would almost halve modulation and worsen this discrepancy. This recording cannot reveal which arithmetic domain Roland uses internally.

Only one positive depth value, 31, is identified here. A nonlinear depth curve, a constant base-cutoff offset and a shifted key-follow pivot can mimic the same local peak. A changed key-follow pivot would act as a constant offset within this patch, whereas the current cross-note tracking already fits. The proposed coefficient change retains the current zero point, sign and linear interpolation; the full positive/negative taper remains unmeasured. It should remain labeled as empirical tuning and be assessed against other presets.

## Reproduction and figures

```sh
OPENBLAS_NUM_THREADS=1 python3 Tools/analyze_supajuce_brightness.py \
  --candidates build-fidelity/hardware-benchmark/brightness-investigation/candidate-renders \
  --output Docs/fidelity/source-audits/supajuce-brightness.json \
  --harmonic-figure Docs/fidelity/figures/supajuce-brightness.png
```

[Cutoff/evaluation overview](supajuce-brightness.png) and [measured harmonic comparison](../figures/supajuce-brightness.png). The JSON's `harmonic_figure_panels` contains every plotted numeric point. The latter figure includes the late-note failure as well as the improved first note. No shipping DSP is changed by the analysis tool.
