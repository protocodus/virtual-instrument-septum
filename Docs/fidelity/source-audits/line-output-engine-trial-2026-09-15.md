# Frozen full-engine line-output trial

The omitted SH-201 line-output network was placed in a copied production
engine and rendered against the same twelve public-recording inputs. This is a
conditional, normalized **linear** circuit trial, not a preamp distortion model
and not a shipping change.

## Frozen setup

- Source revision: `4b9f1bfc609910154066708d2cf03e119c7d7b71`.
- Two stereo line jacks inserted, mute off, nominal 10 kΩ pot and 10 kΩ load.
- Three electrical wiper fractions: 0.1, 0.5 and 1.0. These are circuit
  fractions, not asserted front-panel knob positions.
- Two rational sections model the loaded 22 µF master coupling/wiper network
  and the 22 µF line-output coupling, 100 kΩ shunt, 680+330 Ω series path and
  470 pF jack capacitance. The ideal ×2 line gain and fixed resistive losses are
  normalized out, as in the independent circuit calculation.
- The sections run after the existing Sallen–Key stage inside the existing 8×
  lambda. No new oversampling, latency, oscillator, filter, effect, patch,
  MIDI, gain fit or candidate selection is introduced.
- Every candidate reuses the original public patch/MIDI bytes, saved gain and
  lag. The disabled copied engine must be byte-identical to the production WAV.

The [frozen protocol](../../../build-fidelity/line-output-assessment/prepared-01/protocol.json),
[copied-engine manifest](../../../build-fidelity/line-output-engine/run-01/manifest.json)
and [independent placement review](line-output-experiment-independent-review-2026-09-15.json)
retain source pins, commands and output hashes. The assessment reuses the
original-only spectral masks, RMS windows, K-weighted blocks and transient
landmarks from the earlier characterization. Candidate-specific gain rematching
was forbidden.

## Implementation controls

The compiled line sections agree with the independent physical nodal equations
to a maximum absolute error of `3.02e−13` at the declared frequencies. A
21-point compiled probe has maximum magnitude error `0.000331 dB`, phase error
`0.0483°`, and processor-versus-coefficient error `2.35e−10`. Disabled output
has zero sample mismatches; reset has zero mismatches; the two channels have
independent state; and the 8× callback count remains 800 per 100 host samples.
All 12 disabled renders preserve their production WAV hashes, settings, MIDI,
patch bytes and 93-sample latency.

## Results against the original recordings

The assessment retained all three variants and made no selection. The table
shows the full-volume fraction 1.0 case; the 0.1 and 0.5 cases are retained in
the receipt and have the same conclusion.

| Take | Crest error before → after | Crest change from production | K-level change from production | Interpretation |
| --- | ---: | ---: | ---: | --- |
| Moogie 1 | −4.194 → −4.185 dB | +0.010 dB | −0.004 dB | Does not restore the missing crest or filter body. |
| Dist Bs 1 | −3.806 → −3.134 dB | +0.672 dB | −0.005 dB | Moves in the lively direction, but leaves most of the deficit and widens the measured envelope mismatch. |
| Cotton Wool | −1.585 → −1.652 dB | −0.067 dB | −0.001 dB | Moves away from the original crest. |
| Vangelead | −0.026 → +0.051 dB | +0.077 dB | −0.001 dB | Overshoots an already close crest; envelope correlation is unchanged. |

Across all twelve takes, crest changes range from −0.131 to +0.672 dB at
fraction 1.0. The largest waveform residual is on Dist Bass (22.6% RMS), but
that residual is largely a transient/sub-audio consequence of the high-pass
coupling and does not identify a hardware match. The K-level shifts are at most
about 0.01 dB outside the same Dist transient case; this is not a hidden loudness
explanation.

The result is consistent with the small-signal calculation: the physical
network can alter phase and isolated transient peaks, but it does not supply the
several decibels of common “power” missing from the recordings. Because the
effects are preset-dependent and include counterexamples, the trial does not
justify promoting any fraction or adding a nonlinear analog preamp model.

## Reproduction

The 27 MB full assessment receipt remains in the ignored build directory. The
compact reproducible receipt is
[line-output-engine-trial-2026-09-15.json](line-output-engine-trial-2026-09-15.json)
and contains every take/variant summary, source hashes, frozen protocol pins and
the full-results hash.

```sh
python3 Tools/build_line_output_experiment.py \
  --output build-fidelity/line-output-engine/new-run
python3 Tools/assess_line_output_engine.py prepare \
  --baseline build-fidelity/output-stage-characterization/run-03/results.json \
  --output build-fidelity/line-output-assessment/new-prepared
python3 Tools/assess_line_output_engine.py compare \
  --protocol build-fidelity/line-output-assessment/new-prepared/protocol.json \
  --manifest build-fidelity/line-output-engine/new-run/manifest.json \
  --output build-fidelity/line-output-assessment/new-run
```

No production `Source/` file or preset was changed.
