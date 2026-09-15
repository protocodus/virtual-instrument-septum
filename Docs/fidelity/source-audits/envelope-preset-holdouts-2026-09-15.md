# Filter-envelope hypotheses on unchanged published presets

**Keep the production envelope.** The exponential-in-Hz trajectory favored
by the dry chord measurements does not yet generalize through an assumed raw
control table. Its Moogie-selected implementation worsens average spectral
error across ten named presets. A geometric-cutoff exponential control gives
mixed results too. Neither establishes a hardware algorithm or output match.

The [complete numerical record](envelope-preset-holdouts-2026-09-15.json)
preserves every preset's measurements, fixed-gain sensitivity, source hashes,
calibration and coverage. These are public hardware recordings and unchanged
published same-name presets. Their performance MIDI is reconstructed; the
exact recorded preset revision, velocities, gates and controller state remain
unverified. No preset bytes were adjusted to rescue either candidate.

## Frozen experiment

The [predeclared design](hz-envelope-experiment-design-2026-09-15.md) fixes five
time constants at decay raw49: 0.08, 0.11, 0.15, 0.20 and 0.27 seconds. Both
exponential families use that same grid. All other raw decay times retain
their ratios in the existing filter table. The raw depth, cutoff, attack,
sustain, release, oscillators, resonance and effect parameters are unchanged.

The Hz family interpolates frequency as
`base × [1 + (2^depth − 1) × envelope]`. The log control retains
`base × 2^(depth × envelope)`. Both use an exponential amount decay, with
`T60 = time_constant × ln(1000)`. This changes sustain/attack/release cutoff
behavior in the Hz family as well as decay. It is an explicit hypothesis;
the dry zero-sustain recordings do not establish those other segments.

Only the first Moogie low note selects a candidate, using H4/H2, H6/H2 and
H8/H2 in three predeclared windows. The selected Hz time constant is **0.15 s**
(raw49 T60 1.03616 s); the selected log value is **0.27 s** (T60 1.86509 s).
The log selection reaches the grid boundary and remains an unresolved bound.
Its grid was not expanded using validation results. Both members were frozen
before rendering the other presets. Their first-note errors, 5.519 / 5.489 dB,
are only slightly below production's 5.596 dB.

On the other two long Moogie notes, even-harmonic error changes
5.643 → 5.621 / 5.579 dB for Hz/log, while full H2–H8 error worsens
5.253 → 5.386 / 5.359 dB. The Hz even-harmonic gain reverses at the
predeclared +20 ms onset sensitivity. Fixing frequency at the nominal
oscillator family instead of its effective measured value also changes which
family has the smaller even-harmonic residual. The
[paired scorer record](moogie-envelope-grid-score-2026-09-15.json) preserves
these tests with the original winners frozen. Moogie does not identify the
cutoff interpolation domain.

All renderers use frozen **b0f6c03** DSP with explicit changes confined to
copied experimental sources. The filter's convergence threshold becomes
1e−8 to avoid large cutoff jumps at extreme depth. Amplifier and pitch
envelopes retain their original behavior. The
[source review](envelope-source-review-2026-09-15.md) checks these integration
points and the independent dry physical targets.

## Ten-preset results

Lower spectral distance is better. It measures STFT magnitude residuals;
it is not a percentage of fidelity or a perceptual acceptance test.

| Preset | Production | Hz exponential | Log exponential |
| --- | ---: | ---: | ---: |
| Air Lead 1 | 0.94653 | 0.94653 | 0.94653 |
| Brassy Ld 1 | 0.60861 | 0.61832 | 0.61229 |
| Club Bass | 0.42396 | 0.42396 | 0.42396 |
| Cotton Wool | 0.80692 | 0.78531 | 0.79850 |
| Dist Bs 1 | 0.31972 | 0.31889 | 0.31844 |
| Moogie 1 | 0.35918 | 0.36006 | 0.35955 |
| Pedal Bs 1 | 0.55726 | 0.55809 | 0.55646 |
| So Juno 1 | 0.41714 | 0.42051 | 0.41770 |
| SupaJuce 1 | 0.53771 | 0.57935 | 0.51984 |
| Vangelead | 0.69270 | 0.68857 | 0.69199 |
| Unweighted mean | **0.56697** | **0.56996** | **0.56453** |

Mean log-spectrum error is **13.259 dB** in production, **13.916 dB** for Hz
and **13.300 dB** for log. Cotton's Hz candidate improves spectral distance
while worsening log-spectrum error from 13.738 to 15.620 dB. SupaJuce's Hz
regression is substantial compared with the small Moogie training gain.
These disagreements prevent selecting a global envelope change from the
single aggregate that happens to improve.

Air Lead and Club Bass have zero filter-envelope depth. Both candidate WAVs
are **byte-identical** to production for both complete preset performances,
including effects and the active amplifier/pitch behavior. The independently
built production Moogie WAV also matches the shipping checkpoint exactly.
These controls establish implementation isolation for those fixtures; they
do not prove all envelope modes or raw values.

## Alignment, gain and listening

For each preset, production alone determines one delay from the first 25%
of the recording, using an envelope-correlation search bounded to 50 ms.
Every candidate uses that same delay. Each render gets one RMS gain fitted
only on the aligned first-quarter samples; the remaining interval has
identical coverage across all models. No analysis frame crosses the
calibration boundary. A second measurement retains the exact production
gain for all candidates. There is no per-note alignment, gain, EQ or time warp.

The first-quarter split separates nuisance fitting from evaluation; it does
not erase earlier development's exposure to these recordings. Delay inferred
from an uncertain reconstructed performance is also a nuisance estimate,
not a recovered hardware latency.

The generated listening page uses only the evaluation interval, with the
same training gains and delay as the measurements. One common final scalar
keeps hardware and all candidates below full scale. Raw floats and their
peak/full-scale counts remain available in the JSON. The page is at
`build-fidelity/envelope-hypothesis/preset-holdouts-v1/index.html`.

## Reproduction

[Build the isolated candidates](../../../Tools/build_envelope_experiment.py)
with `--stage factory`, a fresh `--output`, and the verified production
`--comparison-root`. The builder freezes Git sources, profiles, compiler and
binary identities, source diffs, original inputs and render receipts. It
rejects output-directory reuse and a changed production control.

Run [the Moogie scorer](../../../Tools/score_moogie_envelope_candidates.py)
on the emitted `hz-score-input.json` and `log-score-input.json`. Freeze its
selections before running
[the preset comparison](../../../Tools/compare_envelope_preset_holdouts.py)
with the two selected `--candidate id=renderer` arguments and corresponding
`--selection-record` files. The original benchmark audio/preset cache is
required; third-party payloads are not committed here.

The unresolved raw envelope table and waveform mixture prevent interpreting
this as a rejection of every exponential-in-Hz implementation. It does reject
promoting these particular candidates as a general improvement.
