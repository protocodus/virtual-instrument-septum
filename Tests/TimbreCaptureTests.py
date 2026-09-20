#!/usr/bin/env python3
"""Offline capture package validation; optional integration with the real exporter."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Tools"))
import generate_timbre_capture as capture
import render_midi

RENDERER = None


def synthetic_init():
    # A legal synthetic transport fixture, not an assertion of Roland defaults.
    blocks = [bytearray(size) for size in capture.BLOCK_SIZES]
    blocks[0][:12] = b"INIT PATCH  "
    blocks[0][12:21] = bytes((127, 64, 0, 7, 8, 0, 0, 53, 0))
    for block in blocks[1:3]:
        for name, value in capture.base_tone().items():
            block[capture.TONE_FIELDS[name][0]] = value
    blocks[5][3] = 64
    blocks[5][7] = 1
    return capture.encode_syx(blocks)


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="septum-capture-tests-")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.init = self.folder / "init.syx"
        self.init.write_bytes(synthetic_init())

    def test_all_suites_complete_ranges_hashes_and_gate_timing(self):
        manifest = capture.generate(self.folder / "all", "all", init_syx=self.init, channel=16, device_id=23)
        self.assertEqual(manifest["fixture_count"], 95)
        self.assertAlmostEqual(manifest["total_midi_duration_seconds"], 517.0)
        self.assertLess(manifest["total_midi_duration_seconds"], 600)
        self.assertEqual(manifest["system_requirements"]["device_id_panel_display"], 24)
        self.assertEqual(len({f["id"] for f in manifest["fixtures"]}), 95)
        durations = 0
        for fixture in manifest["fixtures"]:
            with self.subTest(fixture=fixture["id"]):
                syx = (self.folder / "all" / fixture["patch"]).read_bytes()
                midi = (self.folder / "all" / fixture["midi"]).read_bytes()
                self.assertEqual(hashlib.sha256(syx).hexdigest(), fixture["patch_sha256"])
                self.assertEqual(hashlib.sha256(midi).hexdigest(), fixture["midi_sha256"])
                packets = [packet + b"\xf7" for packet in syx.split(b"\xf7")[:-1]]
                self.assertEqual(len(packets), 22)
                for index, packet in enumerate(packets):
                    self.assertEqual(packet[:7], bytes((240, 65, 23, 0, 0, 22, 18)))
                    self.assertEqual(packet[7:11], bytes((16, 0, index, 0)))
                    self.assertEqual(len(packet), capture.BLOCK_SIZES[index] + 13)
                    self.assertEqual(sum(packet[7:-1]) % 128, 0)
                    self.assertTrue(all(x < 128 for x in packet[1:-1]))
                blocks = capture.decode_syx(syx)
                self.assertEqual(blocks[0][0x11:0x13], bytes((0, 0)))
                self.assertEqual(blocks[0][0x1A:0x1E], bytes(4))
                for block in blocks[1:3]:
                    self.assertEqual(block[0x14:0x16], bytes((64, 64)))
                    self.assertEqual(block[0x1C], 0)
                    self.assertEqual(block[0x1F], 64)
                    self.assertEqual(block[0x25:0x27], bytes(2))
                    for offset in (0x05, 0x0B, 0x2E, 0x30, 0x38, 0x3A, 0x3C):
                        self.assertEqual(block[offset], 64)
                parsed = render_midi.parse_smf(midi, 96000)
                self.assertEqual(parsed["end_sample"], fixture["duration_ms"] * 96)
                self.assertEqual(parsed["timing"]["ticks_per_quarter"], 1000)
                events = [e for e in parsed["events"] if e["kind"] == "midi"]
                sounding = set()
                observed_notes = []
                for event in events:
                    message = bytes.fromhex(event["hex"])
                    self.assertEqual(event["channel"], 16)
                    if message[0] & 240 == 144:
                        self.assertNotIn(message[1], sounding)
                        sounding.add(message[1])
                        observed_notes.append({"note": message[1], "velocity": message[2], "on_ms": event["tick"]})
                    elif message[0] & 240 == 128:
                        self.assertIn(message[1], sounding)
                        sounding.remove(message[1])
                        observed_notes[-1]["off_ms"] = event["tick"]
                    elif message[0] & 240 == 176 and message[1] == 120:
                        self.assertFalse(sounding, "panic must not substitute for explicit note-offs")
                self.assertEqual(observed_notes, fixture["notes"])
                self.assertFalse(sounding)
                resets = {bytes.fromhex(e["hex"])[1]: bytes.fromhex(e["hex"])[2]
                          for e in events if e["tick"] == 0 and e["hex"].startswith("bf")}
                for cc, value in ((120, 0), (123, 0), (121, 0), (64, 0), (66, 0), (1, 0), (7, 127), (10, 64), (11, 127)):
                    self.assertEqual(resets[cc], value)
                self.assertEqual(events[-1]["tick"] - fixture["notes"][-1]["off_ms"], fixture["release_observation_ms"])
                _, ignored = render_midi.replay_events(parsed, channel=16, tempo_policy="preserve-patch")
                self.assertFalse(any(e.get("degrades_replay") for e in ignored))
                durations += fixture["duration_ms"]
        self.assertEqual(durations / 1000, manifest["total_midi_duration_seconds"])

    def test_sparse_suite_coverage_and_short_default(self):
        all_cases = capture.fixtures("all")
        decay = [f for f in all_cases if f["id"].startswith("envelope-d")]
        self.assertEqual({f["tone"]["filter_decay"] for f in decay}, {37, 49, 58, 61, 64})
        self.assertEqual({f["tone"]["filter_sustain"] for f in decay}, {0, 64, 127})
        self.assertTrue(all(f["notes"][0]["off_ms"] - f["notes"][0]["on_ms"] == 4500 for f in decay))
        self.assertEqual({f["tone"]["osc1_pw"] for f in capture.fixtures("supersaw")}, {0, 41, 64, 127})
        self.assertEqual({f["tone"]["osc1_fine"] - 64 for f in capture.fixtures("aliasing")}, {-17, 0, 17})
        self.assertEqual({f["notes"][0]["note"] for f in capture.fixtures("aliasing")}, {60, 84, 108})
        self.assertEqual(len([f for f in all_cases if f["id"].startswith("phase-")]), 3)
        quick = capture.generate(self.folder / "quick", init_syx=self.init)
        self.assertEqual(quick["fixture_count"], 6)
        self.assertLess(quick["total_midi_duration_seconds"], 30)

    def test_deterministic_output_and_no_overwrite(self):
        capture.generate(self.folder / "first", init_syx=self.init)
        capture.generate(self.folder / "second", init_syx=self.init)
        first = {p.name: p.read_bytes() for p in (self.folder / "first").iterdir()}
        second = {p.name: p.read_bytes() for p in (self.folder / "second").iterdir()}
        self.assertEqual(first, second)
        with self.assertRaises(FileExistsError):
            capture.generate(self.folder / "first", init_syx=self.init)
        self.assertEqual(first, {p.name: p.read_bytes() for p in (self.folder / "first").iterdir()})
        (self.folder / "occupied").mkdir()
        with self.assertRaises(FileExistsError):
            capture.generate(self.folder / "occupied", init_syx=self.init)

    def test_negative_attack_encoded_controls_and_exact_midi(self):
        directory = self.folder / "negative-attack"
        manifest = capture.generate(directory, "negative-attack", init_syx=self.init)
        self.assertEqual(manifest["fixture_count"], 4)
        self.assertEqual(manifest["total_midi_duration_seconds"], 14.4)
        for attack, fixture in zip((0, 13, 24, 36), manifest["fixtures"]):
            with self.subTest(attack=attack):
                blocks = capture.decode_syx((directory / fixture["patch"]).read_bytes())
                common, upper = blocks[0], blocks[1]
                self.assertEqual(common[0x11:0x13], bytes((0, 0)))  # SINGLE UPPER
                self.assertEqual(common[0x19:0x1E], bytes(5))
                self.assertEqual(upper[0x00:0x06], bytes((0, 0, 64, 64, 64, 64)))
                self.assertEqual(upper[0x0F:0x17], bytes((1, 0, 1, 1, 120, 64, 64, 0)))
                self.assertEqual(upper[0x17:0x1E], bytes((attack, 127, 127, 0, 42, 0, 0)))
                self.assertEqual(upper[0x1F], 64)  # neutral AMP velocity
                self.assertEqual(upper[0x21:0x27], bytes((0, 0, 127, 0, 0, 0)))
                for offset in (0x2E, 0x30, 0x38, 0x3A):
                    self.assertEqual(upper[offset], 64)
                self.assertEqual(fixture["capture"]["status"], "not-recorded")
                self.assertIsNone(fixture["capture"]["audio_file"])
                parsed = render_midi.parse_smf((directory / fixture["midi"]).read_bytes(), 96000)
                note_events = [(e["sample"], e["hex"]) for e in parsed["events"]
                               if e["kind"] == "midi" and int(e["hex"][:2], 16) & 0xF0 in (0x80, 0x90)]
                self.assertEqual(note_events, [(48000, "903064"), (288000, "803000")])
                self.assertEqual(parsed["end_sample"], 345600)

    def test_rejects_corrupt_partial_duplicate_and_out_of_range_sysex(self):
        valid = synthetic_init()
        corrupt = bytearray(valid); corrupt[12] ^= 1
        for data in (valid[:-1], bytes(corrupt), valid + valid[:46], valid[46:]):
            with self.subTest(data=data[:24]):
                with self.assertRaises(ValueError):
                    capture.decode_syx(data)
        for field, bad in (("osc1_wave", 9), ("osc1_fine", 127), ("balance", 0), ("key_follow", 85)):
            blocks = capture.decode_syx(valid)
            blocks[1][capture.TONE_FIELDS[field][0]] = bad
            with self.subTest(field=field), self.assertRaises(ValueError):
                capture.encode_syx(blocks)
        for device in (0, 15, 24, 127):
            with self.assertRaises(ValueError):
                capture.encode_syx(capture.decode_syx(valid), device)

    def test_invalid_input_creates_no_partial_package(self):
        for keyword in ({"suite": "unknown"}, {"channel": 0}, {"device_id": 24}):
            with self.assertRaises(ValueError):
                capture.generate(self.folder / "invalid", init_syx=self.init, **keyword)
            self.assertFalse((self.folder / "invalid").exists())
        self.init.write_bytes(b"bad")
        with self.assertRaises(ValueError):
            capture.generate(self.folder / "invalid", init_syx=self.init)
        self.assertFalse((self.folder / "invalid").exists())

    def test_real_exporter_and_renderer(self):
        if RENDERER is None:
            self.skipTest("pass --renderer to validate the real INIT exporter")
        manifest = capture.generate(self.folder / "real", renderer=RENDERER)
        self.assertEqual(manifest["initial_patch"]["kind"], "septum-init-export")
        self.assertEqual(manifest["initial_patch"]["executable_sha256"], hashlib.sha256(RENDERER.read_bytes()).hexdigest())
        for fixture in manifest["fixtures"]:
            process = subprocess.run([str(RENDERER), "--inspect-patch", str(self.folder / "real" / fixture["patch"])],
                                     check=True, capture_output=True, text=True)
            inspected = json.loads(process.stdout)
            self.assertFalse(inspected["delay_on"] or inspected["reverb_on"] or inspected["arpeggio_on"])
            self.assertEqual(inspected["keyboard_mode"], "single")
        fixture = next(f for f in manifest["fixtures"] if f["suite"] == "envelopes")
        command = [sys.executable, str(ROOT / "Tools/render_midi.py"), "--renderer", str(RENDERER),
                   "--syx", str(self.folder / "real" / fixture["patch"]),
                   "--midi", str(self.folder / "real" / fixture["midi"]), "--output", str(self.folder / "test.wav"),
                   "--sample-rate", "48000", "--tail", "0", "--tempo-policy", "preserve-patch", "--strict"]
        rendered = json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)
        self.assertFalse(rendered["degraded_replay"])
        self.assertEqual(rendered["output"]["frames"], fixture["duration_ms"] * 48)
        self.assertEqual(rendered["output"]["active_voices_at_end"], 0)
        self.assertGreater(rendered["output"]["peak"], 0.001)
        self.assertLess(rendered["output"]["peak"], 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--renderer", type=Path)
    args, rest = parser.parse_known_args()
    RENDERER = args.renderer.resolve() if args.renderer else None
    unittest.main(argv=[sys.argv[0]] + rest)
