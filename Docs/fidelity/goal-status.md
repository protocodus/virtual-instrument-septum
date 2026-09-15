# SH-201 replication goal: current evidence

Status: **active; matching hardware output is not established**. Updated
2026-09-15. Work uses public recordings as requested. No physical-unit capture
is required to continue the present investigations.

## Implemented in this checkpoint

- [Zero-resonance filter response](dry-filter-calibration.md): dry public
  LP12/LP24 recordings with original performance MIDI support reducing the
  first section's damping from 2.0 to 1.2. Across note occurrences excluded
  from fitting, lower-harmonic shape error drops 1.358→0.100 dB and
  1.534→0.201 dB respectively. The low-resonance bridge is provisional.
- [LFO endpoints](source-audits/2026-09-15-new-sources.md): free-running periods
  now follow the owner's published 20.59 s and 40.22 ms measurements. The
  interior rate table remains unmeasured. An independent creator video's
  [sample-and-hold cadence](source-audits/public-lfo-clock-2026-09-15.md) is
  approximately 40.215 ms, corroborating the fast endpoint without selecting
  a new value. The camera does not authenticate the raw rate or sync state.
  A separate [pitch-step test](source-audits/public-lfo-step-smoothing-2026-09-15.md)
  finds that carrier phase can masquerade as sub-millisecond smoothing.
  It supplies no correction to the current direct S&H pitch path or to
  the separate filter-parameter smoothing.
- [Audio agreement assessment](equivalence-assessment.md): measure spectral,
  envelope and stereo residuals, freeze gain/alignment before evaluation,
  retain hashes and distinguish original from reconstructed inputs.
- [Reverb return level](source-audits/reverb-new-preset-validation-2026-09-15.md):
  reduce the current network's wet return from 0.8 to 0.4. Five independent
  neutral-damping public recordings support this provisional correction,
  including a new Class A comparison with three frozen articulation variants.
  Club Bass and Ambient SQR retain damped-tail regressions. This is an overall
  current-model improvement, not an identified Roland coefficient; damping
  calibration must revisit the level.

All 34 configured DSP/tool CTests pass in the latest
[return integration run](source-audits/reverb-return-integration-2026-09-15.md).
Its 22 fresh renders reproduce the selected half-return candidate byte-for-byte;
five unaffected presets also match the earlier baseline.
Universal arm64/x86_64 AU, VST3 and standalone Release builds also succeed,
with [current artifact hashes and local signature checks](source-audits/reverb-level-universal-build-2026-09-15.json).
These implementation tests establish the intended model behavior, not
hardware-output equality. The ten official preset recordings still have
substantial residuals; the new damping change produces mixed full-demo
metrics. Their preset bytes and reconstructed performances are preserved.

## Evidence retained without a default change

- [Envelope curvature](source-audits/deepsonic-envelope-shape-2026-09-15.md)
  appears in dry harmonic estimates and maximum-resonance traces. Two curved
  models remain indistinguishable over the available short notes. Neither
  its raw control table nor the envelope-to-cutoff conversion is identified.
  [Longer chords](source-audits/deepsonic-chord-envelope-2026-09-15.md) now favor
  the frozen exponential-in-Hz trajectory, with independent isolation controls.
  This supports an experimental recipe model; its peak/floor remain extrapolated.
  [Actual preset experiments](source-audits/envelope-preset-holdouts-2026-09-15.md)
  now test Hz and log exponential implementations with a timing grid selected
  only on the first Moogie note. Both give mixed results on other notes and
  ten unchanged presets; neither is promoted. Air Lead and Club Bass remain
  byte-identical controls in both candidates.
  [Complete dry-engine replay](source-audits/dry-envelope-engine-2026-09-15.md)
  validates the implemented physical curves and favors Hz interpolation for
  late chords. Limited LP24 harmonic coverage, timing sensitivity and the
  failed generalization still prevent a production raw-control correction.
- [Triangle phase/amplitude candidates](source-audits/waveform-conventions-2026-09-15.md)
  improve Dist Bs 1 but fail other presets' harmonic checks. No global
  waveform change was promoted.
- [Nominal midpoint resonance](source-audits/deepsonic-q50-audit-2026-09-15.md)
  suggests stronger LP12 resonance, but moving-peak leakage invalidates many
  harmonic estimates and LP24 upper harmonics fail validation. No midpoint
  table or topology change was promoted.
  [Complete-engine Q50 replay](source-audits/deepsonic-q50-engine-2026-09-15.md)
  confirms a split: stronger resonance improves most isolated notes under
  one reconstructed envelope, but worsens the complete sequence; the nominal
  one-second envelope reverses the isolated-note gains too.
- Firmware, service, manual, editor and controller-code searches did not
  yield an authenticated DSP firmware payload. The existing schematic model
  and newly found primary measurements are useful evidence; they do not
  reveal the full synthesis program.
- [Additional public recordings and scope captures](source-audits/public-waveform-recovery-2026-09-15.md)
  provide phase-behavior leads. Their unknown patch settings do not justify
  oscillator drift, restart or waveform corrections.
- [Four-phase audio controls](source-audits/dry-phase-sensitivity-2026-09-15.md)
  show that the existing spectral and short RMS windows respond strongly to
  oscillator phase, especially on low notes. Isolated-note spectra become
  much more stable with longer windows. Hardware envelope errors remain
  larger than these controls; the phase distances are neither a correction
  to subtract nor an equivalence threshold.
- [Additional static-filter preset references](source-audits/static-filter-reference-feasibility-2026-09-15.md)
  do not supply an independent raw-cutoff anchor. JuicyFat's moving second
  layer cannot be separated reliably; SequenceBs's opening disagrees with
  its stored static state; The Choir combines unidentified notes, Super Saw,
  noise and effects. No global cutoff law is inferred from those recordings.
  [Eight- and nine-octave taper experiments](source-audits/cutoff-taper-generalization-2026-09-15.md)
  improve Air Lead but fail to improve the other nine presets consistently;
  the Moogie harmonic checks also regress. All ten unchanged-taper controls
  reproduce production byte-for-byte. Neither replacement is promoted.
- [Classic-Saw alias lines](source-audits/deepsonic-saw-aliases-2026-09-15.md)
  establish a 44.1 kHz folding signature across eight pitches and both dry
  filter slopes. Synthetic codec controls rule out that MP3 round-trip as
  the cause in those controls. Production places aliases at the same
  frequencies but substantially underestimates many recorded levels. The
  high-note main-harmonic shape also differs; the responsible source or
  capture stage has not been identified.
  [Short smoothing-filter models](source-audits/high-note-saw-fir-2026-09-15.md)
  fit much of that waveform shape, but miss important alias notches even
  when their median alias level agrees. Those mathematical fits are not
  full-engine renders and do not justify a production oscillator change.
  [Shared local wrap corrections](source-audits/deepsonic-saw-wrap-kernels-2026-09-15.md)
  also transfer the gross waveform across pitches but fail measured notches;
  small waveform residuals conceal large relative errors in quiet components.
  [Asymmetric corrections](source-audits/deepsonic-saw-asymmetric-kernels-2026-09-15.md)
  improve training alias error to 1.47 dB but still miss other pitches'
  notches by about 17 dB. Encoding the actual candidate spectrum changes
  the disputed line by only 0.006 dB under the tested MP3 encoder.
  [Slope/time controls](source-audits/deepsonic-high-note-invariance-2026-09-15.md)
  identify an early, nearly invariant Q0 high-note region followed by a
  moving response. Q50 differs strongly there, ruling out an unconditional
  cutoff-only bypass. A [22.05 kHz image check](source-audits/deepsonic-half-rate-images-2026-09-15.md)
  finds no independent image family at the tested threshold; it does not
  exclude properly bandlimited internal blocks.
  [Paired slope ratios](source-audits/deepsonic-slope-ratio-fits-2026-09-15.md)
  cancel a shared source response and constrain an ordinary extra filter
  section conditionally. High harmonics reject the frozen low-note cutoff
  extrapolation with that section model; they do not identify a raw-control
  law, precise endpoint or switching threshold.
- [Stereo and Super Saw isolation](source-audits/official-stereo-feasibility-2026-09-15.md)
  identifies reverb as the source of Cotton's modeled stereo, but its clean
  opening is too short to resolve the individual detuned oscillators.
  [Complete hardware tails](source-audits/official-reverb-tails-2026-09-15.md)
  are wider than the model controls, contrary to the earlier mixed passages.
  [Full-engine return experiments](source-audits/reverb-return-candidates-2026-09-15.md)
  therefore test both width and level. Half reverb level improves Cotton,
  Air Lead, SupaJuce and Brassy, but worsens Club Bass's tail-envelope error.
  All 20 unchanged controls reproduce the earlier production byte-for-byte.
  [Two additional preset checks](source-audits/reverb-new-preset-validation-2026-09-15.md)
  support the limited level correction above while retaining Ambient's
  envelope/log-spectrum regressions under all nine gate/velocity scenarios.
  Six Ambient alignments hit the fixed search bound; even the three interior
  alignments retain the regression. No preferred reconstruction is selected.
  [Cotton's effective decay](source-audits/cotton-reverb-decay-2026-09-15.md)
  is longer than the model, while the weaker
  [Class A estimate](source-audits/class-a-reverb-decay-2026-09-15.md) goes the
  other way. [Brassy's final tail](source-audits/brassy-reverb-tail-feasibility-2026-09-15.md)
  contains delay steps and lacks clean later support. No global time
  multiplier follows from these recordings.

## Next work

1. Investigate the high-register saw's nonharmonic lines in the original-MIDI
   dry recordings. Test codec artifacts, oscillator models and filter
   interaction separately before changing the high-note sound.
2. Examine creator recordings for independent oscillator measurements,
   retaining uncertain panel state and unmeasured raw settings explicitly.
3. Investigate the damped-tail mismatch in Club Bass and Ambient SQR, keeping
   reverb level, frequency-dependent decay, source release and active delay
   separate. Preserve their regressions under the new return level and
   validate any damping correction independently.
4. Keep independent validation passages and input uncertainty visible.
   Matching a fitted spectral feature cannot establish complete output
   agreement or a market-wide superiority claim.

The [dry replay and complete reproduction](source-audits/zero-resonance-reproduction-2026-09-15.md)
preserve all models, including failed sensitivity controls. The local
[ten-preset listening page](http://127.0.0.1:58511/) is available while this
session's comparison server is running.
The [synchronized dry player](http://127.0.0.1:58512/) adds the original-MIDI
hardware, production and clearly labeled envelope experiment for both
slopes, with [verified frozen adjustments](source-audits/dry-listening-player-2026-09-15.md).
The [reverb before/after player](http://127.0.0.1:58513/) presents seven active
presets with a shared production-prefix gain and timing, including the two
damped-tail counterexamples. Its [21 audio exports and browser transport](source-audits/reverb-listening-player-2026-09-15.md)
are verified; the served final export is `reverb-listening-player/run-03`.
