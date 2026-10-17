#!/usr/bin/env python3
"""Write the committed per-preset demo phrases, Docs/audio/midi/<NN>-<slug>.mid.

One phrase per factory preset (README G3a), written for what that preset is
for: leads play lines with bends and vibrato, basses play bass lines, pads
hold voiced chords, sequences play their patterns. The .mid files are the
committed sources the demo renderer reads; this script only records how they
were written. Re-run it only to change a phrase on purpose, and commit the
changed .mid files on their own:

    python3 Tools/write_preset_midi.py Docs/audio/midi

Every file is format 0 on MIDI channel 1 at 480 PPQ, with a tempo and a track
name, and lasts 10-16 s before the renderer's release tail.
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
    p.note(12, 8, "A5", 110)
    p.ramp_cc(14, 4, 1, 0, 90)
    p.cc(20, 1, 0)
    return p


def trance_pluck():
    p = Phrase(138)
    chords = [["A3", "C4", "E4"], ["F3", "A3", "C4"], ["C4", "E4", "G4"], ["G3", "B3", "D4"]]
    for bar, chord in enumerate(chords * 2):
        for eighth in range(8):
            beat = bar * 4 + eighth * 0.5
            pitches = chord if eighth % 2 else [chord[(eighth // 2) % 3]]
            p.chord(beat + (0.25 if eighth % 2 == 0 else 0), 0.2, pitches, 84 + 12 * (eighth % 2))
    return p


def fb_howl_lead():
    # Legato solo with portamento: overlapping notes glide.
    p = Phrase(100)
    p.line(0, 1, ["D4~", "F4~", "A4~", "C5"], 100)
    p.note(4, 3, "D5", 108)
    p.ramp_bend(5, 1, 0, 0.5)
    p.ramp_bend(6.5, 0.5, 0.5, 0)
    p.line(8, 0.5, ["C5~", "A4~", "G4~", "F4~", "G4~", "A4~", "F4~", "D4"], 98)
    p.note(12, 6, "D4", 104)
    p.ramp_cc(13, 5, 1, 0, 100)
    p.cc(19, 1, 0)
    return p


def sync_sweeper():
    p = Phrase(100)
    p.line(0, 0.5, ["E3", "E3", "G3", "E3", "A3", "E3", "B3", "A3"], 104, gate=0.6)
    p.line(4, 0.5, ["E3", "E3", "G3", "E3", "D4", "B3", "A3", "G3"], 104, gate=0.6)
    p.note(8, 3, "E4", 112)
    p.ramp_bend(8.5, 2, 0, 1)
    p.ramp_bend(10.5, 0.5, 1, 0)
    p.note(12, 4, "B3", 112)
    p.ramp_bend(12.5, 3, 0, -1)
    p.bend(16.5, 0)
    return p


def jupiter_lead():
    p = Phrase(108)
    p.line(0, 1, ["G4", "Bb4", "C5", "D5"], 96)
    p.note(4, 2, "F5", 104)
    p.note(6, 1, "Eb5", 96)
    p.note(7, 1, "D5", 96)
    p.note(8, 4, "C5", 100)
    p.ramp_cc(9, 3, 1, 0, 80)
    p.cc(12, 1, 0)
    p.line(12, 0.5, ["D5", "Eb5", "F5", "G5", "F5", "D5"], 96)
    p.note(15, 4, "G5", 108)
    p.ramp_cc(16, 3, 1, 0, 90)
    p.cc(20, 1, 0)
    return p


def saw_re_fi():
    p = Phrase(110)
    p.line(0, 0.5, ["C4", "C5", "Bb4", "G4", "F4", "G4", "Bb4", "C5"], 100, gate=0.8)
    p.line(4, 0.5, ["Eb5", "D5", "C5", "Bb4", "C5", None, "G4", "Bb4"], 100, gate=0.8)
    p.line(8, 0.5, ["C4", "C5", "Bb4", "G4", "F4", "G4", "Bb4", "Eb5"], 104, gate=0.8)
    p.note(12, 2, "F5", 108)
    p.note(14, 4, "G5", 112)
    p.ramp_cc(15, 3, 1, 0, 70)
    p.cc(18.5, 1, 0)
    return p


def fifth_anthem():
    # The patch voices the fifth itself; the line is single notes.
    p = Phrase(112)
    p.line(0, 1, ["D4", None, "D4", "F4"], 108, gate=0.7)
    p.line(4, 1, ["G4", None, "F4", "C4"], 108, gate=0.7)
    p.line(8, 0.5, ["D4", "D4", "F4", "G4", "A4", "G4", "F4", "G4"], 104, gate=0.7)
    p.note(12, 6, "D4", 112)
    p.ramp_cc(14, 4, 1, 0, 80)
    p.cc(19, 1, 0)
    return p


def soloscreamer():
    p = Phrase(108)
    p.line(0, 0.25, ["A4~", "C5~", "D5~", "E5~", "G5~", "A5"], 110)
    p.note(1.5, 2.5, "A5", 116)
    p.ramp_bend(2, 0.5, 0, 0.5)
    p.ramp_bend(3.25, 0.5, 0.5, 0)
    p.line(4, 0.5, ["G5~", "E5~", "D5~", "C5~", "D5~", "E5~", "G5~", "A5"], 110)
    p.note(8, 4, "C6", 120)
    p.ramp_cc(8.5, 3, 1, 0, 110)
    p.cc(12, 1, 0)
    p.line(12, 0.5, ["B5~", "A5~", "G5~", "E5"], 110)
    p.note(14, 4, "A5", 116)
    p.ramp_bend(14, 1, -0.5, 0)
    return p


# --- Bank B: basses ----------------------------------------------------------

def acid_201():
    p = Phrase(128)
    riff = ["A1", "A1", "A2", "A1", "C2~", "D2", "A1", "G2",
            "A1", "E2", "A1", "A2~", "G2", "A1", "C2", "D2"]
    for bar in range(6):
        notes = riff if bar % 2 == 0 else riff[:12] + ["E2~", "G2~", "A2", "G2"]
        p.line(bar * 4, 0.25, notes, 88, gate=0.55, accents=(0, 6, 11))
    return p


def sub_bass_201():
    p = Phrase(96)
    p.line(0, 2, ["E1", "E1", "G1", "A1"], 100, gate=0.95)
    p.line(8, 1, ["C2", None, "B1", "G1"], 100, gate=0.95)
    p.note(12, 4, "E1", 104)
    return p


def pwm_slapbass():
    p = Phrase(108)
    groove = ["E1", None, "E2", "E1", None, "E1", "G1", "A1",
              "E1", None, "E2", None, "D2", "B1", "A1", "G1"]
    for bar in range(6):
        root = ["E1", "E1", "A1", "B1", "E1", "G1"][bar]
        shift = n(root) - n("E1")
        notes = [None if x is None else n(x) + shift for x in groove]
        p.line(bar * 4, 0.25, notes, 92, gate=0.45, accents=(0, 2, 10))
    return p


def grit_bass():
    p = Phrase(140)
    for bar, root in enumerate(["D2", "D2", "Bb1", "C2"] * 2):
        r = n(root)
        p.line(bar * 4, 0.5, [r, r, r + 12, r, r, r + 10, r, r + 12], 104, gate=0.7)
    return p


def solid_punch():
    p = Phrase(120)
    for bar, root in enumerate(["C2", "C2", "Ab1", "Bb1"] * 2):
        r = n(root)
        p.line(bar * 4, 0.5, [r, None, None, r, None, r, r + 12, None], 112, gate=0.5)
    return p


def reso_squawk():
    p = Phrase(124)
    steps = ["F1", "F2", "F1", "Eb2", "F1", "C2", "F2", "Ab1"]
    velocities = [118, 70, 96, 70, 110, 70, 96, 80]
    for bar in range(6):
        for index, pitch in enumerate(steps * 2):
            p.note(bar * 4 + index * 0.25, 0.15, pitch, velocities[index % 8])
    return p


def dub_sub_201():
    p = Phrase(76)
    p.line(0, 1, ["G1", None, None, "G1"], 104, gate=0.6)
    p.line(4, 1, ["Bb1", None, "C2", "D2"], 104, gate=0.6)
    p.line(8, 1, ["G1", None, None, "F1"], 104, gate=0.6)
    p.note(12, 2, "G1", 108)
    return p


def fb_growlbass():
    p = Phrase(90)
    p.note(0, 3, "E1", 110)
    p.ramp_cc(0.5, 2.5, 1, 0, 100)
    p.cc(3, 1, 0)
    p.note(4, 1.5, "G1", 104)
    p.note(6, 2, "A1", 110)
    p.ramp_bend(7, 1, 0, -0.5)
    p.bend(8.1, 0)
    p.line(8, 0.5, ["E1", "E1", "E2", "D2", "B1", "A1", "G1", "A1"], 104, gate=0.8)
    p.note(12, 4, "E1", 112)
    p.ramp_cc(13, 3, 1, 0, 110)
    p.cc(16.5, 1, 0)
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
                            ["G2", "D3", "B3", "F#4"], ["A2", "E3", "C#4", "E4"]], 4)


def pwm_strings():
    p = slow_chords(90, [["C3", "G3", "E4"], ["A2", "E3", "C4"],
                         ["F2", "C3", "A3", "F4"], ["G2", "D3", "B3", "G4"]], 4)
    p.line(14, 0.5, ["G4", "A4", "B4", "C5"], 84)
    return p


def supersaw_pad():
    return slow_chords(126, [["A2", "E3", "A3", "C4", "E4"], ["F2", "C3", "F3", "A3", "C4"],
                             ["C3", "G3", "C4", "E4", "G4"], ["G2", "D3", "G3", "B3", "D4"]], 8, 92)


def space_choir():
    return slow_chords(72, [["E3", "B3", "G4"], ["C3", "G3", "E4"],
                            ["D3", "A3", "F#4"], ["B2", "F#3", "D#4"]], 3.5, 84, overlap=0.5)


def glass_bell():
    p = Phrase(90)
    melody = [("E5", 0), ("B4", 1), ("G5", 2), ("F#5", 3.5), ("D5", 4), ("E5", 6),
              ("B5", 8), ("A5", 9), ("G5", 10), ("E5", 11.5), ("F#5", 12), ("E5", 14)]
    for pitch, beat in melody:
        p.note(beat, 1.5, pitch, 100)
    p.chord(0, 7.5, ["E3", "B3"], 70)
    p.chord(8, 7.5, ["C3", "G3"], 70)
    return p


def air_ethereal():
    return slow_chords(70, [["G3", "D4", "A4", "B4"], ["E3", "B3", "F#4", "G4"],
                            ["C3", "G3", "D4", "E4"], ["D3", "A3", "E4", "F#4"]], 3.5, 76, overlap=0.75)


def retro_brass():
    p = Phrase(88)
    stab = [["F3", "A3", "C4", "F4"], ["Eb3", "G3", "Bb3", "Eb4"]]
    p.chord(0, 0.4, stab[0], 112)
    p.chord(0.75, 0.4, stab[0], 100)
    p.chord(1.5, 2, stab[1], 108)
    p.chord(4, 0.4, stab[0], 112)
    p.chord(4.75, 0.4, stab[0], 100)
    p.chord(5.5, 2, ["G3", "Bb3", "D4", "G4"], 108)
    p.chord(8, 6, ["Bb2", "F3", "Bb3", "D4"], 90)
    p.ramp_cc(10, 4, 1, 0, 70)
    p.cc(14.5, 1, 0)
    p.chord(14.5, 0.4, stab[0], 120)
    return p


def sweep_aurora():
    p = Phrase(80)
    p.chord(0, 7.75, ["C3", "G3", "D4", "E4"], 84)
    p.chord(8, 8, ["A2", "E3", "B3", "C4"], 84)
    return p


# --- Bank D: sequences and effects -------------------------------------------

def club_split():
    # Split at C4: bass line in the lower tone, chord stabs in the upper.
    p = Phrase(124)
    for bar, (root, chord) in enumerate([("A1", ["A4", "C5", "E5"]), ("F1", ["A4", "C5", "F5"]),
                                         ("C2", ["G4", "C5", "E5"]), ("G1", ["G4", "B4", "D5"])] * 2):
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
    p.note(12, 4, "G3", 104)
    return p


def ion_wind():
    p = Phrase(84)
    p.chord(0, 6, ["C4", "G4"], 90)
    p.ramp_cc(0, 6, 1, 0, 120)
    p.cc(6, 1, 0)
    p.chord(7, 6, ["Bb3", "F4"], 90)
    p.ramp_bend(9, 4, 0, 0.6)
    p.bend(14, 0)
    return p


def arp_chime():
    # The arpeggiator is off in this preset, so the figure is played as notes.
    p = Phrase(120)
    shapes = [["C5", "E5", "G5", "B5"], ["A4", "C5", "E5", "G5"],
              ["F4", "A4", "C5", "E5"], ["G4", "B4", "D5", "F#5"]]
    for bar, shape in enumerate(shapes * 2):
        pitches = [n(x) for x in shape]
        pattern = pitches + [pitches[2] + 12, pitches[3], pitches[2], pitches[1]]
        p.line(bar * 4, 0.5, pattern, 88, gate=0.8, accents=(0,))
    return p


def techno_pulse():
    p = Phrase(130)
    for bar, root in enumerate(["A2", "A2", "C3", "G2"] * 2):
        r = n(root)
        p.line(bar * 4, 0.25, [r, r, r + 12, r, r, r + 7, r, r + 12] * 2, 84,
               gate=0.5, accents=(0, 3, 6, 10, 13))
    return p


def alien_signal():
    p = Phrase(84)
    p.note(0, 2, "E5", 100)
    p.ramp_bend(0.5, 1.5, 0, 1)
    p.bend(2.2, 0)
    p.note(3, 1, "B5", 90)
    p.note(5, 3, "F5", 104)
    p.ramp_bend(5.5, 2, 0, -1)
    p.bend(8.2, 0)
    p.line(9, 0.25, ["C6", "G5", "C6", "G5", "D6", "A5"], 96, gate=0.6)
    p.note(11, 3, "E6", 100)
    p.ramp_cc(11, 3, 1, 0, 110)
    p.cc(14.5, 1, 0)
    return p


def laser_sweep():
    p = Phrase(84)
    for index, pitch in enumerate(["C6", "G5", "E5", "C5", "G4", "E4", "C4", "G3"]):
        p.note(index * 1, 0.4, pitch, 110 - index * 4)
    for index, pitch in enumerate(["A3", "E4", "A4", "C5", "E5", "A5"]):
        p.note(8 + index * 0.5, 0.3, pitch, 100)
    p.note(12, 2, "A5", 112)
    p.ramp_bend(12.25, 1.5, 0, -1)
    p.bend(14.5, 0)
    return p


def space_drone():
    p = Phrase(60)
    p.chord(0, 10, ["C2", "G2", "D3"], 96)
    p.ramp_cc(2, 6, 1, 0, 90)
    p.cc(10, 1, 0)
    return p


# Factory order: Source/DSP/SeptumPresets.cpp, A-1 .. D-8.
PRESETS = [
    ("superlead201", superlead201), ("trance-pluck", trance_pluck),
    ("fb-howl-lead", fb_howl_lead), ("sync-sweeper", sync_sweeper),
    ("jupiter-lead", jupiter_lead), ("saw-re-fi", saw_re_fi),
    ("5th-anthem", fifth_anthem), ("solo-screamer", soloscreamer),
    ("acid-201", acid_201), ("sub-bass-201", sub_bass_201),
    ("pwm-slapbass", pwm_slapbass), ("grit-bass", grit_bass),
    ("solid-punch", solid_punch), ("reso-squawk", reso_squawk),
    ("dub-sub-201", dub_sub_201), ("fb-growlbass", fb_growlbass),
    ("alaska-dual", alaska_dual), ("pwm-strings", pwm_strings),
    ("supersaw-pad", supersaw_pad), ("space-choir", space_choir),
    ("glass-bell", glass_bell), ("air-ethereal", air_ethereal),
    ("retro-brass", retro_brass), ("sweep-aurora", sweep_aurora),
    ("club-split", club_split), ("s-and-h-robot", sh_robot),
    ("ion-wind", ion_wind), ("arp-chime", arp_chime),
    ("techno-pulse", techno_pulse), ("alien-signal", alien_signal),
    ("laser-sweep", laser_sweep), ("space-drone", space_drone),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for index, (slug, build) in enumerate(PRESETS, 1):
        phrase = build()
        last = max(beat for beat, _, _ in phrase.events)
        seconds = last * 60 / phrase.bpm
        if not 9.5 <= seconds <= 16.5:
            raise SystemExit(f"{slug}: {seconds:.1f} s is outside the 10-16 s phrase length")
        path = args.output / f"{index:02d}-{slug}.mid"
        path.write_bytes(phrase.smf(slug))
        print(f"{path.name:28s} {seconds:5.1f} s")


if __name__ == "__main__":
    main()
