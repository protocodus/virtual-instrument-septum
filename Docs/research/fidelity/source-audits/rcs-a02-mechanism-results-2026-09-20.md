# RCS A02 filter mechanism experiment — 20 September 2026

The two experiments that approximate the first note's brightness change fail
the longer note's surviving harmonic pattern. Neither is accepted as a sound
match or a replacement DSP law. The shipping engine is unchanged.
[Listen to hardware, baseline and the two experiments](http://127.0.0.1:8920/rcs-mechanism-listen/).
The [results JSON](rcs-a02-mechanism-results-2026-09-20.json) pins the complete
analysis, render provenance, plots and summaries.

## Experiment and controls

The [predeclared design](rcs-a02-mechanism-design-2026-09-20.md) crosses seven
temporary Upper cutoff/depth settings with four already frozen filter-attack
tables: current, 50, 100 and 150 ms at raw attack 24. These are deliberately
modified experimental presets, not unchanged-preset comparisons. The original
published setting is cutoff 120 and depth −22. All other patch parameters,
estimated MIDI, output settings and DSP sources remain fixed. The grid contains
24 new renders and four reused original-patch controls.

Every input hash, frozen build and expected SysEx mutation was checked. Only
the declared Upper cutoff/depth bytes and their checksum change; all 22 DT1
checksums pass. All audio is finite and unclipped, retains the same 93-sample
engine latency, and ends with zero active voices. No gain, EQ, timing or pitch
adjustment enters the measurements. The listening page uses one constant RMS
gain per complete excerpt.

First-note analysis uses the existing high/low-band ratio and sustained
closure landmarks, plus absolute early/late ratios, raw powers, changes in
each band, bass-band power and PCM RMS. The first-note windows were fixed at
15–35 and 75–95 ms; sensitivity includes ±10 ms onset shifts, three channels
and three Hann windows, with explicit common gate support. Original hardware
measurements reproduce exactly. No missing crossing is replaced by a gate
endpoint, and no aggregate score selects the darkest render.

## A close short-window feature is ambiguous

Two cells have the same depth-to-time slope while their attacks are unfinished:
depth −42 over 100 ms and depth −63 over 150 ms. Both use cutoff 120.
Their current-model final cutoffs differ greatly: approximately 54.6 Hz versus
the 5 Hz lower clamp. The first note lasts approximately 137 ms, so the latter
cannot finish its attack during that note.

| Central first-note feature | Hardware | Both selected mechanism cells |
| --- | ---: | ---: |
| Early high/low power ratio | −6.38 dB | −7.11 dB |
| Late high/low power ratio | −34.96 dB | −33.23 dB |
| High-band late/early change | −30.71 dB | −29.95 dB |
| Low-band late/early change | −2.31 dB | −4.95 dB |
| Sustained 10 / 20 / 30 dB drops | 60.48 / 76.44 / 86.42 ms | 66.30 / 69.30 / 91.25 ms |

The paired equality illustrates an unresolved depth/attack tradeoff, not two
independent confirmations. Their full trajectories remain different from the
hardware, and their first-note harmonic patterns do not match. Fixed 40 ms
harmonic windows contain only about two cycles; rapidly changing candidates
have substantial fit residuals. Unknown Upper/Lower phase interference can
also change H1-normalized ratios. These limitations prevent attributing the
first-note harmonic discrepancy uniquely to oscillator level or filter depth.

The two cells were explicitly frozen in `validation-freeze.json` before any
later software notes were analyzed. They were selected to test this ambiguity,
not accepted as successful matches. No candidate was reselected afterward.

## Longer-note validation

The [hardware endpoint study](rcs-a02-endpoint-2026-09-20.md) establishes that
the long fourth note retains a strong second harmonic. The common comparison
uses eight windows ending before 21.877 seconds, the earliest altered gate.
One 60 ms window centered at 21.850 seconds is excluded from this shared
support; its original-gate result is retained separately. Software channels
are exactly equal in these windows, so only mid is measured. Hardware is
checked across left/right/mid and both lossy copies of the same recording.

| Late common-window median | Hardware | Current original preset | −42 / 100 ms | −63 / 150 ms |
| --- | ---: | ---: | ---: | ---: |
| H2/H1 amplitude | −7.01 dB | −9.79 dB | −44.45 dB | Negligible |
| H3/H1 amplitude | −22.71 dB | −14.69 dB | −68.32 dB | Negligible |
| H4/H1 amplitude | −31.43 dB | −15.65 dB | −78.39 dB | Negligible |
| Periodic power above H1 | 17.01% | 16.06% | 0.0036% | Negligible |

The baseline retains harmonic energy but distributes too much into H3/H4.
The two experiments suppress the higher content excessively. The −63 result
approaches numerical/analysis limits and should not be interpreted as an
accurate measurement of a tiny physical hardware harmonic.

Six additional renders apply the previously declared 5/15 ms note gaps and
15 ms overlaps to the two fixed cells. Their first 6,703 frames are byte-identical
to their primary counterpart, before the earliest altered note-off. Every
gate variant still suppresses the long-note harmonic content: H2/H1 remains
approximately −45 dB for depth −42, and negligible for depth −63.

Transient closure is more gate-sensitive. On the fourth note, the two
adjacent-gate cells observe only 3/3/0 and 3/0/0 of the 27 settings for each
10/20/30 dB crossing, compared with hardware's 27/27/27. Both gap choices restore
27/27/27 crossings, while overlaps give only partial crossings. Gaps therefore
restore an attack under this engine's voice history, but do not restore the
hardware endpoint. In the fixed long-note central windows, gap variants lose
about 39 dB of low-band power versus hardware's 20.9 dB. A closure landmark
alone can conceal that loss.

These are conditional results for the declared patch, phase and gate choices.
They reject the tested realizations; they do not identify a unique Roland
negative-depth curve or rule out every possible coupled model. No original
played MIDI, exact live patch state or isolated hardware transfer measurement
is available.

## Another patch and remaining mechanism questions

[A03 Jupiter8wide](rcs-a03-baseline-comparison-2026-09-20.md) is now the 16th
named reference. Its original-preset baseline also fails to reproduce the
hardware closure. However, [its endpoint analysis](rcs-a03-endpoint-2026-09-20.md)
finds large channel-dependent harmonic differences with modulation delay
enabled. It cannot serve as a clean dry-filter endpoint measurement.

The A02 residual now points to a coupled problem: closing motion, final filter
response, distortion, layer balance and oscillator phase must remain
consistent together. The next useful diagnostic should distinguish these
mechanisms rather than extend a one-dimensional attack or cutoff fit.

The [documentary routing audit](overdrive-routing-documentary-evidence-2026-09-20.md)
supports the current filter-before-overdrive block order: Roland places
overdrive in the AMP section and draws FILTER before AMP. Exact nonlinear
placement relative to the amp envelope, and any unshown internal filtering,
remain unspecified. Moving distortion before the filter is therefore not a
documented correction.

All 14 hardware-comparison tests and 13 timbre-matrix tests passed after the
new reference was added. No production DSP changed, so no new C++ behavior
claim or global calibration is made.
