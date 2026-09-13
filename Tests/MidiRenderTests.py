#!/usr/bin/env python3
"""SMF parsing, replay policy and end-to-end renderer regression checks."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("render_midi", ROOT / "Tools/render_midi.py")
midi = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(midi)
RENDERER = None


def vlq(number):
    result = [number & 127]
    while number > 127:
        number >>= 7
        result.insert(0, (number & 127) | 128)
    return bytes(result)


def track(*events):
    return b"".join(vlq(delta) + message for delta, message in events)


def smf(*tracks, division=480, fmt=None):
    if fmt is None:
        fmt = 0 if len(tracks) == 1 else 1
    return (b"MThd" + struct.pack(">IHHH", 6, fmt, len(tracks), division)
            + b"".join(b"MTrk" + struct.pack(">I", len(data)) + data for data in tracks))


EOT = b"\xff\x2f\x00"
TEMPO120 = b"\xff\x51\x03\x07\xa1\x20"
TEMPO60 = b"\xff\x51\x03\x0f\x42\x40"


class ParserTests(unittest.TestCase):
    def test_running_status_note_on_zero_and_default_tempo(self):
        parsed = midi.parse_smf(smf(track((0, b"\x90\x3c\x64"),
                                          (480, b"\x3c\x00"), (480, EOT))))
        channel = [event for event in parsed["events"] if event["kind"] == "midi"]
        self.assertEqual([event["hex"] for event in channel], ["903c64", "903c00"])
        self.assertEqual([event["sample"] for event in channel], [0, 22050])
        self.assertEqual(parsed["end_sample"], 44100)

    def test_conductor_tempo_map_and_rational_rounding(self):
        conductor = track((0, TEMPO120), (480, TEMPO60), (480, EOT))
        notes = track((240, b"\x90\x3c\x64"), (120, b"\x40\x50"),
                      (120, b"\x3c\x00"), (240, b"\x80\x40\x00"), (240, EOT))
        parsed = midi.parse_smf(smf(conductor, notes))
        channel = [event for event in parsed["events"] if event["kind"] == "midi"]
        self.assertEqual([event["sample"] for event in channel], [11025, 16538, 22050, 44100])
        self.assertEqual(parsed["end_sample"], 66150)
        at_480 = [event["kind"] for event in parsed["events"] if event["tick"] == 480]
        self.assertEqual(at_480, ["tempo", "midi"])

    def test_smpte_drop_frame_ignores_tempo_for_timestamps(self):
        division = (227 << 8) | 80  # -29 means 30000/1001 fps.
        parsed = midi.parse_smf(smf(track((0, TEMPO60), (2400, b"\x90\x3c\x64"),
                                          (0, EOT)), division=division), 48000)
        self.assertEqual(parsed["end_sample"], 48048)
        self.assertEqual(parsed["timing"]["frames_code"], -29)

    def test_channel_lengths_and_meta_payload(self):
        parsed = midi.parse_smf(smf(track((0, b"\xff\x03\x04Name"),
                                          (0, b"\xc2\x07"), (10, b"\xd2\x50"), (0, EOT))))
        self.assertEqual(parsed["events"][0]["hex"], b"Name".hex())
        self.assertEqual(parsed["events"][1]["channel"], 3)
        self.assertEqual(parsed["events"][2]["hex"], "d250")

    def test_meta_and_sysex_cancel_running_status(self):
        for breaker in (b"\xff\x01\x01x", b"\xf0\x02\x7d\xf7"):
            with self.subTest(breaker=breaker):
                with self.assertRaisesRegex(midi.MidiError, "Running status"):
                    midi.parse_smf(smf(track((0, b"\x90\x3c\x64"),
                                             (0, breaker), (10, b"\x3c\x00"), (0, EOT))))

    def test_refuses_malformed_smf(self):
        cases = [b"", b"not-midi", smf(track((0, EOT)), division=0),
                 smf(track((0, EOT)), fmt=2), smf(track((0, b"\x3c\x40"), (0, EOT))),
                 smf(track((0, b"\x90\x3c\xff"), (0, EOT))),
                 smf(track((0, b"\xff\x51\x03\x00\x00\x00"), (0, EOT))),
                 smf(track((0, b"\xff\x51\x02\x07\xa1"), (0, EOT))),
                 smf(track((0, b"\x90\x3c\x64"))),
                 smf(track((0, EOT), (1, b"\x90\x3c\x64"))),
                 smf(b"\x81\x80\x80\x80\x00\xff\x2f\x00"),
                 smf(track((0, EOT)))[:-1], smf(track((0, EOT))) + b"junk"]
        for data in cases:
            with self.subTest(data=data.hex()):
                with self.assertRaises(midi.MidiError):
                    midi.parse_smf(data)

    def test_refuses_format_one_tempo_outside_conductor(self):
        with self.assertRaisesRegex(midi.MidiError, "conductor"):
            midi.parse_smf(smf(track((480, EOT)), track((0, TEMPO60), (480, EOT))))

    def test_replay_channel_controls_and_explicit_omissions(self):
        source = smf(track((0, b"\x90\x3c\x64"), (0, b"\x91\x43\x64"),
                           (0, b"\xb0\x40\x7f"), (120, b"\xe0\x00\x50"),
                           (120, b"\xb0\x40\x00"), (0, EOT)))
        replay, ignored = midi.replay_events(midi.parse_smf(source))
        self.assertEqual([event["value"] for event in replay],
                         ["120", "903c64", "b0407f", "e00050", "b04000"])
        self.assertEqual(len(ignored), 1)
        self.assertFalse(ignored[0]["degrades_replay"])

    def test_program_metadata_requires_explicit_fixed_patch_choice(self):
        parsed = midi.parse_smf(smf(track((0, b"\xb0\x00\x57"),
                                          (0, b"\xc0\x05"), (0, EOT))))
        with self.assertRaisesRegex(midi.MidiError, "ignore-program-changes"):
            midi.replay_events(parsed)
        replay, ignored = midi.replay_events(parsed, ignore_program_changes=True)
        self.assertEqual(len(replay), 1)  # Only implicit tempo.
        self.assertEqual([event["hex"] for event in ignored], ["b00057", "c005"])
        self.assertTrue(all(event["degrades_replay"] for event in ignored))

    def test_strict_refuses_unsupported_sound_changes(self):
        for message in (b"\xb0\x65\x00", b"\xd0\x44", b"\xa0\x3c\x40",
                        b"\xf0\x02\x7d\xf7", b"\xff\x7f\x02\x00\x01"):
            with self.subTest(message=message):
                parsed = midi.parse_smf(smf(track((0, message), (0, EOT))))
                with self.assertRaisesRegex(midi.MidiError, "Strict replay"):
                    midi.replay_events(parsed)
                replay, ignored = midi.replay_events(parsed, allow_unsupported=True)
                self.assertEqual(len(ignored), 1)
                self.assertTrue(ignored[0]["degrades_replay"])

    def test_preserve_patch_clock_and_tempo_range(self):
        source = midi.parse_smf(smf(track((0, TEMPO60), (480, EOT))))
        replay, _ = midi.replay_events(source, tempo_policy="preserve-patch")
        self.assertEqual(replay, [])
        self.assertEqual(source["end_sample"], 44100)  # Timing still uses 60 BPM.
        too_fast = midi.parse_smf(smf(track((0, b"\xff\x51\x03\x00\x00\x01"), (0, EOT))))
        with self.assertRaisesRegex(midi.MidiError, "tempo exceeds"):
            midi.replay_events(too_fast)


class RendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if RENDERER is None:
            raise unittest.SkipTest("Pass the SeptumRenderMidi executable to run integration tests")
        cls.folder = tempfile.TemporaryDirectory(prefix="septum-midi-tests-")
        cls.path = Path(cls.folder.name)
        cls.patch = cls.path / "init.syx"
        subprocess.run([str(RENDERER), "--write-init-patch", str(cls.patch)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def render(self, name, data, **changes):
        source = self.path / f"{name}.mid"
        source.write_bytes(data)
        args = argparse.Namespace(renderer=RENDERER, midi=source, syx=self.patch,
                                  output=self.path / f"{name}.wav", manifest=None,
                                  sample_rate=44100, tail=0.2, master_level=100,
                                  channel=1, tempo_policy="preserve-patch", keyboard_mode=False,
                                  allow_unsupported=False, ignore_program_changes=False)
        for key, value in changes.items():
            setattr(args, key, value)
        return midi.render(args)

    def read_audio(self, manifest):
        data = Path(manifest["output"]["path"]).read_bytes()
        self.assertEqual(data[:4], b"RIFF")
        self.assertEqual(data[8:16], b"WAVEfmt ")
        self.assertEqual(struct.unpack_from("<HH", data, 20), (3, 2))
        self.assertEqual(data[48:52], b"data")
        self.assertEqual(struct.unpack_from("<I", data, 4)[0] + 8, len(data))
        values = struct.unpack("<" + "f" * ((len(data) - 56) // 4), data[56:])
        return values[::2], values[1::2]

    def test_actual_midi_sysex_float_wav_hashes_and_determinism(self):
        source = smf(track((240, b"\x90\x45\x64"), (480, b"\x80\x45\x00"), (240, EOT)))
        first, second = self.render("first", source), self.render("second", source)
        self.assertEqual(first["output"]["sha256"], second["output"]["sha256"])
        self.assertEqual(first["output"]["frames"], 52920)
        self.assertEqual(first["output"]["sample_rate"], 44100)
        self.assertFalse(first["degraded_replay"])
        self.assertFalse(first["output"]["normalised"])
        self.assertGreater(first["output"]["latency_samples"], 0)
        self.assertEqual(first["inputs"]["midi"]["sha256"], hashlib.sha256(source).hexdigest())
        self.assertEqual(first["output"]["initial_patch"]["keyboard_mode"], "single")
        left, right = self.read_audio(first)
        self.assertEqual(max(abs(value) for value in left[:11025]), 0.0)
        self.assertGreater(max(abs(value) for value in left[12000:22000]), 0.001)
        self.assertEqual(len(left), len(right))
        self.assertEqual(first["replay_event_counts"], {"note_off": 1, "note_on": 1})

    def test_sustain_expression_and_note_on_zero_reach_engine(self):
        source = smf(track((0, b"\x90\x45\x64"), (0, b"\xb0\x40\x7f"),
                           (240, b"\x90\x45\x00"), (240, b"\xb0\x0b\x00"),
                           (240, b"\xb0\x40\x00"), (240, EOT)))
        manifest = self.render("pedals", source)
        left, _ = self.read_audio(manifest)
        self.assertGreater(max(abs(value) for value in left[15000:20000]), 0.001)
        self.assertLess(max(abs(value) for value in left[30000:32000]),
                        1e-3 * max(abs(value) for value in left[15000:20000]))
        self.assertEqual(manifest["replay_event_counts"]["note_off"], 1)
        self.assertEqual(manifest["replay_event_counts"]["cc_64"], 2)

    def test_selected_channel_and_explicit_degraded_replay(self):
        source = smf(track((0, b"\x91\x45\x64"), (480, b"\x81\x45\x00"), (0, EOT)))
        manifest = self.render("wrong-channel", source)
        left, _ = self.read_audio(manifest)
        self.assertEqual(max(abs(value) for value in left), 0.0)
        self.assertFalse(manifest["degraded_replay"])
        source = smf(track((0, b"\xd0\x45"), (0, EOT)))
        manifest = self.render("omitted-aftertouch", source, allow_unsupported=True)
        self.assertTrue(manifest["degraded_replay"])

    def test_custom_rate_and_no_invented_end_note_off(self):
        source = smf(track((0, b"\x90\x45\x64"), (480, EOT)))
        manifest = self.render("rate48", source, sample_rate=48000)
        self.assertEqual(manifest["output"]["frames"], 33600)
        self.assertEqual(manifest["output"]["active_voices_at_end"], 1)
        self.assertFalse(manifest["settings"]["automatic_note_offs_at_end"])

    def test_rejects_incomplete_or_corrupt_sysex(self):
        full = self.patch.read_bytes()
        for name, contents in (("partial", full[:full.index(b"\xf7") + 1]),
                               ("corrupt", full[:-3] + bytes([full[-3] ^ 1]) + full[-2:])):
            bad = self.path / f"{name}.syx"
            bad.write_bytes(contents)
            with self.assertRaisesRegex(midi.MidiError, "Incomplete|Invalid checksum"):
                self.render(name, smf(track((0, EOT))), syx=bad)
            self.assertFalse((self.path / f"{name}.wav").exists())

    def test_fragmented_and_shuffled_patch_bytes_preserve_tempo_and_pcm(self):
        # Tempo 260 (three nibbles 1, 0, 4) briefly exceeds the valid range
        # when its high nibble replaces INIT's tempo. Clamping each partial
        # DT1 before receiving the remaining nibbles used to turn it into 8.
        packets = [bytearray(frame + b"\xf7")
                   for frame in self.patch.read_bytes().split(b"\xf7") if frame]
        common = next(packet for packet in packets if packet[9] == 0)
        common[11 + 0x0e:11 + 0x11] = bytes([1, 0, 4])
        upper = next(packet for packet in packets if packet[9] == 1)
        # A synced quarter-note sine LFO modulates oscillator pitch, making
        # tempo part of the rendered audio as well as the patch summary.
        for offset, value in {0x27: 1, 0x29: 1, 0x2a: 11, 0x2b: 0,
                              0x2c: 1, 0x2d: 0, 0x2e: 96}.items():
            upper[11 + offset] = value
        for packet in packets:
            packet[-2] = (-sum(packet[7:-2])) & 127
        fragments = []
        for packet in packets:
            for offset, value in enumerate(packet[11:-2]):
                fragment = packet[:10] + bytes([offset, value])
                fragments.append(fragment + bytes([(-sum(fragment[7:])) & 127, 0xf7]))
        shuffled = fragments.copy()
        random.Random(201).shuffle(shuffled)
        source = smf(track((0, b"\x90\x45\x64"), (960, b"\x80\x45\x00"), (0, EOT)))
        manifests = []
        for name, contents in (("full", packets), ("fragmented", fragments),
                               ("shuffled", shuffled)):
            patch = self.path / f"tempo260-{name}.syx"
            patch.write_bytes(b"".join(contents))
            summary = json.loads(subprocess.check_output(
                [str(RENDERER), "--inspect-patch", str(patch)]))
            self.assertEqual(summary["tempo"], 260)
            manifest = self.render(f"tempo260-{name}", source, syx=patch)
            self.assertEqual(manifest["output"]["initial_patch"], summary)
            manifests.append(manifest)
        for manifest in manifests[1:]:
            self.assertEqual(manifest["output"]["initial_patch"],
                             manifests[0]["output"]["initial_patch"])
            self.assertEqual(manifest["output"]["sha256"], manifests[0]["output"]["sha256"])
        # A control rules out an inaudible fixture that would pass even if
        # rendering ignored tempo or the pitch modulation were disconnected.
        common[11 + 0x0e:11 + 0x11] = bytes([0, 0, 8])
        common[-2] = (-sum(common[7:-2])) & 127
        control = self.path / "tempo8-control.syx"
        control.write_bytes(b"".join(packets))
        slow = self.render("tempo8-control", source, syx=control)
        self.assertNotEqual(slow["output"]["sha256"], manifests[0]["output"]["sha256"])

    def test_arp_requires_explicit_keyboard_mode(self):
        full = bytearray(self.patch.read_bytes())
        # ARPEGGIO SW is byte 1AH of Patch Common (MIDI map p. 5).
        cursor = 0
        while cursor < len(full):
            end = full.index(0xf7, cursor)
            if full[cursor + 9] == 0:
                full[cursor + 11 + 0x1a] = 1
                full[end - 1] = (-sum(full[cursor + 7:end - 1])) & 127
                break
            cursor = end + 1
        arp = self.path / "arp.syx"
        arp.write_bytes(full)
        source = smf(track((0, b"\x90\x45\x64"), (480, b"\x80\x45\x00"), (0, EOT)))
        with self.assertRaisesRegex(midi.MidiError, "keyboard-mode"):
            self.render("arp-refused", source, syx=arp)
        manifest = self.render("arp-permitted", source, syx=arp, keyboard_mode=True)
        self.assertTrue(manifest["output"]["initial_patch"]["arpeggio_on"])
        self.assertEqual(manifest["settings"]["note_semantics"], "Engine keyboard/arpeggiator replay")


if __name__ == "__main__":
    arguments = argparse.ArgumentParser()
    arguments.add_argument("executable", nargs="?", type=Path)
    arguments.add_argument("--renderer", type=Path)
    options, remaining = arguments.parse_known_args()
    if options.renderer or options.executable:
        RENDERER = (options.renderer or options.executable).resolve()
    unittest.main(argv=[sys.argv[0], *remaining])
