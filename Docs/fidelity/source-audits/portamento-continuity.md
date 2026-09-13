# Interrupted SOLO portamento

Research and validation: 2026-09-13.

Roland's [SH-201 Owner's Manual, p. 19](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf#page=19)
describes a smooth transition between pitches and separately distinguishes
SOLO's retriggered attack from SOLO+LEGATO's maintained sound. This supports
preserving pitch continuity when a new key interrupts a running SOLO glide;
it does not establish Roland's exact portamento time or curve.

`Engine::triggerVoice` previously kept the running pitch only when `legato`
was true. In SOLO mode it restarted from the previous key's destination, even
when the oscillator had not reached that destination. Rapid playing therefore
jumped to an unplayed pitch before gliding toward the next note. Returning to
an earlier held key had the same fault.

The correction keeps the current pitch when reusing an active voice from the
same solo part. Envelope articulation stays independent. Fresh/poly voices
retain their existing previous-note source, and SOLO+LEGATO still requires
overlapping keys before enabling portamento. Voice stealing from the other
part does not inherit that part's glide.

`SeptumPortamentoContinuityTests` compares actual output from SOLO and
SOLO+LEGATO with sustained envelopes and isolated sine oscillators. Identical
pitch trajectories should yield identical audio despite their different
articulation modes. The fixtures interrupt ascending and descending two-octave
glides, return to a held key, cover both tones and oscillators, and run at
44.1, 48 and 96 kHz with 37- and 256-sample blocks. A separate audible envelope
test verifies that SOLO still retriggers its attack.

The baseline failed 96 of 193 checks; its maximum SOLO/LEGATO difference was
0.0243086377 full scale. The corrected implementation passes all 193 checks,
with zero audio difference in the sustained-envelope comparisons. These are
behavioral regression results, not measurements of an SH-201 recording.
