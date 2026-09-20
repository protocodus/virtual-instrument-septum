# RCS stereo-delay comparison — 20 September 2026

**A03 supplies conditional evidence against the current stereo-delay model.**
The recorded channel gain and phase cannot be jointly reproduced by the
current stationary transfer at any modulation phase. An unchanged software
control stays much closer. This identifies a useful effects-model constraint;
it does not identify replacement delay coefficients or establish a full sound
match. No production DSP or published preset changed.

![A03 second-harmonic channel relationship versus the current delay model](../figures/rcs-a03-stereo-relationship.png)

## Inputs and method

The [RCS author](https://www.rcssound.com/index.php?page=6) supplies the patch
bank and [labelled hardware video](https://www.youtube.com/watch?v=8LKRnrs8DcQ).
Existing pinned A03/A05 intervals and patch bytes were reused. No performance
MIDI was required for this source-only ratio measurement; the associated
rendered comparisons still use reconstructed MIDI.

Both patches have Upper delay send 127, Lower send 0, centered tones and
reverb off. A03 has +8% feedback; A05 has zero feedback, which still permits
the first delayed signal. Septum currently maps raw delay time 0 to 1 ms,
uses sinusoidal modulation with a 90-degree channel offset, and adds unity
dry and wet signals at maximum send. These timing, waveform and gain laws
are model assumptions, not numerical specifications in Roland's
[Owner's Manual, p. 63](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf#page=63).

Each 40/60/80 ms window fits both channels with **one common frequency and
phase origin**. Higher-harmonic complex R/L can cancel the shared Upper
source only when it is locally stationary and Lower transient leakage is
negligible. Fixed screening requires adequate energy, at most 5% residual
power per channel, stable harmonic-order fits, and at most 1 dB/10 degrees
of central-half-window amplitude/phase drift. Most source measurements fail
one or more guards; rejected rows remain in the analysis.

The dry A01/A02 excerpts have stereo-difference levels approximately 54/57 dB
below mid. The wet A03/A05 differences agree between platform copies, with
correlations 0.996/0.984. This supports patch-associated stereo predating
platform encoding, without proving an unchanged capture path or identifying
the hardware's internal effect topology.

## A03: joint gain and phase reveal a mismatch

Six passing H2 observations at +100/+130 ms, across two window widths and
two encodes, measure **R/L gain +3.230 to +4.208 dB and phase −44.693 to
−31.550 degrees**. Their frequencies are approximately 110 Hz. The plot
shows their relation to the current model; numerical comparisons use each
exact fitted frequency, including damping, interpolation, feedback and the
minimum-delay clamp.

The smallest complex-ratio distance over every modulation phase, divided
by the observed ratio magnitude, is **0.408–0.517**. In the unchanged A03
software control it is **0.003–0.020** for the three passing H2 observations;
all 89 passing software harmonics have maximum 0.089. This distance is a
transfer comparison, not a perceptual error or fidelity percentage.

The six hardware observations overlap and share one performance. Their
maximum within-window ratio drift approaches the screening limits
(0.974 dB/9.793 degrees). The gap therefore supports a **conditional**
model mismatch, not an unconditional identification of a Roland circuit.
Unknown channel processing, live patch state, envelope history and deviations
from local stationarity remain material alternatives. A different oscillator
spectrum alone cannot explain a stationary Upper-only R/L ratio.

## A05: insufficient evidence for a correction

Only the same H3 window survives all guards in each encode: one of 434
harmonic/window observations per copy. Its gain exceeds the current
full-phase envelope by only 0.106/0.035 dB, less than its approximately
0.23 dB within-window ratio drift. All 60 passing software controls are
inside that envelope. A05 does not robustly reject the current mapping.

## Disposition and reproducibility

The next useful work is to constrain the delay law with another qualified
known-preset passage. Fitting filter or distortion coefficients to these wet
spectra first could compensate for an effects error. The dry A02 mismatch
remains a separate unresolved problem.

A bank-only screen ranks **A04 Jupiter8reso** next: it has the same complete
delay settings as A03, overdrive off, and Upper amp sustain 84. Its persistent
Lower sine still excludes H1 from simple Upper-only inference. Its recorded
interval has not yet been qualified. A06 offers a later zero-feedback contrast
with a different modulation depth and rate. None of the remaining RCS patches
varies raw delay TIME, so they cannot alone calibrate that complete curve.

The [compact evidence index](rcs-stereo-delay-results-2026-09-20.json) pins
the designs, source fits, exact transfer calculations, software controls,
plot inputs and scripts. Detailed outputs remain in ignored
`build-fidelity/rcs-stereo-delay-audit-2026-09-20/`; third-party audio is not
added to Git. A synthetic known-delay test verifies ratio sign and origin
to 2.2e-8, and the analysis runners passed help/overwrite checks. Existing
baseline audio was reused; this round required no new instrument renders.
