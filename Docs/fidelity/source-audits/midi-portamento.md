# MIDI portamento source and voice continuation

Research and validation: 2026-09-13.

The [SH-201 Owner's Manual, p. 72](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf#page=72)
lists reception of CC84, Part Portamento Control. Its behavior follows the
[MIDI 1.0 Detailed Specification 4.2.1, printed pp. 16–17 / PDF pp. 21–22](https://www.seriesten.org/docs/protocols/MIDI_1.0_Detailed_Specification.pdf#page=21):
the controller provides a source pitch for the following note, overrides the
portamento switch, and is consumed by that note. An already sounding source
voice continues into the target without a new attack or voice allocation.
The target note number owns the release. Roland's
[JP-8080 manual, p. 192](https://cdn.roland.com/assets/media/pdf/JP-8080_OM.pdf#page=192)
corroborates this behavior with two worked MIDI sequences. The MIDI specification
is a standards-body document hosted by a third-party mirror; the Roland documents
come from Roland's own CDN.

The previous implementation only wrote the source number to each part's
`lastPitch`. It therefore did nothing when the patch's portamento switch was
off, allocated an extra polyphonic voice even when the source was sounding,
and could leave an unused source in the other half of a split.

The engine now consumes a pending source once per incoming note and passes it
to the tone or tones receiving that note. A matching source voice transfers
to the new note and leaves the held-key return stack. Thus a target release
cannot resurrect the old source when its Note Off arrives later. Normal
polyphonic allocation and ordinary solo articulation are unchanged when no
CC84 source is pending. Engine reset and All Sounds Off clear pending state;
processor and MIDI-renderer controller resets also discard it.

The existing unmeasured portamento curve remains in use. A releasing source
preserves its running envelope, including Release, rather than inventing a
new attack or restoring Sustain. This choice implements continuation, but
has not been checked against an SH-201 capture. Hardware interaction with
REMOTE KEYBOARD/arpeggiation is also unmeasured: an incoming key consumed by
the plug-in arpeggiator consumes CC84 without applying it to generated notes.
The default selected-channel mode follows the instrument's single MIDI part;
the plug-in's compatibility omni mode retains its merged input semantics.

`SeptumMidiPortamentoTests` passes 184 checks. The pre-CC84 engine fails 86;
the maximum forced-glide audio difference falls from 0.016328482 to zero.
The tests cover both tones, three voice modes, three sample rates, two buffer
sizes, source reuse, both Note Off orders, one-note consumption, DUAL/SPLIT,
unrelated voices, zero time and resets. A release-tail comparison verifies
that source continuation does not add an attack. The separate 193-check SOLO
continuity suite remains green. Eight processor checks cover MIDI timestamps,
selected-channel handling, resets and changes to the receive channel.
