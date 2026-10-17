# Fractional tempo in offline MIDI replay

The offline renderer now follows a Standard MIDI File's fractional tempo without replacing the patch's saved tempo. Note timestamps already used exact rational arithmetic, but synchronized LFOs and arpeggios previously received a rounded integer BPM. That mismatch made modulation and generated rhythms drift against the recorded notes.

Standard MIDI File tempo is expressed in microseconds per quarter note, so conversion to BPM generally produces a fraction. Mido's official file-format documentation describes this representation and its floating-point BPM conversion. [1] Roland documents tempo-synchronized LFOs on Owner's Manual p. 41 and independent external/system synchronization on p. 68. These contracts support keeping the effective clock separate from the patch's stored integer tempo. [2]

For example, 437,158 microseconds per quarter note represents approximately 137.250147544 BPM. Rounding it to 137 BPM loses 0.250147544 quarter notes per minute: approximately one sixteenth-note arpeggio step per minute, or two cycles per minute for a 1/32-note LFO. The note events remained correctly timed, making the clock disagreement cumulative and audible.

`Tools/render_midi.py` now checks the exact rational BPM against 5–300 before serializing it with enough decimal digits to preserve the double-precision value. This also rejects values just outside the supported range that the previous rounding admitted. `Tools/RenderMidi.cpp` accepts finite fractional clock values and applies `Engine::setTempoClock` at each event sample. The existing clock implementation preserves the musical progress of pending arpeggio steps and gates when tempo changes.

The `preserve-patch` policy retains its previous behavior. With `follow-midi`, the manifest now distinguishes saved `patch_tempo_at_end` from effective `clock_tempo_at_end`, and states that the patch tempo is preserved. Earlier manifests still describe the earlier renderer and are not rewritten.

## Verification

`Tests/MidiRenderTests.py` passes 20 tests, including the existing SMF parser and renderer checks. New cases verify fractional BPM, exact range boundaries, and audible tempo control. A synchronized pitch-LFO fixture produces identical complete WAV output for patches saved at 67 and 299 BPM when following the same fractional MIDI tempo; both saved tempos remain intact. A control with identical note sample positions and only the clock rounded to an integer produces different audio, demonstrating that the test exercises modulation rather than just metadata.

Reproduction from the repository root:

```sh
cmake --build build-fidelity --target SeptumRenderMidi
python3 Tests/MidiRenderTests.py build-fidelity/SeptumRenderMidi
```

This is a correction to offline replay fidelity, not a claim that the SH-201 stores fractional patch tempos. The MIDI-file tempo can be reproduced directly without emulating timestamp jitter from a physical MIDI cable. Effective clock values use double precision; sample placement retains the existing rational calculation and nearest-sample rounding.

## Sources

1. Mido project. [Standard MIDI Files—MIDI Tempo vs. BPM](https://mido.github.io/mido/files/midi.html#midi-tempo-vs-bpm), official documentation, accessed September 13, 2026.
2. Roland Corporation. [SH-201 Owner's Manual](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf), 2006, printed pp. 41 and 68.
