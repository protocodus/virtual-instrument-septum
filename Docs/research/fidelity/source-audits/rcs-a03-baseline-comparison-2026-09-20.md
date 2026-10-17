# RCS A03 — unchanged-preset baseline characterization

2026-09-20. The frozen current engine does not reproduce the selected A03 hardware note's sustained spectral closure. Hardware observes all 81 predeclared 10/20/30 dB landmarks; the unchanged-preset baseline censors all 81. Missing timings and paired errors remain null.

The [source-only audit](rcs-a03-hardware-observations-2026-09-20.md), [case](../reconstructions/expanded/rcs-a03-jupiter8wide.json) and [supplementary catalog](../rcs-a03-reference-catalog.json) were completed and hashed before this first A03 render. The 36.720–36.980-second excerpt contains estimated MIDI 45 at velocity 100, starting 36.764 seconds. Its artificial final note-off at the crop edge was accepted by strict replay. Notes and patch bytes were not changed after model inspection. A03 is now **baseline-characterized**, not an untouched holdout; no modified candidate or attack probe has been evaluated here.

| Relative spectral drop | Hardware median elapsed | Hardware observed | Baseline observed |
| --- | --- | --- | --- |
| 10 dB | 43.71 ms | 27 / 27 | 0 / 27 |
| 20 dB | 52.51 ms | 27 / 27 | 0 / 27 |
| 30 dB | 65.12 ms | 27 / 27 | 0 / 27 |

The original hardware observations were reproduced exactly. The same bands, Hann windows, channels, ±10 ms onset sensitivity, 15–35 ms early reference, 10 ms sustained crossing and 30 ms guard are retained. Hardware STFT time starts at 35 seconds; software time is `36.72 + STFT time − 93/44100`. The known renderer latency is removed from time coordinates only, without shifting PCM, fitting onset, changing gain or applying EQ.

In the 1024-sample mid-channel trace, hardware reaches −43.46 dB relative to its early reference before the guard, whereas the baseline reaches only −1.85 dB. Neither band reaches the numerical `1e-20` floor. The inspected closure plot is `build-fidelity/public-match-2026-09-20/rcs-a03-baseline/closure/baseline-closure.png`.

[Listen to the fixed baseline comparison](http://127.0.0.1:8920/rcs-a03-baseline/). Listening copies use documented scalar RMS matching; the closure measurement uses raw float WAVs. Unknown original velocity, system/controllers, same-take patch state, phase, modulation delay and capture processing remain limitations. Changing upper/lower amplitude balance, overdrive and filtering all affect the measured ratio. Crossing elapsed times do not identify filter attack durations.

The baseline renderer is the existing frozen `public-match-2026-09-20/baseline/SeptumRenderMidi`, SHA-256 `3672d8f6ddf99e1bddbe575c035a9ecae1429e11517e89cc48b8c93eb4b29a34`. The raw A03 render is finite, nonzero, unclipped, 44.1 kHz stereo, 99,666 frames, peak 0.244032, retained latency 93 samples, zero ending voices and nondegraded replay. Its SHA-256 is `bd6c1046c9c5709834060397be76be149e8c151845c5e20c32313aa08d7620bf`; the original patch remains `ac6e5f6c901903172b2b24b35c6a7d36b899818200304d7b8759d5dca1c901dc`.

[The JSON summary](rcs-a03-baseline-comparison-2026-09-20.json) pins the source-only audit, raw audio, MIDI/SysEx, renderer, all frozen build files, analysis and scripts. Full closure data and listening outputs remain under ignored `build-fidelity/public-match-2026-09-20/rcs-a03-baseline/`. All seven local references on its generated page resolve. **14 HardwareComparisonTests and 13 TimbreMatrixTests passed**, each suite run once. No production DSP or older source/catalog pins were changed.
