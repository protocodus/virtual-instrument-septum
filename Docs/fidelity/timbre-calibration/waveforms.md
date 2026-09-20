# Waveform phase, gain and pulse-width candidates

Comparison profiles now express separate phase conventions and signed gains
for saw, square, pulse, triangle and sine, plus the full pulse-width table.
The phase shift moves the waveform and its BLEP/BLAMP correction together.
It does not accumulate in the oscillator clock or change its frequency.
SYNC retains its canonical master clock; this option does not claim to
identify a hardware master-trigger or free-running phase-allocation policy.

This makes the diagnostic in the [Dist Bs 1 audit](../source-audits/dist-overdrive-phase.md)
reproducible without rewriting source. A triangle inversion improved selected
harmonic ratios across six Dist notes but worsened Moogie odd harmonics. It
therefore remains an explicit experiment. Neither
[Roland's waveform descriptions](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf#page=28)
nor the associated recordings establish a universal polarity correction.

The [thirteen-preset follow-up](../source-audits/triangle-crosscheck-2026-09-20.md)
tests seven discrete phase/gain candidates. Triangle gain −1.5 improves all
five affected whole-excerpt spectral scores, but Moogie's odd-harmonic error
still increases in every tested channel/window-shift combination. All eight
unaffected presets remain byte-identical. It remains a diagnostic tradeoff.

Focused audio tests verify default identity for all five waveforms at three
rates, signed gain inversion including corrections, half-cycle equivalence
to polarity inversion for symmetric waves, and pulse-table equivalence to an
independently moved PW control. Phase/range validation precedes installation.
The plug-in does not select a diagnostic convention or alter existing presets.
