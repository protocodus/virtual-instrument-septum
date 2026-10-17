# Synchronized reverb listening player

The player provides seven original / Septum before / Septum after comparisons, including Club Bass and Ambient SQR where some measured errors worsen. The before/after WAVs are the frozen `gain-1` and selected `gain-0.5` controls: the reverb return changes from 0.8 to 0.4. Production rebuild identity is audited separately. No source audio, MIDI, stored patch, candidate scores or DSP is changed by this exporter.

All three tracks play on one Web Audio clock and switch with a 12 ms fade. Each preset preserves **one previously frozen production-prefix delay and gain for both Septum versions**; the after track is not independently level matched. A common attenuation targets the hardware at no more than −20 dBFS RMS and caps every track's peak at 0.98. No EQ, dynamics, time warp or phase fitting is applied. The full aligned assessed excerpt includes its calibration prefix; the evaluated range is marked and has a jump button. The short Ambient clip uses fractional seconds.

| Preset | Playback duration | Evaluated playback seconds | Frozen lag, samples | Shared model gain |
|---|---:|---|---:|---:|
| Air Lead 1 | 3.4323 s | 0.8625–3.4323 | −780 | 3.207378290 |
| Brassy Ld 1 | 3.0276 s | 0.7575–3.0276 | −106 | 4.329190818 |
| Club Bass | 3.2447 s | 0.8125–3.2447 | +232 | 1.825679747 |
| Cotton Wool | 4.9695 s | 1.2500–4.9695 | −1346 | 3.590602948 |
| SupaJuce 1 | 1.7949 s | 0.4500–1.7949 | +223 | 1.753178747 |
| Class A, nominal | 2.9876 s | 0.3000–2.9876 | −549 | 4.224284783 |
| Ambient SQR, nominal v100 | 0.7250 s | 0.4050–0.7250 | −2205 | 7.467905006 |

Lag follows `model[t + lag]` against hardware `t`. The page also displays the original recording clock. Before/after share the same retained coverage as the frozen scoring protocol, including its small omitted end margin for positive lag. Class A and Ambient performances were frozen before their scores; the earlier five came from the existing official-preset experiment. Their unverified MIDI gates, velocity, phase, exact recorded patch state and capture chain still limit comparison. Ambient alignment hits the declared 50 ms search boundary. The source labels “Tail mismatch remains” keep Club/Ambient visible without suggesting they have become hardware matches.

## Identity and verification

The [manifest](reverb-listening-player-2026-09-15.json) records original MP3, raw source WAV, SysEx, MIDI, renderer, render receipt, scoring receipt, tool/template and exported WAV hashes. The exporter checks the nested input identities, shared model family, unchanged before production control, finite 44.1 kHz stereo audio, equal per-case frames, no ignored MIDI events and zero ended voices.

All **21** exported WAVs were read back and verified against the exact source crop × frozen gain × common attenuation at float32. All **21 audio hashes stayed identical across three exports**; subsequent changes were UI/provenance checks only. Generated JavaScript passes `node --check`. Root browser QA on run-01 passed: clean seven-preset layout; Class A play/repeat/after-source/evaluation-jump; live switch to Ambient and before; fractional 0.73 s display; pause/repeat-off/beginning/original reset; no browser warning/error logs. Run-03 retains the same transport code with the requested badge wording and direct original-source links. This verifies UI behavior, not a listening preference or the audio device’s sample-clock output. Original benchmark WAVs are read only. The local output is `build-fidelity/hardware-benchmark/reverb-listening-player/run-03/index.html`.

## Reproduce

```sh
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
/Library/Frameworks/Python.framework/Versions/3.11/bin/python3 \
Tools/build_reverb_benchmark_player.py \
  --gain-run build-fidelity/hardware-benchmark/reverb-gain-candidates/run-01 \
  --new-cases-run build-fidelity/hardware-benchmark/reverb-new-preset-validation/run-01 \
  --production-corpus build-fidelity/hardware-benchmark/final-production-linear-lfo \
  --sources build-fidelity/hardware-benchmark/sources \
  --output build-fidelity/hardware-benchmark/reverb-listening-player/reproduction
```

Use a new output directory and serve it with a local HTTP server. Browser playback requires an explicit Play click. Decoded track identity is checked by SHA-256 in secure/localhost contexts before playback. This artifact enables listening review; it does not establish whole-instrument equivalence.

## Final local serving check

The final `run-03` export is served at http://127.0.0.1:58513/. HTTP bodies for `index.html` and `manifest.json` are byte-identical to disk (SHA-256 `81dd00e7beec8d05abd744cb466e344838795b891be25b03366759bd6932eb17` and `d38c752e9b4bc1d712dfcdffe0c8acfa02756d7b00a5fd429a2c564735e0b3ac`). The final browser page shows the updated “Tail mismatch remains” labels and is idle with original hardware selected.
