# Sexy Back: hardware-only opening transcription

Date: 2026-09-20. [Roland's public BASS page](https://www.rolandus.com/go/sh-201_patches/patch_bass.html) names Sexy Back, identifies it as patch 6, and provides both the [hardware recording](https://www.rolandus.com/go/sh-201_patches/mp3/BASS/TOP8_SexyBack.mp3) and [published bank](https://www.rolandus.com/go/sh-201_patches/shl/SH-201_Patch_BASS.zip). Both are freely downloadable; their hashes match the existing source catalog. No original performance MIDI or authentication of the exact recorded patch revision is available.

The [new reconstruction](../reconstructions/expanded/sexy-back.json) covers the first 1.2 seconds: three separated estimated E-flat2 / MIDI 39 notes, with placeholder velocity 100. The unchanged bank is suitable for checking a higher static cutoff region than the previous diagnostic examples. This transcription used only the official audio and published bank, with no renderer output or DSP parameter search.

## Tuning evidence

Both tone octaves are zero. The current WIDE-aware codec maps the preset as follows:

| Oscillator | Raw signed coarse | WIDE | Physical coarse | Fine | Predicted frequency at MIDI 39 |
| --- | ---: | --- | ---: | ---: | ---: |
| Upper Super Saw 1 | +36 | Off | +12 | +13 cents | 156.736 Hz |
| Upper Super Saw 2 | −12 | On | −12 | −15 cents | 38.555 Hz |
| Lower triangle | −24 | On | −24 | −26 cents | 19.156 Hz |
| Lower saw | +24 | On | +24 | 0 | 311.127 Hz |

The first and third settled windows contain low-frequency peaks around 19.18 and 38.69 Hz. Higher families near 155, 312, 623, 934 and 1244 Hz support the same octave allocation. Median peak/harmonic frequencies for the nominal lower-saw family are 311.70, 311.12 and 311.42 Hz across the three notes. This is note-family evidence, not proof of isolated oscillator frequencies: upper-supersaw harmonics overlap the lower saw, detuning spreads the peaks, and the second note is too short to resolve the lowest oscillator precisely.

The inferred gates are 0.087–0.356, 0.425–0.565 and 0.806–1.008 seconds. An independent 300–5000 Hz energy trace first exceeds its threshold at 0.091, 0.428 and 0.809 seconds and falls below it after 0.355, 0.564 and 1.007 seconds. The onset estimates allow a few milliseconds for the initial pitch transient. Gate uncertainty is approximately 10 ms, not sample accuracy. The excerpt includes the third note's tail and ends before the next attack around 1.25 seconds.

## What this case can establish

The upper LP24 cutoff is 111 and lower LP12 cutoff is 95. Both tones have zero resonance, filter-envelope depth, filter-velocity sensitivity and filter-LFO depths. That makes this an additional published-preset reference for checking static cutoff behavior.

It cannot isolate a cutoff transfer function. The upper tone has two detuned Super Saws, negative pitch-envelope depths −35/−33, portamento time 4 and SOLO+LEGATO mode. The lower triangle also has pitch-envelope depth −34, and the lower tone has overdrive and LOW CUT. Both tones feed the enabled delay and have amplifier velocity sensitivity +8. Original velocities, controllers and recording processing remain unknown. These confounders must remain visible in any subsequent sound comparison.

## Reproduction and artifacts

[The audit script](../../../Tools/analyze_sexy_back_transcription.py) verifies pinned MP3 and bank hashes, decodes the hardware MP3, reads exact tuning bytes, reports settled spectral families and energy boundaries, and produces a diagnostic plot. It does not call an engine renderer.

```sh
python3 Tools/analyze_sexy_back_transcription.py \
  --sources build-fidelity/hardware-benchmark/sources \
  --output NEW_DIRECTORY
```

[The measurement JSON](sexy-back-transcription-2026-09-20.json) is retained in Git. Decoded audio and the visually inspected `hardware-note-evidence.png` remain in the ignored `build-fidelity/hardware-benchmark/sexy-back-transcription-2026-09-20/` directory. Syntax, source hashes, JSON parsing and note gate bounds/order passed. No third-party audio or preset bytes were added to Git.
