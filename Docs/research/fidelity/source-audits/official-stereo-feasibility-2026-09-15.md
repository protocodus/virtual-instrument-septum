# Air Lead and Cotton: stereo and Super Saw measurement feasibility

**The opening comparisons identify a stereo difference, but do not identify a Super Saw detune correction. Complete-file decays reverse the simple “reverb is too wide” interpretation:** Cotton's late hardware tail is wider than the model control, although the model is wider in the early gap and held-note excerpts. See the [complete-tail check](official-reverb-tails-2026-09-15.md) before interpreting the opening measurements.

No shipping source, phase vector, detune table, reverb parameter or reconstructed event was fitted or changed in this audit. The [full result](official-stereo-feasibility-2026-09-15.json) preserves all controls, intervals, spectral peaks, source/build hashes and original parameter blocks.

## Stored controls and forward model

The SysEx files are identical to the previously verified published patches. This establishes the downloaded patch bytes; Roland's recordings do not authenticate their performance MIDI, controller state, capture chain or exact recorded patch revision.

| Control | Air Lead 1 | Cotton Wool |
|---|---|---|
| Active tone | Single Upper, centered pan | Single Upper, centered pan |
| Oscillator 1 | Triangle | Super Saw, spread raw41 |
| Oscillator 2 | Saw | Sine, −12 semitones / −7 cents |
| Mixing | Centered MIX, low-frequency BOOST | Centered MIX, FLAT |
| Delay send / reverb send | 35 / 88 | 0 / 35 |
| Delay block bytes | 47,59,17,5,10 | 70,66,8,5,10 |
| Reverb block bytes | 86,10,7,19,127,127,19,36,0,36 | 104,125,7,19,127,127,19,36,0,36 |
| Documented reverb pre-delay | 1 ms | 100 ms |

Air Lead contains **no Super Saw**. Its active pitch modulation, triangle pitch envelope and wet effects make it a stereo/effects control, not a detune reference.

At checkpoint `b0f6c03`, Super Saw sums seven randomized phases to one sample, passes that sum through its tracked high-pass, then enters the common mixer, voice filter and amplifier. Tone pan turns this mono sample into left/right gains. The active tone is centered, so arbitrary internal phase/spread changes cannot themselves create dry stereo. The delay has quadrature modulation between channels; its return also feeds the reverb. Cotton's delay send is zero. These are implementation facts, not an assertion of original hardware topology. The [Super Saw calibration scope](../timbre-calibration/supersaw.md) and [earlier Cotton phase audit](cotton-envelope-model.md) remain applicable.

Six controls per patch use unchanged reconstructed MIDI: original, both effects off, delay only, reverb only, dry oscillator1 only, and dry oscillator2 only. Oscillator controls change only Upper balance to raw1 or127. Effects controls change only the documented common switches; every edited byte and checksum is retained. All12 renders are finite and finish with zero active voices. Both originals reproduce pinned production WAVs **byte for byte**. Frozen source hashes are checked against Git `b0f6c03`, and the E10 identity build's binary/profile/source hashes are checked against its manifest.

Cotton dry left/right samples are exactly equal. Air's maximum dry channel difference is `2.27e−13`. The separate oscillator controls sum to the dry mix within `2.42e−8` maximum absolute float error. Cotton original equals reverb-only byte for byte; delay-only equals effects-off. Thus any stereo measured in that replay originates in the reverb path.

## Fixed early and later regions

Times use the original excerpt clock. Only the renderer's known93-sample latency is removed. No hardware delay, EQ, global audio gain or phase is fitted. One scalar predicting right from left is fitted to each signal's first named interval and frozen for its later checks; raw stereo ratios are also retained. This scalar describes a channel relation, not a physical capture-gain estimate when the signal is already wet.

The table uses raw `10log10(Pside/Pmid)`, with mid=(L+R)/2 and side=(L−R)/2. Larger numbers mean more side energy. It is not a perceptual error percentage.

| Region, seconds | Hardware side/mid dB | Production side/mid dB |
|---|---:|---:|
| Air training .065–.115 | −9.25 | −15.20 |
| Air second note .155–.215 | −11.41 | −11.29 |
| Air held note .50–1.05 | −10.30 | −9.82 |
| Air later note2.15–2.50 | −7.19 | −6.91 |
| Cotton training .155–.210 | −28.98 | effectively mono |
| Cotton late first note .260–.350 | −28.88 | −28.53 |
| Cotton first gap .410–.485 | −14.77 | +3.17 |
| Cotton second note .535–.610 | −21.44 | −11.21 |
| Cotton held chord2.85–3.30 | −18.32 | −10.96 |
| Cotton repeated bass4.155–4.210 | −17.50 | −7.61 |

Cotton's opening has right/left gain+0.599dB, channel cosine0.99985, and1.75% relative residual after the training scalar. The later .260–.350 window remains+0.602dB/cosine0.99981, with1.95% frozen-scalar residual. Its initial side energy is therefore mostly a fixed channel imbalance, not evidence that Super Saw voices are panned apart. The already observed late divergence is compatible with a growing wet contribution; it does not recover the hardware gate.

Control subtraction locates the first nonzero model effect return at .06356s for Air delay and .08005s for Air reverb; the Air training interval is already wet. Cotton's first return is .25508s. Threshold sensitivities through absolute sample difference`1e−4` move these to .06429/.08079/.25626s respectively. They measure model arrivals, not hardware pre-delay.

## Seven-line resolution

Current spread41 gives nominal first-note frequencies129.920841,130.302988,130.654508,130.812783,130.974208,131.316748,131.683884Hz. The nearest spacing is0.158275Hz at the fundamental,1.58275Hz at harmonic10. The pre-predelay window is55ms: its reciprocal width is18.18Hz and its Hann first-zero half-width36.36Hz. Zero padding cannot improve this resolution.

No oscillator frequencies were optimized. A known seven-line sinusoid design assesses conditioning, while periodograms list every local peak above1% prominence within the declared candidate-predicted region. Conditioning is optimistic: it excludes varying amplitudes, neighboring notes and wet returns. Local maxima are not accepted oscillator lines.

| Cotton region | Harmonic | Seven-line design condition | Hardware / known dry-control peak counts |
|---|---:|---:|---:|
| Clean opening .155–.210 | 10 | 2.19million | 1 / 1 |
| Clean opening .155–.210 | 30 | 2045 | 1 / 1 |
| Longer, wet opening .155–.350 | 10 | 666 | 2 / 1 |
| Longer, wet opening .155–.350 | 30 | 2.7 | 6 / 5 |
| Held E-flat chord family2.85–3.30 | 10 | 1.11 | 6 / 6 |

The longer opening improves high-harmonic resolution but overlaps reverb; harmonic30 is approximately−37dB relative to the hardware fundamental peak. In the held chord, geometric resolution improves, but harmonic10 ranges from−39 to−54dB across its three hardware families, with overlapping notes and wet returns. Even the known dry control does not consistently produce seven independent local peaks. Higher bands acquire many extra maxima as signal level falls. These results do not identify seven frequency offsets, internal phase statistics or a global spread law.

**Next useful hypothesis:** separate wet/dry proportions, frequency-dependent reverb output and decay behavior. A fixed width experiment can be tested provisionally, but must retain the full-file late-tail counterexample. This audit supports no detune or width promotion.

## Reproduction

Build the pinned corpus and E10 identity renderer using the tracked [cutoff experiment workflow](cutoff-taper-generalization-2026-09-15.md), then run:

```sh
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 python3 Tools/assess_official_stereo_feasibility.py \
  --corpus build-fidelity/hardware-benchmark/final-production-linear-lfo \
  --renderer-build build-fidelity/hardware-benchmark/cutoff-taper-candidates/run-01/builds/cutoff-e10 \
  --output build-fidelity/hardware-benchmark/stereo-feasibility/reproduction
```

The tracked tool supplies all patch interventions and measurement definitions. No ignored scratch script is required. Recorded run:`stereo-feasibility/run-02`;12 audio hashes also agree with run01 before the additional manifest guards. Source/renderer identity and raw metrics do not depend on the enclosing worktree's later Git HEAD.
