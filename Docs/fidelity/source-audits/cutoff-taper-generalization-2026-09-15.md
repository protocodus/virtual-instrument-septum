# Cutoff taper: ten-preset generalization experiment

## Result

**Neither E8 nor E9 is promoted.** The E8 curve improves the Air Lead hypothesis context substantially, but its mean spectral and log-spectrum errors worsen across the other nine presets. E9 gives a very small improvement in their mean spectral distance while worsening mean log-spectrum error. The independent inherited Moogie harmonic diagnostic also reveals regressions obscured by its slightly better whole-excerpt spectral score.

Air Lead was kept separate from the nine evaluation presets. No exponent, per-preset cutoff adjustment, envelope change or bypass behavior was selected from these results. Output equivalence remains unestablished.

## Candidates and isolation

The three predeclared profiles set only `filter.cutoff_hz[raw] = 20 × 2^(E × raw / 127)` for **E = 8, 9, 10**. E8 was suggested by Air Lead's conditional raw91 cutoff estimate around 1.1 kHz; it is a hypothesis from one wet preset, not an independently measured control range. E9 is an intermediate diagnostic, and E10 is the production control.

| Curve | Raw0 | Raw91 | Raw127 |
|---|---:|---:|---:|
| E10 control | 20 Hz | 2870.89 Hz | 20480 Hz |
| E8 | 20 Hz | 1063.21 Hz | 5120 Hz |
| E9 | 20 Hz | 1747.10 Hz | 10240 Hz |

These are base cutoff tables before unchanged key follow, velocity, filter envelope, LFO and final safety clamp. The engine applies no new bypass shortcut. Exact original preset bytes, note/controller events, envelope times and depths, resonance damping, oscillator behavior, effects and master settings remain unchanged.

All three engines use one frozen **b0f6c03** DSP snapshot. A small C++ helper evaluates the tables with the same `std::exp2(raw * (E / 127.0))` order as production, avoiding incidental cross-language rounding differences. Its E10 values equal the frozen inline mapping exactly. Only `cutoff_hz` is supplied to `Engine::defaultTimbreCalibration()` through the existing candidate builder.

**All ten E10 raw WAVs are byte-identical to pinned production.** All 30 renders are finite, below full scale and end with zero active voices. E8/E9 Cotton Wool also match production exactly: the only sounding tone has raw cutoff0, the common 20 Hz endpoint. This is an implementation control, not a hardware match.

The durable JSON includes complete 128-entry tables, candidate profiles, build manifests, every frozen DSP/tool hash, original patch/MIDI/raw render hashes, common and tone bytes, all raw envelope parameters, and every measurement. The source snapshot identifies b0f6c03 by retrieved file hashes; incidental Git HEAD fields in nested build manifests describe the enclosing checkout, not a different DSP source.

## Frozen timing and gain policy

This experiment copies the [earlier envelope preset policy](envelope-preset-holdouts-2026-09-15.md): fit one lag using **production alone** over the first 25% of each excerpt, bounded to ±50 ms. Freeze that lag for E8/E9/E10. Fit one RMS gain per complete candidate on the same paired first-quarter samples; also measure every candidate using the unchanged production gain.

Evaluate only the remaining 75%, with identical valid sample bounds for every model. For calibration boundary `cal` and candidate lookup `candidate[t + lag]`, evaluation bounds are `max(cal,cal-lag)` through `min(n,n-lag)`; calibration reference bounds are `max(0,-lag)` through `min(cal,cal-lag)`. No analysis frame crosses the excluded calibration boundary. Exact bounds, gains, frame counts and active-bin counts are retained.

All ten calibration transforms, evaluation bounds and complete production measurements reproduce the prior envelope-holdout run **exactly**. No model gets a timing refit, per-note gain, EQ or event adjustment.

| Preset | Frozen lag samples | E10 gain dB | E8 gain dB | E9 gain dB |
|---|---:|---:|---:|---:|
| air-lead-1 | -780 | 10.123 | 8.404 | 9.513 |
| brassy-ld-1 | -106 | 12.728 | 12.830 | 12.765 |
| club-bass | 232 | 5.228 | 5.230 | 5.229 |
| cotton-wool | -1346 | 11.103 | 11.103 | 11.103 |
| dist-bs-1 | 218 | 0.662 | 0.679 | 0.670 |
| moogie-1 | -475 | -2.493 | -2.449 | -2.477 |
| pedal-bs-1 | 178 | 2.591 | 2.492 | 2.538 |
| so-juno-1 | -337 | 7.617 | 7.582 | 7.601 |
| supa-juce-1 | 223 | 4.877 | 4.555 | 4.720 |
| vangelead | -469 | 6.166 | 6.530 | 6.318 |

## Whole-excerpt holdout metrics

Spectral convergence is the magnitude-STFT residual norm divided by the reference norm. The legacy mean averages 512, 2048 and 8192-sample Hann windows. **It is not an audible-mismatch percentage.** The [phase control](dry-phase-sensitivity-2026-09-15.md) demonstrates substantial short-window sensitivity; no phase robustness grid was run for these cutoff candidates.

Candidate-specific training gain, then fixed timing on the held-out interval:

| Preset | Role | E10 control | E8 | E9 |
|---|---|---:|---:|---:|
| air-lead-1 | context | 0.94653 | 0.77925 | 0.89493 |
| brassy-ld-1 | evaluation | 0.60861 | 0.63113 | 0.61327 |
| club-bass | evaluation | 0.42396 | 0.42405 | 0.42396 |
| cotton-wool | evaluation | 0.80692 | 0.80692 | 0.80692 |
| dist-bs-1 | evaluation | 0.31972 | 0.33378 | 0.32435 |
| moogie-1 | evaluation | 0.35918 | 0.35728 | 0.35883 |
| pedal-bs-1 | evaluation | 0.55726 | 0.55685 | 0.55726 |
| so-juno-1 | evaluation | 0.41714 | 0.41972 | 0.41820 |
| supa-juce-1 | evaluation | 0.53771 | 0.52013 | 0.51428 |
| vangelead | evaluation | 0.69270 | 0.71989 | 0.70256 |
| Mean of nine evaluation presets | evaluation | **0.52480** | **0.52997** | **0.52440** |
| Mean of all ten, including context | context included | 0.56697 | 0.55490 | 0.56145 |

Including the Air Lead context makes the aggregate look more favorable than the independent nine-preset evaluation. Across those nine, E8 raises mean SC at all three resolutions; E9's change is small at each. Both candidates produce mixed per-preset and per-metric results. No significance or perceptual threshold is attached to tiny differences such as Club Bass or Pedal Bs E9.

Mean log-spectrum errors, in dB, with the inherited pairwise union activity mask and −80 dB floor:

| Preset | E10 control | E8 | E9 |
|---|---:|---:|---:|
| air-lead-1 | 23.960 | 9.256 | 16.907 |
| brassy-ld-1 | 12.507 | 14.338 | 13.004 |
| club-bass | 15.644 | 16.036 | 15.773 |
| cotton-wool | 13.738 | 13.738 | 13.738 |
| dist-bs-1 | 10.416 | 11.441 | 10.988 |
| moogie-1 | 7.828 | 9.759 | 8.306 |
| pedal-bs-1 | 17.934 | 15.311 | 16.582 |
| so-juno-1 | 10.044 | 10.407 | 10.188 |
| supa-juce-1 | 8.591 | 9.641 | 8.666 |
| vangelead | 11.932 | 17.322 | 14.296 |
| Mean of nine evaluation presets | **12.071** | **13.110** | **12.393** |

E8's Air Lead SC improves .94653→.77925 and log error 23.960→9.256 dB. However, Vangelead worsens .69270→.71989 and 11.932→17.322 dB; Brassy and Dist also regress. Moogie and SupaJuce improve their aggregate SC while worsening log-spectrum error. These disagreements matter more than selecting a favorable average.

Fixed-production-gain spectral sensitivity:

| Preset | E10 control | E8 | E9 |
|---|---:|---:|---:|
| air-lead-1 | 0.94653 | 0.91113 | 0.93829 |
| brassy-ld-1 | 0.60861 | 0.62902 | 0.61245 |
| club-bass | 0.42396 | 0.42401 | 0.42394 |
| cotton-wool | 0.80692 | 0.80692 | 0.80692 |
| dist-bs-1 | 0.31972 | 0.33353 | 0.32424 |
| moogie-1 | 0.35918 | 0.35604 | 0.35835 |
| pedal-bs-1 | 0.55726 | 0.55300 | 0.55520 |
| so-juno-1 | 0.41714 | 0.41928 | 0.41798 |
| supa-juce-1 | 0.53771 | 0.52887 | 0.51811 |
| vangelead | 0.69270 | 0.70245 | 0.69530 |
| Mean of nine evaluation presets | **0.52480** | **0.52812** | **0.52361** |

Air Lead's E8 advantage is much smaller under fixed production gain (.94653→.91113). The main candidate-specific gain is 1.719 dB lower than production, reflecting a whole-patch level change that the prescribed nuisance fit absorbs. This sensitivity is retained rather than interpreted as a universal timbral improvement.

## Every resolution and RMS envelope result

Candidate-specific first-quarter gain. RMS columns are 10 ms / 50 ms P95 absolute envelope error in dB. Spectral columns are separate resolutions; no short-window score is interpreted alone as an audible defect.

| Preset | Curve | SC512 | SC2048 | SC8192 | RMS10 / RMS50 P95 dB |
|---|---|---:|---:|---:|---:|
| air-lead-1 | E10 | 0.89859 | 0.94275 | 0.99826 | 4.724 / 4.119 |
| air-lead-1 | E8 | 0.69769 | 0.77206 | 0.86799 | 4.920 / 4.082 |
| air-lead-1 | E9 | 0.83388 | 0.89123 | 0.95968 | 4.792 / 4.270 |
| brassy-ld-1 | E10 | 0.62014 | 0.62246 | 0.58322 | 10.601 / 9.122 |
| brassy-ld-1 | E8 | 0.63793 | 0.64273 | 0.61272 | 13.836 / 12.928 |
| brassy-ld-1 | E9 | 0.62286 | 0.62624 | 0.59071 | 12.765 / 11.142 |
| club-bass | E10 | 0.52301 | 0.37038 | 0.37850 | 6.969 / 5.665 |
| club-bass | E8 | 0.52186 | 0.37060 | 0.37970 | 6.884 / 5.500 |
| club-bass | E9 | 0.52262 | 0.37045 | 0.37882 | 6.911 / 5.712 |
| cotton-wool | E10 | 0.79559 | 0.81242 | 0.81276 | 11.777 / 11.663 |
| cotton-wool | E8 | 0.79559 | 0.81242 | 0.81276 | 11.777 / 11.663 |
| cotton-wool | E9 | 0.79559 | 0.81242 | 0.81276 | 11.777 / 11.663 |
| dist-bs-1 | E10 | 0.35691 | 0.31156 | 0.29070 | 24.824 / 15.000 |
| dist-bs-1 | E8 | 0.37747 | 0.32351 | 0.30036 | 24.856 / 15.032 |
| dist-bs-1 | E9 | 0.36276 | 0.31592 | 0.29436 | 24.839 / 15.015 |
| moogie-1 | E10 | 0.54615 | 0.28288 | 0.24851 | 4.378 / 0.947 |
| moogie-1 | E8 | 0.53641 | 0.28643 | 0.24899 | 4.242 / 0.895 |
| moogie-1 | E9 | 0.54236 | 0.28510 | 0.24902 | 4.279 / 0.923 |
| pedal-bs-1 | E10 | 0.61265 | 0.52428 | 0.53486 | 18.916 / 17.325 |
| pedal-bs-1 | E8 | 0.61276 | 0.52487 | 0.53292 | 18.215 / 17.319 |
| pedal-bs-1 | E9 | 0.61244 | 0.52495 | 0.53439 | 18.839 / 17.351 |
| so-juno-1 | E10 | 0.51533 | 0.37079 | 0.36529 | 36.345 / 34.152 |
| so-juno-1 | E8 | 0.52216 | 0.37132 | 0.36570 | 30.224 / 27.973 |
| so-juno-1 | E9 | 0.51828 | 0.37092 | 0.36539 | 33.864 / 31.030 |
| supa-juce-1 | E10 | 0.54306 | 0.54075 | 0.52932 | 10.538 / 8.710 |
| supa-juce-1 | E8 | 0.52957 | 0.52561 | 0.50521 | 10.600 / 8.614 |
| supa-juce-1 | E9 | 0.52178 | 0.51883 | 0.50222 | 10.547 / 8.664 |
| vangelead | E10 | 0.68788 | 0.70404 | 0.68617 | 7.340 / 7.304 |
| vangelead | E8 | 0.71410 | 0.73075 | 0.71481 | 7.491 / 7.539 |
| vangelead | E9 | 0.69730 | 0.71374 | 0.69664 | 7.408 / 7.370 |

The JSON also preserves every log-spectrum mean/P95 and fixed-production-gain counterpart. Pairwise activity masks are candidate dependent, so log/RMS differences have that qualification; spectral convergence is unmasked.

## Active raw cutoff values and predictions

Only sounding tones are listed here; both complete tone blocks remain in the JSON. Every value is before the unchanged dynamic modulation and final clamp.

| Preset / tone | Raw cutoff | E10 Hz | E8 Hz | E9 Hz |
|---|---:|---:|---:|---:|
| air-lead-1 upper | 91 | 2870.89 | 1063.21 | 1747.10 |
| brassy-ld-1 upper | 50 | 306.33 | 177.48 | 233.17 |
| club-bass upper | 103 | 5526.55 | 1795.43 | 3150.01 |
| club-bass lower | 110 | 8097.97 | 2437.29 | 4442.65 |
| cotton-wool upper | 0 | 20.00 | 20.00 | 20.00 |
| dist-bs-1 upper | 36 | 142.67 | 96.31 | 117.22 |
| dist-bs-1 lower | 57 | 448.86 | 240.93 | 328.85 |
| moogie-1 upper | 30 | 102.83 | 74.11 | 87.30 |
| moogie-1 lower | 47 | 260.06 | 155.69 | 201.22 |
| pedal-bs-1 upper | 34 | 127.92 | 88.26 | 106.25 |
| so-juno-1 upper | 12 | 38.50 | 33.77 | 36.06 |
| so-juno-1 lower | 41 | 187.44 | 119.81 | 149.86 |
| supa-juce-1 upper | 27 | 87.30 | 65.02 | 75.34 |
| vangelead upper | 58 | 474.04 | 251.68 | 345.41 |
| vangelead lower | 101 | 4955.05 | 1645.30 | 2855.26 |

A single global table explains the changes. No per-patch controls were retuned. In particular, the raw47 value from the earlier dry reconstructed recipe would move from 260.06 Hz to 155.69/201.22 Hz before key follow; that recipe was conditional on its prior taper and is not an independent raw47 hardware anchor. This experiment does not silently refit it.

## Inherited Moogie harmonic diagnostic

The existing scorer's three long-note onsets (.029, .939, 1.901 s), offsets +.10/.18/.26 s, 80 ms windows and −20/0/+20 ms hardware timing sensitivity are reused unchanged. It fits 96 sinusoid/ramp harmonics, uses hardware-only eligibility, and compensates the renderer by 93 samples. Candidate frequency estimates are frozen from production for each note, with a second run using nominal 38.890873 Hz throughout. No frequency, ratio offset or gain is fitted to a cutoff candidate.

This is a **separate note-window diagnostic**, not the whole-excerpt lag/gain policy. First-note and later-note rows all remain in the data. The inherited scorer's `--frozen-candidate cutoff-e10` names the baseline control to disable selection; its `selection` field does not choose a taper. No smallest score or timing shift is selected.

Later-note ratio RMS errors, at zero timing shift:

| Frequency policy | Curve | H2–H8 / H1 dB | Odd / H1 dB | H4,H6,H8 / H2 dB |
|---|---|---:|---:|---:|
| estimated | E10 | 5.252 | 4.038 | 5.643 |
| estimated | E8 | 6.060 | 4.371 | 6.890 |
| estimated | E9 | 5.333 | 3.631 | 5.987 |
| nominal | E10 | 5.181 | 4.063 | 5.503 |
| nominal | E8 | 6.002 | 4.210 | 6.852 |
| nominal | E9 | 5.250 | 3.493 | 5.905 |

At estimated frequency, E8 raises full ratios 5.252→6.060 dB and even ratios 5.643→6.890 dB; E9 raises them to 5.333/5.987 dB. E8's full/even regression persists at both timing shifts and with nominal frequency. E9 improves odd ratios, but even ratios worsen across all six frequency/timing combinations; its full-ratio result changes sign at +20 ms. Every candidate retains the same hardware-selected observations: at zero shift, 42 full / 18 odd / 18 even later-note ratios.

The moving-filter frequency estimates are effective fit nuisances, not measured oscillator tuning. Mixed waves, layers, effects, relative phase and reconstructed articulation remain confounded; even-family interpretation assumes symmetric lower square/triangle behavior and sufficiently linear processing. These checks establish no stationary filter response or harmonic acceptance threshold. Air Lead's existing harmonic analysis uses only the opening 65–95 ms and belongs to the hypothesis context; no new independent Air or Club harmonic validation was invented.

## Reproduction and qualification

Run from a checkout containing b0f6c03, Python 3.11 with NumPy/SciPy, and a C++20 compiler. The comparison root must be the prior hash-verified production corpus produced by `Tools/compare_hardware.py` using the pinned production renderer and original official source cache. The [production identity record](final-production-verification-2026-09-15.json) pins its ten raw render, MIDI and patch hashes; the [earlier reproduction instructions](zero-resonance-reproduction-2026-09-15.md) describe acquiring/recreating the underlying original-media comparisons. Generated decoder containers are validated against each run's comparison metadata, not treated as original media identities.

```sh
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 python3 Tools/compare_cutoff_taper_candidates.py \
  --comparison-root build-fidelity/hardware-benchmark/final-production-linear-lfo \
  --output build-fidelity/hardware-benchmark/cutoff-taper-candidates/NEW_RUN
```

This tool reconstructs sources directly from Git, generates and pins all profiles, compiles three engines, guards E10 identity, renders all cases and generates a held-out comparison player. It depends on no ignored build scripts or preexisting experimental source snapshots. The measured run is `build-fidelity/hardware-benchmark/cutoff-taper-candidates/run-01`.

For the additional Moogie diagnostic, replace `NEW_RUN` below with the new experiment path:

```sh
OPENBLAS_NUM_THREADS=1 python3 Tools/score_moogie_envelope_candidates.py \
  --hardware NEW_RUN/cases/moogie-1/hardware-excerpt-raw.wav \
  --production NEW_RUN/cases/moogie-1/cutoff-e10.wav \
  --candidate cutoff-e10=NEW_RUN/cases/moogie-1/cutoff-e10.wav \
  --candidate cutoff-e8=NEW_RUN/cases/moogie-1/cutoff-e8.wav \
  --candidate cutoff-e9=NEW_RUN/cases/moogie-1/cutoff-e9.wav \
  --sysex NEW_RUN/cases/moogie-1/original-patch.syx \
  --midi NEW_RUN/cases/moogie-1/reconstructed-performance.mid \
  --frozen-candidate cutoff-e10 --frequency-policy estimated \
  --output NEW_RUN/moogie-harmonics-estimated
```

Repeat with `--frequency-policy nominal` and `--output NEW_RUN/moogie-harmonics-nominal`. Exact executed commands and scorer hashes are also retained in the durable JSON. The scorer's waveform/timing guards and synthetic self-tests passed. These are all-candidate diagnostics, not another parameter selection.

Durable results: [full engine measurements and provenance](cutoff-taper-generalization-2026-09-15.json), [Moogie estimated-frequency measurements](cutoff-taper-moogie-estimated-2026-09-15.json), [nominal-frequency sensitivity](cutoff-taper-moogie-nominal-2026-09-15.json). Complete preset/MIDI hashes, all E10 identities and previous-policy equality were checked; no production changes or new runtime tests were required.

The recorded patch revisions, original MIDI, performance controls, source compression and capture processing remain uncertain. Air Lead's apparent cutoff anchor can still be confounded by its waveform mixture and capture response. These results do not establish a global raw cutoff curve, its endpoints, market superiority, or instrument-output equivalence.
