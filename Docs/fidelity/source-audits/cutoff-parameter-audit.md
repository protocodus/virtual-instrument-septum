# Cutoff and envelope parameter audit

2026-09-13. This is a source and implementation audit, not a newly measured hardware cutoff table. No shipping DSP was changed for this audit.

**No incorrect signed range, missing scale factor, or wrong C4 key-follow pivot was found in the current import path.** The important unresolved quantities are the cutoff frequency curve, filter-envelope depth and sustain curves, and velocity's cutoff offset. Public Roland editor values do not establish their DSP units. The baseline inspected here used a **10-octave** filter-envelope maximum, not 18, and unmodulated cutoff endpoints of **20 and 20,480 Hz** before the final sample-rate clamp.

The subsequent [brightness investigation](../brightness-investigation.md) adopted a **12-octave** envelope range from conditional recording comparisons. That changes the empirical depth calibration; it does not change the documented byte interpretation or make the numerical range a documented Roland specification. The base cutoff curve remains unchanged.

## Primary sources and exact fields

The [MIDI Implementation](https://static.roland.com/assets/media/pdf/SH-201_MI.pdf), printed p. 5, and the public [Roland Editor 1.10](https://static.roland.com/assets/media/dmg/SH201_Editor110_osx.dmg) agree on the following tone-block bytes:

| Offset | Editor field | Wire range | Native interpretation |
| --- | --- | --- | --- |
| `13` | `filterCutoffFrequency` | 0–127 | Unsigned control value |
| `14` | `filterCutoffKeyfollow` | 44–84 | `(raw−64)*10`, giving −200…+200 |
| `15` | `filterCutoffVelocitySens` | 1–127 | `raw−64`, giving −63…+63 |
| `16` | `filterResonance` | 0–127 | Unsigned control value |
| `17` | `filterEnvAttackTime` | 0–127 | Unsigned control value |
| `18` | `filterDecayTime` | 0–127 | Unsigned control value |
| `19` | `filterSustainLevel` | 0–127 | Unsigned control value |
| `1A` | `filterReleaseTime` | 0–127 | Unsigned control value |
| `1B` | `filterEnvDepth` | 1–127 | `raw−64`, giving −63…+63 |

Reading-copy locations are `BufferModel.xml.utf8.txt` lines 654–725 and `PatchFilter.xml.utf8.txt` lines 75–125, 185–259. The cutoff knob and its display bind directly to the same field. Key-follow display applies offset −64 and `kf-200-10Table`; `Resource.xml.utf8.txt` lines 548–554 lists −200, −190, …, 0, …, +190, +200. Depth and velocity displays use offset −64. There is no cutoff Hz table or depth-to-octaves table in these bindings.

The editor envelope graph binds its start/end levels to 0, its attack peak to 127, and both sustain points to `filterSustainLevel`. Its four times bind to the documented ADSR fields. This corroborates the graph's stages and endpoints; it does **not** prove that its drawn vertical coordinate is physical Hz, logarithmic frequency, or an exact firmware control curve.

The [Owner's Manual](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf), p. 36, graph was rendered and visually checked: its lines intersect at **C4**, +100 gives one octave of cutoff change per keyboard octave, and +200 gives two. The current `(glidePitch−60)/12 * keyFollow/100` follows that diagram. Page 37 gives the envelope's direction and segment roles, including sustain moving downward when depth is negative. Page 61 repeats the numeric parameter ranges; it additionally distinguishes the panel shortcut's nonnegative cutoff-velocity settings from the wider signed editor range.

The official [Synthesizer 101 Course with SH-201](https://cdn.roland.com/assets/media/pdf/sh_201_synthesis_101.pdf), printed pp. 11–12, independently illustrates the filter, envelope, and key-follow controls. It describes the cutoff minimum as making most sound inaudible, but supplies no absolute cutoff endpoint or envelope-depth calibration. Its examples use knob positions rather than physical frequency/time tables. They cannot justify inferring such a table from the pictures.

## Current DSP mapping

At settled controls, before clamping and excluding any LFO/lever contribution:

```text
log2(fc) = log2(20)
         + cutoff * 10/127
         + keyFollow/100 * (glidePitch−60)/12
         + (velocitySens/63) * (velocity/127−0.5) * 8
         + envelopeLevel * depth * range/63

fc = clamp(2^log2(fc), 5 Hz, 0.45*sampleRate)
envelope sustain level = rawS/127
range = 12 octaves after calibration; 10 in the inspected baseline
```

The filter's TPT coefficient is `tan(pi*fc/sampleRate)`. This `fc` denotes the modeled natural frequency, not necessarily a −3 dB corner or the frequency of maximum resonant gain. The [transfer audit](filter-transfer-audit.md) already checked the coefficient arithmetic against an independent transfer calculation. Moving its meaning to a different physical frequency requires calibration evidence, rather than treating the label CUTOFF as proof of a particular corner definition.

| Raw cutoff | Current natural frequency |
| ---: | ---: |
| 0 | 20.00 Hz |
| 30 | 102.83 Hz |
| 31 | 108.60 Hz |
| 47 | 260.06 Hz |
| 64 | 657.71 Hz |
| 91 | 2,870.89 Hz |
| 95 | 3,571.32 Hz |
| 127 | 20,480.00 Hz |

The baseline depth scaling implies that one envelope-depth step contributes about **2.016 cutoff-control steps** at the envelope peak; the adopted 12-octave range gives **2.419**. These follow algebraically from the chosen mappings; neither relationship is established by the byte ranges. The editor's signed depth range alone cannot determine whether the hardware uses either relationship, a different gain, or a nonlinear table.

The envelope currently rises linearly to 1, falls linearly to `S/127` using the previously adopted decay fit, and releases exponentially. Filter attack/release timing and the sustain curve remain provisional. The [Moogie decay investigation](../filter-darkness-investigation.md) supports the conditional raw-D49 decay duration, not every ADSR value or an independently measured sustain law. A linear sustain fraction in logarithmic cutoff space is not the same as a linear interpolation in Hz.

Velocity currently adds a bipolar offset around MIDI velocity 63.5. Its full sensitivity spans nearly −4…+4 octaves. The manuals establish sensitivity and direction but do not specify this pivot, magnitude, or interpolation. Cotton's sensitivity +18 therefore gives −1.125 octaves at velocity 1, +0.657 at 100, and +1.143 at 127. Raising the reconstructed velocity from 100 to 127 changes its modeled cutoff by only +0.486 octave. These are implementation predictions; the original performance velocities are not known.

## Findings relevant to the brightness comparison

1. **Use independent controls to identify independent curves.** Air Lead 1 has cutoff 91, envelope depth 0, velocity sensitivity 0, and key-follow +50. After establishing its performed note, its filter response can constrain the base cutoff curve without an envelope-depth or velocity ambiguity. Moogie has sustain 0, key-follow 0, and velocity sensitivity 0 in both tones; its transient and later tail help separate base cutoff from envelope depth and decay. Those recordings still have their documented waveform/layer limitations.
2. **Cotton cannot determine all curves by itself.** Its upper tone combines cutoff 0, depth +39, sustain 87, velocity sensitivity +18, and key-follow +60. At sustain, changing depth, the sustain curve, or the unknown performed velocity can all change the same total cutoff offset. A global brightness correction fitted only to Cotton can absorb the wrong cause. SupaJuce's depth +31 and sustain 74 provide another intermediate-envelope anchor with velocity sensitivity 0; these raw settings are recorded in the existing [named-reference inventory](named-reference-filter-candidates.json).
3. **There is a separate, unresolved keyboard-shift question.** `glidePitch` is the incoming note number. System transpose, system octave shift, master key shift, and tone octave shift are added later to oscillator pitch, while key-follow uses unshifted `glidePitch`. Owner's Manual pp. 18–19 and 69 describe shifting the keyboard range, but the inspected material does not explicitly define the resulting filter-keyfollow ordering. A comparison of a physically higher key against OCT UP on a low key would resolve this. It is a concrete implementation asymmetry to investigate, not a confirmed bug or a reason to alter pitch-bend/oscillator-coarse tracking. At zero system shifts it cannot explain the current brightness discrepancy.

Further calibration should hold velocity sensitivity and envelope depth at zero while estimating cutoff, then estimate envelope depth against that fixed curve. Sustain needs at least one held note with an intermediate sustain value and enough time to reach it. A known-velocity capture is needed before changing velocity's center or gain. The present documentation supports the parameter routing and signs; it does not justify silently replacing the numerical curves with values borrowed from another Roland instrument.

## Review of the adopted depth change

Comparison with the isolated `brightness-investigation/renderers/depth-10` baseline found exactly one functional edit: `filterEnvOctaves` changes from `depth*10/63` to `depth*12/63`. `SeptumEngine.cpp` is identical. The helper has one production callsite, which adds the signed voice-envelope contribution to logarithmic cutoff. Pitch and amplifier envelopes, base cutoff, velocity, LFO depth, and the separate AUDIO FILTER do not use this helper. Parameter IDs and stored raw signed values are unchanged; a state or UI migration would be inappropriate for this model calibration.

`testFilterEnvelopeRange` probes the actual voice engine at depths −21, 0, and +21, testing expected shifts of −4, 0, and +4 octaves at 44.1/48/96 kHz. Its frequencies stay below the sample-rate cutoff clamp, and its low-amplitude EXT-IN stimulus avoids internal limiter saturation. The test meaningfully checks depth magnitude, direction, and neutrality. It pins the adopted model; the negative and extreme settings remain unmeasured hardware extrapolations, as the source comment states. No functional issue was found in this narrow change.

## Source identification

Original-byte hashes, distinct from normalized XML reading copies:

| Source | SHA-256 |
| --- | --- |
| Owner's Manual PDF | `b4a2968d429c7f3e907a6243723d5e803ae2e0014e8e9107c85bd966deea8e79` |
| MIDI Implementation PDF | `71a8fe00a8d232c494a5aba6885756d99e6650fc14671115260d9446c3009546` |
| Synthesizer 101 PDF | `3ffa5f7b52c87332ff3ff682b1addca36f5eb14513c298b7620cfc50bbb62d2f` |
| Editor `BufferModel.xml` | `e8b51e54b397eb1715a05a2efa52e984e1d7cd4929e071ded58d30b022c313d5` |
| Editor `PatchFilter.xml` | `0aad4d92a038fd42106167c10155e456a863578e6be635b0f94ec847763d47cc` |
| Editor `Resource.xml` | `e609e52d8006023946754668c5a313168e0d69e07154dcd0a19d40c13ef84840` |

The editor package provenance is retained in the [oscillator semantics audit](oscillator-semantics.md). These resources are public editor definitions, not recovered DSP firmware. The baseline audited before depth adoption had `SeptumEngine.h` SHA-256 `8deba4bc921b25e4e596b0e8d182daa3964057cb5faa7d959099000c24382239`, `SeptumEngine.cpp` `5026b016905b7743091b010078d4d378087ea3b15e48a19d722fd19739998bd4`, and `SeptumSysEx.cpp` `8d7a431f7275e7a9185f5e718080335b40a23331f9f200fe0f07557ac47bf138`.
