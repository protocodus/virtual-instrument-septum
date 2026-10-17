# Output-stage reference characterization

**The recordings do not support a single missing gain or extra compressor as the explanation for “less lively.”** Moogie and Dist already have lower peak-to-average dynamics than hardware by 4.19 and 3.81 dB; Cotton is lower by 1.58 dB. Vangelead's crest factor is almost identical. Air and Brassy go the opposite way. These are whole-instrument observations, not evidence locating compression inside an output stage.

This audit uses the final production W4 WAVs verified byte-identical to the frozen candidate in the [twelve-case integration receipt](saw-w4-production-integration-2026-09-15.md). It changes no source, patch, MIDI, waveform, gain policy or alignment, and fits no compressor, saturation curve or EQ. Moogie, Dist, Cotton and Vangelead receive priority because of the user's listening notes; all other cases remain reported.

## Frozen measurement policy

- Primary measurements use the existing factory production-prefix scalar/lag/evaluated interval, and the existing dry note36 scalar/−1406-sample lag. The dry primary intervals exclude note36 calibration and the entire fitted note91 interval. Every STFT/RMS/loudness frame remains inside one evaluated segment.
- Stereo channels remain separate. The dry mono reference and mean production channel use the same convention as the previous dry audit. Full native WAV and original excerpt hashes are verified; original-only spectral masks reproduce all inherited counts, including exact factory packed-mask hashes.
- The separate **loudness-matched sensitivity** uses one scalar per case from K-weighted 400 ms blocks with 100 ms hops. Both signals use the blocks selected by the original recording's −70 absolute/−10 relative gates. This is a post-hoc descriptive sensitivity, not a newly fitted production gain or independently gated broadcast-compliance measurement. The filter processes the complete streams before frames are selected; earlier filter state is preserved.
- Dynamics use sample peaks, RMS, crest factor, absolute-sample quantiles, fourth moment and 10/50 ms RMS envelopes. Original-only −60 dB envelope activity masks and −80 dB floors keep denominators fixed. Source-only smoothed rise landmarks are descriptive transients, not recovered MIDI onsets. All accepted and rejected landmarks remain in the receipt.

The K-weighting uses the De Man parametrization documented in [pyloudnorm's filter implementation](https://github.com/csteinmetz1/pyloudnorm/blob/master/pyloudnorm/iirfilter.py) and its [meter implementation](https://github.com/csteinmetz1/pyloudnorm/blob/master/pyloudnorm/meter.py). Independent FFmpeg controls at 125, 1000 and 8000 Hz agree within 0.048 LU, below its displayed 0.1-LU resolution. A doubled-amplitude control gives exactly +6.0206 dB and a matching scalar of 0.5. The 48-kHz coefficient-table check differs by 1.05e−12 from rounded tabulated values.

## Level and dynamics: all twelve

Positive level deltas mean **production exceeds original** under the primary saved gain. Crest is sample peak divided by RMS and is unchanged by constant loudness matching. The 50 ms range is P95−P10 over original-active frames; it is not standardized loudness range. K blocks show selected/available 400 ms windows, which overlap and are not independent observations.

| Recording | RMS delta dB | K-level delta dB | Crest dB, original → production | 50 ms envelope range dB, original → production | K blocks |
|---|---:|---:|---:|---:|---:|
| Dry LP12 | -0.26 | -0.31 | 15.14 → 14.39 | 11.00 → 11.79 | 278/279 |
| Dry LP24 | -0.34 | -0.39 | 15.65 → 15.14 | 10.85 → 11.96 | 278/279 |
| air-lead-1 | -0.51 | -0.07 | 12.34 → 13.51 | 5.53 → 5.13 | 22/22 |
| brassy-ld-1 | -0.71 | -0.45 | 10.34 → 12.56 | 23.40 → 23.27 | 19/19 |
| club-bass | -0.08 | -1.53 | 14.37 → 9.14 | 44.22 → 44.47 | 12/21 |
| cotton-wool | -0.08 | -0.20 | 15.61 → 14.02 | 18.65 → 16.76 | 34/34 |
| dist-bs-1 | -0.23 | -1.02 | 11.08 → 7.27 | 29.06 → 17.02 | 6/6 |
| moogie-1 | +0.22 | +0.01 | 8.97 → 4.78 | 1.16 → 0.69 | 24/24 |
| pedal-bs-1 | -4.93 | -4.67 | 9.63 → 9.10 | 11.15 → 20.63 | 8/8 |
| so-juno-1 | -1.40 | -1.96 | 9.45 → 8.12 | 36.19 → 38.20 | 8/8 |
| supa-juce-1 | -0.52 | -0.97 | 12.12 → 12.20 | 17.31 → 12.32 | 10/10 |
| vangelead | +0.39 | -0.08 | 10.14 → 10.11 | 5.47 → 8.77 | 35/35 |

Moogie is already within **0.012 dB** of the original K-weighted level; Cotton and Vangelead are within 0.21 dB. Increasing gain cannot restore their missing peak contrast or correct a different envelope. Dist needs a +1.02 dB scalar in the matched sensitivity, but its crest deficit remains unchanged. Pedal's −4.67 dB K-level difference is a counterexample to assuming every saved prefix scalar predicts the later level; its reconstructed performance remains uncertain.

The measured peaks above digital full scale for scaled Air/Brassy are floating-point comparison values, not clipped native WAVs. Their loudness-matched virtual peaks are 1.017 and 1.237; no clipping, limiter, export or audio modification is applied. Every raw production render remains finite and below full scale.

## Frequency balance after loudness matching

The table reports production minus original **band power in dB**, with the same original-only bins, 8192-sample Hann windows and unchanged timing. The 2048-sample sensitivity, original power fractions, exact counts, full unmasked band powers and all signed deltas are retained in the JSON. “—” means no original-active support, not a huge measurable deficit. † identifies a band carrying less than −40 dB of the original full STFT power; this descriptive flag removes no data and supplies no acceptance threshold.

| Recording | 20–120 Hz | 120–500 Hz | 500–2000 Hz | 2–6 kHz | 6–16 kHz |
|---|---:|---:|---:|---:|---:|
| Dry LP12 | +0.30 | +0.04 | -0.10 | -0.49 | -2.38 |
| Dry LP24 | +0.34 | -0.03 | +0.03 | -0.44 | -2.25 |
| air-lead-1 | -15.61† | +1.36 | -2.16 | +12.87 | — |
| brassy-ld-1 | +8.04† | -1.35 | +1.53 | +0.39 | -9.80† |
| club-bass | +1.94 | -7.62 | +8.43 | -4.72† | — |
| cotton-wool | +2.03 | +0.25 | -2.66 | +2.57 | +2.80† |
| dist-bs-1 | +0.78 | -3.03 | -3.42 | -6.15 | — |
| moogie-1 | +0.56 | -4.32 | -3.90 | -4.72† | — |
| pedal-bs-1 | -0.33 | +9.10 | — | — | — |
| so-juno-1 | +1.04 | -3.34 | -0.92 | -1.60 | -9.12 |
| supa-juce-1 | +8.72† | +3.82 | -0.89 | -0.62 | +0.84 |
| vangelead | +0.14† | +0.59 | +0.18 | -3.15 | -14.54 |

### The four listening priorities

- **Moogie:** production has about +0.56 dB in 20–120 Hz, while 120–500 Hz is −3.91/−4.32 dB and 500–2000 Hz is −3.71/−3.90 dB across the two resolutions. This is loss of upper-bass/midrange body relative to the fundamental, not a simple lack of sub-bass power. Its 50 ms level range is small in both recordings; no original rise passes the predeclared 3 dB transient guard. The 4.19 dB crest deficit instead describes within-note waveform/peak structure, which can depend on oscillator phase and filter response.
- **Dist:** the same strong bands show +0.78 dB sub-bass, −3.03 dB upper bass and −3.42 dB mids at 8192 samples. Its envelope range is also much narrower: 29.06 → 17.02 dB. Two source-derived rises give a median attack-peak/body deficit of 4.07 dB, but pre-gate contrast remains sensitive to the reconstructed timing and its driven dual layers. More conventional peak compression would move the observed crest contrast further from hardware.
- **Cotton:** the result is nonuniform: +2.03 dB sub-bass, almost equal upper bass, −2.66 dB mids and +2.57 dB in 2–6 kHz. Its five accepted rise landmarks have median attack/body and peak/body deficits of 2.18 and 2.47 dB. Velocity-dependent filter brightness, gate/release uncertainty, Super Saw phase and reverb remain possible contributors. A blanket high-frequency boost would worsen an already excessive 2–6 kHz band.
- **Vangelead:** overall level/crest are close, yet its 50 ms envelope correlation is only 0.051 under the frozen timing; its level range is 3.30 dB wider. It also lacks roughly 3.15 dB in 2–6 kHz. This combination is not explained by a constant gain. The dual layers' different attacks and uncertain original gates remain material; a memoryless output curve cannot by itself be inferred to repair that temporal disagreement.

## Review and floor qualification

A separate code review found no consequential axis, power normalization, frozen-coverage/gain/lag or original-mask error. It identified one narrow reporting qualification: K-matched envelope errors in the JSON add the scalar in dB after applying the original-fixed amplitude floor. The [floor-support check](output-stage-envelope-floor-support-2026-09-15.json) finds 83 selected dry frames at that floor (LP12: 32/8 for 10/50 ms; LP24: 33/10), and none among the official excerpts. Treat that JSON field as a **floored-log sensitivity**, not a fresh envelope measurement with the same absolute floor after scaling. All primary envelope values, crest/RMS statistics and band measurements above are unaffected.

## What the measurements identify

A conventional extra peak compressor is **not supported as a universal cure**: the largest Moogie/Dist/Cotton crest deficits would be pushed in the wrong direction, whereas Air/Brassy already have excessive crest. An expander would have the converse conflict. These comparisons do not rule out every nonlinear circuit; they do rule out selecting a global dynamics setting merely because the originals sound more powerful.

A single simple tone tilt is also unsupported. Moogie/Dist lack upper-bass and midrange body; Cotton already has excessive bass and upper treble, while Air's 2–6 kHz excess is large. The original-MIDI dry recordings are much closer through the strong low/mid bands after level matching, with only about −0.44/−0.49 dB at 2–6 kHz and −2.25/−2.38 dB in the weaker 6–16 kHz band. A fixed narrow correction could affect different spectra differently, so these broad-band ratios do not prove that every common EQ is impossible. They do not identify one defensible EQ curve to install.

The current `AnalogOutput` implementation is a linear coupling/reconstruction-filter model with nominal gain normalized out. Lower measured crest is therefore not proof that it contains a compressor. Upstream oscillator/filter/drive/envelope differences, capture processing and oscillator phase can all alter these statistics. Public performance MIDI, recording-specific patches, master/capture gain and line/phones or L-only jack state remain unverified. The schematic/source audit is complementary; absolute recording levels cannot calibrate its driver gain from these normalized excerpts.

**Decision:** no output-stage parameter is identified by this audit. The data support preserving punch and investigating the loss of bass overtones and preset-specific temporal shape before adding generic saturation. A later bounded output-path control should be judged against these retained counterexamples and the same original masks; no new output hypothesis was rendered or fitted here.

## Receipts and reproduction

The [original protocol](output-stage-characterization-original-protocol-2026-09-15.json) was frozen before hardware statistics. The [reporting revision](output-stage-characterization-protocol-2026-09-15.json) keeps every metric, input, mask, threshold and support unchanged, replacing 14 zero-support band ratios with explicit nulls and adding original power fractions. All 226 supported band records and every earlier level/dynamics/transient value were checked exactly unchanged. No result or parameter was selected after that correction.

```sh
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 python3 Tools/characterize_output_stage_references.py prepare \
  --integration build-fidelity/saw-w4-production-integration/run-02/results.json \
  --output build-fidelity/output-stage-characterization/new-prepared

OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 python3 Tools/characterize_output_stage_references.py measure \
  --protocol build-fidelity/output-stage-characterization/new-prepared/protocol.json \
  --output build-fidelity/output-stage-characterization/new-run
```

The [complete compact receipt](output-stage-reference-characterization-2026-09-15.json) equals the parsed full `build-fidelity/output-stage-characterization/run-03/results.json`. It contains all masks, frame starts, envelope levels, K blocks, source rise/rejection records, band powers and native/source hashes. No production source or preset was edited, and this task made no commit.

- Tool SHA: `6dad4b78ca71e5152824606cd825fe6c836850177ed53df527bbb66e5e3d7e7a`.
- Original frozen protocol SHA: `7c0f281117be9bff3a0775092721075bb6acb288f707ac30543e03f09bac01cb`.
- Final protocol SHA: `ac0f95358704f655816536f4be01af0d45193b1e9cc39a22e52ee3d7a0cb0649`.
- Full result SHA: `761b5d4004e7ba62fdefd57af28badbe154f1acd9a7f65ea0c8177a24479bad7`.
- Compact result SHA: `6df8dc0c9a8d2b6d702f5fc27f348cb56999045a774a4b58c68754f7a31e650a`.
