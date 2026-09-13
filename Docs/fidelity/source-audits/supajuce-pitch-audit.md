# SupaJuce 1: independent WIDE octave check

The hardware recording supports a **2:1 oscillator-frequency ratio** on all six opening notes. The archived old render instead produces 8:1; the corrected render restores 2:1 with identical MIDI, original preset bytes and replay settings. This is strong evidence for the +12-semitone interpretation of stored coarse100 with WIDE off, conditional on the named audio/preset association. It does not calibrate every intermediate raw value or WIDE-on behavior.

The source is Roland's [SupaJuice 1 demo link](https://www.rolandus.com/go/sh-201_patches/mp3/LEAD/TOP8_SupaJuce1.mp3), associated with `SupaJuce 1` in its [LEAD patch bank](https://www.rolandus.com/go/sh-201_patches/patch_lead.html). MP3 SHA-256: `e9c1dbe5cddf241f69b0d7b044201bb18e212345dc080c35a09001cb9afe103f`. Exact input hashes, patch summaries and source URLs are retained in [the quantitative JSON](supajuce-pitch-audit.json).

The published active Upper tone uses two square oscillators, MIX, OSC1 coarse100/WIDE0, OSC2 coarse64/WIDE0, and tone OCTAVE −1. Measured lower oscillator frequencies are **329.479, 219.916, 219.915, 219.914, 293.521 and 195.901 Hz**, corresponding to sounding E4, A3, A3, A3, D4 and G3. Given the published tone octave and unchanged system tuning, reconstructed played notes 76, 69, 69, 69, 74 and 67 are consistent. Original performance MIDI, velocities, gates, system settings and exact recorded patch revision remain unknown.

In the first, least-contaminated window (0.163–0.218 s), hardware harmonics H2/H1, H6/H1, H10/H1 and H14/H1 are +12.2, +1.8, +1.1 and +1.9 dB. H4/H1 and H8/H1 are −32.4 and −49.1 dB. That H2/H6/H10/H14 family is the odd harmonics of a square at twice the lower frequency. The old render instead has H8/H1 at +7.3 dB and essentially absent H2/H1 (−72.7 dB). The corrected render places H2/H1 at +4.2 dB and suppresses H8/H1 to −53.4 dB.

| Note | Hardware power in octave-square family | Before | After | Harmonic-energy distance, before → after |
|---|---:|---:|---:|---:|
| 1 | 0.932 | <0.001 | 0.722 | 0.945 → 0.265 |
| 2 | 0.855 | <0.001 | 0.809 | 0.883 → 0.258 |
| 3 | 0.880 | <0.001 | 0.807 | 0.893 → 0.222 |
| 4 | 0.898 | <0.001 | 0.769 | 0.909 → 0.214 |
| 5 | 0.910 | 0.051 | 0.752 | 0.872 → 0.208 |
| 6 | 0.821 | <0.001 | 0.662 | 0.867 → 0.206 |

Power fractions use the modeled first 24 harmonics. Distance is total variation between normalized harmonic-energy distributions, from 0 (identical) to 1 (disjoint), not a percentage hardware-fidelity score. Each analysis window starts 40 ms after reconstructed onset and ends at the earlier of onset+95 ms or note-off−15 ms. Fits use the channel mean, a constant/trend, and joint sine/cosine coefficients; rendered windows include 93 samples of latency. Later notes contain delay/reverb or prior-note tails, with fit residual power 4–17%; the first hardware window has 2.5% residual and is the strongest isolated check.

**Residual:** the upper harmonic family is still too weak and rolls off too much. The first note's corrected H14/H2 is 11.6 dB below hardware, and notes 2–5 are approximately 8.0–10.6 dB low. Whole-excerpt power centroid changes from 1711 Hz before to 697 Hz after, versus hardware 1642 Hz. The old centroid was coincidentally close because it put the main oscillator in the wrong octave; the corrected pitch family is closer even though the overall sound remains darker. No further oscillator/filter parameters were fitted in this audit.

Reproduce the measurements with:

```sh
OPENBLAS_NUM_THREADS=1 python3 Tools/analyze_supajuce_octaves.py \
  --root build-fidelity/hardware-benchmark/wide-pitch-implementation \
  --output Docs/fidelity/source-audits/supajuce-pitch-audit.json
```

The [script](../../../Tools/analyze_supajuce_octaves.py) verifies identical MIDI, SysEx, hardware audio and settings across both renders, and verifies WAV hashes against their manifests. The lower-frequency search refines the supplied hardware-only pitch hypotheses within ±1.5%; it does not recover original note numbers independently of system/tone tuning. No shipping source was changed.
