# Five further improvements: validation

Baseline: `850bddf`. Final checks ran in the native macOS Release build with
JUCE 8.0.14. All 18 CTest suites passed in 14.77 seconds. VST3, Audio Unit and
standalone targets built successfully. Cross-platform CI and universal-binary
builds were not run in this task.

| New suite | Passing checks | Distinguishing evidence |
| --- | ---: | --- |
| TempoClock | 25,633 | Fractional clocks, jitter, endpoint quantization, dropout/reacquisition, block partitioning, arpeggio/gate scheduling, paused clocks and free/synced LFO behavior |
| TempoSyncProcessor | 61 | SYSTEM/MIDI/HOST output matches reference-rate patches; wrong-rate controls differ; fractional host BPM, invalid/missing host data and native/DAW state migration |
| PortamentoContinuity | 193 | Pre-change engine fails 96 checks; maximum distinguishing audio error 0.0243086377 → 0 |
| MidiPortamento | 184 | Pre-change engine fails 86 checks; maximum forced-glide audio difference 0.016328482 → 0 |
| FeedbackSync | 10 | Pre-change engine fails 7 checks; corrected fractional-reset error below 7.4e−8 |
| ReverbDamping | 6,846 | Pre-change engine fails both tail checks; endpoints, complex response and live frequency edits verified |

The existing processor suite passes 4,162 checks, including eight added CC84
integration checks. The existing engine suite passes 4,599 checks. Remaining
suites cover hardware voice/performance behavior, smoothing, effects, analog
output, the reference-rate prototype, MIDI rendering, patch extraction, the
fidelity tool and demonstration rendering.

The new clock APIs and parameters did not exist in the baseline. Their
verification therefore compares the integrated external-source output with an
identically segmented reference patch at the intended rate, and includes a
wrong-tempo positive control. It does not claim that all new clock unit tests
can be compiled unchanged against the old interface.

An independent review caught two edge cases before final verification:

- A half-sample MIDI interval tolerance rejected some valid 300 BPM clocks at
  22.05/32 kHz. Allowing the full quantization error between two timestamps
  resolves it, with both rates covered by tests.
- A near-Nyquist reverb integrator could expose excess stored energy during
  a large live corner change. Direct-form-I history preserves previous signal
  values instead. Every pair of published corners is checked at six rates;
  the maximum tested endpoint-edit error is below 1.4e−18.

Nine editor snapshots were generated under
`build-fidelity/five-further-snapshots/`. Full and compact views were inspected.
Each reports 229 labels, with none outside the editor or requiring text
condensation. The CLOCK selector and both tempo controls remain visible.

The focused tests measure implementation contracts and audio differences, not
physical-hardware identity. The exact reverb transition shape, FB OSC reset
topology, portamento time curve and MIDI clock estimator of the SH-201 remain
unmeasured. See the [research report](five-further-improvements.md) and its
linked candidate audits for evidence and interpretation.

## Reproduce

For the dependency-free DSP build:

```sh
cmake -S . -B build-dsp -DCMAKE_BUILD_TYPE=Release -DSEPTUM_BUILD_PLUGIN=OFF -DBUILD_TESTING=ON
cmake --build build-dsp --parallel
ctest --test-dir build-dsp --output-on-failure
```

For the complete local build, configure another directory with
`SEPTUM_BUILD_PLUGIN=ON` and optionally `SEPTUM_JUCE_PATH` pointing to a local
JUCE 8.0.14 checkout. Run CTest there to include the two processor suites.

The final local run used:

```sh
cmake -S . -B build-fidelity -DCMAKE_BUILD_TYPE=Release -DSEPTUM_BUILD_PLUGIN=ON -DSEPTUM_BUILD_UNIVERSAL=OFF -DSEPTUM_JUCE_PATH=build-ui/_deps/juce-src -DBUILD_TESTING=ON
cmake --build build-fidelity --parallel 6
ctest --test-dir build-fidelity --output-on-failure -j 4
build-fidelity/SeptumPluginProcessorTests --editor-snapshots build-fidelity/five-further-snapshots
```
