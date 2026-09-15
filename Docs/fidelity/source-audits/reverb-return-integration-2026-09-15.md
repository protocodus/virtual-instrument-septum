# Half reverb return: shipping DSP integration verification

**The shipping `reverbWetReturn` change from 0.8 to 0.4 reproduces every tested half-return candidate exactly.** The complete DSP test suite passes. This verifies integration of the already measured candidate; it does not establish hardware equivalence or remove its known damped-preset regressions.

## Source and build

All current `Source/DSP` files and `Tools/RenderMidi.cpp` were checked against frozen candidate baseline `b0f6c03`. The only changed file is `SeptumEngine.h`. Removing comments/whitespace and restoring the single return constant from 0.4 to 0.8 makes that header identical to the baseline. No oscillator, envelope, filter, delay, reverb feedback, width, damping, send law or patch change is part of this integration.

`cmake --build build-fidelity --parallel 2` succeeded with Release, tools and testing enabled, plugin disabled, and sanitizers disabled. The fresh `SeptumRenderMidi` contains x86_64 and arm64 slices. These tests and renders use host execution; this receipt does not independently establish PCM identity under the other architecture. Root's separate universal plugin build is outside this receipt.

The complete registered **34-test CTest suite ran once: 34 passed, zero failed**, in 102.63 seconds. The receipt preserves the registered test list, each test result, full CTest output hashes, build configuration and fresh renderer hash. Names such as `HardwareEquivalence` denote verification-tool tests; a passing suite is not evidence that the synthesizer matches hardware.

## Complete frozen-performance replay

The [verification tool](../../../Tools/verify_reverb_return_integration.py) freshly renders all ten original comparison cases and all twelve predeclared new-case scenarios. The twelve scenarios come from two new recordings, not twelve independent hardware references. Each complete MIDI and published SysEx file is copied unchanged and verified against its frozen candidate receipt.

The replay retains sample rate 44.1 kHz, two-second tail, master level 100, MIDI channel 1, stored patch tempo, original tempo-clock events, and all note/controller timing. Complete settings, initial patch summaries, event lists, MIDI timing, tempo-at-end and the known 93-sample output latency match their earlier receipts. No gain fit, alignment, cropping or normalization is applied during this check.

| Frozen cohort | Cases | Complete WAVs identical to half-return candidate |
|---|---:|---:|
| Existing named-preset comparisons | 10 | 10 |
| Class A nominal / gap / overlap | 3 | 3 |
| Ambient SQR three gate × three velocity scenarios | 9 | 9 |
| **Total** | **22** | **22** |

Every WAV is **byte-identical**, not merely within tolerance: maximum PCM difference is zero. The candidate had multiplied the wet double by 0.5 before the old 0.8 return multiplication; shipping uses 0.4 at the original return multiplication. The complete render comparison confirms that this arithmetic placement produces identical output for the tested inputs.

Dist Bs 1, Moogie 1, Pedal Bs 1, So Juno 1 and Vangelead also remain byte-identical to the previous full-return baseline. These are the five existing cases unaffected by this reverb return change. Every fresh render is finite, stays below full scale, has zero active voices at the end, and reports no ignored events or degraded replay.

Because all complete WAVs match the frozen candidate files, their previously reported hardware scores transfer exactly; rerunning those score calculations would add no new evidence. The original performance reconstructions, source associations, capture uncertainty and contrary results remain unchanged.

## Reproduction and receipts

Recorded output: `build-fidelity/hardware-benchmark/reverb-return-integration/run-01`. The [durable JSON](reverb-return-integration-2026-09-15.json) stores all build/test/source identities, input and output hashes, per-case PCM equality, and copied replay settings. Generated audio and complete logs stay in the ignored output directory.

Build and run the complete suite once. If preserving CTest logs, use absolute filenames for `--output-log` and `--output-junit`:

```sh
cmake --build build-fidelity --parallel 2
ctest --test-dir build-fidelity --output-on-failure --parallel 2
```

Then replay the frozen runs to a new directory:

```sh
python3 Tools/verify_reverb_return_integration.py \
  --renderer build-fidelity/SeptumRenderMidi \
  --legacy-run build-fidelity/hardware-benchmark/reverb-gain-candidates/run-01 \
  --new-run build-fidelity/hardware-benchmark/reverb-new-preset-validation/run-01 \
  --output build-fidelity/hardware-benchmark/reverb-return-integration/reproduction
```

No new test mirroring the constant was added, and this verification made no source edits. Hardware equivalence remains unestablished.
