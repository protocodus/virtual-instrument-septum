# Moogie 1: octave notes and temporal harmonic audit

The baseline transcription omits **three brief high Eb notes**. An independent hardware-only check supports MIDI 75 at approximately **0.400–0.495, 1.315–1.410 and 2.245–2.335 seconds**, followed by MIDI 63. These pitches undo the published preset's −36-semitone oscillator tuning. The revision contains 16 notes, remains explicitly reconstructed MIDI, and preserves the 13-note baseline. [Roland's named recording and bank](https://www.rolandus.com/go/sh-201_patches/patch_bass.html), [original MP3](https://www.rolandus.com/go/sh-201_patches/mp3/BASS/TOP8_Moogie1.mp3)

## Independent evidence for the octave revision

The three brief segments have a waveform period near **12.90 ms**, approximately 77.5 Hz. Their following low notes repeat near **25.90 ms**, approximately 38.6 Hz. At the low pitch's harmonic grid, the brief segments suppress the total odd-harmonic power by **39.5–46.8 dB** relative to even harmonics. The following low notes instead have odd-harmonic power about **9.6 dB above** even harmonics. An already-transcribed high Eb segment gives the same short period and −42.3 dB odd/even ratio.

| Hardware segment (s) | Best period near 13 ms | Normalized waveform difference at that period | Odd/even harmonic power |
|---|---:|---:|---:|
| 0.435–0.480 | 12.902 ms | 0.00056 | −44.65 dB |
| 1.345–1.380 | 12.902 ms | 0.00033 | −39.51 dB |
| 2.270–2.310 | 12.902 ms | 0.00080 | −46.84 dB |
| 0.785–0.895, previously identified high note | 12.925 ms | 0.00051 | −42.26 dB |
| 0.545–0.690, following low note | 12.744 ms | 1.79629 | +9.60 dB |

A static recording EQ cannot repeatedly turn the same low note into these brief double-frequency waveforms while restoring the odd harmonics afterward. Phase cancellation is also a weaker explanation than octave notes: the pattern is repeated three times, suppresses all measured odd harmonics, and matches the already-identified high notes. Unknown controller or waveform changes cannot be strictly excluded without original MIDI. Exact transition times remain approximately **20 ms uncertain**; release overlap and velocity remain unknown.

The alternate event file is [moogie-1-octave-revision.json](moogie-1-octave-revision.json). It does not overwrite [the baseline](../reconstructions/moogie-1.json). Render this revision separately before updating whole-excerpt comparisons; no DSP parameters were fitted or changed.

## A timbral discrepancy that survives constant EQ

Within three held low Eb notes that do not contain the omitted octave events, the hardware's third-harmonic/fundamental amplitude ratio changes substantially over time. The baseline render is nearly stationary after the first 35 ms.

| Baseline note-on | Hardware change in H3/H1 | Septum change in H3/H1 | Hardware range with ±25 ms window shift | Septum range with ±25 ms shift |
|---|---:|---:|---:|---:|
| 0.029 s | +7.58 dB | +0.03 dB | +4.00 to +7.58 dB | −0.02 to +0.03 dB |
| 0.939 s | +8.98 dB | −0.04 dB | +0.85 to +8.98 dB | −0.04 to +0.03 dB |
| 1.901 s | +7.73 dB | +0.16 dB | +7.20 to +8.26 dB | +0.01 to +0.40 dB |

This is a **diagnostic target, not an identified DSP correction**. Comparing the same harmonic ratio at two times approximately cancels a fixed recording gain and fixed linear frequency response. Unknown dynamic processing, relative oscillator phase, filter/envelope behavior and undocumented controllers remain possible explanations. A sum of two independently filtered tones can change a harmonic by cancellation; the data do not justify fitting a single cutoff or decay constant. The most robust of these three timing checks is the note starting at 1.901 seconds.

## Reproducible method and limits

[The JSON report](moogie-harmonic-audit.json) records source hashes, each segment, all measured periods and residuals, harmonic-window shifts and library versions. Inputs are the existing `comparison-final/moogie-1/hardware-excerpt-raw.wav` and `septum-raw.wav`. Hardware analysis uses the mean of its two float PCM channels, with no level match, EQ or pitch correction. The underlying original MP3 hash is also recorded.

For each selected hardware segment, subtract its mean. For each integer lag within ±1.5% of `44100/77.3` and `44100/38.65`, compute:

```python
x0, x1 = x[:-lag], x[lag:]
error = mean((x0 - x1)**2) / (mean(x0**2) + mean(x1**2))
```

Report the lag minimizing this normalized difference. A near-zero value identifies a repeating waveform; the low notes have a small residual at approximately 26 ms but a large residual near 13 ms.

Harmonic amplitudes come from simultaneous least squares using a constant, centered time, and sine/cosine terms for harmonics 1–12, sampled every fourth PCM frame. The constant and slope prevent slow offset tails from leaking into the harmonic estimates. For the octave table, optimize a high-octave frequency from 76–79 Hz, then fit the harmonic grid at half this frequency and sum odd/even squared amplitudes. Regression residual power is roughly 0.6–1.7% in these selected windows.

For temporal changes, estimate each low note's fundamental within ±3% of nominal across note-on +30 ms to note-off −20 ms. Compare windows **35–115 ms after note-on** and **105–25 ms before note-off**, and repeat both windows with −25/0/+25 ms shifts. Include Septum's retained 93-sample latency when placing its windows. Compute `20*log10((H3/H1)_late / (H3/H1)_early)`. Stable source frequency and locally steady recording response are assumptions; a fixed EQ's long transient or a time-varying processor may violate the cancellation argument.

This audit establishes one transcription correction and a bounded temporal discrepancy. It does not measure percentage hardware accuracy or identify a uniquely correct replacement for the engine's envelope, filter or oscillator models.
