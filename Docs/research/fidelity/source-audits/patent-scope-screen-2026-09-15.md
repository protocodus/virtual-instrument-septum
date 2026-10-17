# Patent screening: no SH-201 algorithm identification

2026-09-15. A bounded search for Roland sawtooth generation, waveform
interpolation and antialias patents did not establish an implementation link
to the SH-201. These documents are useful historical context, not replacement
DSP specifications.

| Primary patent document | Verified scope | Consequence for this task |
|---|---|---|
| [US4715257A](https://patents.google.com/patent/US4715257A/en), Roland, priority 1985-11-14 | Stored waveform differences and interpolation using integrated low-pass responses; selectable interpolation characteristics | An actual Roland interpolation technique, but no SH-201 identification or recovered SH-201 coefficient table |
| [US9542923B1](https://patents.google.com/patent/US9542923B1/en), Roland, filed 2015-09-29 | Multiband input-pitch tracking for a synthesizer; its example describes a phase-accumulator saw | Later guitar/input-tracking context does not identify the SH-201 classic oscillator or establish that it is a naive saw |
| [US20060145733A1](https://patents.google.com/patent/US20060145733A1/en), Korg, priority 2005-01-03 | Bandlimited analog-waveform synthesis | Search surfaced it near the right era, but it is Korg's document; not evidence for a Roland implementation |

Searches combined Roland/“Roland Corporation” with sawtooth, aliasing,
waveform generation, interpolation, band-limited and FIR, including
Google-Patents-specific queries. Broad results also included unrelated
inventors named Roland and analog guitar instruments; those were excluded.
Document headings, assignees, dates and relevant descriptions were inspected.
No legal-status or product-licensing conclusion is being made.

The 1987 document's interpolation example must not be transplanted as an
SH-201 algorithm solely because the assignee matches. Any related numerical
candidate still needs to predict the independently measured main harmonics
and alias lines across pitches. The [source-feasibility audit](sh201-high-note-source-feasibility-2026-09-15.md)
and [failed simple smoothing models](high-note-saw-fir-2026-09-15.md) retain
the current implementation and capture uncertainties.
