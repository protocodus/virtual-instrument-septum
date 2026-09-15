# Exploratory 22.05 kHz fold/image check

2026-09-15. **No independently detectable 22.05 kHz fold/image family appears at the inherited threshold in these passages.** This does not exclude a properly bandlimited half-rate internal block. No engine, preset, original alias tool or its rate list changed.

## Method

[The separate diagnostic](../../../Tools/analyze_deepsonic_half_rate_images.py) uses a hash-verified copy of the [existing alias audit's](deepsonic-saw-aliases-2026-09-15.md) harmonic nuisance helper, its original-MIDI note selection and all six cached hardware/control WAVs. It verifies the original MIDI/MP3 identities, existing WAV hashes and unchanged helper before and after execution.

The exploratory family is `abs(22050 - h*f0)` for positive integer `h`, retaining 300–15000 Hz on **both** `22050-h*f0` and `h*f0-22050` branches. This includes images above 11025 Hz. Eight MIDI pitches are unchanged: 69/76/81/84/86/88/91/93. Each uses the existing 80 ms windows centered 100 and 160 ms after MIDI onset. The two windows overlap by 20 ms; their repetition is not independent statistical replication.

Candidate centers and spectral search bins must be more than 37.5 Hz from ordinary harmonics and from either `abs(44100-h*f0)` branch. All 255 candidate frequencies remain eligible for this particular note set: 125 on the first branch and 130 on the second. There are 510 line-windows per input. The existing quadratic complex harmonic-amplitude nuisance fit removes the nominal harmonic signal. Detection retains the same interior local peak within ±6 Hz, ≥12 dB prominence above the local residual median, and ≥−75 dB relative to H1. A repeated line must pass in both windows.

## Results

| Input | Passing line-windows | Repeated lines |
|---|---:|---:|
| Original SH-201 LP12 Q0 | 0 / 510 | 0 |
| Original SH-201 LP24 Q0 | 0 / 510 | 0 |
| Existing bandlimited negative, PCM | 0 / 510 | 0 |
| Existing bandlimited negative, MP3 | 0 / 510 | 0 |
| Existing injected 44.1 kHz family, PCM | 0 / 510 | 0 |
| Existing injected 44.1 kHz family, MP3 | 0 / 510 | 0 |
| New injected 22.05 kHz family, PCM | 64 / 510 | 32 / 32 planted |
| New injected 22.05 kHz family, MP3 | 64 / 510 | 32 / 32 planted |

The strongest genuine interior hardware candidates are −78.56 dB/H1 in LP12 and −78.97 dB/H1 in LP24, both below 9 dB local prominence. Three LP24 search-window maxima exceed −75 dB/H1, but are unrelated flanks rather than interior peaks; none passes the existing peak check.

For sensitivity, the new control adds the first two eligible parent harmonics on each branch for each note to the existing bandlimited negative, with fixed 0.0001 peak amplitude and the existing gate convention. All 32 planted lines survive in both windows, both before and after mono 320 kbit/s MP3 encoding. Detected levels span −60.09 to −60.04 dB/H1 in PCM and −60.32 to −59.89 dB/H1 after MP3; minimum MP3 prominence is 29.35 dB. These are synthetic sensitivity checks, not evidence of hardware architecture.

## Interpretation and reproduction

The main-harmonic notch near 10–11 kHz alone does not establish a 22.05 kHz processing stage. This diagnostic finds no corresponding independent image family at its stated threshold. Missing images cannot exclude a block whose input or output is properly bandlimited; these measurements do not identify every DSP block's execution rate.

[The durable JSON](deepsonic-half-rate-images-2026-09-15.json) records protocol, summaries, strongest candidates, hashes and runtime versions. Full line measurements and the copied helper are retained in ignored `build-fidelity/deepsonic/half-rate-images-v1/`. The raw result SHA-256 is `a6747b8c832dfff02222be81b08972660a712bfe91f7a3e85f64aac4384d1b2b`.

```sh
OPENBLAS_NUM_THREADS=1 python3 Tools/analyze_deepsonic_half_rate_images.py \
  --experiment-dir build-fidelity/deepsonic/saw-alias-audit-v2 \
  --output build-fidelity/deepsonic/half-rate-images-new
```

Use a new output directory. The original helper hash is pinned; if it changes, review or restore that exact source revision before rerunning.
