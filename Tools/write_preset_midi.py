#!/usr/bin/env python3
"""Write the committed preset demo phrases, Docs/audio/midi/<NN>-<slug>.mid.

Eight of the 32 factory presets, two from each bank, each showing a different
side of the instrument (README G3, G3a): a lead with vibrato, oscillator sync
under the bender, an acid line on a resonant filter, a PWM bass, a DUAL pad,
a bell over fifths, a SPLIT bass and stabs, and a sample-and-hold sequence.
Each phrase is written for what its preset is for. NN is the program number.
The .mid files are the committed sources the demo renderer reads; this script
only records how they were written. Re-run it only to change a phrase on
purpose, and commit the changed .mid files on their own:

    python3 Tools/write_preset_midi.py Docs/audio/midi

Every file is format 0 on MIDI channel 1 at 480 PPQ, with a tempo and a track
name, and its last event falls at 5.5-9.5 s, so the renderer's 2.5 s release
tail keeps every demo within 8-12 s (G3c).
"""
import argparse
from pathlib import Path
import struct

PPQ = 480
NAMES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def n(name: str) -> int:
    """'C4' is MIDI 60; sharps as 'F#3', flats as 'Bb2'."""
    pitch = NAMES[name[0]]
    rest = name[1:]
    if rest[0] == "#":
        pitch, rest = pitch + 1, rest[1:]
    elif rest[0] == "b":
        pitch, rest = pitch - 1, rest[1:]
    return 12 * (int(rest) + 1) + pitch


class Phrase:
    def __init__(self, bpm: float):
        self.bpm = bpm
        self.events = []  # (beat, order, bytes); note-offs sort before note-ons

    def note(self, beat, length, pitch, velocity=96):
        pitch = n(pitch) if isinstance(pitch, str) else pitch
        self.events.append((beat, 1, bytes([0x90, pitch, velocity])))
        self.events.append((beat + length, 0, bytes([0x80, pitch, 64])))

    def chord(self, beat, length, pitches, velocity=90):
        for pitch in pitches:
            self.note(beat, length, pitch, velocity)

    def line(self, beat, step, pitches, velocity=96, gate=0.9, accents=()):
        """Equal steps; None rests; a '~' suffix ties into the next note (legato)."""
        for index, pitch in enumerate(pitches):
            if pitch is None:
                continue
            legato = isinstance(pitch, str) and pitch.endswith("~")
            length = step * (1.05 if legato else gate)
            accent = 24 if index in accents else 0
            self.note(beat + index * step, length, pitch.rstrip("~") if legato else pitch,
                      min(127, velocity + accent))

    def cc(self, beat, controller, value):
        self.events.append((beat, 2, bytes([0xB0, controller, value])))

    def ramp_cc(self, beat, length, controller, start, end, steps=32):
        for step in range(steps + 1):
            fraction = step / steps
            self.cc(beat + length * fraction, controller, round(start + (end - start) * fraction))

    def bend(self, beat, value):
        """value -1..+1 of the patch's bend range."""
        raw = max(0, min(16383, round(8192 + value * 8191)))
        self.events.append((beat, 2, bytes([0xE0, raw & 0x7F, raw >> 7])))

    def ramp_bend(self, beat, length, start, end, steps=24):
        for step in range(steps + 1):
            fraction = step / steps
            self.bend(beat + length * fraction, start + (end - start) * fraction)

    def smf(self, name: str) -> bytes:
        def vlq(value):
            out = [value & 0x7F]
            value >>= 7
            while value:
                out.append(0x80 | (value & 0x7F))
                value >>= 7
            return bytes(reversed(out))

        tempo = round(60_000_000 / self.bpm)
        track = bytearray()
        track += b"\x00\xff\x03" + vlq(len(name)) + name.encode("ascii")
        track += b"\x00\xff\x51\x03" + tempo.to_bytes(3, "big")
        last = 0
        for beat, _, message in sorted(self.events, key=lambda e: (e[0], e[1], e[2])):
            tick = round(beat * PPQ)
            track += vlq(tick - last) + message
            last = tick
        track += b"\x00\xff\x2f\x00"
        return (b"MThd" + struct.pack(">IHHH", 6, 0, 1, PPQ)
                + b"MTrk" + struct.pack(">I", len(track)) + track)


# --- Bank A: leads -----------------------------------------------------------

def superlead201():
    p = Phrase(120)
    p.line(0, 0.5, ["A4", "C5", "E5", "A5", "G5", "E5", "D5", "E5"], 100)
    p.line(4, 0.5, ["F5", "E5", "D5", "C5", "D5", "E5", "C5~", "B4"], 100)
    p.line(8, 0.5, ["A4", "C5", "E5", "A5", "B5", "C6", "B5", "G5"], 104)
    p.note(12, 6, "A5", 110)
    p.ramp_cc(13, 4, 1, 0, 90)
    p.cc(18.5, 1, 0)
    return p


def sync_sweeper():
    p = Phrase(100)
    p.line(0, 0.5, ["E3", "E3", "G3", "E3", "A3", "E3", "B3", "A3"], 104, gate=0.6)
    p.line(4, 0.5, ["E3", "E3", "G3", "E3", "D4", "B3", "A3", "G3"], 104, gate=0.6)
    p.note(8, 3, "E4", 112)
    p.ramp_bend(8.5, 2, 0, 1)
    p.ramp_bend(10.5, 0.5, 1, 0)
    p.note(12, 3, "B3", 112)
    p.ramp_bend(12.5, 2.25, 0, -1)
    p.bend(15.25, 0)
    return p


# --- Bank B: basses ----------------------------------------------------------

def acid_201():
    p = Phrase(128)
    riff = ["A1", "A1", "A2", "A1", "C2~", "D2", "A1", "G2",
            "A1", "E2", "A1", "A2~", "G2", "A1", "C2", "D2"]
    for bar in range(4):
        notes = riff if bar % 2 == 0 else riff[:12] + ["E2~", "G2~", "A2", "G2"]
        p.line(bar * 4, 0.25, notes, 88, gate=0.55, accents=(0, 6, 11))
    return p


def pwm_slapbass():
    p = Phrase(108)
    groove = ["E1", None, "E2", "E1", None, "E1", "G1", "A1",
              "E1", None, "E2", None, "D2", "B1", "A1", "G1"]
    for bar in range(4):
        root = ["E1", "A1", "B1", "E1"][bar]
        shift = n(root) - n("E1")
        notes = [None if x is None else n(x) + shift for x in groove]
        p.line(bar * 4, 0.25, notes, 92, gate=0.45, accents=(0, 2, 10))
    return p


# --- Bank C: pads and strings ------------------------------------------------

def slow_chords(bpm, chords, beats, velocity=80, overlap=0.25):
    p = Phrase(bpm)
    for index, chord in enumerate(chords):
        p.chord(index * beats, beats + overlap, chord, velocity)
    return p


def alaska_dual():
    # DUAL halves the voices to five per tone: four-note voicings.
    return slow_chords(80, [["D3", "A3", "E4", "F#4"], ["B2", "F#3", "D4", "A4"],
                            ["G2", "D3", "B3", "F#4"], ["A2", "E3", "C#4", "E4"]], 3)


def glass_bell():
    p = Phrase(100)
    melody = [("E5", 0), ("B4", 1), ("G5", 2), ("F#5", 3.5), ("D5", 4), ("E5", 6),
              ("B5", 8), ("A5", 9), ("G5", 10), ("E5", 11.5), ("F#5", 12), ("E5", 14)]
    for pitch, beat in melody:
        p.note(beat, 1.5, pitch, 100)
    p.chord(0, 7.5, ["E3", "B3"], 70)
    p.chord(8, 7.5, ["C3", "G3"], 70)
    return p


# --- Bank D: sequences and effects -------------------------------------------

def club_split():
    # Split at C4: bass line in the lower tone, chord stabs in the upper.
    p = Phrase(124)
    for bar, (root, chord) in enumerate([("A1", ["A4", "C5", "E5"]), ("F1", ["A4", "C5", "F5"]),
                                         ("C2", ["G4", "C5", "E5"]), ("G1", ["G4", "B4", "D5"])]):
        r = n(root)
        p.line(bar * 4, 0.5, [r, r + 12, None, r, r + 12, None, r, r + 12], 104, gate=0.4)
        for offbeat in (0.5, 1.5, 2.5, 3.5):
            p.chord(bar * 4 + offbeat, 0.3, chord, 92)
    return p


def sh_robot():
    p = Phrase(96)
    p.line(0, 1, ["C3", "C3", "Eb3", "C3"], 100, gate=0.8)
    p.line(4, 1, ["F3", "Eb3", "C3", "Bb2"], 100, gate=0.8)
    p.note(8, 4, "C3", 104)
    p.note(12, 3, "G3", 104)
    return p


# Program number (Source/DSP/SeptumPresets.cpp, A-1 .. D-8), slug and phrase.
PRESETS = [
    (1, "superlead201", superlead201), (4, "sync-sweeper", sync_sweeper),
    (9, "acid-201", acid_201), (11, "pwm-slapbass", pwm_slapbass),
    (17, "alaska-dual", alaska_dual), (21, "glass-bell", glass_bell),
    (25, "club-split", club_split), (26, "s-h-robot", sh_robot),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for number, slug, build in PRESETS:
        phrase = build()
        last = max(beat for beat, _, _ in phrase.events)
        seconds = last * 60 / phrase.bpm
        if not 5.5 <= seconds <= 9.5:
            raise SystemExit(f"{slug}: its last event at {seconds:.1f} s is outside 5.5-9.5 s")
        path = args.output / f"{number:02d}-{slug}.mid"
        path.write_bytes(phrase.smf(slug))
        print(f"{path.name:28s} {seconds:5.1f} s")


if __name__ == "__main__":
    main()
