# RCS A03 settled hardware harmonics — 2026-09-20

A03 retains substantial Upper harmonic content, but strong stereo and time-dependent interference prevents using these windows as a clean dry-filter endpoint. The enabled modulation delay is a material confound, even when harmonic ratios exclude the shared fundamental.

This supplements the locked [A03 hardware audit](rcs-a03-hardware-observations-2026-09-20.md) without changing its case, source or catalog pins. The [author video](https://www.youtube.com/watch?v=8LKRnrs8DcQ) labels A03 at 35 and 40 seconds. The selected onset is approximately 36.764 seconds, with sounding families near 55 and 110 Hz. The published Upper square is one octave below the played key and the saw is at key pitch, followed by filtering and overdrive. Lower sine has amp sustain 0 but decay 64; it cannot be assumed silent merely from its sustain setting.

Measurements use fixed 60 ms rectangular windows at 36.900 and 36.930 seconds, left/right/mid channels, both platform encodes, and joint DC/trend plus 40 harmonic least squares. Independent local frequency searches span 49–61 Hz. Each window contains roughly 3.3 periods; this measures a common-period approximation to a changing wet output, not an isolated oscillator cycle. No software rendering or engine parameter fitting was used.

| Source / center | H2/H1 | H3/H1 | H4/H1 | H5/H1 | H6/H1 | H7/H1 | H8/H1 | Periodic-fit residual |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| YouTube mid / 36.900 s | +5.550 | −2.782 | −3.927 | −7.092 | −5.848 | −17.572 | −7.953 | 1.149% |
| YouTube mid / 36.930 s | +5.947 | −2.246 | −3.385 | −5.356 | −10.154 | −10.790 | −11.267 | 0.904% |
| SoundCloud mid / 36.900 s | +5.666 | −3.009 | −4.147 | −7.225 | −6.555 | −17.188 | −7.931 | 0.935% |
| SoundCloud mid / 36.930 s | +6.210 | −2.102 | −3.104 | −4.999 | −10.727 | −10.733 | −11.162 | 0.826% |

Ratios are amplitude dB. Across all twelve channel/window/encode measurements, local fitted frequencies are 54.800–55.212 Hz and full periodic-fit residuals are 0.606–1.478% of signal variance. These frequencies are descriptive, not identified master tuning. Sine-only fits leave 70.3–93.7% unexplained; nonfundamental modeled power is 72.7–94.4%, so this is clearly a harmonically rich endpoint.

The channel differences are much larger than the encode differences. At 36.900 seconds, YouTube H2/H1 is +1.110 dB left and +10.280 dB right. Removing H1 does not remove the confound: H4/H2 is −28.245 dB left versus −5.436 dB right, a **22.81 dB** difference. At 36.930 seconds, those H4/H2 values become −15.586 and −6.005 dB, a **9.58 dB** difference. This moving notch behavior is consistent with the enabled modulation delay and cannot be assigned uniquely to dry oscillator balance or filter cutoff.

Upper delay send is 127, with raw time/encoded-feedback/HF-damping/mod-rate/mod-depth values `[0,53,12,3,49]`. Lower delay send is zero; reverb is globally off. Lower decay, Upper/Lower phase and the mixed fundamental remain uncertain, while wet/dry interference affects even H2+ ratios that an ideal Lower sine would not contribute. The recording therefore supplies a useful wet-output comparison target, not a new isolated global filter-law anchor.

SoundCloud uses the existing fixed offset of −1.4925170068 seconds. The local 36.840–36.990-second mid-channel PCM correlation at that offset is 0.99748, corroborating the same performance without refitting alignment. Two encodes are not independent hardware evidence.

The [JSON](rcs-a03-endpoint-2026-09-20.json) retains all twelve H1–H8 amplitude/phase measurements, residuals and provenance. Reproduce the full source-only measurements with:

```sh
OPENBLAS_NUM_THREADS=1 python3 \
  build-fidelity/rcs-a03-endpoint-2026-09-20/analyze_hardware_harmonics.py
```

The script checks source hashes, existing case/bank/source-audit identities, floating stereo PCM at 44.1 kHz, finite/non-silent windows, fit rank and interior frequency estimates; all pinned inputs are rechecked after analysis. No production source, existing case/catalog or A03 modified render was changed or created.
