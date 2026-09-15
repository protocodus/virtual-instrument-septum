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
  interior rate table remains unmeasured.
- [Audio agreement assessment](equivalence-assessment.md): measure spectral,
  envelope and stereo residuals, freeze gain/alignment before evaluation,
  retain hashes and distinguish original from reconstructed inputs.

All 34 configured DSP/tool CTests pass across the recorded validation runs.
Universal arm64/x86_64 AU, VST3 and standalone Release builds also succeed.
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

## Next work

1. Investigate the high-register saw's nonharmonic lines in the original-MIDI
   dry recordings. Test codec artifacts, oscillator models and filter
   interaction separately before changing the high-note sound.
2. Examine newly accessible creator recordings for independent LFO,
   portamento and oscillator measurements. Retain uncertain panel state and
   unmeasured raw settings explicitly.
3. Use unchanged named presets to investigate oscillator mixture, Super Saw
   stereo structure and wet tails. Air Lead and Cotton currently have the
   largest spectrum/stereo residuals, with uncertain original performances.
4. Keep independent validation passages and input uncertainty visible.
   Matching a fitted spectral feature cannot establish complete output
   agreement or a market-wide superiority claim.

The [dry replay and complete reproduction](source-audits/zero-resonance-reproduction-2026-09-15.md)
preserve all models, including failed sensitivity controls. The local
[ten-preset listening page](http://127.0.0.1:58511/) is available while this
session's comparison server is running.
