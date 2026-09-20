# Air Lead 1: conditional static-cutoff candidate

2026-09-20. A lower cutoff at raw91 substantially improves Air Lead 1 across
the existing ten-note reconstruction, including notes and harmonics excluded
from the fit. It remains an **experimental comparison profile**, not a verified
global hardware curve. No production DSP or preset bytes were changed.

The [earlier resonance audit](air-lead-resonance.md) independently fitted
cutoff in each window. This experiment instead fits **one opening window** and
holds its base cutoff fixed across the whole phrase. The fit uses the current
two-stage damping, current LOW FREQ BOOST shelf, and documented +50 key follow.
It selects raw91 = **1,106.45 Hz**, compared with the incumbent **2,870.89 Hz**,
a difference of approximately −1.38 octaves. The actual opening-note corner
includes key follow and is about 1,206.6 Hz.

The source remains Roland's named [Air Lead 1 recording](https://www.rolandus.com/go/sh-201_patches/mp3/LEAD/TOP8_AirLead1.mp3)
and its associated original patch on the [LEAD bank page](https://www.rolandus.com/go/sh-201_patches/patch_lead.html).
The [existing reconstruction](../reconstructions/expanded/air-lead-1.json)
supplies estimated notes, gates and velocity100. Original performance MIDI and
the original recording chain are unavailable. Both renders preserve the
complete published SysEx and all its effects.

## Fit and held-out checks

Training uses the mid channel, a 50 ms Hann window centered at 75 ms, and
H4/H6/H8 relative to H2 after removing the saw's ideal 1/n slope. H10/H12 are
excluded from fitting. A symmetric triangle is assumed to contribute no even
harmonics. The real isolated triangle waveform remains unmeasured.

For validation, the script measures left, right and mid channels with 30, 40
and 50 ms windows. Four centers cover the opening note; twelve more cover all
nine later notes. These overlapping observations test sensitivity, not 143
independent recordings. The table excludes the one training observation.

| Full-engine metric | Incumbent | Candidate |
| --- | ---: | ---: |
| Opening-note H4…H12/H2 median error, 35 observations | 33.31 dB | **2.21 dB** |
| Later-note H4…H12/H2 median error, 108 observations | 39.72 dB | **6.10 dB** |
| Later-note withheld H10/H12 median error | 46.29 dB | **4.25 dB** |
| Worst later-note H4…H12/H2 error | 50.12 dB | **26.23 dB** |

Every nontraining observation improves on both reported error metrics. The
remaining later-note errors are substantial: delay/reverb, differential pitch
modulation, estimated articulation, oscillator assumptions and the capture
chain still matter. These selected harmonic errors are not an overall fidelity
percentage. The analytic model alone is reported separately from actual engine
renders in the [data summary](air-lead-cutoff.json).

Refitting only the opening channels/windows gives conditional base cutoffs
from **1,069 to 1,132 Hz**. This is sensitivity to those analysis choices, not
a confidence interval for hardware. The production key-follow slope is held
fixed; it is not optimized from the recording. Later notes use the same
1,106.45 Hz anchor, without individual cutoff adjustments.

## Why the candidate is not a production table

The [profile](../../../Tools/timbre-profiles/experimental-air-lead-cutoff.json)
preserves raw0…64 and raw127 by design and uses monotone PCHIP interpolation
in log frequency through raw64, raw91 and raw127. **Only raw91 has a
recording-derived conditional anchor.** The lower controls, endpoint and
interpolation are not new hardware measurements.

| Raw cutoff | Incumbent | Experimental table |
| ---: | ---: | ---: |
| 64 | 658 Hz | 658 Hz |
| 69 | 864 Hz | 674 Hz |
| 91 | 2,871 Hz | 1,106 Hz |
| 101 | 4,955 Hz | 1,779 Hz |
| 110 | 8,098 Hz | 3,521 Hz |
| 127 | 20,480 Hz | 20,480 Hz |

Keeping Moogie, Dist, Cotton and SupaJuce unchanged is useful experimental
isolation, but cannot validate the changed part of the curve. Independent
presets with controls above64 must improve before adopting a global mapping.
The companion ten-preset comparison slightly worsens Club Bass and Vangelead
while greatly improving Air Lead; this supports retaining the profile as an
experiment. The Choir was also screened as a possible static-filter reference,
but its polyphonic opening, Super Saw, noise and effects do not currently
provide a clean independent cutoff anchor.

## Reproduction and identities

The [analysis tool](../../../Tools/analyze_air_lead_cutoff.py) verifies the
audited MP3, bank and complete SysEx hashes, validates both frozen renderer
identities, requires matching original source snapshots, and requires the
candidate's saved profile to exactly match the regenerated profile. It rejects
silent or nonfinite audio and measurements. Resonant-fit searches check multiple
local minima rather than silently accepting an incorrect boundary result.

```sh
python3 Tools/build_timbre_candidate.py \
  --profile Tools/timbre-profiles/diagnostic-baseline.json \
  --output /tmp/air-cutoff-baseline-new
python3 Tools/build_timbre_candidate.py \
  --profile Tools/timbre-profiles/experimental-air-lead-cutoff.json \
  --output /tmp/air-cutoff-candidate-new
OPENBLAS_NUM_THREADS=1 python3 Tools/analyze_air_lead_cutoff.py \
  --output /tmp/air-cutoff-analysis-new \
  --baseline /tmp/air-cutoff-baseline-new/SeptumRenderMidi \
  --candidate /tmp/air-cutoff-candidate-new/SeptumRenderMidi
```

All output paths must be new. `--profile-output NEW.json` can write a freshly
generated profile; omit the renderer arguments for analytic-only inspection.
The retained verified run is
`build-fidelity/public-match-2026-09-20/air-cutoff-analysis-verified/`.
Its full analysis, original/decoded hardware, MIDI, SysEx, raw WAVs and replay
manifests remain in ignored storage. The committed summary contains source,
script, profile, renderer, build-manifest, audio and complete-analysis hashes,
aggregate errors and every center's channel/window range.

The two full renders are finite, non-silent and below full scale. Both report
93 samples of output latency, compensated only when selecting analysis windows.
No EQ, compression, time warping or audio gain optimization enters the harmonic
measurements. The tool fits a diagnostic model; it does not install that model
in the plug-in.
