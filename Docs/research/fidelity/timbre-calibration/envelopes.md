# Filter-envelope calibration implementation

Explicit comparison profiles can replace all 128 attack, decay, sustain and
release values independently. Attack/decay remain linear in envelope control
amount; release seconds mean time to −60 dB of that amount. Sustain is a
normalized value that feeds the existing log-cutoff excursion. This supports
measured nonlinear slider tables without confusing milliseconds with a time
constant, or envelope control with physical cutoff Hz.

The present D49 anchor and remaining ambiguity are documented in the
[SupaJuce audit](../source-audits/supajuce-brightness.md) and
[Cotton envelope analysis](../source-audits/cotton-envelope-model.md).
[Roland's manual, pp. 37–38](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf#page=37)
describes the stages, without providing numerical curves. No candidate is
promoted to the default from these mixed/processed recordings.

Only the voice filter envelope receives the profile. AMP and PITCH timings,
native patch values and SysEx bytes remain independent. Reconfiguring a held
note retains its envelope state and existing two-sided sustain transition.
Installation of a different model clears the sound as documented by the API.

Focused audio comparisons cover 44.1, 48 and 96 kHz: default tables reproduce
attack/decay/sustain/release exactly, and independently shifting all four
tables matches a reference patch with the corresponding four controls moved.
Invalid durations or changed sustain endpoints are rejected before rendering.
Changing the segment curvature or adopting linear-Hz interpolation would be
a separate model-family experiment requiring additional evidence.
