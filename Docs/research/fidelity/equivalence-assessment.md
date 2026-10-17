# Audio agreement assessment

**The present recordings do not establish matching output.** The new
`Tools/assess_hardware_equivalence.py` measures audio differences that the
previous RMS/centroid summaries cannot resolve. Its acceptance gate remains
`not_established` until acceptance margins have independent evidence. There
is no default percentage or dB threshold labeled “realistic” or “equivalent.”

Public recordings can support a scoped assessment of perceptual agreement.
Original MIDI is useful evidence rather than an absolute prerequisite for
that assessment. Input uncertainty must remain visible: a public performance
with a documented panel recipe is different from a recording-specific SysEx
dump, and a published named preset is different from an authenticated recorded
revision. A small metric is insufficient to settle those uncertainties or to
establish superiority over other instruments.

The [near-silence alignment correction](source-audits/alignment-silence-regression-2026-09-15.md)
centers the candidate RMS envelope and requires each search window to have
variance above 1e−12 times the candidate's complete prefix energy. This
gain-invariant numerical guard prevents FFT round-off divided by almost-zero
variance from selecting a false perfect match. It is not an audibility or
acceptance threshold. Of 171 historical fits replayed, only the newly added
201vsJP8000 early-release scenario changes; the others preserve exact lag
and gain, including the baseline below.

The subsequent [four-phase dry control](source-audits/dry-phase-sensitivity-2026-09-15.md)
measures a material limitation of these metrics: at MIDI 24, changing only
saw phase produces 512-sample spectral distances around 0.76, falling to
0.006–0.012 with 8192 samples. Full-sequence distances remain sensitive to
transients and changing note mixtures. Report each resolution and stable
harmonic features together; do not interpret these distances as audible
error percentages, subtract the control, or derive an equivalence margin
from four synthetic phases. Hardware envelope errors still exceed the
observed phase-control range.

## Baseline: ten official Roland recordings

The baseline renders are identified as `d343d04`. Input/output and comparison
manifest hashes are in the [measurement record](source-audits/equivalence-baseline-d343d04.json).
The first **25% of every excerpt** fits one positive scalar gain and one global
delay within **±50 ms**, using 10 ms RMS-envelope correlation. The remaining
samples evaluate the frozen transformation. A guard ensures both signals'
evaluation windows start after calibration. No per-note gain, EQ, pitch shift,
resampling or time warp is fitted. No alignment reached the search boundary.

These are **samples held out from gain/delay fitting**, not recordings held out
from DSP tuning. Several recordings informed earlier filter and envelope changes.
Reconstructed notes, velocities and releases remain unchanged. All ten use
unchanged published presets and estimated performance MIDI.

| Recording | Spectral distance | Log spectral error, dB | Envelope P95, dB | Side fraction difference | Gain, dB | Delay, ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Air Lead 1 | 0.947 | 23.93 | 4.68 | 0.0691 | +9.98 | −19.21 |
| Brassy Ld 1 | 0.600 | 11.93 | 12.57 | 0.0052 | +13.26 | −2.36 |
| Club Bass | 0.424 | 15.57 | 7.00 | 0.0032 | +5.23 | +5.28 |
| Cotton Wool | 0.813 | 11.83 | 11.80 | 0.0949 | +11.17 | −30.43 |
| Dist Bs 1 | 0.327 | 10.91 | 24.92 | 0.0005 | +0.76 | +5.06 |
| Moogie 1 | 0.360 | 8.55 | 4.24 | 0.0003 | −2.33 | −10.45 |
| Pedal Bs 1 | 0.535 | 16.52 | 18.36 | 0.0004 | +3.32 | +3.83 |
| So Juno 1 | 0.421 | 11.04 | 29.41 | 0.0130 | +7.68 | −7.53 |
| SupaJuce 1 | 0.538 | 8.59 | 10.54 | 0.0515 | +4.88 | +5.06 |
| Vangelead | 0.711 | 12.69 | 7.71 | 0.0293 | +7.00 | −12.90 |

Lower distances mean closer measured features; zero means equality of those
features. **A spectral distance of 0.327 does not mean 67.3% fidelity.** Delay
uses `candidate[t + delay]` against `reference[t]`. Positive gain raises the
candidate. Absolute output gain is uncalibrated; the JSON also retains raw
measurements before either fitted correction.

### What this suggests investigating

1. **Spectral shape and its motion:** Air Lead, Cotton and Vangelead have the
   largest energy-weighted spectral discrepancies. Check harmonic/filter
   trajectories using dry isolated references before changing shared DSP.
   Air Lead and Cotton also have the largest stereo-energy differences.
2. **Gates, release and effects:** So Juno, Dist and Pedal have large envelope
   tail errors. Their P95 values include quiet tails and are not loudness
   weighted. Wrong reconstructed releases, differing original velocities and
   recording noise can enlarge them; they do not isolate amplifier-envelope
   error or justify retuning it on their own.
3. **Keep simple dry references:** Dist Bs is useful for waveform/overdrive
   comparisons because its excerpt excludes obvious pitch movement and the
   published delay/reverb are disabled. Moogie's repeated notes support
   within-phrase checks, but repeated velocity is unknown. SupaJuce provides
   resonant harmonic motion. Cotton remains more uncertain because of chord
   voicing, modulation phase and wet tails.

The newly located deepsonic filter recordings have original sequence MIDI and
a documented patch recipe. They offer stronger isolation for filter work than
the reconstructed musical demos. They must be labeled
`original_performance` plus `documented_recipe_reconstruction`, not exact
recording-specific preset captures.

## Measurements and limits

- **Spectral distance:** mean of `norm(|candidate STFT| − |reference STFT|) /
  norm(|reference STFT|)` across Hann windows of 512, 2048 and 8192 samples at
  44.1 kHz, with 75% overlap. Window sizes scale to nearby powers of two at
  other rates. Short windows follow attacks; long windows separate low bass
  harmonics. Left/right magnitudes remain separate and all frequencies from
  DC through Nyquist are included.
- **Log spectral error:** mean absolute magnitude difference in dB over the
  union of reference/candidate bins above −60 dB relative to each reference
  STFT's peak, using a −80 dB reference-relative floor. Candidate-only energy
  is included. These numerical thresholds define the analysis; they are not
  human audibility or acceptance thresholds. Quiet bins and codec differences
  can contribute substantially.
- **Envelope P95:** the larger 95th-percentile absolute RMS-level difference
  from 10 ms and 50 ms windows at 5 ms hops, with a corresponding activity
  mask. These are output RMS traces, not isolated amplifier envelopes.
- **Stereo:** side energy as a fraction of total mid/side energy, plus channel
  balance in dB. This detects stereo collapse that magnitude spectra alone
  miss. Whole-window stereo summaries cannot characterize every moving image.
- **Waveform residual:** normalized RMS subtraction error is retained as a
  diagnostic and excluded from the acceptance margins. Oscillator/modulation
  phase, capture-clock drift and lossy encoding can prevent a waveform null
  even when sound is perceptually similar.

No single metric is a psychoacoustic model. The tool rejects silent/nonfinite
files, implicit sample-rate conversion, mismatched channel layouts and
unexplained truncation. Existing comparison manifests may explicitly crop the
renderer's extra release tail. Their raw audio hashes must match before use.

## Acceptance gate

Without a separate protocol, the output is `not_established` regardless of
distance. A protocol must define scope, public-input uncertainty, independently
justified maximum errors for **all five summary measures**, hardware
repeatability and perceptual-validation evidence, and evidence that the protocol
preceded evaluation. Those evidence artifacts are hashed. The protocol must
also bind the reference hash, calibration frame count, lag bound and tool hash.
Its declaration must state that evaluation data were excluded from DSP tuning.

Given a complete protocol, results are `within_registered_bounds` or
`outside_registered_bounds`. Failed numerical margins remain visible even when
missing evidence keeps the overall status `not_established`. A numerical failure
is an **audio-pair discrepancy**, not proof that DSP alone caused it. A numerical
pass applies only to the declared data and scope. File hashes prove artifact
identity; a human must still review authenticity, independence and the margin
justification. The tool does not turn a self-authored evidence file into an
authenticated hardware or listening experiment.

This deliberately leaves acceptance margins unset for the current ten demos.
Neither the MP3 recording chain's repeatability nor a perceptually validated
distance limit has been established. Their observed distances cannot be used
to choose their own passing limits.

## Reproduce

Install the optional packages in `Tools/requirements-hardware.txt`. Run one case:

```sh
python3 -B Tools/assess_hardware_equivalence.py \
  --comparison build-fidelity/hardware-benchmark/baseline-d343d04/moogie-1/comparison.json \
  --calibration-fraction .25 --max-lag-seconds .05 \
  --output build-fidelity/moogie-equivalence-new.json
python3 -B Tests/HardwareEquivalenceTests.py
```

Apply the same command to each case listed in the measurement record to reproduce
the table. Full per-case reports are under
`build-fidelity/hardware-benchmark/baseline-d343d04/equivalence-prefix25/`.
Whole-excerpt gain-only exploratory reports were also retained under
`equivalence-assessment/`; these are a distinct, less controlled measurement.

For new original-MIDI/recipe pairs, use equal-length, equal-rate WAVs with
`--reference`, `--candidate` and `--provenance`. The provenance JSON schema is:

```json
{
  "schema_version": 1,
  "source_url": "https://source.example/recording-and-inputs",
  "midi": {
    "status": "original_performance",
    "artifact": {"path": "original.mid", "sha256": "HASH_OF_ORIGINAL_MIDI"}
  },
  "preset": {
    "status": "documented_recipe_reconstruction",
    "artifact": {"path": "source-recipe.html", "sha256": "HASH_OF_SOURCE_RECIPE"}
  },
  "uncertainties": ["No recording-specific SysEx dump; MP3 capture chain"]
}
```

The twelve regression tests check false equivalence from equal RMS/centroid,
reordered notes with equal average spectra, phase-induced stereo collapse,
frozen prefix calibration, altered held-out envelopes, source hashes, silent
inputs and unsupported acceptance margins. They test measurement/gate behavior,
not SH-201 fidelity. CMake registers `Septum.HardwareEquivalence` when its Python
interpreter has NumPy and SciPy; they are optional analysis dependencies.

## Existing comparison-tool audit

`compare_hardware.py` correctly preserves original compressed sources, raw PCM,
raw synthesis, estimated-MIDI labels and scalar-gain listening copies. Its
centroid/RMS summaries and long-term plots were never numerical equivalence
tests. A published bank verifies exported patch bytes but cannot authenticate
the recorded revision. Current source-file hashes also do not by themselves
prove that an arbitrarily supplied renderer was compiled from those files;
retain the renderer fingerprint and build provenance. The new assessor adds
audio-pair measurements without changing any of those existing renders.
