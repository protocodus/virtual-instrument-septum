# W4 production integration: complete raw replay

**The final production renderer, including the Sync-mode guard, reproduces all twelve frozen candidate WAVs byte for byte.** Both original-MIDI dry filter slopes and all ten unchanged official-preset reconstructions pass. Across **4,966,322 stereo frames** there are zero changed samples, zero maximum/RMS residual, and zero float32 ULP difference. Every complete two-second tail is included. No numerical tolerance was needed.

## Preserved inputs and policy

The [input inventory](saw-w4-production-integration-inputs-2026-09-15.json) was frozen before production replay. Each source's complete SysEx and MIDI file was copied byte-identically; candidate config JSON/native vector, selected 32 coefficients, canonical phase zero and unit ramp were verified. The dry candidate comes from `candidate-dry-01`; the ten official candidates come from `saw-w4-official-comparison/run-01`.

All settings and replay event/metadata records reproduce: 44.1 kHz, master level 100, channel 1, stored-patch tempo policy, arpeggiator-off semantics and two-second tail. There is no audio gain, alignment, normalization, crop or nuisance fit. Each dry performance retains all 124 note-ons and 124 note-offs. Its original MIDI's single FF20 channel-prefix metadata omission is retained identically; no other event is omitted. Official cases omit no events.

Comparison is against the selected full-engine candidate, **not against hardware recordings**. The separate dry and official hardware reports retain their improvements, mismatches and uncertainty. Byte identity means those existing candidate measurements also describe these production outputs.

## All twelve results

| Input | Stereo frames | Absolute output peak | Complete WAV/PCM | Role |
|---|---:|---:|---|---|
| Dry LP12 | 1,386,394 | 0.213373 | Exact | Selected Saw candidate |
| Dry LP24 | 1,386,394 | 0.231865 | Exact | Selected Saw candidate |
| air-lead-1 | 240,345 | 0.256107 | Exact | Selected Saw candidate |
| brassy-ld-1 | 221,823 | 0.269957 | Exact | Selected Saw candidate |
| club-bass | 231,525 | 0.231546 | Exact | Exact non-Saw control |
| cotton-wool | 308,700 | 0.190178 | Exact | Exact non-Saw control |
| dist-bs-1 | 143,766 | 0.570786 | Exact | Selected Saw candidate |
| moogie-1 | 251,370 | 0.735546 | Exact | Exact non-Saw control |
| pedal-bs-1 | 156,555 | 0.215299 | Exact | Exact non-Saw control |
| so-juno-1 | 156,555 | 0.239537 | Exact | Selected Saw candidate |
| supa-juce-1 | 167,580 | 0.509688 | Exact | Exact non-Saw control |
| vangelead | 315,315 | 0.334932 | Exact | Selected Saw candidate |

All output samples are finite and below full scale. Every replay ends with zero active voices and all queued MIDI events already processed. The five non-Saw controls are also byte-identical to their pre-W4 production baselines; the guard verifies that baseline-to-candidate identity before replay. Tail coverage is measured from the original MIDI end sample through the final frame, with all 88,200 tail frames per case compared.

Before rendering, the tool froze maximum absolute residual ≤2⁻²³, RMS residual ≤10⁻⁸ full scale, and residual/reference RMS ≤10⁻⁶ as a fallback for arithmetic-order changes. The five non-Saw controls still required exact bytes. All twelve instead achieve exact bytes, so the fallback does not influence acceptance. Identity and planted one-ULP controls verified the difference calculator and first/last changed-frame reporting before replay.

## Initial pass and independent Sync regression

The [initial run-01 receipt](saw-w4-production-integration-initial-replay-2026-09-15.json) also passed all twelve exact comparisons. A separate full test suite then caught a hard-sync identity regression: the fitted kernel could continue after a forced oscillator reset. That mode is absent from these twelve inputs; the [raw preset coverage receipt](saw-w4-integration-sync-coverage-2026-09-15.json) verifies that every active tone uses Mix raw 0, with no Sync raw 1 or Ring raw 2.

The implementation owner applied a bounded guard: OSC1 Saw uses the prior waveform throughout Sync mode, preserving its reset behavior; ordinary mixing retains the selected W4 correction. The root rebuilt production, and this task repeated the **same frozen inventory as run-02**. All twelve final WAVs match both the selected candidate and initial run-01 byte for byte. No patch, coefficient, parameter, gate, gain or tolerance was changed for the repeated comparison. The isolated source/test review covers Sync itself; these twelve musical examples do not.

Initial raw run-01 SHA: `abfa12e5b5c859712772bab63568ecbb0ef49f42aad19c5c6e6ee3f5304fbccb`. Final raw run-02 is `build-fidelity/saw-w4-production-integration/run-02/results.json` and is the source of the main receipt below. The initial numerical success is preserved without presenting it as sufficient coverage of untested modes.

## Production provenance

The root-built native binary is `build-fidelity/SeptumRenderMidi`, SHA-256 `7e0a8a67038f00bccb671e838b31fc851e018c82d22482265192826f39a094df`. This is the actual production target, with no experimental runtime config; the replay explicitly removes the isolated prototype's configuration/statistics environment keys.

Git HEAD at replay was `545b3d37d9cc1f80bf39bc5d0bf49c0cced1d9f6` plus the then-uncommitted integrated Saw source and focused test registration. The receipt pins every current `Source/DSP` file, native renderer/wrapper and CMake file before and after replay. In particular:

- `Source/DSP/ClassicSaw.h`: `9e94ee0530970a8cb7848f1d675cc833b363220d6813057fc682ce8c2f73102b`.
- `Source/DSP/SeptumEngine.cpp`: `e371d22052c4732cdefe249326acdc5bf9239a6aad2a4a09db313664ba095d5b`.

These source/binary/wrapper hashes did not change during replay. Compilation and focused-test evidence belong to the separate root build/test receipts; this tool does not build or alter production sources.

## Reproduction

Use the reviewed production build corresponding to the captured source hashes:

```sh
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 python3 Tools/verify_saw_w4_production_integration.py prepare \
  --dry-root build-fidelity/saw-w4-engine/candidate-dry-01 \
  --official-run build-fidelity/saw-w4-official-comparison/run-01 \
  --output build-fidelity/saw-w4-production-integration/new-prepared

OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 python3 Tools/verify_saw_w4_production_integration.py replay \
  --inventory build-fidelity/saw-w4-production-integration/new-prepared/input-inventory.json \
  --renderer build-fidelity/SeptumRenderMidi \
  --output build-fidelity/saw-w4-production-integration/new-run
```

The [complete compact receipt](saw-w4-production-integration-2026-09-15.json) is identical to the parsed full run JSON. All candidate/production WAV and receipt hashes were independently rechecked after completion. Raw WAVs remain in the ignored run directory; no Source edits or commits were made by this task.

- Tool SHA: `8bed664455c24e224eccb40482dbe6e6b72d7497088d6d8c39519d20b9527431`.
- Prepared inventory SHA: `d9f15916e5fb82b72a899ff546cca26516e190f4e013e3b3885beb853af3f6b7`.
- Full result SHA: `a96632cc2912a941ed2201835a035ecae9b4754d2627d5b3dd3e970278720ca3`.
- Compact result SHA: `ce510feb3c66d37e1a854dd8c691850ea4241066537d942ee26ea65bc5112aa9`.
