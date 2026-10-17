# Reconstructed input and oscillator balance audit

2026-09-20. The three added recordings have consistent published-patch routing
and supported pitch families; this audit found no demonstrated note or routing
error to correct. Original performance MIDI and the exact recorded patch
revision remain unavailable. Published presets and authoritative reconstructions
were not changed. The [measurement JSON](benchmark-input-audit-2026-09-20.json)
retains input hashes, exact perturbations and source identities.

## Bounded gate sensitivity

Each probe uses the frozen baseline renderer, unchanged SysEx, 44.1 kHz,
master 100 and preserved patch tempo. The same whole-excerpt metric measures
normalized stereo Welch power in 32 geometric bands from 25 to 12,500 Hz.
These are sensitivity probes, not recovered MIDI or fitted replacement gates.

| Case | Replay uncertainty tested | Original residual | Perturbed residual | Largest model-shape change |
| --- | --- | ---: | ---: | ---: |
| Class A | Add 2, 10 or 25 ms note overlap | 2.069 dB | 2.541 dB | 0.816 dB |
| Sexy Back | Shift notes by +/-10 ms; separately change releases by +/-10 ms | 5.680 dB | 5.680-5.756 dB | 0.882 dB |
| Trancefloor | Shift onsets by +/-3 ms; separately change releases by +/-15 ms | 2.892 dB | 2.745-2.934 dB | 0.336 dB |

Model-shape change compares the perturbed render against the original software
render using its own reference-band mask. It is not directly interchangeable
with the hardware residual or a confidence interval. Small changes in the
aggregate hardware residual can conceal larger changes in individual bands.

Class A is single Upper, saw plus saw one octave apart, in SOLO+LEGATO mode.
The reconstruction's adjoining note-offs precede simultaneous note-ons, so
they retrigger envelopes. Even 2 ms overlap selects different legato behavior.
The hardware's continuous phrase does not establish those original key gates.
Its two-saw mixture also has overlapping, phase-sensitive harmonics.

Sexy Back uses dual tones: two Upper Super Saws and Lower triangle plus saw.
The settled triangle fundamental near 19.16 Hz is below the matrix's 25 Hz
analysis bound. Its waveform score therefore depends on higher harmonics,
mixed-source cancellation and overdrive, rather than direct measurement of
that fundamental. Its separated notes support the stated gates approximately;
the release perturbations remain inside their documented uncertainty.

Trancefloor uses two Upper Super Saws, with estimated MIDI 39 and octave
spacing consistent with the patch. Its later crop retains a quiet hardware
effects tail while software starts with empty effects. Both this and Class A
contain no active triangle: triangle-only candidates should leave their raw
renders identical.

All raw sensitivity WAVs, MIDI files and render manifests remain under
`build-fidelity/public-match-2026-09-20/benchmark-routing-audit/`. The unchanged
baseline comparisons remain in their original case directories. The JSON
records the renderer, source audio, preset, reconstruction and analysis hashes.

## What the 13-case set says about triangle candidates

Only **five** cases contain an active triangle: Moogie 1, Dist Bs 1, Air Lead 1,
Club Bass and Sexy Back. The other eight are regression controls, not eight
additional votes supporting a triangle change. Selection over all 13 without
that distinction dilutes regressions in the five affected sounds.

Current classic oscillators start at zero phase on engine reset, retain their
phase across note triggers, and advance only while their voice is active
(`SeptumEngine.cpp`, reset, `triggerVoice`, and the active-voice render loop).
They do not independently keep running while idle. Consequently a fixed
waveform phase candidate can compensate for unknown hardware voice allocation
or prior phase history. A polarity improvement alone does not identify which
of those conventions differs on hardware.

Before considering a general waveform change, declare training and validation
roles, assess all five affected sounds separately, inspect withheld harmonic
ratios and temporal windows, and verify that the candidate's ranking survives
plausible gates and onset shifts. Once a sweep is selected using every case,
those same cases are no longer untouched heldouts. Raw level and nonlinear
processing differences also need inspection alongside normalized listening.

## Oscillator BALANCE: source evidence and interpretation

Roland's manual establishes which oscillator becomes favored in each direction
and that the endpoints isolate one oscillator. Its parameter list and MIDI map
specify the signed range. The inspected passages provide no gain graph,
numerical center attenuation, or constant-sum/constant-maximum specification.
The page 33 illustration is a panel diagram, not a transfer curve.
[Owner's Manual, pp. 33 and 60](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf#page=33),
[MIDI Implementation, p. 5](https://static.roland.com/assets/media/pdf/SH-201_MI.pdf#page=5)

With stronger leg fixed at one, the current weaker leg is `1-|b|/63`.
The proposed alternative `(63-|b|)/(63+|b|)` changes the weaker leg at
`b=-26` from 0.58730 to 0.41573, a **-3.001 dB relative change**. Both formulas
preserve the center and endpoint gains. The alternative comes from a linear
constant-sum crossfade followed by normalization of its stronger leg to one;
the final gains are therefore **constant maximum, not constant sum**.

Uncalibrated recording level and scalar RMS normalization cannot distinguish
absolute gain normalization in a linear path. Relative oscillator families
can constrain the mix ratio only conditional on waveform/phase conventions,
filter response and recording processing. Class A's octave saws have coincident
harmonics; SupaJuce's separated square-wave harmonic families provide cleaner
relative-level evidence, while their frequency-dependent filter and capture
response remain confounders. A shared deficit at one balance value does not
establish the entire knob curve.

Finally, `mapping::balanceLegGain` is used for both oscillator and tone balance.
An oscillator experiment must not silently change between-tone mixing as well.
Roland documents tone balance separately without a numerical gain law; the
two oscillator references cannot establish that second curve.
[Owner's Manual, p. 64](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf#page=64)
