# Nominal 50% resonance: conditional evidence, rejected calibration

**The recordings suggest stronger midpoint resonance in the low harmonics,
but do not establish a replacement resonance curve or LP24 topology.** Most
80 ms windows fail the harmonic estimator's existing validity rule. Shorter
windows admit useful observations, but LP24 upper harmonics remain poorly
explained. Known-engine controls show that moving narrow resonance alone can
cause these failures; they do not prove hardware self-oscillation or distortion.
No DSP was changed for this audit.

## Source and scope

The owner's [filter comparison](https://www.deepsonic.ch/deep/htm/deepsonic_analytics_filter_comparison.php)
supplies the original MIDI and LP12/LP24 recordings labeled 0%, 50% and 100%
resonance. Its dry recipe uses one saw, key follow of one octave per keyboard
octave, a cutoff envelope falling approximately three octaves in one second,
and no effects, LFO, velocity or pitch modulation. Those are instructions for
setting the patch by ear, rather than exported raw controls.

This experiment verifies the original MIDI and both Q050 MP3 hashes against
the [acquisition record](deepsonic-acquisition-2026-09-15.json), then decodes
the MP3s into a fresh directory. It uses the same six MIDI note/onset pairs as
the zero-resonance study. Notes are not transposed or retuned to improve a fit.

**The label “50%” does not establish raw resonance 63 or 64.** There is no
SysEx dump, editor value or documented rounding rule for this recording.
The two nearest midpoint integers are useful hypotheses, not known settings.
Current damping at these integers is respectively `[0.298862, 0.5]` and
`[0.289866, 0.5]`, with only the first section active for LP12. The known
zero-resonance comparison is `[1.2, 1.2]`. Damping is the coefficient in the
modeled two-pole response; a smaller positive value gives a sharper resonance.

## Validity first

The existing estimator jointly fits harmonic quadratures and independent
local linear ramps on the full 44.1 kHz sample grid. A window is valid only
when its matrix condition number is at most 100 and unexplained signal power
is at most 1%. These checks are unchanged from the zero-resonance work.

At the four original offsets, 100, 180, 260 and 340 ms, **all 48 Q50 windows
of width 80 ms fail the power rule**. LP12 unexplained power is 2.37–6.22%;
LP24 is 4.16–19.06%. Zero-resonance windows had passed comfortably.

Adding independent times 140, 220, 300 and 380 ms gives the following totals.
The power medians include only windows that pass the conditioning check;
the final valid count additionally applies the 1% power limit.

| Width | LP12 median unexplained power | LP12 valid / attempted | LP24 median unexplained power | LP24 valid / attempted |
| --- | ---: | ---: | ---: | ---: |
| 40 ms | 0.185% | 21 / 48 | 0.736% | 16 / 48 |
| 60 ms | 0.998% | 24 / 48 | 3.057% | 20 / 48 |
| 80 ms | 4.105% | 6 / 48 | 11.138% | 0 / 48 |
| 100 ms | 6.927% | 1 / 48 | 17.325% | 0 / 48 |

At 40 ms, 24 windows per slope are rejected for conditioning: MIDI 24 and
29 do not provide enough cycles to separate their locally moving harmonics.
The remaining note holdouts are MIDI 31 and 57. Selecting 40 ms followed
inspection of the 80 ms failure, so it is an exploratory change with explicit
holdouts, not a predeclared acceptance result.

## Conditional response fits

Only valid 40 ms windows from the first MIDI 36 note select damping: four
LP12 windows and three LP24 windows. Each window has its own nuisance cutoff.
H2–H8 select the model; H9–H16 are withheld. Both use the existing hardware-only
floor of −45 dB relative to H1. There is no fitted EQ or per-harmonic gain.
Four starting values reduce the risk of choosing a local resonance minimum.

| Topology hypothesis | Fitted damping | Training H2–H8 RMSE |
| --- | --- | ---: |
| One damping shared by every section | 0.26289 | 1.738 dB |
| LP12 independent; two equal LP24 sections | LP12 0.16628; LP24 0.29379 / 0.29379 | 1.496 dB |
| LP12 shared with LP24 first section | First 0.17533; second 0.42962 | 1.514 dB |
| All three section parameters independent | LP12 0.16628; LP24 0.29379 / 0.29379 | 1.496 dB |

The independent LP24 fit returns two equal sections, but the near-equal
performance of the linked-first-section model does not identify the actual
topology. Frequency-domain cascades also cannot distinguish section order.

For the independent-LP12/equal-LP24 diagnostic, held-out low harmonics improve:

| Valid 40 ms group | Current raw 64 H2–H8 | Diagnostic fit H2–H8 | Diagnostic fit withheld H9–H16 |
| --- | ---: | ---: | ---: |
| LP12, other notes, original times | 1.402 dB | 0.503 dB | 0.582 dB |
| LP12, other notes, new times | 1.355 dB | 0.293 dB | 0.298 dB |
| LP24, other notes, original times | 2.106 dB | 0.818 dB | 1.413 dB |
| LP24, other notes, new times | 1.946 dB | 0.679 dB | 1.596 dB |

The low-harmonic result is suggestive, particularly for LP12. However, on
the training MIDI 36 note, LP24 withheld upper-harmonic RMSE is **12.25 dB
at original times and 26.09 dB at new times**. The latter has only seven
eligible upper-harmonic observations. The current raw-64 hypothesis fails
similarly at 11.71/25.49 dB. Global explained power does not guarantee accurate
weak individual harmonics, and a fixed −45 dB floor does not fix leakage from
a strong moving resonant component. These errors cannot be treated as an
accepted match or corrected by fitting only the strong harmonics.

## Independent moving-resonance control

A separate C++ fixture renders the actual engine from the frozen source used
by the [zero-resonance bias control](filter-estimator-bias-2026-09-15.md).
It uses single saws, key follow 100, cutoff 34, envelope depth 21, decay 63,
zero attack, sustain 0 for moving or 127 for stationary, AMP level 50,
velocity 100, and no effects/LFO/velocity sensitivity. Its initial cutoff is
7.823 × f0 and decay lasts 1.01387 seconds. The public calibration API supplies
known section damping; the estimator never generates the audio.

| Known sections | Signal | Recovered sections, 40 ms windows |
| --- | --- | --- |
| 0.289866 / 0.5 | Stationary | 0.290094 / 0.500013 |
| 0.289866 / 0.5 | Moving | 0.298082 / 0.511712 |
| 0.166279 / 0.293791 | Stationary | 0.166441 / 0.293789 |
| 0.166279 / 0.293791 | Moving | LP12 alone 0.178882; second section not accepted |

The stronger moving control has only one valid LP24 training window at 40 ms,
so joint damping is deliberately not reported. At 80 ms its median unexplained
power is 2.05% for LP12 and 12.49% for LP24; no LP24 windows pass. Thus a known
stable, positive-damping engine can reproduce the scale of the hardware's
power failure through filter movement. Static recovery remains accurate.

For the current-midpoint moving control, correct-model held-note errors at
40 ms are 0.134/0.346 dB for LP12/LP24 low harmonics, and 0.161/0.469 dB for
withheld upper harmonics. First-section bias is upward, not the decrease
required to turn 0.290 into the hardware diagnostic 0.166. This supports
investigating stronger nominal-midpoint resonance, while the unknown hardware
envelope and large LP24 failures prevent transferring those fitted numbers
directly into production. These synthetic controls bound their stated recipe,
not every possible time-varying or nonlinear filter.

## Decision and reproduction

Keep the production resonance curve unchanged. The supported result is a
direction for further calibration, plus rejection of an overconfident static
fit at high resonance. A stationary single-saw capture at several exact raw
resonance/cutoff values, with SysEx and bypass/source references, would separate
the resonance curve from envelope movement. A physical time-varying model
could also be tested against these existing recordings; it would need its own
held-out waveform validation.

The [analysis tool](../../../Tools/analyze_deepsonic_q50.py) reproduces the
hardware diagnostics using only catalog-pinned original MIDI/MP3 assets:

```sh
OPENBLAS_NUM_THREADS=1 python3 Tools/analyze_deepsonic_q50.py \
  --sources build-fidelity/deepsonic \
  --output build-fidelity/deepsonic/q50-audit-reproduction
```

The [durable measurement record](deepsonic-q50-audit-2026-09-15.json) includes
source/tool hashes, validity decisions, fit starts, held-out summaries,
40 ms measurements and model results. It also includes complete independent
C++/Python control fixtures, settings and source/audio hashes. Render controls
from their artifact directory using `c++ -std=c++20 -O2 -fno-fast-math
render.cpp DSP/SeptumEngine.cpp -o render`, then `./render .` and
`OPENBLAS_NUM_THREADS=1 python3 analyze.py`. The control depends on its frozen
DSP snapshot; both damping settings are explicitly supplied by calibration.

Full local hardware result: `build-fidelity/deepsonic/q50-audit-v2/results.json`,
SHA-256 `a2de09354baa075a4f779e3fcb03e9d535155b913d08c70e14aa49ffd104ffde`.
Full control result: `build-fidelity/deepsonic/q50-dynamic-control/results.json`,
SHA-256 `8cbb02e2f4e56fba659a0048e8262f2f6d6ee1b03e65897f957130dd5b9becd4`.
Hardware numerical results replayed exactly. MP3 compression, unknown capture
chain, missing raw patch, assumed ideal saw spectrum, and a single hardware
unit remain limitations. No whole-instrument equivalence is established.
