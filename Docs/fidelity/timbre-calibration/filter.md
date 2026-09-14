# Filter calibration implementation

The experimental model accepts 128-point cutoff, first-stage damping and
second-stage damping tables. These act on the voice filter; external AUDIO
FILTER remains independent. No replacement hardware table is claimed or
selected by default. The host plug-in continues to use its existing model.

The source of the open calibration question is the
[Air Lead audit](../source-audits/air-lead-resonance.md): moderate resonance
received an earlier conditional correction, but static peak placement still
differs. [Roland's manual, pp. 35–36](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf#page=35)
establishes control behavior, without specifying a natural-frequency or Q
table. Existing wet MP3s do not uniquely identify those curves.

`Engine::defaultTimbreCalibration()` supplies all incumbent values. Disabled
sections retain the exact equations. Explicit table mode uses independent
second-stage control smoothing, allowing a future measured response to avoid
the incumbent clamp coupling. Both pole dampings and log cutoff remain
continuous during patch automation. Model replacement itself is a comparison
setup operation and clears voices/effects; it is not a patch parameter.

Validation rejects nonfinite, out-of-range and nonmonotone tables before
changing model or runtime state. Fixed-size arrays allocate nothing in the
audio path. The bounds limit experiments but are not a mathematical stability
proof for every automated schedule.

The first 102 focused checks compare complete audio with an independent
control-selection reference at 44.1, 48 and 96 kHz, both slopes. Static default
tables equal the existing model; a twelve-control-step shift matches the same
shift in a reference patch. Invalid model installation leaves sounding audio
unchanged. Future measurements should hold velocity, envelope and modulation
at zero, cover both slopes and multiple levels, and reserve unused settings
for validation rather than fit the same patch repeatedly.
