# Independent review of the isolated envelope experiment

Reviewed `Tools/build_envelope_experiment.py` and the `dry-v2` copied sources
against production commit `b0f6c03` and the
[predeclared design](hz-envelope-experiment-design-2026-09-15.md).
**No consequential implementation defect was found in the reviewed transform.**
This is a source and fixture review, not approval of an envelope-law change.

- Filter envelopes alone receive the calibration pointer. The AMP path keeps
  its original coefficient constant and its `1e-4` decay / `1e-5` release
  termination thresholds. The copied pitch-envelope configuration was checked
  byte-for-byte against the frozen source and is identical.
- The exponential coefficient consumes `T60=tau*ln(1000)`. For the dry Hz
  hypothesis, `tau=0.2140763348 s` becomes `T60=1.4787869318 s`; the amount
  exponential therefore has the intended time constant. It does not use tau
  directly as a 60 dB duration.
- The 35 ms Hz fixture realizes cutoff `243.8044877 Hz` at MIDI 60 / raw 47
  and depth `3.1283167106` octaves at raw depth 80. Its 30/40 ms companions
  compensate the initial coefficient consistently with the same frozen decay
  trajectory. The log-domain control uses the corresponding exponential-log
  fit with its own floor and time constant.
- The factory grid scales the committed **filter** decay table by its raw-49
  value, as declared. The Hz transform changes the complete filter envelope's
  cutoff interpolation, including attack, sustain, release and negative depth;
  those consequences are explicitly part of the experimental design.
- The new `1e-8` termination levels apply to calibrated filter envelopes only.
  Their extreme-depth behavior still needs the design's independent continuity
  validation; source inspection does not replace that audio check.

The initial builder lacked an automatic dry production identity guard. That
guard, the original MIDI hash and the permitted FF20-only omission check were
added following review. Independently hashing the already-rendered `dry-v2`
production files gives exactly the pinned Q0 reference hashes:

| Slope | Production WAV SHA-256 |
| --- | --- |
| LP12 | `e960507e6c9404554980eceae90d51e1253347d22fbe7e661f48730dce7484da` |
| LP24 | `dd505cd6a020417a5b86c52083a8dd6091b3f18edbad7c28a0de431df2356a33` |

This resolves the practical concern about reading an ignored recipe or using
`preserve-patch` instead of the historical replay's tempo policy for this
specific dry fixture. The reviewed files, hashes and scope are recorded in the
[review record](envelope-source-review-2026-09-15.json). No shipping DSP or
experiment builder was edited by this reviewer.
