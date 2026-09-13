# Cotton Wool: current envelope mechanics and source-phase ambiguity

This audit finds **no verified arithmetic or SysEx-routing error** in Cotton Wool's filter envelope. It establishes what the present implementation actually does, without treating that implementation as a measured Roland envelope law. The main unresolved choices are sustain interpolation, attack/decay/release time maps, velocity response and the Super Saw source itself.

An instrumented copy of the production renderer generated a **byte-identical WAV** to the brightness-corrected Cotton comparison. The observations below therefore describe the audible production render, not a substitute analytic synth. No shipping source or preset was changed.

## Published settings and source limits

Roland's [PAD patch page](https://www.rolandus.com/go/sh-201_patches/patch_pad.html) links the [Cotton Wool recording](https://www.rolandus.com/go/sh-201_patches/mp3/PAD/TOP8_Cotton_Wool.mp3) and [PAD librarian bank](https://www.rolandus.com/go/sh-201_patches/shl/SH-201_Patch_PAD.zip). PAD #1 is `Cotton Wool`. The current comparison uses its original exported SysEx, SHA-256 `e7f23e39445895f2158482037b37a19dfe413e536869c0e6f78352de6e49fbef`.

The Upper tone is active in Single/Poly mode. Its relevant bytes decode as follows; offsets are within the Upper tone's 64-byte block:

| Parameter | Offset | Wire value | Decoded value |
|---|---:|---:|---|
| Filter type / slope | `11` / `12` | 1 / 1 | LPF / 24 dB |
| Cutoff | `13` | 0 | 0 |
| Key follow | `14` | 70 | +60 |
| Cutoff velocity sensitivity | `15` | 82 | +18 |
| Resonance | `16` | 0 | 0 |
| Filter A / D / S / R | `17`–`1A` | 10 / 58 / 87 / 105 | unchanged |
| Filter depth | `1B` | 103 | +39 |
| Amp A / D / S / R | `21`–`24` | 0 / 0 / 127 / 39 | unchanged |
| Amp velocity sensitivity | `1F` | 64 | 0 |
| Tone delay / reverb send | `25` / `26` | 0 / 35 | 0 / 35 |
| OSC1 wave / PW | `00` / `04` | 7 / 41 | Super Saw / spread 41 |
| OSC2 wave / coarse / fine | `06` / `08` / `09` | 4 / 28 / 57 | sine / −12 physical semitones with WIDE off / −7 cents |

`SeptumSysEx.cpp` reads filter S/R/depth from `19`/`1A`/`1B`, without swapping them with the amp parameters. The signed and scaled conversions agree with the [MIDI implementation](https://static.roland.com/assets/media/pdf/SH-201_MI.pdf), p. 5, and public [Editor 1.10](https://static.roland.com/assets/media/dmg/SH201_Editor110_osx.dmg) `BufferModel.xml` field definitions. These sources establish raw values and control identity, not the numerical DSP transfer functions.

The [Owner's Manual](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf), pp. 37 and 61, specifies an attack toward the envelope peak, a decay to a sustained cutoff, and a release toward minimum. It gives no durations in milliseconds, no sustain-to-Hz interpolation and no declaration that the diagram's cutoff axis is linear in Hz. The diagram alone cannot establish a linear-Hz envelope. Local primary-source copies and their hashes are recorded in [the adjacent SupaJuce audit](supajuce-brightness.md).

The comparison's **velocity 100 and note gates are reconstructed placeholders**, not values recovered from the performance. The original MIDI, controllers, system settings and recorded patch revision remain unauthenticated. Both global delay and reverb switches are enabled, but the active Upper tone's delay send is **0** and reverb send is **35**. Reverb is therefore the relevant modeled wet path here; the global delay switch alone does not imply an audible delay return.

## What cutoff 0 and sustain 87 mean in the current engine

The actual filter cutoff is not fixed at the cutoff knob's base value. At velocity 100, the current equations are:

```text
E_sustain = 87/127 = 0.6850393701
depth_octaves = 39 * 12/63 = 7.4285714286
velocity_octaves = (18/63) * (100/127 - 0.5) * 8 = 0.6569178853
base_Hz = 20 * 2 ** (0.6*(played_note-60)/12 + velocity_octaves)
cutoff_Hz = base_Hz * 2 ** (E * depth_octaves)
```

Thus the cutoff knob is the base before the positive envelope, key-follow and velocity offsets:

| Played MIDI note | Base Hz | Peak Hz | Held sustain Hz |
|---|---:|---:|---:|
| 48, first low note | 20.80 | 3584.16 | 708.05 |
| 60, repeated C | 31.53 | 5432.56 | 1073.20 |
| 63, held E-flat | 34.99 | 6027.81 | 1190.80 |
| 65, held F | 37.50 | 6460.44 | 1276.26 |
| 69, held A | 43.08 | 7421.10 | 1466.04 |

These are mathematical targets; the trace differs slightly around attacks because controls update on sample groups. The resonance-zero first-stage damping is 2 and the second stage's damping is 1.2. The oscillator's tracked high-pass is a separate upstream stage, not the voice cutoff in this table.

Sustain 87 currently means **68.5% of the envelope's log-cutoff excursion**, not 68.5% of peak frequency. For this depth, sustained cutoff is only **19.75% of peak Hz**. An alternative linear-Hz interpolation between the same base and peak would place the first low note near 2462 Hz instead of 708 Hz. That large difference makes the interpolation domain worth measuring, but the published documentation does not justify choosing the alternative. It would affect attack and decay trajectories as well as the sustained value.

Likewise, velocity 100 supplies an offset of +0.657 octave under the current voiced sensitivity mapping. Matching raw preset bytes does not remove uncertainty in the unknown original velocity or in that response curve. No velocity was adjusted to improve this comparison.

## Timing and verified trace

The implementation's current mappings give:

| Segment | Current meaning and duration |
|---|---|
| Filter A10 | Linear envelope rise from zero to peak in **1.9555 ms** |
| Filter D58 | Linear envelope decline from peak to S87 in **757.8646 ms** |
| Filter S87 | Envelope level **0.685039**, held until note-off |
| Filter R105 | Exponential envelope release: **2.658878 s to −60 dB of the envelope amount**, time constant **384.912 ms** |
| Amp R39 | Exponential amplitude release: **28.9234 ms to −60 dB**, time constant **4.187 ms** |

The filter's D mapping comes from a prior conditional recording calibration; its A/R and sustain curves remain voiced. Filter release is exponential in envelope amount. Because that amount modulates an exponential cutoff map, the resulting release in Hz is not a single ordinary exponential toward zero.

For the first reconstructed event, MIDI 48 starts at about 0.125 s and ends at 0.370 s. The trace shows:

| Age after note-on | Filter envelope | Actual target cutoff Hz | Amp envelope |
|---|---:|---:|---:|
| 1.995 ms | 0.999991 | 3583.98, peak | 1 |
| 25.034 ms | 0.990416 | 3411.57 | 1 |
| 105.034 ms | 0.957169 | 2874.79 | 1 |
| 244.989 ms | 0.899005 | 2130.79 | 1 |
| 264.943 ms, about 20 ms after release | 0.853586 | 1686.45 | 0.008894 |

The filter already declines throughout absolute time approximately 0.150–0.230 s. That fact alone does not establish a hardware attack mismatch. A 70 ms analysis window centered at 0.150 s straddles the estimated onset and cannot be treated as a clean stationary frame. The cleaner [parallel temporal audit](cotton-envelope.md) reports only a 1.39 dB hardware high/mid-band rise from 0.190 to 0.230 s; the subsequent decline from 0.230 to 0.330 s is stronger, from −2.50 to −7.55 dB. The production ratio is nearly flat over that latter interval, −7.41 to −7.10 dB, despite its falling cutoff. These differences deserve source/filter isolation, but neither the short rise nor the band ratios alone identify a slow Roland envelope attack. Detuned partial interference, finite windows and reverb must be separated first.

The long held E-flat event, MIDI 63 at about 2.625 s with a one-second gate, does reach the current sustain stage:

| Age after note-on | Target cutoff Hz | State |
|---|---:|---|
| 1.995 ms | 6027.51 | Peak |
| 400.000 ms | 2571.89 | Decay |
| 750.000 ms | 1216.13 | Decay |
| 759.977 ms | 1190.80 | Sustain |
| 900.068 ms | 1190.80 | Sustain |
| 1000.000 ms | 1190.80 | Sustain, immediately before release |
| 1019.955 ms | 996.42 | Release; amp level 0.008894 |

The one-second held A and F notes also reach sustain. Their overlapping detuned spectra and wet returns make that recording section less straightforward than a dry isolated note, but it is the relevant section for testing sustain, unlike the many 125 ms gates.

The envelope implementation does not skip sustain or restart on routine patch updates. Its decay step is `(1-sustain)/(D_seconds*sample_rate)`, so it reaches the requested sustain within the segment duration. The convergence tolerance is `1e-4` in envelope level; for Cotton this creates at most about 0.000743 octave of final cutoff adjustment, too small to explain a broad brightness mismatch. Released voices are freed by the amp envelope. In the trace they disappear about **48.3 ms after note-off**, at the amp's approximately −100 dB threshold, while the filter envelope is still releasing. This prevents the full filter R105 trajectory from remaining audible as a dry voice.

A slowly fading recorded sine after the reconstructed gate may reflect an incorrect gate estimate, a different amp-release curve or wet tails. The present source audit cannot distinguish those possibilities and does not recommend changing amp release on that basis.

## Super Saw beating is a real competing mechanism

Cotton's Super Saw phase vector is randomized on each engine trigger. The detune polynomial, seven frequency offsets and phase behavior derive from related JP-8000 research; the exact SH-201 topology, fixed internal center/side mix and tracked high-pass are not directly calibrated. This is already an open fidelity question, not a newly discovered filter bug.

At PW41 the current spread factor is **0.0619729710**. For the first MIDI-48 Super Saw, the seven frequencies are approximately:

```text
129.920841, 130.302988, 130.654508, 130.812783,
130.974208, 131.316748, 131.683884 Hz
```

The outer pair's difference is 1.763043 Hz. Its beat period is about **567 ms at the fundamental**, and **56.7 ms at the tenth partial**. Therefore high harmonics can rise, fall or cancel over ordinary short measurement windows even while the filter cutoff falls monotonically. A single-saw `1/n` source correction or a single amplitude sample at each exact harmonic would conflate these source changes with the filter.

Sine/Super Saw balance also cannot be inferred from one short spectral frame without accounting for the stack's phases and its upstream high-pass. A robust next measurement would track energy across the complete detuned harmonic clusters and compare repeated notes/independent phase realizations before assigning a broad-band brightness trajectory to the envelope. No exact Roland phase vector or filter law has been inferred from these calculations.

## Reproduction and provenance

The scratch instrumentation and its build/render commands are retained under:

```text
/tmp/septum-hw-benchmark/cotton-envelope-model/build_trace.py
/tmp/septum-hw-benchmark/cotton-envelope-model/trace.csv
/tmp/septum-hw-benchmark/cotton-envelope-model/phases.csv
/tmp/septum-hw-benchmark/cotton-envelope-model/provenance.json
```

Run `python3 /tmp/septum-hw-benchmark/cotton-envelope-model/build_trace.py` to rebuild the observed frozen renderer and regenerate the trace. It copies the preserved `brightness-investigation/renderers/depth-12` snapshot, adds only file logging after the actual cutoff calculation, and renders the existing production-after MIDI and SysEx. It asserts audio hash equality. Source and trace hashes:

| Artifact | SHA-256 |
|---|---|
| Frozen renderer profile | `643331150fb06da22363fef7c047455cdbd69931068f3554a7d56badef604d7f` |
| Uninstrumented `SeptumEngine.cpp` | `5026b016905b7743091b010078d4d378087ea3b15e48a19d722fd19739998bd4` |
| Reconstructed MIDI | `9794993003bca0f1af71f2a39d30e294c6bf862ab1d6aabdbea50d145d0ce69f` |
| Production WAV **and** trace WAV | `38ff7e62a22b4d65d5785072093ec5d9022bfba8d442770a723fbb4d159adb12` |
| `trace.csv` | `11667a706f0cbde95f05ca39be4bbefc02336b73c63d8b10631d861c6651c347` |
| `phases.csv` | `19f768388f5ec392be2478120dc3912105c0b4658ff5d0452d0084c256af7720` |

Trace `age=1` identifies the first low note; `age=33` identifies the held E-flat. `elapsed_samples/44100` is voice age at the logged control update, not the recording's absolute time. Filter stage numbers are Idle=0, Attack=1, Decay=2, Sustain=3 and Release=4. The rendered audio retains its declared 93-sample output latency.
