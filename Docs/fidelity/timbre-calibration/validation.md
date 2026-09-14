# Timbre calibration validation

Baseline: `7532a13`. Native Apple Silicon macOS Release, JUCE 8.0.14.
All **32 CTest suites pass** in 29.47 seconds. VST3, Audio Unit and standalone
targets build successfully. There are no new editor controls; the existing
UI and serialized patch formats are unchanged.

| Area | Result |
| --- | --- |
| TimbreCalibration | 584 checks; filter/envelope reference audio, waveform phase/polarity, Super Saw detune/filter response, rejection atomicity and omitted-field automation isolation |
| ReferenceRateEngine | 5,267 checks; selected synthesis rates, causal MIDI timing, converter rejection, input latency, reset, block partitions and no render allocations |
| TimbreCandidate | 15 tests; strict JSON, duplicate/type/range errors, frozen-source integrity, emitted full C++ profile and real baseline/triangle/filter/reference renders |
| TimbreCapture | Six tests; 22-block SysEx integrity, documented ranges, exact MIDI/gates, hashes, refusal to overwrite and software replay |
| Existing plug-in processor | 4,210 checks pass |
| Existing engine | 4,599 checks pass |
| Remaining suites | All pass, including prior fidelity, MIDI, effects, timing, analog-output and renderer coverage |

The independently compiled default-model comparison against the baseline
has identical full-audio hash `e454596d055f83cb` across eight waveform types
at 44.1, 48 and 96 kHz. It includes note changes/releases, nontrivial filter
settings and effects. Therefore these additions do not silently retune the
shipping default. Table-enabled tests separately verify their audible effects.

Review caught two important experimental confounders. A cutoff-only profile
initially changed the stage-two resonance transition by 5.11% relative RMS in
a short fixture, because the second stage was smoothed independently. That
law now changes only when an explicit second-stage table is provided. A
Super Saw profile that changes mix alone similarly keeps the original
continuous detune polynomial; only an explicit detune table selects linear
interpolation. Dedicated dynamic comparisons pass exactly for omitted fields.

The reference-rate correction was tested by restoring the old scheduler in
an isolated build. Four causal event-audio cases then fail, while an integer
ratio control and eight static renders retain the original result. The
configurable-rate renderer remains experimental because its per-sample
control cadence, CPU cost and extra external-input latency are still material
integration choices. At 48 kHz, the final combined run measured about 13.0%
of one core for the reference case versus 4.3% native, with other suites
running concurrently. Use the isolated numbers in [reference-rate.md](reference-rate.md)
for the more controlled comparison; neither is a portable performance promise.

## Listening comparisons

`build-fidelity/timbre-candidates-audio/` contains ten stereo 24-bit WAVs at
48 kHz, paired on a local listening page. The five original dry performances
exercise an octave-lower cutoff, filter decay multiplied by 0.7, triangle
polarity inversion, Super Saw mix 0.55 versus 0.75, and a 44.1 kHz comparison
core versus native 48 kHz. These are diagnostic settings, not selected
hardware calibrations. Every pair has nonzero audio differences.

All float renders are finite. A single gain per pair limits both outputs to
a maximum absolute sample of 0.75; neither independent normalization nor time
alignment was applied. The reference-rate pair retains its different reported
latencies (93 versus 171 host samples), control cadence and conversion filter.
Those differences prevent treating it as an isolated aliasing or fidelity score.
Chrome playback verification loaded all five cards, decoded and played audio,
switched A/B on the progressing timeline, and stopped/reset at the end. The
desktop layout was visually checked; local results are recorded in `qa.json`.

The manifest records exact source, compiler, renderer, profile, patch, event
and WAV hashes. Its frozen DSP files match the delivered implementation.
The recorded pre-commit HEAD and dirty status describe the actual render-time
snapshot; the file hashes establish its content. The source-tree SHA-256 is
`049b11eb5d02e4d9962448a3795ed7cf6a320fb25e90dbe250b56f072fde0f5a`.

## Reproduce

```sh
cmake -S . -B build-fidelity -DCMAKE_BUILD_TYPE=Release -DSEPTUM_BUILD_PLUGIN=ON -DSEPTUM_BUILD_UNIVERSAL=OFF -DSEPTUM_JUCE_PATH=build-ui/_deps/juce-src -DBUILD_TESTING=ON
cmake --build build-fidelity --parallel 6
ctest --test-dir build-fidelity --output-on-failure -j 4
```

A dependency-free DSP/tool build uses `SEPTUM_BUILD_PLUGIN=OFF`; processor
suites require JUCE. The candidate integration tests require a GCC/Clang-style
`c++` executable and skip that class if it is unavailable. Schema tests still
run. Native macOS was tested here; universal and other-platform CI were not.

Final local logs are `/tmp/septum-timbre-build-final.log` and
`/tmp/septum-timbre-tests-final.log`. The standalone candidate integration log
is `/tmp/septum-timbre-candidate-tests-final.log`. Source copies and logs from
the isolated scheduling mutation are in `/tmp/septum-reference-rate-v2/`.

## Commits

The implementation is delivered as five commits, listed by:

```sh
git log --oneline --reverse 7532a13..HEAD
```

They cover the filter, envelope, basic waveforms, Super Saw and synthesis-rate
comparison path respectively. The last includes the common candidate/capture
tools and combined documentation. Existing user changes to CI, packaging and
the root README are excluded from all five commits.
