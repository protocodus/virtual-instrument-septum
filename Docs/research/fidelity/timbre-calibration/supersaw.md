# SH-201-specific Super Saw calibration path

The comparison engine now accepts the complete detune-control table, seven
frequency offsets, separate center/side gain curves, tracked high-pass ratio
and Q, and overall normalization. Each oscillator uses its own modulated
spread value. SYNC uses the same calibrated offsets as ordinary rendering;
the central oscillator remains at nominal pitch.

The shipping model still uses its existing JP-8000-derived polynomial and
offsets plus the project's fixed mix. The factory comparison profile preserves
those values at every integer control. Its polynomial has a tiny local detune
decrease around raw 4–6, so the experimental table validates bounds without
inventing a monotonic replacement. Only an explicitly supplied detune table
uses linear interpolation for fractional modulation. A mix/filter-only profile
retains the continuous original polynomial exactly, including under LFO control.

[Roland's SH-201 product brief](https://cdn.roland.com/assets/media/pdf/SH-201_STK_STS.pdf)
identifies its Super Saw and Feedback Oscillator with the V-Synth family.
That is useful lineage evidence, not proof of numeric DSP identity with
another instrument. Dry SH-201 measurements are still needed to choose the
right offsets, mix, filter and phase statistics. No guessed replacement is
installed in the plug-in.

Focused tests verify static identity and independently moved detune controls
at three rates, both MIX and SYNC. A center-only saw isolates the tracked
filter: doubling its corner matches an independent Butterworth response ratio.
Separate center/side zero gains produce exact silence. Invalid offsets and
filter Q are rejected. These checks establish implementation correctness, not
that any alternative profile matches a physical SH-201.
