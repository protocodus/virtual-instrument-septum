# Preserve reconstructed pitch gestures in benchmark MIDI

The Class A recording contains a continuous pitch rise during its held
note. The reconstruction writer now accepts an optional `pitch_bends`
array of `{time, value}` points, in source-clock seconds and MIDI's
14-bit range 0–16383. Center is 8192. This lets an independently measured
gesture reach the existing renderer without adding new note attacks.
The published patch still determines bend range.

At the same MIDI tick, note-offs precede pitch bend, which precedes
note-ons. The existing 20,000-ticks/second time grid and tempo policy
remain unchanged. Invalid values, out-of-coverage times and duplicate
bend ticks are rejected. No DSP or default instrument behavior changed.

Verification regenerated all ten existing benchmark MIDI files and found
byte-identical output. A two-note control was independently decoded by
`render_midi.parse_smf`: center/max/min became `e00040`, `e07f7f`, `e00000`
at samples 0, 22050 and 33075 at 44.1 kHz. The shared 22050-sample event
ordered note-off, bend, then note-on. Negative, oversized, boolean,
fractional and duplicate-tick bend inputs were rejected.

This verifies MIDI encoding and preservation. A source-derived gesture
remains a reconstruction: the original controller samples, physical
lever position and performance MIDI are unavailable. A tracked pitch
trajectory cannot authenticate those original inputs.
