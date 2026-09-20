# Timbre calibration: implementation and experiments

This work starts the five selected sound-model improvements from baseline
`7532a13`. It implements their calibration paths and a reproducible way to
hear candidate sounds, plus a concrete event-timing correction in the
fixed-rate comparison renderer. No new dry hardware capture is available.
The shipping plug-in keeps its incumbent timbre; none of the diagnostic
curves is presented as a verified replacement for Roland's DSP.

| Candidate | Implementation | Remaining evidence |
| --- | --- | --- |
| [Filter response](filter.md) | Independent cutoff/damping tables, validated before use; continuous coefficient changes | Dry response grid with modulation disabled, multiple input levels and withheld control settings |
| [Filter envelope](envelopes.md) | Separate attack, decay, sustain and release tables in defined units | Known note gates, sustained plateaus and releases across slider positions |
| [Basic waveforms](waveforms.md) | Phase/gain conventions plus pulse-width curve, with matching BLEP/BLAMP corrections | Individual-wave and mixed-wave captures that distinguish phase cancellation from spectral shape |
| [Super Saw](supersaw.md) | Detune/offset/mix/tracked-filter calibration with consistent sync behavior | SH-201-specific dry spectra and repeated-note beating/phase distributions |
| [Synthesis clock](reference-rate.md) | Configurable core rate and corrected causal control scheduling | Hardware alias trajectories; further CPU and input-latency integration work |

The first four routes can change actual voice-engine audio, but are exposed
through the comparison tools rather than new patch controls. An explicit
model installation clears the prior sound. It is neither host automation
nor serialized SysEx/native preset data. No existing host parameter IDs,
patch bytes or UI controls are changed.

## Build and hear a candidate

The builder copies all DSP sources into a new directory, installs a generated
profile through the public engine API, and compiles that frozen copy. It does
not edit DSP implementation text or link an old support archive. Its manifest
records original/canonical profile hashes, every copied source, compiler
identity and command, renderer hash and exact enabled fields. Reusing an
output directory or supplying malformed data fails before compilation.

```sh
python3 Tools/build_timbre_candidate.py \
  --profile Tools/timbre-profiles/diagnostic-triangle-inversion.json \
  --output build-fidelity/candidates/triangle

python3 Tools/render_midi.py \
  --renderer build-fidelity/candidates/triangle/SeptumRenderMidi \
  --syx /path/to/complete-patch.syx --midi /path/to/performance.mid \
  --output build-fidelity/candidates/triangle-comparison.wav \
  --sample-rate 48000 --tempo-policy preserve-patch --strict
```

The builder requires Python 3 and a GCC/Clang-compatible C++20 compiler. Use
`--compiler clang++` if the default `c++` driver is unavailable. The normal
plug-in build remains independent of this optional tool.

A minimal candidate is:

```json
{
  "version": 1,
  "id": "triangle-phase-diagnostic",
  "evidence": "Experimental phase convention; not a hardware calibration.",
  "waves": { "wave_gain": [1, 1, 1, -1, 1] }
}
```

Wave order is saw, square, pulse, triangle, sine. Profiles may provide
`filter`, `envelope`, `waves`, `supersaw` and `reference_rate_hz`; exact fields
and bounds are centralized in `Tools/build_timbre_candidate.py::FIELDS` and
matched by C++ validation. Curve arrays contain all 128 raw control values.
Only supplied fields are replaced. In particular, a cutoff-only profile
retains the incumbent second-stage resonance coupling, and a Super Saw
mix-only profile retains its continuous detune polynomial during modulation.
Explicit replacement detune tables interpolate fractional controls linearly.

Three committed examples are diagnostics: a disabled baseline, triangle
inversion and an octave-lower cutoff curve. The octave shift makes the path
audible; it is not a recommended global correction. Triangle inversion has
cross-patch limitations recorded in the earlier source audit. Additional
local A/B cases exercise shorter filter decay, a changed Super Saw mix and
an explicit 44.1 kHz core. All are labeled as experiments.

The local listening page is `build-fidelity/timbre-candidates-audio/index.html`.
It contains five baseline/candidate pairs with the precise changed setting
shown beside each player. Its manifest includes the frozen renderer sources,
profiles, patch SysEx, event timelines and audio hashes. These generated
artifacts are outside Git. To reopen the page locally:

```sh
python3 -m http.server 8913 --bind 127.0.0.1 --directory build-fidelity/timbre-candidates-audio
```

Then open <http://127.0.0.1:8913/>.

## Reproducible input packages

```sh
python3 Tools/generate_timbre_capture.py \
  --renderer build-fidelity/SeptumRenderMidi \
  --output build-fidelity/timbre-inputs --suite quick
```

The quick package contains six fixtures totaling 29.1 seconds. `--suite all`
creates 95 fixtures totaling 517.0 seconds. Individual suites are `filter`,
`envelopes`, `negative-attack`, `waveforms`, `supersaw` and `aliasing`.
The four-fixture `negative-attack` suite lasts 14.4 seconds and isolates
raw filter attacks 0, 13, 24 and 36 with one dry saw and depth −22. It supplies
new test inputs, not recordings or an established hardware timing curve.
Each fixture includes a
complete original INIT-derived patch, exact MIDI gates, parameter overrides,
input hashes and explicit system/routing assumptions. The generator never
sends MIDI or writes a hardware patch bank. These inputs can already be used
for software comparisons and later reused with a physical unit.

## Validation and current limits

The calibration suite passes 584 focused checks at 44.1, 48 and 96 kHz.
Tests compare complete audio against independently edited reference patches,
polarity/phase identities and a Butterworth high-pass magnitude equation.
They also verify that rejected profiles leave active audio unchanged.
Omitted-field automation tests caught and prevented two cross-control
confounders before delivery.

The isolated builder passes 15 tests, including real C++ builds, disabled
baseline WAV identity, audible waveform/filter changes, a selected core
rate, fully populated profile validation, source hashes and malformed input.
The capture generator passes six tests, including complete SysEx checksums,
note-offs, frame counts, no-overwrite behavior and actual software replay.

A separate 24-case production regression probe renders eight waveforms at
three rates, with notes, releases, filters and effects. The old and new
default models give identical full-audio hash `e454596d055f83cb` with the same
compiler. This is a local regression check, not a portable cross-compiler
golden value or a hardware match score.

Combined build/test and audition results are recorded in [validation.md](validation.md).
The remaining calibration work is choosing numeric curves from evidence
that generalizes across recordings, notes and control settings. The present
work makes those experiments implementable and repeatable; it does not
manufacture the missing measurements.
