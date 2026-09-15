# SH-201 replication goal: current evidence

Status: **matching hardware output is not established**. Updated
2026-09-15. Work uses public recordings as requested. No physical-unit capture
is required to continue the present investigations.

## Implemented DSP and validation

- [Classic Saw wrap response](source-audits/saw-w4-engine-comparison-2026-09-15.md):
  one frozen asymmetric correction learned through the complete engine improves
  alias proxy RMS across all 32 original note/offset/slope windows. Excluding
  the trained note, LP12 error falls 23.690→7.911 dB and LP24 27.309→11.435 dB.
  Air Lead and the unfitted high note 84 also improve spectrally. Some LP24
  harmonics and original-only quiet-bin preset errors regress; all results
  remain visible. The correction is provisional, with fixed 44.1 kHz support
  duration at other host rates and unchanged canonical phase clocks.
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

All 35 configured DSP/tool CTests pass after the Saw integration, including
the existing hard-sync regression and independent source/rate checks.
The [complete production replay](source-audits/saw-w4-production-integration-2026-09-15.md)
reproduces all twelve frozen candidate WAVs byte-for-byte; five unaffected
presets also match the earlier baseline. Universal arm64/x86_64 AU, VST3 and
standalone Release builds succeed, with
[current build logs, artifact hashes and local signature checks](source-audits/saw-w4-production-build-2026-09-15.json).
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
  The [creator-published RCS Acid set](source-audits/rcs-acid-patch06-feasibility-2026-09-15.md)
  adds nine schema-checked presets and numbered demo passages. Patch 06's
  active filter LFO prevents a static cutoff anchor, while its short passage
  and changing note mixtures do not establish an interior LFO rate.
  [Patch 01's longer passage](source-audits/rcs-acid-patch01-feasibility-2026-09-15.md)
  permits many putative cycles, but its dominant brightness cadence coincides
  with the measured level cadence. Known no-LFO sequences reproduce that ambiguity,
  and sequencing can conceal a planted modulation. These features do not
  calibrate raw rate 88 or exclude a weaker recoverable LFO signature.
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
  [Frequency-estimator controls](source-audits/saw-alias-frequency-sensitivity-2026-09-15.md)
  also rule out small pitch or recording-clock offsets as the explanation
  for those large level errors: local-frequency refinement changes the
  measured lines by at most 0.0007 dB in the retained windows.
  [Simultaneous alias separation](source-audits/saw-alias-separation-2026-09-15.md)
  additionally preserves the failed notch predictions when both first and
  second fold families are fitted together. Its independent controls also
  show that omitting a nearby family can bias a joint estimator more than
  the original Hann detector; the benchmark default remains unchanged.
  [Forty-eight periodic-table models](source-audits/high-note-wavetable-models-2026-09-15.md)
  test sampled/Fourier tables, three interpolation methods and deterministic
  harmonic caps with equal postfilter freedom. None reproduces the alias
  pattern across pitches, and no table architecture is identified.
  An [original Roland interpolation patent](source-audits/roland-integrated-interpolation-patent-2026-09-15.md)
  describes distinct windowed low-pass kernels, finite fractional lookup
  and pitch-selected cutoff banks. Its difference coding is algebraically
  equivalent to convolution with the same weights. It supplies a bounded
  new hypothesis, but no SH-201 implementation link or recovered coefficients.
  The subsequent [24 fixed sinc models](source-audits/high-note-sinc-models-2026-09-15.md)
  pass independent kernel and phase-search controls, but every model still
  has at least 33.95 dB alias-bin RMS error on another pitch. Quiet unresolved
  bins remain flagged, and a joint detector retains the failures. These are
  effective waveform-plus-FIR fits, not a comparison against shipping audio.
  An [actual-engine W4 trial proposal](source-audits/asymmetric-w4-engine-test-proposal-2026-09-15.md)
  addresses that distinction: measure the full production baseline and
  learn any source correction through the existing downstream path, so its
  filtering is counted once. A useful partial improvement need not identify
  Roland's architecture or solve every notch before it can be tested.
  The [complete-engine baseline](source-audits/production-high-note-saw-2026-09-15.md)
  now verifies the existing dry renders and measures all five original windows
  with unchanged timing, gains and hardware-only alias masks. H2–H8 ratio
  error is 4.53–11.30 dB for LP12 and 2.94–9.78 dB for LP24; one LP12
  harmonic is 21.97 dB too strong. Fundamental level is within 0.39 dB,
  so a global level correction cannot fix the shape. Both excessive and
  deficient folded components remain. Raw waveform error is reported
  separately because canonical engine phase was not fitted. This completes
  the baseline prerequisite. The subsequent
  [complete-engine W4 comparison](source-audits/saw-w4-engine-comparison-2026-09-15.md)
  selects one frozen source vector, now provisionally adopted as described above.
  Its [independent review](source-audits/production-high-note-baseline-independent-review-2026-09-15.json)
  verifies all ten sample windows, 100 retained alias rows and 344 numerical
  values without discrepancy.
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
  A new [creator routing audit](source-audits/deepsonic-capture-chain-controls-2026-09-15.md)
  finds a 2020 analog MOTU route but cannot authenticate the 2010 recording
  session. [Four same-collection instruments](source-audits/filter-collection-high-notes-2026-09-15.md)
  lack the SH-201's sampled high-note dip/rebound. This weakens a universal
  collection-coloration explanation but does not exclude an SH-specific
  capture path or identify the oscillator's pre-filter response.
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
  A [separate first-key extension](source-audits/ambient-first-note-followup-2026-09-15.md)
  also retains it. All five supportive active presets use SINGLE mode and
  both contrary presets use DUAL, so damping is confounded with layering.
  The common 4 kHz HF corner is above Club's useful measured tail bands;
  a damping diagnosis cannot follow just from the stored negative gain.
  [Common-phase controls](source-audits/dual-reverb-phase-sensitivity-2026-09-15.md)
  preserve both envelope regressions, including on common later supports.
  Half-cycle pairs are exact polarity inversions, so the four tested phases
  represent only two distinct magnitude responses. Independent layer and
  oscillator phases remain separate uncertainties. A subsequent
  [4 × 4 Upper/Lower grid](source-audits/dual-layer-phase-sensitivity-2026-09-15.md)
  retains the regressions in all 16 layer states, with eight distinct
  magnitude responses after polarity symmetry. Individual oscillator
  phases within each layer remain untested.
  [Club's low-band tail](source-audits/club-reverb-decay-2026-09-15.md)
  grows quieter relative to hardware by 2.31–2.42 dB in stereo and
  4.41–4.58 dB in side between fixed early and later supports. Constant
  return gain cannot remove that temporal mismatch. Actual-engine burst
  controls show unstable early modal slopes, preventing a unique damping
  or time-law correction from these short intervals.
  [Cotton's effective decay](source-audits/cotton-reverb-decay-2026-09-15.md)
  is longer than the model, while the weaker
  [Class A estimate](source-audits/class-a-reverb-decay-2026-09-15.md) goes the
  other way. [Brassy's final tail](source-audits/brassy-reverb-tail-feasibility-2026-09-15.md)
  contains delay steps and lacks clean later support. No global time
  multiplier follows from these recordings.
  [201vsJP8000](source-audits/reverb-mode-damping-followup-2026-09-15.md)
  adds a SINGLE preset with −10 dB HF damping under two frozen gate
  hypotheses. Half return slightly improves spectra but worsens stereo
  side-fraction error; its short, mostly direct-sound opening has no isolated
  tail and does not identify a mode or damping correction.
  [Stereo-transfer controls](source-audits/reverb-stereo-transfer-feasibility-2026-09-15.md)
  show that high coherence and phase invariance do not guarantee an accurate
  reverb estimate from short musical windows. Cotton's limited common
  spectral support and the other presets' modulated delays prevent a
  dependable parameter anchor under the tested protocol.
  A [short-tail recurrence control](source-audits/reverb-tail-recurrence-2026-09-15.md)
  passes on simple known modes but fails to predict the exact current FDN's
  later envelope at every declared order. No public pole fitting follows.
  [Verified bus decomposition](source-audits/reverb-tail-bus-decomposition-2026-09-15.md)
  now reproduces three shipping recordings exactly and separates Upper/Lower
  dry, delay, direct-fed reverb and delay-fed reverb. Club's later Side deficit
  belongs to its Upper reverb response: dry Side is zero to rounding, and
  halting new input 250 ms after the reconstructed gate changes no sample.
  Mono output-coupling state explains its low dry-output tail but cannot
  explain that Side mismatch. Ambient's paths remain coherently mixed;
  Cotton's controlled extension still is not its original final performance.
  The decomposition identifies current model contributions, not hardware
  damping coefficients or a global time curve.
  A [fixed-input HF shelf removal](source-audits/reverb-hf-unity-ablation-2026-09-15.md)
  preserves original replay bytes and neutral Cotton exactly, but improves
  Club's later whole-Side level by only 0.50 dB, leaving a 6.85 dB deficit.
  Several Mid bands regress and Ambient's Side excess remains. The endpoint
  changes phase as well as loss; it neither corrects the main discrepancy nor
  identifies an intermediate hardware gain.

## Benchmark numerical correction

The new 201 release hypothesis exposed an
[alignment error near silence](source-audits/alignment-silence-regression-2026-09-15.md).
The scorer now centers candidate envelopes and rejects negligible-variance
windows before normalizing correlation. All 14 assessment tests pass,
including late attacks across four delays and three gain scales. An audit
of 171 historical fitted transformations changes only that new case;
the other 170 retain exact lag and gain. The corrected 201 run preserves
all six original rendered WAVs byte-for-byte. This fixes measurement
reliability and does not change the instrument's DSP.

## Next work

The user's latest listening comparison identifies these concrete targets:

| Preset | Reported difference to correct |
|---|---|
| Vangelead | Increase attack time |
| Moogie 1 | Reduce brightness and increase filter resonance |
| Dist Bs 1 | Reduce brightness, increase filter resonance and restore bass weight |
| Cotton Wool | Increase filter resonance; likely shorten filter-envelope decay |

The [exact control audit](source-audits/listening-feedback-preset-controls-2026-09-15.md)
preserves each active tone's filter, envelope, drive and velocity settings.
These are listener observations, not newly measured parameter laws. Preserve
the original preset bytes while investigating shared DSP behavior. Moogie 1
and Cotton Wool have no active classic Saw and are exact unchanged controls
in the W4 comparison, so their discrepancies require separate work.

1. Investigate the remaining LP24/time-dependent response and quiet alias
   notches after the complete-engine W4 correction. Keep the frozen source,
   original-MIDI and ten-preset comparisons as the new reference, including
   their regressions. A source fitted through the current downstream model
   may absorb downstream or capture-path error; preserve that uncertainty
   when changing the filter or output path.
2. Examine creator recordings for independent oscillator measurements,
   retaining uncertain panel state and unmeasured raw settings explicitly.
3. Investigate the remaining reverb response/state and original excitation
   uncertainty. Verified input halts and the HF-unity endpoint leave Club's
   later Side deficit; they do not identify a replacement network or time law.
   Cotton's opening reconstruction does
   not authenticate its final recorded excitation; preserve that limitation
   and the original Club/Ambient/Class A counterexamples.
4. Keep independent validation passages and input uncertainty visible.
   Matching a fitted spectral feature cannot establish complete output
   agreement or a market-wide superiority claim.

The [current synchronized Saw player](http://127.0.0.1:8766/run-04/index.html)
provides all twelve hardware/baseline/W4 comparisons with
[verified audio and transport](source-audits/saw-w4-listening-player-2026-09-15.md).
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
