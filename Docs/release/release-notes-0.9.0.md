# Septum 0.9.0 release notes

The complete change list for 0.9.0, moved here from the README's version
history, which keeps a concise summary.

- Hardened malformed parameters, nonfinite external input, SysEx/MIDI parsing,
  host-state loading and processor lifecycle boundaries; added seeded fuzzing,
  sanitizer CI, allocation audits and strict VST3 validation.
- Removed callback buffer growth and MIDI publication allocations, fixed
  concurrent patch publication and UI note overflow, and made host-state recall
  normalize on/off parameters after fractional automation.
- Cached unchanged effect coefficients and added deterministic `--jobs` demo
  rendering across independent engine instances.
- Added full bundled dependency notices and commercial macOS packaging checks,
  with notarized/stapled ZIP bundles and installer validation.
- Increased the filter-envelope range from ±10 to ±12 octaves after named
  hardware recordings showed its peak cutoff opening too little. SupaJuce's
  early upper harmonics improve across six notes; Cotton's opening high band
  provides an independent check. Cutoff, resonance and envelope timing retain
  their prior behavior. The range remains an empirical calibration.

- Strengthened voice-filter resonance from two independent recorded patches.
  The 24 dB path now adds bounded resonance in its second section. Zero
  resonance, external AUDIO FILTER and existing cutoff/envelope timing remain
  unchanged. The moderate Q calibration and high-range cap are empirical.

- Corrected WIDE-dependent hardware coarse tuning in SysEx and pitch CCs:
  the normal range is ±12 semitones, WIDE is ±36. Retained raw pitch positions
  across CC/SysEx fragments and preserved native-session pitch semantics.
  Added a fourth hardware comparison and revised the labeled transcriptions.

- Adopted a dedicated linear filter decay after the Moogie hardware comparison
  showed the old curve closing too soon: approximately 419 ms at raw 49, with
  provisional power interpolation between 2 ms and 12 s. Filter release,
  cutoff, amplifier and pitch envelopes retain their existing behavior;
  this does not establish a complete hardware envelope table.
- Implemented [ten further hardware-fidelity corrections](../../Docs/research/fidelity/hardware-round3.md):
  polyphonic keyed LFOs, individual note fades, the reported pitch-envelope
  limit, codec input DC filtering, signed linear delay feedback, sample-grid
  arpeggio timing and four MIDI reception behaviors, with source-linked tests.
- First complete instrument: both tones with every tone parameter, all nine
  waveforms, MIX/SYNC/RING, the filter, three envelopes, two LFOs with tempo
  sync, overdrive, delay → reverb with per-tone sends and the 16 templates,
  SINGLE/DUAL/SPLIT with 10/5+5 voices, solo/legato, portamento, per-tone
  pitch bend, the System Common tune, key shift, octave and transpose, and the
  analog output stage.
- Added the arpeggiator: the documented grid, duration and tie chains, all
  twelve motifs held to the manual's three worked examples, octave range,
  accent, velocity, END STEP as a parameter and a panel control, hold and
  split.
- Added the external-input path — INPUT VOL, CENTER CANCEL, the four-type
  AUDIO FILTER, and EXT-IN as a selectable oscillator waveform — with the
  monitor/voice changeover the manual's own recipe settles.
- Added a faithful SysEx codec for the documented address map and the
  64-patch matrix.
- Overdrive is evaluated at a fixed internal rate through half-band polyphase
  stages, so its character no longer follows the host's sample rate; its stage
  state now survives a voice takeover and its own switch.
- Registered every voiced constant in the engine's `mapping` namespace with
  the open question that owns it — no bare numbers left in the render code,
  and the demos re-rendered bit-identically.
- Re-pinned the resonance curve to a square-root taper chosen by ear, after a
  linear taper put the control's whole audible range in the top fifth of its
  travel.
- Fixed the band-pass so it gains with resonance instead of losing 21 dB
  across the top of the knob and returning inverted past the oscillation
  threshold.
- Band-limited the triangle, which the shipping coefficient did not.
- Let a hard-sync reset be the naive reset it is documented as.
- Made INTERVAL an interval against OSC 1, and printed what the manual prints
  for KEY FOLLOW, delay FEEDBACK and PITCH WIDE.
- Fixed sostenuto so it no longer catches later presses, and stopped the
  octave cycle leaving the MIDI range.
- Rebuilt the panel around a fixed control geometry that scales to the window,
  lighting bipolar knobs from zero.
- Removed the D Beam, which is a control surface a plug-in has no hand above.
  Its four Patch Common bytes stay stored and round-tripped, published as
  non-automatable so a host offers no lane that changes nothing; PITCH WIDE
  now follows the same inert-data rule.
- Made the panel say which tone it is editing: EDIT TONE in the header, every
  per-tone section wearing the tone's name and colour, no mixed sections, and
  a key band that draws the split point where it falls. The drawn keyboard was
  applying the octave shift twice.
- Removed three mechanisms that asserted facts no source supports — a "tube"
  stage ahead of the overdrive, NOISE read from an LFSR's successive states,
  and a re-pinned second filter stage — and re-read the parameter address map
  in full, which corrected six bytes, made block addresses absolute, made the
  arpeggio grid sixteen blocks rather than one, and made a DT1 address a byte
  rather than a block.
- Answered OQ-01's rate half and OQ-18 from Roland's own editor XML, driver
  readmes and demo recordings, and re-pinned reverb PRE DELAY to the editor's
  four-run table.
- Made INIT PATCH Roland's INIT PATCH — all 103 declared defaults — and moved
  the neutral base the 32 original programs were written against to a private
  `presetBase()` that makes no claim about the instrument.
- Made an imported arpeggio grid survive and play: it is held beside the
  parameters, plays in place of the selected template until the selector
  moves, is saved with the session and survives a re-export.
- Fixed the resonance knob, which was not monotone — the state limiter left
  the whole high-Q shoulder unbounded below RESONANCE 122, and one knob step
  fell 17.8 dB; a SUSTAIN moved under a settled note, which stepped in one
  sample; and NOISE, which was 5.92 dB quieter at 192 kHz than at 44.1.
- Fixed All Notes Off, which was a second All Sounds Off, and added the three
  Universal Realtime messages the implementation lists.
- Fixed the publish protocol between the audio and message threads across
  several rounds: every republish now publishes the value the engine renders
  from, a state save can no longer serialise a patch that never existed, and
  a save no longer destroys the arpeggio grid it is saving. The remaining
  whole-patch and notification collisions now use the policy documented above.

