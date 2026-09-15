# Ambient SQR: first-key articulation follow-up

**Holding only the first reconstructed key until the next onset does not remove the reverb-level counterexample.** Half return still improves spectral convergence while worsening envelope and log-spectrum errors. No preferred MIDI reconstruction is selected, and no additional DSP change follows from this experiment.

The [source-only articulation audit](ambient-first-note-articulation-2026-09-15.md) found persistent but unresolved harmonics through 0.40 s. Detuned-oscillator beating, envelope motion and coherent effects prevent identifying the original key release. It motivates a wider articulation sensitivity, not a recovered note-off.

Commit `8265b54` freezes the separate `ambient-sqr-first-held-until-next` JSON/MIDI before rendering it. Its only performance change from canonical nominal velocity 100 is the first D5 key-up, **0.200→0.418 s**. The writer sends note-off before the coincident E5 note-on. Other notes, velocity, original SysEx, source start 0, calibration end 0.405 and excerpt end 0.775 remain unchanged. The hypothesis was proposed **after the earlier candidate outcomes**, and the evaluator's `--exploratory` flag records that status. It is not another independent validation recording.

## Later evaluation

One previous-return prefix lag and gain are shared across all three return models. The new lag is −48.685 ms, close to the fixed −50 ms bound; the prefix gain is 4.77684, compared with 7.46791 for the earlier nominal gate. That scalar difference itself illustrates the performance uncertainty. No later gain or alignment is fitted.

| First key held to next onset | Previous return | Half return | Quarter return |
|---|---:|---:|---:|
| Spectral convergence | 0.68276 | 0.61580 | 0.60939 |
| Log-spectrum error, dB | 14.003 | 14.535 | 15.294 |
| Envelope P95 error, dB | 4.892 | 8.192 | 11.315 |
| Stereo side-fraction error | 0.39435 | 0.24074 | 0.16026 |
| Stereo balance error, dB | 0.2427 | 0.5321 | 0.6089 |

The half-return envelope regression remains approximately **3.30 dB**. Narrowing the first-gate uncertainty to the original 0.16–0.24 s bracket therefore was not necessary to produce the counterexample. Conversely, this one extension does not exclude other performance, relative oscillator-phase or layer-mix explanations. Absolute scores across gate scenarios are not used to choose a transcription.

The [durable receipt](ambient-first-note-followup-2026-09-15.json) preserves the frozen protocol, earlier nominal and new results, all input/audio hashes, and the separately labeled reference-only activity-mask sensitivity. Three new renders are finite, unclipped, finish with zero active voices and report no ignored events or degraded replay. They use the same frozen gain family already integrated into shipping DSP.

## Reproduce

```sh
OPENBLAS_NUM_THREADS=1 python3 Tools/evaluate_reverb_validation_cases.py \
  --exploratory \
  --case Docs/fidelity/reconstructions/reverb-validation/ambient-sqr-first-held-until-next.json \
  --sources build-fidelity/hardware-benchmark/sources \
  --models build-fidelity/hardware-benchmark/reverb-gain-candidates/run-01 \
  --output build-fidelity/hardware-benchmark/reverb-articulation-followup/reproduction
```

All original nine Ambient scenarios and their [known regressions](reverb-new-preset-validation-2026-09-15.md) remain unchanged. No output-equivalence claim is supported.
