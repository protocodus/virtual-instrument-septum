# RCS A05 Jupiter8Perc — locked hardware-only excerpt

2026-09-20. The isolated attack near **63.164 seconds** in the [author demonstration](https://www.youtube.com/watch?v=8LKRnrs8DcQ) supports a short whole-patch comparison. The [locked case](../reconstructions/expanded/rcs-a05-jupiter8perc.json) spans **63.130–63.370 seconds**, with reconstructed MIDI **38**, velocity 100, onset 0.034 seconds and an artificial note-off at the crop boundary. No original performance MIDI is available; the downloaded SMF contains patch SysEx and zero note events.

The parent independently inspected a paused decoded A05 frame displaying **1:01** after 45 frame-forward keys from 60 seconds, then a fresh decoded A05 frame at the **65-second seek target**. The first clock has one-second precision; it is not a precise 61.000-second observation. The [supplementary catalog](../rcs-a05-reference-catalog.json) therefore accepts only **62–65 seconds**. The earlier attractive 60.520-second attack is excluded, as is A06 observed at 70 seconds. Slideshow labels do not establish live numeric controls, continuous patch state or exact transitions. Existing catalogs remain unchanged.

The [author page](https://www.rcssound.com/index.php?page=6) links this recording and the [original bank](https://www.rcssound.com/download.php?kod=6). Bank slot 5 is Jupiter8Perc. Its Upper square is physically −12 semitones and the pulse is unshifted; the Lower active sine is −12 semitones, with zero fine tune and tone octave. Early source windows 63.175–63.265 and 63.180–63.300 seconds both have a low-family Hann spectral peak at **36.674 Hz**, supporting sounding D1 and played D2/MIDI 38 under the published tuning and neutral system transpose. Zero padding interpolates the short-window peak; it does not provide independent frequency resolution. No pitch bend or retuning was fitted.

The waveform first exceeds absolute amplitude 0.01 at **63.163673 seconds**. The next strong attack edge is approximately **63.404830 seconds**, outside the crop. Pre-attack 63.050–63.150-second RMS is **52.81 dB below** the 63.180–63.290-second active interval. The synthetic crop-end note-off is not a measured release; original velocity, overlap and gate timing remain unknown.

The Upper filter is LP24, cutoff 106, depth −22, resonance 0 and envelope 24/127/127/127, with keyfollow and cutoff velocity both zero. Overdrive is enabled at 33. Upper amp ADSR is 0/42/12/0; Lower amp ADSR is 0/64/0/14. These changing layer levels make the mixed fundamental an uncertain normalization reference.

Actual original delay bytes are **`[0,49,12,65,4]`**. The [Roland MIDI Implementation](https://static.roland.com/assets/media/pdf/SH-201_MI.pdf), page 6, maps encoded feedback 0–98 onto −98% to +98%; the matching decoder computes `(wire−49)*2`, so byte 49 is verified **0% feedback**. HF-damping index 12 is **3150 Hz**. Upper delay send is **127**, Lower send **0**, modulation rate **65** and modulation depth **4**. Global delay is on; reverb is off. Raw time 0 does not mean the delay is disabled: a single modulated wet tap remains even with zero feedback. These are original bytes, not parameters selected to match the recording.

The fixed earlier closure metric was applied to source PCM before any A05 software rendering: high/low power ratio using 1500–12000 Hz and 300–1500 Hz, Hann windows 512/1024/2048, 44-sample hops, L/R/mid channels, ±10 ms onset uncertainty, a 15–35 ms early reference, sustained 10 ms crossings, and a 30 ms guard before the artificial note-off. The hardware STFT grid starts at 63 seconds.

| Relative ratio drop | Observed / 27 | Minimum elapsed | Median elapsed | Maximum elapsed |
| --- | ---: | ---: | ---: | ---: |
| 10 dB | 27 | 35.16 ms | 40.81 ms | 54.80 ms |
| 20 dB | 27 | 40.35 ms | 52.30 ms | 66.77 ms |
| 30 dB | 26 | 57.11 ms | 63.94 ms | 76.75 ms |

These landmarks are spectral changes, **not filter attack-duration measurements**. High-band power reaches the recording/codec floor near 100 ms after onset; later ratio rebound cannot be interpreted as renewed filter opening. L/R PCM correlation is 0.9657 over 63.180–63.300 seconds, and early H2–H8 channel differences reach about 5 dB. The active modulation delay remains material despite its small depth setting. Mid-channel periodic-fit residual grows from about 2% to 7% as the waveform decays. This is a useful qualified whole-patch attack reference, not a dry oscillator or unique filter-endpoint measurement.

[The JSON audit](rcs-a05-hardware-observations-2026-09-20.json) retains all source/patch/case/catalog hashes, source-only scripts, harmonic observations and closure settings. Case SHA-256 is `0b0743e1b98210710edec60ef1e01d4046286ab0324e724d87f437d3b8979a66`; original SysEx SHA-256 is `584a1e75e2cfb735cab9bd3f26c56429f9cbcf655f1486e941ba0112bdf9dd7d`. This source-only lock precedes baseline characterization; no modified A05 candidate informed selection.
