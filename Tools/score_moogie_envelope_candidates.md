# Score existing Moogie envelope renders

`score_moogie_envelope_candidates.py` reads existing WAVs, selects a candidate
using the first long low note, and reports untouched notes and timing checks.
It never builds DSP, renders audio, changes MIDI/SysEx, or fits EQ/gain offsets.

## Manifest input

Paths may be absolute or relative to the manifest directory. Keep WAV time
origin at zero on the unchanged performance timeline. Audio must be finite
44.1 kHz floating mono/stereo PCM; stereo is averaged to mono.

```json
{
  "hardware_wav": "/absolute/path/hardware-excerpt-raw.wav",
  "production_wav": "/absolute/path/production.wav",
  "sysex": "/absolute/path/original-patch.syx",
  "midi": "/absolute/path/reconstructed-performance.mid",
  "renderer_latency_samples": 93,
  "candidates": [
    {
      "id": "hz-tau49-0.15",
      "wav": "/absolute/path/candidate.wav",
      "tau49_seconds": 0.15,
      "T60_raw49_seconds": 1.0361632918473205
    }
  ]
}
```

The candidate time labels and other extra metadata are retained as declarations;
the scorer does not use them to change audio. Optional candidate `render_metadata`
points to a renderer JSON sidecar. Otherwise, an adjacent `candidate.render.json`
is checked automatically. Matching WAV, SysEx, MIDI and latency hashes are
verified, and the renderer hash is recorded. Without a sidecar the provenance
limit is explicit. The tool requires the known unchanged Moogie SysEx and
frozen reconstructed MIDI hashes. That MIDI is not an original performance.

```sh
OPENBLAS_NUM_THREADS=1 python3 Tools/score_moogie_envelope_candidates.py \
  --manifest build-fidelity/envelope-hypothesis/factory-v1/hz-score-input.json \
  --output build-fidelity/envelope-hypothesis/hz-score-reproduction
```

Direct paths are also supported:

```sh
python3 Tools/score_moogie_envelope_candidates.py \
  --hardware hardware.wav --production production.wav \
  --candidate fast=fast.wav --candidate slow=slow.wav \
  --sysex original-patch.syx --midi reconstructed-performance.mid \
  --output score-results
```

## Fixed scoring protocol

- MIDI note 39 at 0.029, 0.939 and 1.901 s; lowest physical oscillator family
  is MIDI 27, approximately 38.89 Hz. The raw/display −36 value is not used as
  a physical transpose.
- 80 ms windows centered 100, 180 and 260 ms after each onset.
- Hardware center: `on + offset + timing_shift`.
- Render center: `on + offset + 93/44100`. Selecting later rendered samples
  advances its audio by the known latency exactly once. MIDI bytes are unchanged.
- Timing shifts −20/0/+20 ms affect hardware observations only, keeping rendered
  envelope age fixed. No best offset is selected. The original-MIDI dry recording's
  roughly 35 ms delay is not added to audio-transcribed Moogie onsets.
- Full-sample joint quadratures and independent local linear ramps measure
  96 harmonics. Hardware/production effective frequencies are estimated once
  within ±3% of the nominal family; every candidate inherits production frequencies.
- Only hardware determines eligible harmonics: residual power at most 1%,
  amplitude above −45 dB relative to H1, and coefficient SNR proxy at least
  20 dB. A missing candidate harmonic increases error; it cannot remove itself.
- Selection uses unadjusted H4/H2, H6/H2 and H8/H2 error on the first note at
  zero shift. At least two even ratios must qualify in every training window.
  Candidates must explain at least 99% of their training-window signal power.
- H2–H8/H1, odd H3/H5/H7/H1, and even H4/H6/H8/H2 errors are reported separately
  for training and held-out notes. Counts accompany every aggregate.

The even-harmonic interpretation assumes symmetric lower square/triangle
waves and a sufficiently linear path. The effective fitted frequency can
absorb moving-filter phase; it is not an oscillator-tuning measurement. To
check that assumption, preserve the original winner and use nominal frequency:

```sh
python3 Tools/score_moogie_envelope_candidates.py \
  --manifest hz-score-input.json --frequency-policy nominal \
  --frozen-candidate hz-tau49-0.15 --output hz-nominal-sensitivity
```

Nominal-frequency mode requires an explicit frozen candidate and does not
reselect it. A grid-boundary winner remains an unresolved bound. Differences
between model families or timing variants do not authorize selecting a new
anchor using holdouts.

## Output and checks

The fresh output directory receives `results.json`: input/sidecar/tool hashes,
all hardware masks and measurements, candidate measurements, per-window
residuals, group summaries, and a selection record. `selected_holdouts` retains
the chosen candidate's summaries at every fixed timing shift. Preserve the
full output and frozen selection when evaluating other presets.

`--self-test` verifies known harmonic amplitudes with local ramps, exact
93-sample compensation, hardware-only masks, and first-note selection. A real
production-WAV identity control additionally verifies direct-path ingestion
and identical measurements/scores. These checks validate the scorer; they do
not establish SH-201 output equivalence.
