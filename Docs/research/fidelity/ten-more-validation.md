# Ten additional improvements: validation

Baseline: `fdd6c75`. Validation ran on native Apple Silicon macOS in Release,
using JUCE 8.0.14. The research rationale and evidence limits are in the
[selection report](ten-more-improvements.md).

## Focused evidence

| Candidate | Focused suite | Distinguishing evidence |
| --- | --- | --- |
| MIDI mono/poly reception | MidiModeProcessor | 570 checks; CC126/127, channel rejection, timestamps, stopping existing voices/effects, subsequent polyphony and an envelope-retrigger positive control |
| SPLIT voice allocation | SplitPolyphony | 66 checks; the old five-per-side cap fails 42; shared capacity and unchanged DUAL limit |
| Fractional SMF tempo | MidiRender | 20 tests; exact microseconds-per-quarter conversion, range endpoints, and identical replay under different stored patch BPMs |
| MIDI bank selection | MidiBankProcessor | 46 checks; both 32-slot banks, decimal LSB 20, unsupported-bank rejection, per-channel latches, RX switches, state migration and audio equivalence |
| AMP envelope alignment | AmpEnvelopeLatency | 40 checks; old path fails 12; independent transient RMS error 0.371 → below 4 × 10⁻⁸ at 44.1 kHz |
| Remote Keyboard | RemoteKeyboard / RemoteKeyboardProcessor | 150 engine and 12 processor checks; old undifferentiated engine route fails 42; source ownership, arpeggios, channels, pedals and migration |
| Reverb geometry transitions | ReverbGeometry | 3,118,014 checks at six rates; 96 settled configurations retain audio hash `37f04048a39c69ec`; first-return transient improvement 21.7 dB at 48 kHz |
| DIRECT transposition | DirectMidiTranspose | 384 checks; old path fails 72; worst waveform error 0.152 → 0, with master/tone pitch controls preserved |
| PATCH REMAIN | PatchRemain / PatchRemainProcessor | 78 engine and 14 processor checks; former path fails 43 of the original 72 checks; old-voice audio, controllers, key release, tail reporting and program-selection revisions |
| Send/balance smoothing | EffectSendSmoothing | 807 checks; old path fails 42; maximum first gain step 1 → 0.00903; exact output across block partitions |

Counts describe assertions in focused synthetic fixtures, not independent
hardware measurements. Baseline failures use each isolated pre-change engine
with matching headers or an explicitly documented compatibility path. The
audits identify the comparison for each candidate.

## Combined verification

All **29 CTest suites pass**, in 14.69 seconds. VST3, Audio Unit and standalone
targets build successfully. The general engine suite passes 4,599 checks;
the general plug-in processor suite passes 4,210. Existing hardware voice,
hardware performance, effects, smoothing, clock, portamento, analog output,
reference-rate, patch-extraction, fidelity-tool and demo-render suites pass.

Nine editor snapshots were regenerated in
`build-fidelity/ten-more-snapshots/`. Every view reports 233 labels, zero
outside the editor and zero requiring condensation. Full and compact views
were visually inspected; RX BANK, MIDI NOTES and REMAIN remain accessible.
The final local logs are `/tmp/septum-ten-final-configure.log`,
`/tmp/septum-ten-final-build.log`, `/tmp/septum-ten-final-tests.log` and
`/tmp/septum-ten-snapshots.log`.

Two existing test setups needed adjustment: the LFO phase fixture now resets
both engines after loading its patch, so its silent preroll changes phase
without also settling only one engine's patch-level gain. The mono-mode
fixture now reaches a lower sustain level before the second note, so its
positive control actually detects an unwanted envelope retrigger. Equality
tolerances were retained.

The integrated review also covered source-aware note release, retained LFO
state, a stale staged-program revision race, and default reverb read-head
weight initialization. Regression coverage accompanies the corrections.

## Before/after audition

Six original procedural cases compare the baseline with the completed DSP:
eight notes in one split zone, held notes across a patch change, direct MIDI
alongside a keyboard arpeggio, very short AMP notes, reverb geometry edits,
and effect-send/tone-balance edits.

The local artifact is `build-fidelity/ten-more-audio/index.html`, served at
<http://127.0.0.1:8912/> while the local server runs. `manifest.json` records
every DSP source/header SHA-256, the renderer fixture hash, event timelines,
raw peaks, output hashes and gain normalization. `render_cases.cpp` and
`build_audition.py` retain the local reproducer; `QA.md` records media checks.
Generated audio and build artifacts are intentionally outside Git.

All twelve WAVs are finite stereo 48 kHz/24-bit PCM, with correct durations
of 4–7 seconds and peaks no greater than 0.75. Each pair shares one gain;
there is no independent loudness matching or limiter. Chrome decoded all
twelve files and all six A/B selectors switched successfully. The page was
visually inspected. No subjective listening or hardware-match score is
claimed. A full-round comparison can include interactions among changes.

## Compatibility and scope

- Native preset format 6 appends RX BANK, MIDI NOTES and REMAIN. Older
  supported formats migrate to RX BANK on, CHANNEL input and REMAIN off.
- Existing host parameter identifiers stay in place; new identifiers are
  appended. Bare MIDI program changes retain the flat 0–63 map until an
  explicit bank is selected on that channel.
- The voice pool remains ten. Retained voices share the selected patch's
  delay/reverb network; repeated notes at one pitch from one source retain
  the existing release-all behavior across program generations.
- The time constants for control smoothing and reverb crossfades are
  numerical quality choices. No oscillator/filter remapping or unmeasured
  global timbral recalibration is claimed.
- Native macOS VST3, Audio Unit and standalone are the build targets for this
  run. Universal macOS and Linux/Windows CI were not run here.

## Reproduce

Dependency-free DSP and tool tests:

```sh
cmake -S . -B build-dsp -DCMAKE_BUILD_TYPE=Release -DSEPTUM_BUILD_PLUGIN=OFF -DBUILD_TESTING=ON
cmake --build build-dsp --parallel
ctest --test-dir build-dsp --output-on-failure
```

The complete local run, including processor integration and editor captures:

```sh
cmake -S . -B build-fidelity -DCMAKE_BUILD_TYPE=Release -DSEPTUM_BUILD_PLUGIN=ON -DSEPTUM_BUILD_UNIVERSAL=OFF -DSEPTUM_JUCE_PATH=build-ui/_deps/juce-src -DBUILD_TESTING=ON
cmake --build build-fidelity --parallel 6
ctest --test-dir build-fidelity --output-on-failure -j 4
build-fidelity/SeptumPluginProcessorTests --editor-snapshots build-fidelity/ten-more-snapshots
git log --oneline --reverse fdd6c75..HEAD
```

The final command lists the ten candidate commits in implementation order.
Each contains its source audit, implementation and focused tests. The last
also contains this combined validation and the ranked research report.

## Ten commits

| Order | Commit | Change |
| ---: | --- | --- |
| 1 | `7990167` | Receive MIDI mono/poly mode changes |
| 2 | `d457679` | Share all ten voices in SPLIT |
| 3 | `625b527` | Preserve fractional tempo during MIDI replay |
| 4 | `8110b36` | Receive PRESET/USER bank selections |
| 5 | `36eb637` | Align AMP envelopes with oversampling latency |
| 6 | `b5ec9a7` | Separate direct MIDI and Remote Keyboard input |
| 7 | `898f0a0` | Crossfade reverb geometry changes |
| 8 | `39df836` | Isolate direct MIDI from keyboard transposition |
| 9 | `db9e950` | Preserve sounding voices across patch changes |
| 10 | This report's commit | Smooth effect sends and tone balance |
