# Release validation

This document records the release-hardening work and the checks to repeat on
an actual release candidate. Passing these checks reduces known risks; it
cannot establish compatibility with every host or input sequence.

## Behavioral guarantees covered by regression tests

- Invalid/nonfinite sample rates are bounded before allocating buffers or
  converting numbers to sample counts. Engine scratch storage is independent
  of the block-size hint.
- Invalid patch enums and integer parameters are clamped. Nonfinite performance
  controllers retain their last valid value. External NaN/Inf samples become
  silence before entering feedback state; extreme finite input is limited to
  ±64 (36 dB above full scale).
- Host blocks larger than the preparation hint are processed in bounded chunks.
  MIDI and UI publication do not grow buffers or post messages from the callback.
- MIDI events at the same sample retain their supplied order, including program
  changes, controls, note releases, and new notes. No note-type sorting is done.
  Invalid messages are ignored and received MIDI is consumed by the instrument.
  Out-of-block timestamps clamp to the block boundaries. Explicit host patch/
  state transactions take precedence over overlapping MIDI parameter edits,
  while notes and pedal releases continue. Notification-only collisions defer
  parameter messages in a fixed 256-message FIFO; messages replay before newer
  parameter messages when access resumes. Host transactions invalidate old
  deferred messages; overflow drops the oldest parameter edit, retaining the
  newest controls. No note/pedal event is queued or dropped by this mechanism.
- SysEx rejects invalid status/data bytes, corrupt checksums and mismatched
  device IDs. Length checks cannot wrap. Rejected messages leave patches intact;
  bank scanning recovers after an unterminated frame.
- Host state is size/depth bounded and validated before publication. Rejected
  state leaves the previous patch intact. Restoring state republishes parameter
  values even when JUCE's stored tree already contains the requested values;
  this fixes a Boolean parameter restoration failure found by pluginval.
- UI note-queue overflow retains each note's final action, preventing lost
  releases and stuck notes. Deferred host notifications use a polling timer
  with lifetime protection when the processor is destroyed off the UI thread.
- Effect coefficients are cached until their controls or sample rate change.
  Offline demo takes can render on separate cores with `SeptumRenderDemos
  --jobs 4 <output-directory>`. Output files and reported results retain their
  original ordering. Each take uses an independent engine.

Live DSP remains on the host's audio thread. Its eight-sample voice ticks share
voice allocation, modulation, external input and effects. Adding worker wakeups
and barriers to those ticks has no demonstrated deadline benefit. DAWs may run
separate plug-in instances on separate cores; independent offline takes are
parallelized explicitly.

## Recorded local validation — 2026-09-14

The final native arm64 builds were tested on an Apple M1 Max, macOS 26.5.1,
Apple Clang 21, with JUCE 8.0.14. This records the working-tree candidate;
no release tag, publication, or merge was performed.

| Check | Result |
| --- | --- |
| Complete Release CTest suite | 37/37 passed, 48.31 seconds |
| ASan + UBSan + float-cast-overflow suite, including JUCE processor tests | 37/37 passed, 94.57 seconds; all seven processor suites passed again after the final processor changes |
| VST3 pluginval 1.0.4 | Strictness 10, seed `0x53455054`, GUI tests enabled: passed |
| Apple Audio Unit validator | `auval -v aumu Spt1 Sptm -strict -stress 30`: passed |
| DSP mutation/allocation stress | 797,436 frames, 49,152 control/note events, 1,536 malformed patches; no failures or post-prepare C++ allocations in the audited operations |
| SysEx mutation stress | 50,000 seeded mutations passed |
| Offline input mutations | 5,000 malformed SMF inputs and 100 replay mutations passed |
| Serial versus four-worker demo render | All 11 WAVs byte-identical; 5.094 seconds versus 2.723 seconds locally |
| Packaging | Mock regressions and actual arm64 ZIP/PKG smoke build passed; ZIP CRC and all four copies of dependency notices verified |

The DSP benchmark measured 4.2–7.2% less render time at the full ten-voice
load, and 3.2–13.2% across the six tested scenarios. All six audio hashes were
unchanged. These are best-of-three local timings, including checksum work,
and do not establish a realtime scheduling guarantee.

Local raw logs are under `out/release-validation/`, including
`release-tests-complete.log`, `sanitizer-tests-final.log`,
`sanitizer-processors-complete.log`, `pluginval-complete.log`, `auval.log`,
`dsp-benchmark.txt`, and `package-smoke.log`. The temporary AU installation was
moved back into that output directory after validation.

The generated `build-fidelity/dist/Septum-0.9.0-build-0-macOS-arm64.zip` and
`.pkg` are development smoke artifacts. Their bundles use ad-hoc signatures;
the installer has no Developer ID signature and neither artifact is notarized.
Windows/Linux host runs, the Intel macOS slice, the supported DAW matrix, and
commercial signing/notarization remain release-candidate checks.

## Repeatable checks

Configure a normal release build with `BUILD_TESTING=ON`, build all targets,
then run `ctest --test-dir <build-directory> --output-on-failure --parallel 4`
(add `-C Release` for multi-configuration generators).

For address, undefined-behavior and float-to-integer conversion checks:

```sh
cmake -S . -B build-sanitize -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DSEPTUM_BUILD_UNIVERSAL=OFF -DSEPTUM_BUILD_PLUGIN=OFF \
  -DSEPTUM_ENABLE_SANITIZERS=ON -DBUILD_TESTING=ON
cmake --build build-sanitize --parallel 4
ctest --test-dir build-sanitize --output-on-failure --parallel 4
```

Set `SEPTUM_BUILD_PLUGIN=ON` in the same configuration to include JUCE and
the processor suites, as in the recorded local sanitizer run.

`Septum.ProtocolRobustness` runs 50,000 seeded SysEx mutations and numeric
boundary cases. `Septum.EngineRobustness` stresses malformed patches, control
and note events, external input and lifecycle changes, and audits heap
allocations. `Septum.RenderToolRobustness` covers malformed offline inputs and
serial/parallel equivalence. `Septum.ProcessorRobustness` requires a JUCE build
and covers the host callback, MIDI order and realtime allocation behavior.
Release-validation CI runs the JUCE-free sanitizer suites on Linux and the
full release suite plus strict VST3 validation on macOS.

`SeptumEngineRobustnessTests --benchmark` records render times and output
hashes. Compare the same compiler, optimization, hardware, rate and voice count;
wall-clock results depend on other work running on the machine.

Also validate the actual VST3 binary using
[pluginval](https://github.com/Tracktion/pluginval) at strictness level 10. Use
`--random-seed 0x53455054` to repeat a failure. For example:

```sh
pluginval --strictness-level 10 --random-seed 0x53455054 \
  --output-dir out/release-validation --validate /absolute/path/to/Septum.vst3
```

Test Audio Unit separately, plus loading/saving, automation, transport changes,
MIDI routing and offline bouncing in each supported DAW. Run native builds on
Windows and Linux, and test both macOS architecture slices where distributed.

## Distribution gates

A release still requires the publisher's choice of JUCE licensing terms,
appropriate entitlement or fulfillment of the applicable open-source terms,
and verification of included dependency notices. See
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md). Repository source licensing
alone does not establish a publisher's commercial JUCE entitlement.

Set `COMMERCIAL_RELEASE=1`, `APP_SIGN_IDENTITY`, `INSTALLER_SIGN_IDENTITY`,
`NOTARY_PROFILE` and a numeric `BUILD_NUMBER` when running
`scripts/sign-and-package-macos.sh` for commercial macOS packages. This mode
requires Developer ID identities and a configured notary profile before
staging changes. Both the ZIP bundles and the installer must be accepted and
stapled; the extracted final ZIP is verified as well. Ad-hoc CI artifacts are development
builds. Do not advertise them as notarized release installers. Confirm the
chosen product version, supported platforms, support contact and distribution
assets before publishing. This hardening pass does not publish or merge a release.
