# RCS A02 hardware endpoint — 2026-09-20

The long fourth note retains a strong second harmonic after its high frequencies close. Under the published patch and a linear capture chain, the Upper tone remains audible; nearly muting it and leaving the Lower sine is not a successful endpoint match. This does not identify a unique cutoff or envelope depth.

The [author video](https://www.youtube.com/watch?v=8LKRnrs8DcQ) labels A02 at 20, 25 and 30 seconds. Its [published bank](https://www.rcssound.com/index.php?page=6) has an Upper square one octave below the key plus a pulse at key pitch, overdrive enabled, and a negative filter envelope. The Lower has one active sine one octave below the key, no overdrive and a static filter. Original performance MIDI, live control state, oscillator phase and capture processing are unavailable. The [source audit](rcs-a02-hardware-observations-2026-09-20.md) records these qualifications.

## Long fourth note: endpoint characterization

The reconstructed fourth note runs approximately 21.621–21.892 seconds, sounding near 103.8 Hz. Joint DC, linear-trend and 16-harmonic least squares measured windows centered at 21.830, 21.840 and 21.850 seconds, with widths 30, 40 and 60 ms. The frequency search used hardware PCM only. All windows end by 21.880 seconds. Left, right and mid channels were checked in YouTube Opus and the aligned SoundCloud MP3: 54 measurements of one performance. These are sensitivity checks, not independent recordings or an untouched holdout; the later hardware closure was already observed.

| Late quantity | Median | Observed range |
| --- | ---: | ---: |
| H2/H1 amplitude, dB | −7.029 | −7.132 to −6.898 |
| H3/H1 amplitude, dB | −22.765 | −23.119 to −22.289 |
| H4/H1 amplitude, dB | −31.504 | −31.816 to −30.780 |
| H2+ fraction of modeled periodic power | 16.95% | 16.60–17.39% |
| Best sine-only residual power | 16.99% | 15.89–17.92% |
| Full harmonic-model residual power | 0.073% | 0.032–0.223% |
| H2 phase minus twice H1 phase | −14.79° | −18.36 to −12.07° |

The matched-encode H2/H1 differences are at most 0.045 dB; H3 and H4 differences are at most 0.161 and 0.275 dB. This supports the strong low harmonic observation despite lossy encoding. It is not a second hardware reference.

In the representative YouTube mid-channel 40 ms window at 21.840 seconds, H1–H4 peak amplitudes are 0.19419, 0.08641, 0.01386 and 0.00514 in normalized PCM units. In the early window at 21.661 seconds they are 0.41572, 0.17816, 0.08106 and 0.11420. H1 and H2 each fall by about 6–7 dB, while H4 falls about 27 dB. The endpoint is dominated by H1 and H2, not H1 alone. Absolute amplitudes include the unknown capture gain and both amp envelopes.

With a near-pure Lower sine and linear capture, the H2+ content must come from Upper. A Lower-only explanation would instead require roughly 45% harmonic distortion by amplitude, principally H2, despite its disabled overdrive. Such an alternative is not mathematically excluded because actual sine purity and the capture chain were not measured. The two tones share H1, so their separate fundamental amplitudes cannot be recovered from this recording. Upper overdrive and its bias can redistribute harmonics; phase also mixes oscillator, filter and recording effects. Endpoint data alone cannot separate a lower base cutoff from stronger negative envelope depth.

## First-note training spectra

These source-only measurements characterize the first note for the parent's parameter-grid training; they are separate from the long-note endpoint validation. Each 40 ms window is centered 80, 90 or 100 ms after the estimated 21.210-second onset. The final window ends at 21.330 seconds, only 2 ms before the earliest plausible release estimate. Exact gating and codec pre-ringing remain uncertainties.

The following are YouTube mid-channel measurements using a jointly fitted DC/trend and 40 harmonics. Each row independently estimates its frequency from hardware audio; the changing waveform can bias that estimate, so these values must not be interpreted as hardware master tuning.

| Elapsed center | Fitted Hz | H2/H1 | H3/H1 | H4/H1 | H5/H1 | H6/H1 | H7/H1 | H8/H1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 80 ms | 51.2742 | −5.160 | −12.662 | −9.202 | −16.161 | −19.789 | −19.423 | −21.443 |
| 90 ms | 51.1567 | −4.831 | −12.313 | −8.940 | −15.850 | −19.832 | −19.287 | −20.984 |
| 100 ms | 51.0441 | −4.861 | −11.950 | −8.737 | −15.892 | −19.481 | −19.813 | −21.853 |

Harmonic ratios are amplitude dB. Fit residuals are 0.33–0.51% of signal variance. The [JSON](rcs-a02-endpoint-2026-09-20.json) retains both platforms' mid-channel measurements and endpoint summaries; the full ignored analysis also retains L/R observations. These short first-note windows contain only about two cycles and still change spectrally, which limits precise phase interpretation.

## Reproduction and validation

Run from the repository root:

```sh
OPENBLAS_NUM_THREADS=1 python3 Tools/analyze_rcs_a02_endpoint.py \
  --output build-fidelity/hardware-benchmark/rcs-reference-screen-2026-09-20/hardware-endpoint/analysis.json
```

The analyzer verifies source and alignment hashes, 44.1 kHz floating stereo PCM, finite/non-silent data, crop duration, fit rank and non-boundary frequency estimates. SoundCloud time equals YouTube time minus 1.4925170068 seconds. It reads no renderer, software spectrum or candidate parameter. No production DSP changed. Stored hashes pin the script, input audit, alignment and full analysis.
