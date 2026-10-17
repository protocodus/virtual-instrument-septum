# One frozen full-engine W4 candidate: ten official presets

**Air Lead's spectral match improves; the wider result is mixed.** All ten native controls reproduce current production byte for byte, and all five presets without an active classic Saw remain byte-identical with W4 enabled. No coefficient, phase, event, patch or model choice was changed after these comparisons.

## Exact scope

The one 32-coefficient vector was frozen by the separate original-MIDI dry-engine training experiment before validation: `build-fidelity/saw-w4-engine/hardware-fit-01/candidate.json`, SHA-256 `3ef847bad8c0cc9990fd01b40a0bd9a8ba09374153a166c1f6b910dea82b6e91`. This run uses `build-fidelity/saw-w4-engine/build-03`, based on shipping revision `545b3d37d9cc1f80bf39bc5d0bf49c0cced1d9f6`, at canonical phase 0 and unit ramp. Its build-manifest SHA is `b2fcaae46b02388799655688e32211259c09ca500aa2783114e3ec59773e3360`.

The [prepared protocol](saw-w4-official-protocol-2026-09-15.json) retains the previously frozen [ten-case inventory](saw-w4-official-inputs-2026-09-15.json). Every published SysEx byte, reconstructed MIDI event, full render duration, master level 100, channel 1, 44.1 kHz rate, 2 s tail and stored-patch tempo policy was preserved. Both native and W4 receipts were compared with current production's complete input/settings/event records. These public recordings have no verified original performance MIDI or recording-specific patch dump; the same-name stored patches and reconstructed performances retain that uncertainty.

Timing and evaluation samples are the saved production-only first-quarter policy. The current-half-return production scalar was independently reproduced from that exact prefix and shared by baseline and W4. Candidate-prefix gain is a separate sensitivity only. No new delay, waveform phase, frequency, EQ or time warp was fitted. Existing 512/2048/8192-sample spectral means are preserved, with 1024-sample results additionally retained; all four resolutions, 10/50 ms RMS, complete stereo, Mid and Side metrics are in the JSON. STFT frames stay within the frozen evaluation slice.

## All ten outcomes

Lower error is better. SC is the unchanged 512/2048/8192 spectral-convergence mean. Log error uses the inherited pair-union activity mask; it is a descriptive metric, not a perceptual threshold. RMS P95 is the larger 95th-percentile absolute envelope error from 10/50 ms windows. Arrows show **current production → W4**, using the shared production gain.

| Preset | SC | Log-spectrum error dB | RMS P95 dB | W4 byte identity |
|---|---:|---:|---:|---|
| Air Lead 1 | 0.852247→0.813642 | 22.900→21.789 | 4.290→4.346 | Changed Saw |
| Brassy Ld 1 | 0.606242→0.603477 | 12.120→12.127 | 8.992→9.053 | Changed Saw |
| Club Bass | 0.424456→0.424456 | 14.604→14.604 | 10.020→10.020 | Exact |
| Cotton Wool | 0.702993→0.702993 | 12.326→12.326 | 9.114→9.114 | Exact |
| Dist Bs 1 | 0.319719→0.319725 | 10.416→10.417 | 24.824→24.824 | Changed Saw |
| Moogie 1 | 0.359177→0.359177 | 7.828→7.828 | 4.378→4.378 | Exact |
| Pedal Bs 1 | 0.557264→0.557264 | 17.934→17.934 | 18.916→18.916 | Exact |
| So Juno 1 | 0.417137→0.417323 | 10.044→10.549 | 36.345→36.345 | Changed Saw |
| Supa Juce 1 | 0.457252→0.457252 | 7.837→7.837 | 5.335→5.335 | Exact |
| Vangelead | 0.692700→0.691789 | 11.932→12.474 | 7.340→7.320 | Changed Saw |

Equal-case means across all ten are SC 0.538919→0.534710, log 12.79410→12.78873 dB and RMS 12.95538→12.96507 dB. Across only the five active-Saw cases, SC 0.577609→0.569191 and log 13.48220→13.47147 dB improve modestly while RMS 16.35836→16.37776 dB worsens. These descriptive means do not erase the contrary cases or measure an audible percentage.

## Useful improvements and retained regressions

- **Air Lead:** every STFT resolution improves: 512 samples 0.800537→0.760405, 1024 samples 0.814261→0.774554, 2048 samples 0.840395→0.801328 and 8192 samples 0.915810→0.879195. Log errors improve by about 1.00–1.29 dB across these resolutions. The 50 ms envelope P95 nevertheless worsens 3.006→3.391 dB; Side-envelope P95 rises 6.033→6.587 dB. The complete shape is not uniformly closer.
- **Brassy:** small spectral-energy improvement coexists with small log/envelope regressions. Its Side log error rises 9.212→9.290 dB, although Side SC improves 0.857268→0.853457.
- **So Juno:** tiny energy-distance change hides a larger log-spectrum regression: 10.044→10.549 dB, with positive log-error deltas at every resolution. Mid log error rises 9.438→9.973 dB. Active-bin counts remain available; no claim of a phase-invariant or perceptually calibrated 0.5 dB mismatch follows.
- **Vangelead:** fixed-gain SC improves slightly while log error worsens by 0.542 dB. Candidate-prefix gain changes 2.03380→2.10359 and reverses the SC comparison to 0.692700→0.706406. This sensitivity is retained, not used to pick a favorable gain convention.
- **Dist:** changes are extremely small but remain recorded: SC +0.000006, log error about +0.00150 dB and envelope P95 about +0.000018 dB. They are not claimed audible.

Air's candidate-prefix gain sensitivity still improves SC to 0.822914, but worsens its envelope P95 to 4.440 dB. Brassy's corresponding SC is 0.604773. All candidate-prefix gains and every stereo/Mid/Side measurement remain in the complete receipt.

## Fixed original-bin sensitivity

A separately requested [original-only mask diagnostic](saw-w4-official-original-mask-2026-09-15.md) retains the same timing, gain, floor and four STFT resolutions, and reproduces all 400 checked legacy values before measuring. It does not overwrite any result above. Air improves on the fixed bins too, but its aggregate log improvement shrinks from −1.111 dB to −0.137 dB. Brassy regresses by +0.391 dB, So Juno by +0.552 dB and Vangelead by +0.629 dB. Across all ten cases the original-only mean rises 9.014715 → 9.158241 dB.

These results show that the quiet-spectrum tradeoffs survive a constant denominator. Original-only masks omit candidate-only artifacts, so both mask policies remain relevant; neither defines a perceptual threshold.

## Harmonic coverage and engineering controls

The inherited Moogie harmonic protocol provides a useful **unchanged-waveform control**: three notes, offsets +.10/.18/.26 s, 80 ms windows, −20/0/+20 ms timing sensitivity and 96 quadrature/ramp harmonics. Hardware and production frequencies are copied from the prior cutoff-taper receipt, with its separate nominal-frequency sensitivity; no frequency is re-estimated. It uses the existing +93-sample renderer convention, distinct from the whole-excerpt lag. Original harmonic values/masks reproduce within 1e−9 dB. Both sets of 27 candidate windows pass the existing 1% residual guard and are exactly identical to production's harmonic results.

No new harmonic acceptance mask was invented for the remaining wet mixed-oscillator excerpts. Air Lead's prior opening-only probe cannot provide independent later-note harmonic validation; the original-MIDI dry corpus supplies the substantive Saw harmonic checks separately. These limitations are explicit in each case record.

All ten native-disabled controls ran before any enabled W4 render and matched both WAV hashes and decoded PCM. The five no-active-Saw W4 controls also matched WAV hashes exactly. Every W4 output is finite, below full-scale, and ends with zero active voices. Maximum output peak is 0.73555. Recorded filter-state/output limiter call counts are zero for every native/W4 render. The five active-Saw cases reach measured corrected-source peaks 1.409–1.428; the native source-peak counter is not populated and must not be read as a silent oscillator. No tested preset invokes a Saw hard-sync reset, so this corpus does not validate that mode.

## Listening and reproduction

The local listening page is `build-fidelity/saw-w4-official-comparison/run-01/index.html`. Every case contains original, production and W4 listening WAVs with identical frames, the primary fixed gain, and one common attenuation. They cover the full aligned available excerpt and identify the evaluated range. Raw engine/reference WAVs remain untouched. This page is a simple set of audio players; synchronized transport and human listening preference were not verified in this task.

```sh
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 python3 Tools/compare_saw_w4_official_presets.py prepare \
  --build build-fidelity/saw-w4-engine/build-03 \
  --output build-fidelity/saw-w4-official-comparison/new-prepared

OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 python3 Tools/compare_saw_w4_official_presets.py compare \
  --prepared build-fidelity/saw-w4-official-comparison/new-prepared \
  --selection build-fidelity/saw-w4-engine/hardware-fit-01/candidate.json \
  --output build-fidelity/saw-w4-official-comparison/new-comparison
```

The commands consume the hash-pinned cached input/build/selection bundles identified in the receipts. The tracked builder can recreate an isolated build; no firmware or fresh online media are required. Complete numeric outcomes, input and render settings, selected coefficients, source/build/config/WAV hashes, state diagnostics and listening export hashes are retained in the [compact comparison JSON](saw-w4-official-comparison-2026-09-15.json), which was checked equal to the full parsed run results.

- Tool SHA: `7faf718490592e939d8dda5ac074f5e008ac5eed81ae84418412ac7298af217c`.
- Prepared protocol SHA: `6a6ddc594a00220e82685f106670f3e1801e5a267d9a3323e92112acab199126`.
- Compact receipt SHA: `699e4d2698f4850173955de66fab0ccb092b58da283376bcf878462ae0d34f29`.
- Full run results SHA: `db2703598678513b3c0a26618d62605f199d722477d51f5c51bfd3908bbf8505`.

This is modest, Air-led evidence of spectral improvement alongside retained regressions. It establishes neither uniform preset improvement nor whole-instrument equivalence. No shipping DSP edit or promotion was made by this comparison task.
