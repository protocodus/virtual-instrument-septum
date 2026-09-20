# RCS candidate checks — 20 September 2026

Two newly identified author patches reject the previously proposed global triangle and cutoff changes. A separate attack-time experiment improves a broad spectral score but fails the predeclared temporal measurement. **No candidate is promoted; production DSP is unchanged.** These are conditional comparisons with reconstructed performance MIDI.

The [source audit](rcs-reference-screen-2026-09-20.md) establishes the author, public audio, patch-bank identities and visible video labels. The [A01 transcription](rcs-a01-transcription-2026-09-20.md) and [A02 transcription](rcs-a02-hardware-observations-2026-09-20.md) were selected from hardware before software rendering. Both patches have no active internal delay/reverb contribution, but both include overdrive. The exact performed patch revision and system/recording controls remain unverified.

## Previously proposed models

| New reference | Fixed model hypothesis | Current broad residual | Candidate |
| --- | --- | ---: | ---: |
| A01 Moog BASS, three separated notes | Triangle polarity inverted, gain 1.5 | 3.469 dB | 5.470 dB |
| A02 Moog BASS PW, five-note phrase | Air Lead cutoff interpolation | 10.696 dB | 15.593 dB |

The broad metric is the existing normalized stereo 32-band Welch residual, 25–12,500 Hz. It is not a perceptual or overall-fidelity score. Source/MIDI/preset/settings identities match in each pair. Listen to [A01](http://127.0.0.1:8920/rcs-a01-listen/) and [A02](http://127.0.0.1:8920/rcs-a02-listen/).

A01 also worsens under the existing harmonic estimator. Its median H2–H8/H1 error increases from 2.503 to 8.468 dB; odd H3/H5/H7/H1 increases from 2.466 to 9.093 dB. All 27 note/channel/window-shift groups worsen, with H2–H8/H1 increases of 5.557–6.517 dB. These groups test sensitivity within one performance; they are not 27 independent recordings. Overdrive, filter velocity response and unknown phase prevent attributing every residual solely to triangle shape. They still provide a strong conditional guard against the proposed global change.

The ignored `build-fidelity/rcs-candidate-validation-2026-09-20/analyze_triangle.py` invokes the existing waveform cross-check estimator on the locked A01 case. Its output pins that script, the estimator, WAVs, renderer manifests and comparison inputs. The [machine-readable audit](rcs-candidate-checks-2026-09-20.json) retains summaries and artifact hashes.

## Filter attack probes

The [hardware-only closure measurement](rcs-a02-closure-2026-09-20.md) finds repeated 10/20/30 dB drops in the high/low spectral-power ratio around 60–100 ms after the five A02 attacks. The long fourth note continues for about 271 ms, separating the closure from its release. The current raw24 filter attack is about 5 ms.

Three predeclared candidates changed only the filter attack table. For raw control `r`, they use `0.001 + 4.999 × (r/127)^p`, with `p` chosen to make raw24 last 50, 100 or 150 ms. Raw0 and raw127 remain 1 ms and 5 seconds. The intervening law and endpoints are hypotheses, not recovered hardware measurements. Amp and pitch envelopes retain their existing maps.

| Conditional raw24 duration | A02 broad residual | Brassy Ld1 broad regression |
| --- | ---: | ---: |
| Current: 5.001 ms | 10.696 dB | — |
| 50 ms | 7.748 dB | +0.236 dB |
| 100 ms | 6.221 dB | +0.549 dB |
| 150 ms | 5.486 dB | +0.698 dB |

Despite the attractive broad scores, **none reproduces the predeclared sustained 10/20/30 dB closure landmarks on the first note**. Missing crossings remain censored, never treated as zero timing error. The same fixed bands, three window lengths, three channels and ±10 ms onset sensitivity are applied to hardware and software, with the documented 93-sample engine latency accounted for. Slower attack alone does not explain the hardware's much deeper brightness drop.

Across all fifteen named cases, 39 additional renders plus six reused A01/A02 renders provide a global-interpolation regression check. Eight earlier presets are byte-identical controls. Brassy Ld1 worsens for all three tables; some other cases improve. No aggregate score selects a winner. All renders are finite, unclipped, retain 93-sample latency and have zero active voices at the end; the maximum peak in this regression set is 0.666274.

Original A02 performance gates remain unknown. The neutral adjoining-gate reconstruction can reuse an active SOLO voice whose envelope has not returned to zero, suppressing later attack sweeps in the current model. Therefore first-note failure is the primary timing result; later-note behavior also needs gate-history sensitivity. Neither an inferred gap nor an inferred envelope reset can be treated as original hardware MIDI.

The subsequent [gate sensitivity](rcs-a02-gate-closure-2026-09-20.md) tests 5/15 ms gaps and 15 ms overlaps in the baseline and 150 ms probe. Both hardware and software are measured only before the earlier of the original/variant release minus the same 30 ms guard. All six software variants still have no sustained closure landmarks. Hardware's first-note 10/20 dB landmarks remain observed in every variant; the shortest common interval correctly censors its 30 dB result. This preserves the first-note rejection without letting a changed release masquerade as filter closure.

The [terminal-model trace](rcs-a02-terminal-model-2026-09-20.md) verifies the original bytes and finds no clear implementation bug. In the current model, raw cutoff120 and depth−22 end at 765.506 Hz regardless of attack time. Post-filter overdrive can regenerate high harmonics. At the held-note endpoint, the measured high/low ratio is −13.212 dB for software versus −58.714 dB for hardware. Cutoff with negative envelope depth, waveform/DC behavior with overdrive, and retrigger history remain coupled unknowns; the new evidence does not identify a unique global correction.

## Reproduction

Use `Tools/compare_hardware.py` with `--catalog Docs/fidelity/rcs-reference-catalog.json`, the audited source directory, the frozen renderer and the explicit A01/A02 case. The default catalog remains Roland's official demos. Author-catalog excerpts must remain inside the audited label interval.

`Tools/analyze_rcs_a02_closure.py` measures the pinned hardware crop. `Tools/analyze_rcs_attack_probes.py` reapplies that unchanged metric to manifest-verified renders. The ignored `build-fidelity/rcs-attack-probes-2026-09-20/` directory retains each experimental profile, frozen build, render, run script, design and regression manifest. No third-party media or preset payload is added to Git.
