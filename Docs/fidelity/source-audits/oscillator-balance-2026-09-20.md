# Oscillator BALANCE experiment — 2026-09-20

**Keep experimental; do not change the global oscillator mix law.** A stronger OSC1 improves SupaJuce's separated square families, but Class A's independent saw-family check does not confirm the proposed law. All published patch bytes and reconstructed MIDI stayed fixed. No production DSP source changed.

The [Roland Owner's Manual](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf), pp. 33 and 60, establishes the direction, solo endpoints and −63…+63 control range. It gives no numeric interior gain law or absolute center gain. The candidate is a normalized linear crossfade: stronger oscillator gain 1, weaker `(63−|balance|)/(63+|balance|)`, compared with the incumbent weaker `(63−|balance|)/63`. Center and endpoints are preserved **by design**, not calibrated from hardware. At −26, the upper/lower oscillator amplitude ratio changes from 63/37 = **1.702703** to 89/37 = **2.405405**, a 3.001 dB increase in dominance.

Only the two oscillator gain calls in a staged copy of `SeptumEngine.cpp` change. The shared tone/part BALANCE mapping stays intact. [The builder](../../../Tools/build_oscillator_balance_candidate.py) freezes the exact edit, original source hashes and compiler inputs; the baseline and candidate share the same original 18-file DSP/renderer snapshot. [The JSON audit](oscillator-balance-2026-09-20.json) retains those hashes, per-case audio/input identities, source associations and full-precision results.

## Source-family check

Roland's [SupaJuce recording](https://www.rolandus.com/go/sh-201_patches/mp3/LEAD/TOP8_SupaJuce1.mp3) and [Class A recording](https://www.rolandus.com/go/sh-201_patches/mp3/LEAD/TOP8_ClassA.mp3) correspond by name to its [published LEAD bank](https://www.rolandus.com/go/sh-201_patches/patch_lead.html). Both original Upper tones use BALANCE −26 and an octave oscillator interval. SupaJuce uses two squares; Class A uses two saws. Original performance MIDI and the precise recorded patch revision remain unverified.

SupaJuce's lower square contributes odd harmonics of the lower fundamental; its upper square contributes harmonics 2, 6, 10…. Fit the existing filter model using only the upper family, then infer oscillator ratio from lower harmonics 3, 5 and 7. The first note's 27 channel/window observations imply a conditional ratio **2.565054–3.148270**, median **2.769412**. This is not a direct gain measurement: applying the same estimator to full-engine renders yields median 1.551189 for the known incumbent ratio 1.702703, and 2.179437 for candidate 2.405405. Wet effects and model error bias the estimator. Later hardware note medians range 2.094–2.788.

The validation metric compares neighboring upper/lower harmonic amplitude ratios directly against hardware, without fitting either rendering. Windows are 25, 35 and 45 ms, evaluated in left, right and mid channels; overlapping observations are sensitivity checks, not independent recordings. SupaJuce's first-note windows motivate the hypothesis; five later notes and the separately transcribed Class A phrase are held out. Class A's first two notes are excluded because its weak lower family and short windows provide insufficient cycles. The remaining intervals predate this experiment. Frequency optimization within ±1.5% only follows each signal's measured pitch; MIDI is never fitted to candidate output.

| Targeted family RMSE, median | Incumbent | Candidate | Improved observations |
|---|---:|---:|---:|
| SupaJuce first note | 5.460484 dB | 2.891005 dB | 27/27 |
| SupaJuce later notes | 6.635365 dB | 5.657360 dB | 113/129 |
| Class A held-out phrase | 5.908500 dB | 6.080305 dB | 45/72 |

Class A's median worsens despite a majority of individual observations improving. Its overlapping saw harmonics also depend on unknown relative phase. It does not establish that the candidate is wrong, but it prevents claiming an identified global law.

## Unchanged-input cross-preset check

All 13 frozen comparisons use 44.1 kHz, master 100, two seconds of tail, preserved patch tempo and strict MIDI replay. The score below is normalized power error in 32 logarithmic bands from 25–12,500 Hz, excluding reference bands more than 50 dB below the strongest band. Lower is better; this is not an overall fidelity score.

| Original patch | Incumbent | Candidate |
|---|---:|---:|
| Moogie 1 | 4.738066 | 4.738066 |
| SoJuno 1 | 6.712208 | 6.755347 |
| Dist Bs 1 | 5.708621 | 5.708621 |
| Pedal Bs 1 | 7.813277 | 7.813277 |
| Club Bass | 7.734216 | 7.755616 |
| Cotton Wool | 6.347978 | 6.347978 |
| Air Lead 1 | 13.403697 | 13.403697 |
| Vangelead | 3.695659 | 3.692591 |
| SupaJuce 1 | 5.437396 | 4.617085 |
| Brassy Ld 1 | 6.510110 | 6.510110 |
| Class A | 2.069395 | 1.903277 |
| Sexy Back | 5.679952 | 5.030033 |
| Trancefloor | 2.891835 | 3.012537 |

Moogie, Dist, Pedal, Cotton, Air Lead and Brassy are six **centered active-oscillator mix** controls with byte-identical WAVs; no endpoint-only fixture is claimed. SupaJuce and Sexy Back improve broadly, while Trancefloor worsens and Class A's more targeted metric disagrees with its broad improvement. These mixed results do not support shipping the candidate.

## Reproduction and limits

Run `Tools/build_oscillator_balance_candidate.py --output <new-build-directory>`, then `Tools/analyze_oscillator_balance.py --candidate <new-build-directory>/renderer/SeptumRenderMidi --output <new-analysis-directory>`. The analyzer uses the frozen public-match comparison inputs by default; `--baseline-root` can identify another complete matching set. The retained verified result is `build-fidelity/public-match-2026-09-20/balance-linear-comparison-verified/analysis.json`.

The analyzer checks sample rates, finite nonzero stereo audio, matching original-source snapshots, renderer/frozen-input provenance, MIDI/SysEx hashes and output hashes after rendering. The verification rerun reproduces all 13 WAV hashes. Nine synthetic harmonic recovery cases across three frequencies and three widths have maximum absolute amplitude error 5.44×10⁻¹⁵. Pivoted QR avoids a reproducible NumPy SVD failure on one finite window; no observations are discarded or notes retuned to conceal that failure. Both new Python files compile.

Unknown gates, velocities, controllers, oscillator phase history, effects state and MP3/capture processing remain material confounds. Promotion needs independent interior BALANCE settings with family-level improvement across notes and uncertainty windows, plus no material cross-preset regressions. An isolated two-oscillator capture with bypassed filter/effects and fixed MIDI would distinguish gain law from phase and effect coloration. The current result is a useful SupaJuce hypothesis, not a recovered Roland parameter curve.
