# Negative filter-attack capture inputs — 2026-09-20

Four newly generated SysEx/MIDI pairs make the next hardware measurement reproducible. **No hardware has been recorded or accessed.** These are new test inputs, not recovered performance MIDI; no production DSP calibration follows from software replay.

The optional `negative-attack` suite in [the generator](../../../Tools/generate_timbre_capture.py) uses SINGLE UPPER, one saw oscillator, neutral pitch, MIX balance −63 and LOW FREQ FLAT. Every fixture has LP24 cutoff 120, resonance 0, depth −22 (wire 42), filter decay/sustain/release 127/127/0 and AMP ADSR 0/0/127/0. Only filter attack changes: **0, 13, 24, 36**. Tone LEVEL remains the generator's 96 and patch LEVEL is 127. Drive, effects, arpeggio, portamento, LFO modulation, key follow and velocity modulation are disabled.

Each MIDI plays note 48 at velocity 100 from 0.500 to 3.000 seconds. All Sound Off occurs at 3.500 seconds and the file ends at 3.600 seconds: **14.4 seconds total**, excluding patch-loading waits and recording setup. Every patch contains 22 checksum-verified DT1 packets targeting temporary addresses `10 00`. Loading replaces the current edit buffer; no USER-bank write is included. The README preserves the existing device/system settings, packet spacing and unprocessed recording protocol.

The ignored package is `build-fidelity/public-match-2026-09-20/SH-201-negative-attack-capture-inputs.zip`. It contains four `.syx`/`.mid` pairs, the original INIT, manifest and README. All capture fields remain `not-recorded`; software WAVs are separate. [The audit JSON](negative-attack-capture-inputs-2026-09-20.json) pins the package, exact input bytes and complete validation report.

All four inputs replay strictly through the frozen baseline renderer at 96 kHz, with 345,600 finite stereo float frames each, no clipping or degraded replay, 90 samples of retained latency and zero ending voices. Peaks are 0.05966, 0.05964, 0.05959 and 0.06576. These checks establish usable inputs, not hardware sound matching. Actual encoded blocks and MIDI events were independently checked against the requested settings.

Seven capture tests pass, including the real exporter/replay and a new encoded-control/MIDI test. Direct old/new generation also confirms byte-identical prior SysEx/MIDI payloads and unchanged prior manifests apart from the generator hash. `all` appends four fixtures, becoming 95 fixtures/517.0 seconds; `quick` remains unchanged at six fixtures. No existing hardware source, preset catalog or production DSP changed.

Reproduce the inputs with a new output directory:

```sh
python3 Tools/generate_timbre_capture.py --suite negative-attack \
  --renderer build-fidelity/public-match-2026-09-20/baseline/SeptumRenderMidi \
  --output /path/to/new-negative-attack-inputs
```

These settings remove the layers, overdrive and spatial effects that confound the public A02/A03 demonstrations. A recorded held-note trajectory could discriminate the proposed attack mappings, but four controls alone would not establish the full hardware attack curve.
