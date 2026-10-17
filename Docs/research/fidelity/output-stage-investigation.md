# Does the SH-201 need a more colorful output-stage model?

The user's description—more lively and powerful—is a useful listening target.
The evidence so far points to differences in harmonic body and transient shape,
but does **not** identify a missing saturating line preamp. This investigation
keeps physical circuit behavior separate from a louder playback level. Hardware
equivalence remains unproven.

## What the original hardware supports

The [original service and component documents](source-audits/output-stage-primary-sources-2026-09-15.md)
show a DAC/reconstruction stage, a loaded passive master-volume pot, a ×2 line
amplifier and a higher-gain headphone amplifier, powered from ±8 V. The line
and headphone paths have different headroom and load behavior; L/MONO alone
also connects the two line drivers through their output resistors.

Typical documented amplifier slew rate and distortion do not support adding
substantial saturation during ordinary line playback. Published characteristics
at ±15 V do not identify an exact clipping/recovery curve at the unit's ±8 V.
The benchmark recordings do not authenticate master position, output jack choice
or capture loading, so their fitted playback gains cannot supply that curve.

The [loaded circuit calculation](source-audits/output-stage-circuit-calculation-2026-09-15.md)
and its independent node-equation review cover 144 declared small-signal cases.
After removing only constant physical gains, their magnitude changes stay below
0.046 dB from 20 Hz to 20 kHz. This is much smaller than the observed body
differences. Phase changes remain a separate transient question.

The [copied-engine trial](source-audits/line-output-engine-trial-2026-09-15.md)
then rendered all three declared electrical fractions through the real 8×
processing path. It passed exact disabled controls and state-isolation checks.
At full volume, the largest priority-preset crest improvement was Dist Bass at
about 0.67 dB, leaving most of its 3.81 dB deficit; Moogie changed by 0.01 dB,
Cotton moved 0.07 dB farther from the original and Vangelead overshot an
already-close crest. This does not identify a shipping setting.

The AK4552 source audit also verifies that de-emphasis is disabled in the unit.
Its documented DAC filter is within ±0.5 dB through 20 kHz, but the public
datasheet does not give coefficients or a phase curve from which to reconstruct
an exact additional DAC model.

## What the current instrument and recordings show

The [actual output-code audit](source-audits/output-path-code-audit-2026-09-15.md)
finds a linear analog model and an inactive final limiter throughout all twelve
complete benchmark takes. No extra stereo plug-in compression is hidden after
the engine. The largest native sample is 0.736, below the limiter's 0.9 knee.

The [same-recording characterization](source-audits/output-stage-reference-characterization-2026-09-15.md)
retains the existing gain, timing and original-only measurement supports.
A separate, explicitly post-hoc loudness sensitivity helps separate level from
shape; it changes no production setting.

| Preset | Measured difference from the original |
| --- | --- |
| Moogie 1 | Almost equal loudness; 4.19 dB less peak-to-average contrast. Adequate sub-bass, but roughly 4 dB less upper-bass/midrange body. |
| Dist Bs 1 | 3.81 dB less peak-to-average contrast, about 3 dB less upper-bass/midrange body after loudness matching, and a narrower level envelope. |
| Cotton Wool | 1.58 dB less peak-to-average contrast; a mixture of excess bass/upper treble and deficient mids. |
| Vangelead | Overall loudness and peak contrast are close, while the time-varying envelope differs substantially. |

Air and Brassy have excessive peak contrast, providing counterexamples to a
single global dynamics correction. These statistics do not locate the cause
inside a specific DSP block. Oscillator phase, filter/envelope behavior, drive,
effects and reconstructed-performance uncertainty all remain possible causes.
They also do not override the user's listening observations about brightness
and resonance: a broad band-power ratio is not an isolated filter measurement.

## Decision and next useful correction

Do not add a generic compressor, gain boost or saturation curve as a claimed
SH-201 output correction. A constant gain cannot restore waveform dynamics;
additional peak compression would move the largest crest deficits farther from
the originals. A shared tone tilt is also unsupported by the preset differences.

The loaded linear line-stage trial is kept separate from production and judged
using the same original supports. The concrete remaining listening targets are
longer Vangelead attack, Moogie/Dist filter body and resonance, and Cotton's
resonance/filter-envelope decay. Preserve the published preset bytes while
investigating those shared DSP behaviors.
