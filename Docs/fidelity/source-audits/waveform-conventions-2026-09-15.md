# Triangle convention: independent preset checks

**No tested triangle convention justifies a global DSP change.** Inverting
the triangle and doubling its amplitude reduces Dist Bs 1's diagnostic
harmonic error substantially, including later notes that did not select the
candidate. It worsens Club Bass and Moogie's odd harmonics. Shipping waveform
phase and gain remain unchanged.

This experiment extends the [earlier Dist phase audit](dist-overdrive-phase.md)
with quarter-cycle, half-cycle and three-quarter-cycle conventions, amplitude
alternatives, current physical tuning, and a new Club Bass comparison.
The baseline is the DSP source snapshot recorded in
`build-fidelity/hardware-benchmark/baseline-d343d04/`.

## Sources and fixed inputs

Roland's [BASS patch page](https://www.rolandus.com/go/sh-201_patches/patch_bass.html)
associates each named demonstration with its published patch bank. The four
recordings used here are [Dist Bs 1](https://www.rolandus.com/go/sh-201_patches/mp3/BASS/TOP8_DistBs1.mp3),
[Moogie 1](https://www.rolandus.com/go/sh-201_patches/mp3/BASS/TOP8_Moogie1.mp3),
[Club Bass](https://www.rolandus.com/go/sh-201_patches/mp3/BASS/TOP8_ClubBass.mp3),
and [Pedal Bs 1](https://www.rolandus.com/go/sh-201_patches/mp3/BASS/TOP8_PedalBs1.mp3).
The [Owner's Manual](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf#page=28)
does not supply oscillator initialization phase or relative waveform gain.
These discrete candidates are experimental hypotheses, rather than a
manufacturer-specified correction.

Every render preserves the original imported SysEx, reconstructed MIDI,
velocity placeholders, master level, sample rate, effects and note timing.
No EQ, compression, time warping, per-candidate pitch fitting or patch edits
are applied. Original performance MIDI, controllers, system settings and
capture processing remain unavailable. A shared name does not authenticate
the exact preset revision used to make the demonstration.

The lowest modeled oscillator family is the played MIDI note minus 12
semitones in Dist, Moogie and Club, and minus 24 in Pedal. These are physical
offsets after WIDE conversion and tone octave; the former raw/display −36
interpretation is not reused. Dist's played notes are 39, 39 and 41. Its
source crop begins at 1.94 seconds. Moogie's three long low notes use MIDI 39
at 0.029, 0.939 and 1.901 seconds. Club uses the first three MIDI 38 notes and
its later MIDI 41. The JSON preserves complete original reconstruction
metadata and input hashes.

## Selection and measurements

Eight phase/amplitude settings are declared before rendering. Only Dist's
first note selects the candidate, using H2–H8 amplitudes relative to H1 in dB.
The later two Dist notes, Moogie and Club do not select the candidate.
The selected baseline control and all candidates are built through the public
calibration API from one frozen source copy.

Each measurement jointly estimates twelve harmonics, DC and a linear trend.
The early window is 35–115 ms after reconstructed note-on; the late window
is 105–25 ms before reconstructed note-off. Septum's recorded 93-sample
latency is included. Windows shift together by −10, 0 and +10 ms for timing
sensitivity. Hardware and baseline frequency are estimated separately within
3% of the expected family; every candidate inherits the baseline estimate.

Values below are RMS errors in dB; smaller means closer for those particular
features. “Moogie odd” uses H3/H1, H5/H1 and H7/H1. “All” uses H2–H8/H1.

| Triangle phase / amplitude | Dist first note | Dist later notes | Moogie all | Moogie odd | Club all |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline: 0 / 1× | 7.99 | 7.64 | 6.04 | 4.93 | 10.07 |
| ¼ cycle / 1× | 6.76 | 6.63 | 6.22 | 4.45 | 11.94 |
| ½ cycle / 1× | 3.32 | 3.48 | 5.84 | 5.48 | 9.61 |
| ¾ cycle / 1× | 5.78 | 5.88 | 5.83 | 6.34 | 12.99 |
| 0 / ½× | 5.33 | 5.12 | 5.95 | 5.05 | 13.44 |
| 0 / 2× | 10.39 | 10.28 | 6.28 | 4.73 | 11.07 |
| ½ cycle / ½× | 3.44 | 3.53 | 5.85 | 5.34 | 12.34 |
| **½ cycle / 2×, selected on Dist** | **2.71** | **2.90** | **5.88** | **5.77** | **10.96** |

The selected candidate reduces aggregate Dist error from 7.76 to 2.84 dB.
Across the three timing offsets, its aggregate error stays 2.84–2.98 dB;
baseline stays 7.76–8.01 dB. Its Club error stays 10.40–10.96 dB, worse than
the corresponding baseline measurements of 9.49–10.08 dB. Thus the principal
holdout failure survives the stated timing perturbation.

Unit-amplitude inversion is less damaging: it slightly improves the overall
Moogie and Club metrics. Moogie's odd-harmonic error nevertheless rises from
4.93 to 5.48 dB. Its even-harmonic ratios normalized to H2 remain essentially
unchanged, about 5.97 versus 5.96 dB RMS error. The independent
[Moogie pulse-bound investigation](moogie-oscillator-shape.md) still applies:
a symmetric triangle convention cannot resolve its extra even-harmonic
shape. Pooling all harmonics into a single number can conceal that failure.

## Measurement qualifications and validation

Dist's selected hardware windows leave less than 1% unexplained variance in
the harmonic fit; the corresponding maxima are about 1.5% for Moogie and
2.5% for Club. These support the local feature estimates, not capture-chain
or preset authentication. Club retains its published reverb; early windows
do not certify a perfectly dry recording.

Pedal contains Super Saw and sine, with no triangle. All eight full Pedal
renders are **sample-identical** to baseline, making it a useful neutrality
check. Its harmonic-family optimizer reaches the search boundary, so its
fit is unsuitable for calibrating triangle phase or claiming a new tuning
measurement. Its numeric observations remain in the data with this limit.

The independently generated synthetic twelve-harmonic signal is recovered
with maximum amplitude error `4.996e-16`. The separately compiled baseline
reproduces all four benchmark waveforms exactly. All eight frozen DSP source
hashes match the benchmark snapshot. Compilation and all 32 renders complete
successfully, with finite output. Python syntax compilation and whitespace
validation pass.

An initial run crossed a concurrent LFO-rate source update. It was superseded
by the complete `v2` rerun from one frozen snapshot; no table in this report
uses the mixed-source run. The analysis tool now freezes sources once and
rejects DSP hashes that differ from any benchmark input.

## Reproduction and next evidence

The tool, compact results, source hashes, waveform hashes, render manifests
and timing-sensitive per-note metrics are retained in
[analyze_waveform_conventions.py](../../../Tools/analyze_waveform_conventions.py)
and [the measurement JSON](waveform-conventions-2026-09-15.json).
Full build snapshots, profiles, audio and observations are under
`build-fidelity/hardware-benchmark/waveform-conventions-d343d04-v2/`.
The complete result JSON has SHA-256
`059647a1cd099bf85a43e71c327d473b992d48a122839cdd881c2897f6c8e400`.

```sh
OPENBLAS_NUM_THREADS=1 python3 Tools/analyze_waveform_conventions.py \
  --comparison-root build-fidelity/hardware-benchmark/baseline-d343d04 \
  --source-root build-fidelity/hardware-benchmark/waveform-conventions-d343d04-v2/source-snapshot \
  --output build-fidelity/hardware-benchmark/waveform-conventions-reproduction \
  --jobs 2
```

A dry same-note capture of isolated pulse, square, triangle and sine, followed
by pulse+triangle and square+triangle at fixed balance, would distinguish
relative amplitude, waveform convention and initialization behavior. Repeat
note-ons and export the exact patch/system state. Until that evidence exists,
the best Dist-specific result remains an experimental diagnostic profile.
