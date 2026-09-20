# Juicy Fat static-filter screen — 2026-09-20

**Unsupported as an isolated cutoff calibration.** Juicy Fat is the most promising unused named reference in the existing cache, but its opening does not separate its static pulse from its moving saw layer. No DSP, original patch or MIDI reconstruction changed. [Measurements and provenance](juicy-fat-static-cutoff-screen-2026-09-20.json) retain the exact result.

The catalog contains **24 named-preset recordings and eight FX category montages**, not 32 identified presets. After the existing 13 comparisons and prior Sequence Bs/Choir screens, Juicy Fat is the only remaining dry candidate with a static basic oscillator. Other unused named cases involve Super Saw/feedback sources, filter modulation, synchronization, overdrive or substantial effects; the JSON records the screen. The eight montages cannot identify one patch.

[Roland's Juicy Fat demo](https://www.rolandus.com/go/sh-201_patches/mp3/BASS/TOP8_JuicyFat.mp3) is associated by name with record 7 of its [BASS bank](https://www.rolandus.com/go/sh-201_patches/patch_bass.html). The original patch has two active tones and globally disabled delay/reverb. Upper emits one pulse at PW64, with static LP12 cutoff43/resonance33: no filter envelope depth, key follow, cutoff velocity modulation, filter LFO or overdrive. Lower emits detuned saws an octave apart through LP24 cutoff12/resonance50, envelope depth25 and ADSR21/52/40/38. Both Lower saws overlap the Upper pulse's odd harmonics. Lower's octave saw also contributes strong even harmonics.

A hardware-only spectrogram selected the opening ~65.4 Hz note. The most stationary tested region is centered at **0.230 s**, with 50, 70 and 90 ms widths. Its fitted fundamental is 65.450–65.546 Hz across left, right and mid. The Lower saw is nominally only four cents below the Upper pulse: about **0.151 Hz** separation, whose inverse is **6.62 s**. The short note cannot resolve those source amplitudes independently.

At 0.230 s / 70 ms / mid, harmonics H2, H4, H6, H8 and H10 are −4.46, −17.64, −15.83, −13.20 and −12.43 dB relative to H1. In particular, H8/H10 exceed their neighboring odd harmonics by roughly 7–10 dB. The second layer remains prominent; it cannot be treated as a negligible background.

To test identifiability, a deliberately conditional fit treats odd harmonics H3…H15 as one ideal pulse followed by LP12, keeping the existing raw33 damping at 0.665227. Only cutoff varies. The apparent cutoff changes with measurement width:

| Mid-channel width | Apparent cutoff | Shape residual |
|---|---:|---:|
| 50 ms | 1067.369 Hz | 3.466 dB |
| 70 ms | 1166.937 Hz | 0.985 dB |
| 90 ms | 1603.579 Hz | 1.584 dB |

Across channels the apparent range is 1066.258–1608.011 Hz, versus the incumbent raw43 mapping of 209.057 Hz. **These apparent values are not hardware cutoff estimates.** A sub-1 dB fit in one window is misleading when the overlapping moving layer contributes at every fitted frequency. Removing low odd harmonics or changing neighboring windows does not establish a stable isolated source. Earlier/later opening windows also produce substantial harmonic-model residuals and frequency fits at the search boundary.

The useful result is the rejection criterion: require independently separable source harmonics or a demonstrably negligible second layer before interpreting such a large apparent cutoff discrepancy. Original velocities, gates, controller state and recorded patch revision remain unknown. A dry isolated oscillator capture with static filter settings could test the shared cutoff/resonance laws; this mixed opening cannot justify changing them. This is a bounded rejection of the selected region, not a claim that the complete recording contains no recoverable information.
