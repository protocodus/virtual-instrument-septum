# Independent review of the reverb return candidates

**No implementation or benchmark-split bug found.** The width and equal-channel gain experiments change only the final wet reverb return. All ten scale-1 renders in each experiment are byte-identical to the pinned production renders. This verifies candidate isolation, not hardware accuracy or promotion of either family.

[Audit tool](../../../Tools/audit_reverb_width_candidate_isolation.py), [width data](reverb-width-candidate-isolation-2026-09-15.json), [gain data](reverb-gain-candidate-isolation-2026-09-15.json).

## Source and benchmark verification

The independent audit checks the experiment's copied script, source manifest, and every frozen DSP/helper file against commit `b0f6c03`. It compares each variant against the exact expected engine text and verifies that the DSP files copied into the compiled build equal that variant. Generated calibration profiles enable no sections, change no fields and apply no reference-rate override.

- **Width W=0.5/0.25:** compute wet mid/side after the reverb high-cut state updates, then scale only wet side.
- **Gain G=0.5/0.25:** multiply both wet return channels equally at the same location.
- **Scale 1:** retains the original arithmetic; no redundant mid/side conversion is inserted.
- No feedback, diffuser, damping, high-cut state, oscillator, filter, envelope, delay or patch code changes. The transformed local return variables are not fed back into the reverb or delay state.

Original patch, reconstructed MIDI and production WAV hashes match the ten-case production guard. Candidate WAV and renderer hashes match the recorded outputs. All ten scale-1 WAVs in both experiments match production bytes independently of the experiment's success flags. The reconstructed files contain no CC10 pan events, and the engine's final part pan defaults to center.

For every case, the audit recomputes the first-quarter sample boundary and the exact gain from that prefix, using the production lag. Both calibration supports stop at or before the boundary; both evaluation supports begin at or after it. The lag is bounded by ±2205 samples at 44.1 kHz. The evaluator receives only those cropped evaluation arrays and uses STFT `boundary=None, padded=False`, so no spectral window crosses the calibration boundary. The separate fixed-production-gain sensitivity is present in the experiment; the primary per-render gain can change the final mid level even when the DSP width transform preserves wet mid.

## Actual-route controls and rendered output

A small C++ control uses the pinned **actual `AnalogOutput` implementation and verbatim `outputLimit` function**, including the float wet/dry mix, common master slew, final pan law and final float conversion. It supplies a synthetic wet return and tests width and gain at three scales, with centered wet-only audio, mixed dry/wet audio, off-center pan, intentional limiting and pure mid. This tests the output route without rerendering any full preset or inventing a reverb network.

| Check | Measured result |
|---|---:|
| Centered small-signal width: maximum final mid deviation | 1.30e−8 |
| Centered small-signal width: maximum side error against W×baseline | 8.38e−9 |
| Width W=0.5 wet-only side RMS ratio | 0.4999999996 |
| Equal-channel gain: isolated small-signal wet mid/side scaling | Exact at G=0.5/0.25 in stored float output |
| Pure-mid width control | Byte-identical output across widths |
| Maximum raw mid change across ten width renders | 4.47e−8 |
| Maximum affine output error across either full experiment | 8.94e−8 |
| Maximum raw candidate peak across either experiment | 0.73555; below the 0.9 limiter knee |

The affine check is `C(0.25) = 1.5*C(0.5) - 0.5*C(1)` before benchmark gain fitting. It tests whether the three full-engine outputs differ by the intended linear return contribution through the shared output circuit. Both width and gain pass within float precision. As expected, equal-channel gain changes wet mid; the largest raw total-mid change across those candidates is 0.16402.

### Necessary scope qualifications

“Mid unchanged” applies to the **wet width transform**. It is not universal final-output invariance:

- Off-center final pan has unequal left/right gains and mixes mid with side. The width control deliberately demonstrates a 0.0141 maximum mid change in this condition.
- The final per-channel limiter is nonlinear. The deliberate overload control changes mid and breaks the affine relation, as expected. It remains inactive in the actual candidate renders.
- Dry/delay stereo content is unchanged by either candidate. Consequently total-output side does not generally scale by W, and total-output mid/side does not generally scale by G. The mixed-input controls demonstrate this.
- Equal-channel gain preserves the stereo relationship of isolated, unclipped wet audio. Changing its amount relative to dry or delay audio can still change the stereo statistics of the full mix.
- Benchmark gain fitting is a later global scaling operation; raw DSP invariants must be checked before it.

These are expected route consequences, not discovered defects. The candidate-isolation checks do not resolve the contrary late-tail hardware evidence, unknown performance MIDI or capture processing, and do not establish an optimal hardware width or return gain.

## Reproduce

After the two frozen full-engine experiments have produced their results:

```sh
python3 Tools/audit_reverb_width_candidate_isolation.py \
  --experiment build-fidelity/hardware-benchmark/reverb-width-candidates/run-01 \
  --output build-fidelity/hardware-benchmark/reverb-width-candidates/isolation-replay
python3 Tools/audit_reverb_width_candidate_isolation.py \
  --experiment build-fidelity/hardware-benchmark/reverb-gain-candidates/run-01 \
  --output build-fidelity/hardware-benchmark/reverb-gain-candidates/isolation-replay
```

Each output directory must be new. The command compiles the bounded route control, verifies the existing source/render artifacts and writes `results.json`. Tracked width/gain data are exact copies from `isolation-audit-v2` and `isolation-audit-v1`, respectively. The copied experiment scripts are verified separately, so later edits to the working comparison tool do not silently change the audited run.
