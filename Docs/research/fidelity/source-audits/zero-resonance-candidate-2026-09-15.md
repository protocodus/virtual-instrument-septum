# Superseded quadratic low-resonance candidate: ten unchanged official presets

## Result

The public-demo evidence is mixed. The candidate does not establish an overall
improvement or equivalent output. With each renderer's gain/delay fitted on its
first 25%, mean spectral distance changes from **0.567562 to 0.566980**
(−0.000583); mean log spectral error increases **0.091 dB**, and mean envelope
P95 increases **0.516 dB**. These are unweighted descriptive means across ten
excerpts, not a perceptual score or statistical significance test.

When the candidate uses the baseline's exact gain, delay and evaluation frames,
mean spectral distance instead increases **0.003852**. Some apparent improvement
therefore depends on nuisance refitting. Both analyses are retained.

No shipping default was changed by this quadratic experiment. The dry-filter
recordings provide more isolated evidence for zero-resonance damping; these
musical demos remain confounded by estimated MIDI, velocity, preset revision,
phase and recording chain.

## Per-case measurements

Positive deltas mean greater numerical error. They are not calibrated audibility
judgments. The final column freezes the baseline nuisance transformation. Raw
resonance values are Upper / Lower; a tone can be inactive, and a quiet secondary
tone may have little effect.

| Case | Raw resonance | Spectral distance before → after | Δ spectral | Δ log spectral, dB | Δ envelope P95, dB | Δ spectral, fixed baseline transform |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| air-lead-1 | 44 / 0 | 0.94653 → 0.94653 | +0.00000 | +0.000 | +0.000 | +0.00000 |
| brassy-ld-1 | 0 / 0 | 0.60182 → 0.60861 | +0.00679 | +0.568 | -1.993 | +0.02249 |
| club-bass | 41 / 0 | 0.42399 → 0.42396 | -0.00003 | -0.001 | +0.010 | +0.00008 |
| cotton-wool | 0 / 0 | 0.81283 → 0.80692 | -0.00591 | +1.912 | -0.022 | -0.00184 |
| dist-bs-1 | 31 / 0 | 0.32664 → 0.31979 | -0.00686 | -0.495 | -0.095 | -0.00536 |
| moogie-1 | 0 / 0 | 0.35968 → 0.35918 | -0.00051 | -0.726 | +0.138 | +0.00450 |
| pedal-bs-1 | 0 / 0 | 0.53461 → 0.55726 | +0.02266 | +1.412 | +0.552 | -0.00454 |
| so-juno-1 | 0 / 0 | 0.42087 → 0.41714 | -0.00373 | -1.001 | +6.932 | -0.00624 |
| supa-juce-1 | 40 / 0 | 0.53771 → 0.53771 | +0.00000 | +0.000 | +0.000 | +0.00000 |
| vangelead | 0 / 0 | 0.71094 → 0.69270 | -0.01824 | -0.755 | -0.365 | +0.02944 |

- **Pedal Bs 1**: spectral/log/envelope errors increase with separate prefix
  fits. Spectral distance improves slightly using the baseline transform, so
  the interpretation depends on the assumed recording gain.
- **Brassy Ld 1**: spectral and log spectral errors increase under both
  transform policies; its envelope statistic improves about 1.99 dB.
- **So Juno 1**: spectral/log errors decrease, but envelope P95 increases
  6.93 dB. This statistic includes quiet release tails and uncertain gates.
- **Cotton Wool**: energy-weighted spectral distance decreases while log
  spectral error increases 1.91 dB; stereo side-fraction error improves.
- **Vangelead**: spectral/log/envelope errors improve after separate gain fits;
  its spectral distance worsens with the baseline transform. Candidate gain
  changes −0.835 dB and fitted delay moves 100 samples (2.27 ms).
- **Moogie 1**: spectral/log error improves slightly after separate fitting;
  envelope P95 increases 0.138 dB and fixed-transform spectral error increases.
- **Dist Bs 1**: spectral/log/envelope errors improve under both transform
  policies for the spectral measure.
- **Club Bass**: changes are tiny. Its Upper resonance is 41, but its active
  Lower tone has resonance zero, so the combined WAV is not identical.
- **Air Lead 1 and SupaJuce 1**: raw WAVs are byte-identical to the control.
  Their active Upper resonances are 44 and 40; the Lower tones are inactive.

No fitted lag reached ±50 ms. Most candidate/control lag changes are at most
14 samples; Vangelead is the largest at 100 samples. The full summary retains
all gains, lags, raw-level errors, stereo measurements, original input hashes,
raw-render hashes and detailed report hashes.

## Controlled construction

Both renderers were built with `Tools/build_timbre_candidate.py` from the same
18 frozen DSP/renderer inputs. The control contains the current measured LFO
correction and has all calibration sections disabled. The candidate supplies
only `filter.resonance_damping`:

```
b = 2 - 2.04 * sqrt(v / 127)
old = 2 * (b / 2)^1.5 if b > 0 else b
k = max(-0.04, old - 0.8 * max(1 - v / 40, 0)^2)
```

This gives k(0)=1.2 and restores the prior integer table from raw 40 onward.
The −0.04 clamp only handles the existing profile's bounded endpoint at raw127,
where binary arithmetic otherwise produces −0.040000000000000036.
`secondStageIndependent` remains false, so stage two derives clamp(k,0.5,1.2)
from the live first-stage damping. No other calibration fields are supplied.
The candidate table is monotonic and passed the builder's validation.

Frozen manifests prove both builds consumed identical DSP/renderer bytes.
All twenty rendered MIDI and SysEx hashes also match the original ten cases in
`baseline-d343d04`. All raw audio is finite, with no full-scale samples,
44.1 kHz stereo, 93-sample retained latency and zero active voices at the end.
The candidate peak maximum is 0.73555 (Moogie 1).

This is a comparison of samples held out from prefix gain/delay fitting. The
recordings are not held out from earlier DSP development. Acceptance remains
`not_established`; the assessor supplies no arbitrary perceptual pass margin.

## Files and reproduction

- `frozen-source-manifest.json`: original source revision/diff and byte hashes.
- `profiles/`: control and candidate profile definitions.
- `run-01/{lfo-only,zero-resonance-k1p2}/build/`: compiled renderer, profile,
  frozen inputs, compiler log and build manifest.
- `run-01/{lfo-only,zero-resonance-k1p2}/comparisons/`: ten unchanged inputs,
  original excerpts, raw renders, A/B listening pages and detailed metrics.
- `run-01/summary.json`: complete comparison and both nuisance policies.

To reconstruct the frozen source and reproduce in a new output directory using
only tracked scripts, the pinned bundle and original source caches:

```sh
python3 -B Tools/reproduce_zero_resonance_benchmark.py \
  --output build-fidelity/hardware-benchmark/reproduction-new \
  --sources build-fidelity/hardware-benchmark/sources \
  --deepsonic-sources build-fidelity/deepsonic
```

The complete numeric and provenance record is [zero-resonance-candidate-2026-09-15.json](zero-resonance-candidate-2026-09-15.json). Generated file locations above are relative to `build-fidelity/hardware-benchmark/zero-resonance-candidate/`.
See [reproduction details](zero-resonance-reproduction-2026-09-15.md) for
dependencies, strict original-media hashes and private decoding.

## Final linear-bridge follow-up

The final production change uses a straight bridge from k0=1.2 to the prior k40=.5591507918157866; the quadratic interpolation above is a retained experiment. Its zero-resonance endpoint and raw40+ values are unchanged. Only Dist Bs1 has an active intermediate resonance in this ten-preset set (Upper31, Lower0). Rebuilding a linear profile from the same frozen inputs gives spectral distance **0.319719**, compared with **0.319787** for the quadratic candidate and **0.326645** for the LFO-only control. Log spectral error is **10.4158 dB**, compared with **10.4193** and **10.9143**; envelope P95 is **24.8242 dB**, compared with **24.8257** and **24.9208**. These small numeric changes do not establish audibility or validate the unmeasured interior curve. Full data: [linear Dist follow-up](zero-resonance-linear-dist-2026-09-15.json).

All ten raw renders from the final production renderer are **byte-identical**
to their frozen-profile counterparts: nine to this candidate and Dist to the
linear follow-up. MIDI/SysEx identities and zero maximum PCM differences are in
the [production verification](final-production-verification-2026-09-15.json).
The more controlled [dry original-MIDI replay](dry-end-to-end-2026-09-15.md)
supports the zero-resonance endpoint conditional on the reconstructed cutoff
trajectory, while retaining the counterexample from the nominal one-second
envelope.
