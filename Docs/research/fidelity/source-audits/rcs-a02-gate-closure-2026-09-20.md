# RCS A02 closure — separate gate sensitivity

2026-09-20. The [primary attack-probe result](rcs-a02-attack-probes-2026-09-20.md) remains unchanged: no supported timing winner. A separate check of six gate variants also yields **zero observed software crossings**, with all 405 landmarks censored for each variant.

The frozen baseline and 150 ms attack probe were each replayed with the first four note-offs moved 5 ms earlier, 15 ms earlier, or 15 ms later. Onsets, pitches, velocities, final note-off, duration and published patch stayed fixed. These are explicitly invented gaps/overlaps testing uncertainty in one reconstructed performance, not independent hardware observations or a search for preferred performance MIDI.

The same bands, windows, early reference, onset shifts, 10 ms sustained threshold and 30 ms guard were retained. For this sensitivity only, both hardware and software are measured before **`min(original note-off, variant note-off) − 30 ms`**. This common interval avoids counting changed releases as envelope closure. The largest centered Hann window plus median-filter future support is 25.215 ms; assertions verify that all included windows stay before either release. Shortened common intervals can censor additional hardware landmarks, which are retained as missing rather than assigned zero.

| Gate variant | Hardware note 1 observed counts: 10/20/30 dB | Hardware note 2 | Hardware note 3 | Hardware note 4 | Hardware note 5 |
| --- | --- | --- | --- | --- | --- |
| 5 ms earlier | 27 / 27 / 24 | 27 / 27 / 18 | 27 / 27 / 9 | 27 / 27 / 27 | 27 / 27 / 27 |
| 15 ms earlier | 27 / 27 / 0 | 27 / 24 / 0 | 27 / 6 / 0 | 27 / 27 / 27 | 27 / 27 / 27 |
| 15 ms later | 27 / 27 / 27 | 27 / 27 / 27 | 27 / 27 / 18 | 27 / 27 / 27 | 27 / 27 / 27 |

All software counts in this table are **0 / 0 / 0** for both tested renderers. Thus the first-note 10 and 20 dB failures survive every tested gate change. The shortest common interval cannot assess its hardware 30 dB crossing, so no 30 dB timing conclusion is drawn from that interval.

The script validates original and variant case/MIDI hashes and actual renderer replay events, allowing only the declared four note-off changes. It verifies unchanged patch/renderer/settings, all frozen build sources, finite unclipped WAVs, 93-sample retained latency and zero ending voices. The first 6703 PCM frames match each model's original render exactly. Known latency is removed from time coordinates only; no EQ, gain or time fit is used.

[The JSON summary](rcs-a02-gate-closure-2026-09-20.json) pins inputs and results. Full observations and the bounded wrapper are in ignored `build-fidelity/rcs-attack-probes-2026-09-20/gate-robustness/`: `common-interval-closure-analysis/analysis.json` and `analyze_closure.py`. The wrapper imports the pinned, unchanged `Tools/analyze_rcs_attack_probes.py` metric. An earlier original-guard exploratory output in `closure-analysis/` is superseded by the common-interval result and is not used for conclusions. No production DSP was changed, and spectral crossing elapsed times are not attack-duration measurements.
