# Prospective reverb validation: independent code review

**No immediate blocker was found in the reviewed evaluator.** This review and
its checks were saved before inspecting any new-case candidate scores.
Neither the evaluator nor shipping DSP was edited.

Reviewed [evaluate_reverb_validation_cases.py](../../../Tools/evaluate_reverb_validation_cases.py)
and the render, MIDI, build and measurement helpers. Exact source hashes and
the frozen Ambient SQR/Class A case hashes are in the [receipt](reverb-validation-independent-review-2026-09-15.json).

## Verified behavior

- Original MP3/bank/member/preset identities are checked against the catalog
  and the source-only case pins. Render receipts are tied to the expected
  renderer, MIDI, SysEx and output hashes.
- MIDI is frozen before rendering and checked against a canonical sibling
  when present. Generated render inputs must match these frozen bytes.
- Lag and gain use only the baseline prefix. The primary comparisons share
  that lag, gain and evaluation support across every candidate. Separately
  fitted candidate-prefix gains remain labelled sensitivities.
- Calibration and evaluation supports are disjoint in **both** signals for
  either lag sign. STFT frames cannot extend before their evaluation slice.
- Listening applies the same primary transformations and one additional
  common scalar. That listening scalar does not enter the metrics.
- Both canonical cases and every Class A diagnostic retain at least 250 ms
  at the worst allowed positive or negative 50 ms lag.

Five synthetic checks planted delays of −50, −37, 0, +37 and +50 samples at
1 kHz, with gain 1.3. The helper recovered each delay and reciprocal gain.
Replacing **all later candidate samples** with large independent noise left
every prefix transformation unchanged. Explicit index checks confirmed no
calibration/evaluation overlap. The complete runnable fixture is embedded in
the JSON receipt; the evaluator also passed syntax compilation.

## Qualifications and missing checks

1. **Activity masks differ by candidate.** The measurement helper uses
   `max(reference, candidate)` separately for each pair. Log-spectrum and
   envelope statistics therefore need not use identical active bins, despite
   common time coverage. Unmasked spectral convergence has common support.
   If masked metrics affect a promotion decision, retain a common-union-mask
   sensitivity rather than treating their ranking as identical-bin evidence.
2. **Source anchoring relies on the prior build audit.** This evaluator checks
   the recorded frozen files/manifests/binaries, but does not independently
   re-establish every source byte against Git `b0f6c03` or validate the prior
   `source-manifest.json` hash. The parent separately reported that gain-1's
   frozen Source equals current Source. Final-run provenance verification is
   still a separate step.
3. **Embedded helper metadata has a different scope.** The auxiliary baseline
   comparison includes whole-excerpt listening gains and current-worktree DSP
   hashes. Use the evaluator's outer prefix protocol and build identities
   for the prospective comparisons.
4. **Generic preflight bounds are looser than the helpers require.** Other
   cases could pass the generic 200 ms remainder check and then fail the
   measurement's 250 ms requirement after lag trimming. The two current
   cases pass. Unidentifiable or boundary alignment is recorded but does not
   automatically prevent scoring; inspect those flags before interpretation.

These checks establish protocol behavior, not accurate reconstructed gates,
original patch/controller state, hardware equivalence or a reverb-gain value.
