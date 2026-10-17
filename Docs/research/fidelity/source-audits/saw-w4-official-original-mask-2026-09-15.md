# W4 official presets: fixed original-only spectral bins

**Air Lead improves on unchanged original bins, while Brassy, So Juno and Vangelead regress.** The Air mean log improvement is smaller than in the legacy pair-union metric. This diagnostic was requested after the frozen ten-case comparison; it changes no coefficient, input, timing, gain or prior result.

## Fixed policy and controls

The original-only activity mask uses hardware magnitudes at least −60 dB relative to the peak of that hardware STFT. Both models use exactly those bins and the same −80 dB magnitude floor. Stereo channels remain separate; no downmix cancels energy. Periodic-Hann STFT windows are 512/1024/2048/8192 samples with one-quarter-window hops, no padding, and no frame crossing the saved evaluated interval. Original sample supports, production lag and current-production prefix scalar are copied unchanged from the main run. No gain sensitivity or extra fit is introduced here.

Every saved legacy union count, mean, P95, unmasked spectral convergence and frame count reproduced: **400 values across all ten cases and four resolutions**. The same original-mask bin count and packed-mask hash apply to production and W4. All five non-Saw controls remain exact.

The original-only mask deliberately omits candidate-only artifacts. The legacy union mask remains useful for those artifacts, and both policies must be read together. Neither is a perceptual threshold or a phase-invariance proof; reconstructed performance and recording-specific patch uncertainty remain.

## Complete fixed-bin comparison

Lower log error is better. The aggregate preserves the original 512/2048/8192 resolution mean. The four deltas and bin counts are ordered **512 / 1024 / 2048 / 8192**. Each bin includes frequency, time and channel. All resolution-specific means, P95 values, deltas, mask hashes, absolute thresholds, frame bounds and legacy counts remain in the JSON.

| Case | Original-only mean dB, production → W4 | Aggregate delta dB | Four resolution deltas dB | Fixed original-bin counts |
|---|---:|---:|---|---|
| air-lead-1 | 10.548207 → 10.411509 | -0.136698 | -0.2310/-0.1979/-0.1192/-0.0599 | 61586/51034/38248/26577 |
| brassy-ld-1 | 7.887620 → 8.279116 | +0.391495 | +0.4518/+0.3825/+0.4289/+0.2937 | 59658/41080/25207/17529 |
| club-bass | 8.501677 → 8.501677 | +0.000000 | +0.0000/+0.0000/+0.0000/+0.0000 | 12553/11875/10323/7070 |
| cotton-wool | 7.639397 → 7.639397 | +0.000000 | +0.0000/+0.0000/+0.0000/+0.0000 | 108397/97663/88887/67524 |
| dist-bs-1 | 9.734985 → 9.734714 | -0.000272 | +0.0008/-0.0017/-0.0014/-0.0003 | 10962/14271/15589/9838 |
| moogie-1 | 7.299880 → 7.299880 | +0.000000 | +0.0000/+0.0000/+0.0000/+0.0000 | 28877/29976/28926/23693 |
| pedal-bs-1 | 9.710070 → 9.710070 | +0.000000 | +0.0000/+0.0000/+0.0000/+0.0000 | 4146/2229/1716/1083 |
| so-juno-1 | 9.870765 → 10.422462 | +0.551697 | +0.3863/+0.6355/+0.7156/+0.5532 | 35133/37643/35000/22158 |
| supa-juce-1 | 7.078923 → 7.078923 | +0.000000 | +0.0000/+0.0000/+0.0000/+0.0000 | 91658/78306/65178/49169 |
| vangelead | 11.875631 → 12.504661 | +0.629030 | +0.9994/+0.6706/+0.4916/+0.3960 | 255261/182009/129127/61785 |

Across all ten cases, original-only mean error rises **9.014715 → 9.158241 dB** (+0.143525 dB); among the five active-Saw cases, it rises **9.983442 → 10.270492 dB** (+0.287051 dB). Those equal-case summaries retain the unchanged controls and all regressions. The old union aggregate remains 12.794097 → 12.788733 dB and is not overwritten.

Air improves at all four resolutions with both masks, but its original-only aggregate improvement is −0.136698 dB versus −1.110594 dB with the pair-union mask. Brassy's original-only regression is +0.391495 dB versus +0.007693 dB with the union mask. So Juno and Vangelead also regress at every resolution on original-only mean error. Dist changes are tiny and vary in sign by resolution; no audible claim follows.

This supports the main report's mixed-result conclusion and strengthens the need to retain the quieter-spectrum tradeoffs. It supplies no new candidate selection, shipping change or whole-instrument equivalence claim.

## Reproduction and receipts

```sh
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 python3 Tools/assess_saw_w4_official_original_mask.py \
  --comparison build-fidelity/saw-w4-official-comparison/run-01/results.json \
  --output build-fidelity/saw-w4-official-comparison/new-original-mask
```

The tool verifies the frozen full comparison SHA and its hardware/production/candidate audio hashes before measuring. It does not render or modify original outputs. See the [main comparison](saw-w4-official-comparison-2026-09-15.md) and [complete diagnostic JSON](saw-w4-official-original-mask-2026-09-15.json).

- Tool SHA: `824041a2f337a7c7ef9f6e08ee5bd105b94eba126fcc8695908b4393c0fdbe61`.
- Full diagnostic SHA: `232cfa31fe7da169a89d10a476f81f49380c42a67399c4c49b727f0617b7072b`.
- Compact diagnostic SHA: `961a7130009ef4b2e8126fb0c235d7fc204542d436017b8dfcae751a22deb205`.
