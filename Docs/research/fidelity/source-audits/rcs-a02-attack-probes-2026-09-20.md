# RCS A02 attack probes — fixed spectral-closure metric

2026-09-20. **No supported first-note timing winner.** The frozen baseline and filter-only attack probes targeting 50, 100 and 150 ms at raw 24 fail the hardware's sustained 10/20/30 dB spectral-ratio closure test. All 81 first-note landmarks per software variant are censored. No missing value is converted to zero, and no fallback metric selects a candidate.

The original hardware analysis is preserved: high-band power (1500–12000 Hz) divided by low-band power (300–1500 Hz), Hann windows of 512/1024/2048 samples, 44-sample hops, left/right/mid channels, ±10 ms assumed-onset shifts, median early reference at 15–35 ms, 10 ms continuously below each drop threshold, and a 30 ms guard before reconstructed note-off. The existing hardware observations were reproduced **exactly**, including all crossing times and censored values.

Software uses raw float WAVs without gain adjustment, EQ or time fitting. The known retained renderer latency is removed from analysis timestamps only: `source time = 21.18 + STFT time − 93/44100`. The PCM is not shifted or resampled. The original sample grids differ by their known origins; no grid is fitted to improve agreement.

| First-note source | 10 dB crossing | 20 dB crossing | 30 dB crossing |
| --- | --- | --- | --- |
| Hardware | 60.48 ms median (53.47–73.11) | 76.44 ms (65.62–88.07) | 86.42 ms (77.41–101.04) |
| Frozen baseline | Censored 27/27 | Censored 27/27 | Censored 27/27 |
| Attack 50 ms probe | Censored 27/27 | Censored 27/27 | Censored 27/27 |
| Attack 100 ms probe | Censored 27/27 | Censored 27/27 | Censored 27/27 |
| Attack 150 ms probe | Censored 27/27 | Censored 27/27 | Censored 27/27 |

The 1024-sample, mid-channel, unshifted first-note trace explains the censoring. Before the gate guard, the hardware reaches −40.83 dB relative to its early reference. Baseline reaches only −6.28 dB; the 50 and 100 ms probes have brief periodic dips to −11.19 and −11.67 dB, with at most three and two contiguous frames below −10 dB (about 3 and 2 ms). The 150 ms probe reaches only −4.03 dB. These are descriptive checks of the fixed metric, not substitute selection criteria. Neither band reaches the numerical `1e-20` power floor; software's first-note minimum high-band powers are approximately `2.8e-7` to `3.0e-6`.

The other four notes are reported separately as sensitivity observations from **the same recording**. Every software variant also censors all 324 later-note landmarks. Hardware observes every later-note landmark except nine of 27 observations for the third note's 30 dB drop. Software traces on later notes mostly coincide across attack probes: the higher notes remain nearly flat relative to their early reference, while lower notes show short periodic dips. Unknown overlap and mono retrigger history can influence these later notes, so they do not independently determine an attack curve. The first-note failure remains separate from that concern.

All four software WAVs are finite, nonzero, unclipped, 44.1 kHz stereo, and agree with their stored output hashes and frame/peak metadata; no degraded replay or active voices remain at the end. MIDI, original SysEx, replay events and renderer settings match across variants. Renderer binaries, build manifests, frozen input files and original source maps were verified. Input and source hashes are retained in [the JSON summary](rcs-a02-attack-probes-2026-09-20.json).

The focused reproducible tool is `Tools/analyze_rcs_attack_probes.py`; full observations and the inspected plot are in ignored `build-fidelity/rcs-attack-probes-2026-09-20/closure-comparison-verified/`. Its `--help` documents explicit input paths. The metric tests combined filter, drive and layer-balance behavior. **A spectral crossing's elapsed time is not an attack duration**, and improved whole-excerpt spectral error alone does not establish this temporal closure behavior.
