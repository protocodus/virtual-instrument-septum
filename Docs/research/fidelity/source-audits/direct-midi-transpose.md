# Direct MIDI and keyboard pitch shifts

The [SH-201 Owner's Manual, p. 18](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf#page=18)
describes OCT UP/DOWN as shifting the keyboard range. Its [KEYBOARD parameter
table, p. 69](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf#page=69)
places OCTAVE SHIFT and TRANSPOSE VALUE in the controller section. In contrast,
[MASTER KEY SHIFT, p. 68](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf#page=68)
shifts the entire instrument. Native tone OCTAVE SHIFT is separately stored in
each tone ([MIDI Implementation, p. 5](https://cdn.roland.com/assets/media/pdf/SH-201_MI.pdf#page=5)).

The [MIDI 1.0 Detailed Specification 4.2.1, Appendix A-6](https://www.seriesten.org/docs/protocols/MIDI_1.0_Detailed_Specification.pdf#page=69)
recommends that an instrument's transposition system affect keyboard data
separately from received MIDI data going to its voice module.

The engine previously added the keyboard octave and transpose offsets to
every voice, including ordinary MIDI sent directly to the sound generator.
For example, incoming MIDI note 60 with the keyboard shifted up one octave
sounded as note 72, even with REMOTE KEYBOARD off. A live keyboard shift also
retuned already sounding direct MIDI notes.

Direct MIDI voices now omit the two keyboard offsets. MASTER KEY SHIFT,
MASTER TUNE, native tone OCTAVE SHIFT, oscillator tuning and pitch bend retain
their existing sound-generator roles. Onboard and remote-keyboard input still
follow the keyboard offsets. This implements the documented separation of
controller and sound-generator functions; an isolated SH-201 hardware capture
of this routing has not been made.

`Tests/DirectMidiTransposeTests.cpp` compares complete sine-wave renders from
both oscillators and either tone at 44.1, 48 and 96 kHz. It checks the positive
and negative keyboard limits, combined offsets, live changes on a held direct
note, unchanged keyboard behavior, and retained master/tone transposition.

Validation: all 384 checks pass after the change. The isolated pre-change
engine and matching headers fail 72 checks; the largest direct-note sample
error falls from 0.151869752 to exactly zero. The pre-change snapshot already
includes the direct-input routing API, so this comparison isolates keyboard
transposition rather than conflating it with arpeggiator reception.
