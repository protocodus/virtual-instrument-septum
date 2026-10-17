# Remote Keyboard and direct MIDI notes

Roland's [SH-201 Owner's Manual, p. 22](https://cdn.roland.com/assets/media/pdf/SH-201_OM.pdf#page=22)
states that the arpeggiator normally responds only to the instrument's own
keyboard. External MIDI notes can drive it when REMOTE KEYBOARD is enabled.
[Page 69](https://cdn.roland.com/assets/media/pdf/SH-201_OM.pdf#page=69) defines
the switch and says that a remote external keyboard can transmit on any MIDI
channel; the normal setting is OFF.

Previously every received MIDI note used the keyboard/arpeggiator path, while
the processor's channel filter rejected notes on other channels. An external
sequencer therefore could not play a sustained part alongside an onboard
arpeggio, and enabling the documented remote behavior was impossible.

The engine now provides `noteOnDirect` and `noteOffDirect` for ordinary MIDI
sound-generator input. Existing `noteOn` and `noteOff` remain the keyboard
path used by the onboard keyboard and REMOTE KEYBOARD input. Both paths use
the patch's SINGLE/DUAL/SPLIT tone routing and the same physical voice budget.
Direct MIDI keys do not enter the arpeggiator's chord or migrate into it when
the arpeggiator is enabled during a performance.

Each voice and held-key entry retains its input source. This prevents a
keyboard arpeggio's generated note-off from ending a direct MIDI note at the
same pitch, and prevents the opposite source's release from taking another
key away. SOLO return priority restores the surviving key's source. Separate
sostenuto latches preserve the same ownership across pedal use. All Notes Off
still releases direct MIDI notes when an ARPEGGIO HOLD chord shares their
pitch; All Sounds Off ends both sources.

`Tests/RemoteKeyboardTests.cpp` exercises sustained direct MIDI against a
gated arpeggio, same-pitch source overlap in both release orders, arpeggiator
switch edits, SINGLE/DUAL/SPLIT routing, SOLO and LEGATO returns, sostenuto and
panic. At 44.1, 48 and 96 kHz all 150 checks pass. Routing both input kinds
through the old keyboard path with the original engine and headers fails 42
checks. The existing engine suite also passes all 4,599 checks.

These tests establish the source-routing contract rather than a measured
hardware voice-stealing or pedal implementation. The processor integration
supplies the REMOTE switch, any-channel remote reception and settings
persistence. Existing keyboard pitch-shift behavior is outside this change.

The plug-in exposes **MIDI NOTES** with three choices: DIRECT is the hardware
OFF behavior; REMOTE is its ON behavior; CHANNEL retains Septum's previous
selected-channel keyboard/arpeggiator route. CHANNEL is the default and the
migration value for old sessions, so existing arpeggios and receive-channel
choices keep playing as before. REMOTE accepts notes, bend, modulation,
volume/pan/expression, hold, sostenuto and portamento control on any channel;
program, panel and channel-mode edits retain the configured receive-channel
boundary. The manual does not enumerate this exemption list, so that boundary
is a conservative integration choice.

Changing MIDI NOTES releases currently held keys and pedals, preserving
normal release/effect tails. ARPEGGIO HOLD retains its latched chord, as it
does after physical key releases. UI keyboard events now consume the current
patch and tempo settings before routing, including a patch selected just
before a queued UI press. Native preset formats 5 and later, and host state, retain the
choice; earlier native formats migrate it without weakening validation of
older required parameters. Processor audio comparisons verify DIRECT chord
playback, REMOTE arpeggiation on a foreign channel, UI arpeggiation in DIRECT,
CHANNEL receive filtering, controller/program boundaries, route-change
release and migration.
