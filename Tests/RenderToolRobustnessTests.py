#!/usr/bin/env python3
"""Bounded malformed-input fuzzing and deterministic offline-render regression tests."""
import argparse
import importlib.util
import json
from pathlib import Path
import random
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("render_midi", ROOT / "Tools/render_midi.py")
midi = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(midi)
RENDERER = None
DEMOS = None


def smf(*tracks, division=480):
    return (b"MThd" + struct.pack(">IHHH", 6, int(len(tracks) > 1), len(tracks), division)
            + b"".join(b"MTrk" + struct.pack(">I", len(track)) + track for track in tracks))


class ParserRobustnessTests(unittest.TestCase):
    def test_same_tick_and_sample_collisions_keep_source_order(self):
        data = smf(b"\0\xb0\x78\0\0\x90\x3c\x64\x01\x80\x3c\0\0\xff\x2f\0",
                   b"\0\xb0\x40\x7f\x01\x90\x40\x64\0\xff\x2f\0", division=32767)
        parsed = midi.parse_smf(data, 8000)
        replay, _ = midi.replay_events(parsed, tempo_policy="preserve-patch")
        self.assertEqual([event["sample"] for event in replay], [0] * 5)
        self.assertEqual([event["value"] for event in replay],
                         ["b07800", "903c64", "b0407f", "803c00", "904064"])

    def test_rejects_unrenderable_duration_before_serializing_replay(self):
        with self.assertRaisesRegex(midi.MidiError, "one hour"):
            midi.parse_smf(smf(b"\xff\xff\xff\x7f\xff\x2f\0", division=1))

    def test_bounded_reads_reject_large_sparse_input(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "oversized.mid"
            with path.open("wb") as output:
                output.truncate(64 * 1024 * 1024 + 1)
            with self.assertRaisesRegex(midi.MidiError, "64 MiB"):
                midi.read_input(path)

    def test_seeded_smf_mutations_fail_cleanly_or_preserve_invariants(self):
        rng = random.Random(0x5E971)
        seeds = [smf(b"\0\x90\x3c\x64\x60\x3c\0\0\xff\x2f\0"),
                 smf(b"\0\xff\x51\x03\x07\xa1\x20\0\xff\x2f\0",
                     b"\0\xb0\x40\x7f\0\x90\x40\x64\x60\x80\x40\0\0\xff\x2f\0")]
        accepted = rejected = 0
        for _ in range(5000):
            data = bytearray(rng.choice(seeds))
            for _ in range(rng.randint(1, 5)):
                position = rng.randrange(len(data))
                operation = rng.randrange(3)
                if operation == 0:
                    data[position] ^= 1 << rng.randrange(8)
                elif operation == 1:
                    del data[position:position + rng.randint(1, 4)]
                else:
                    data[position:position] = rng.randbytes(rng.randint(1, 4))
            try:
                parsed = midi.parse_smf(bytes(data), rng.choice((8000, 44100, 192000)))
            except midi.MidiError:
                rejected += 1
                continue
            accepted += 1
            samples = [event["sample"] for event in parsed["events"]]
            self.assertEqual(samples, sorted(samples))
            self.assertTrue(all(0 <= sample <= parsed["end_sample"] for sample in samples))
            for event in parsed["events"]:
                if event["kind"] == "midi":
                    message = bytes.fromhex(event["hex"])
                    self.assertTrue(0x80 <= message[0] <= 0xef)
                    self.assertTrue(all(value < 128 for value in message[1:]))
        self.assertGreater(accepted, 0)
        self.assertGreater(rejected, 4000)


class ReplayRobustnessTests(unittest.TestCase):
    def setUp(self):
        if RENDERER is None:
            self.skipTest("Pass --renderer to exercise the compiled replay tool")
        self.folder = tempfile.TemporaryDirectory(prefix="septum-render-robustness-")
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name)
        self.patch = self.path / "init.syx"
        subprocess.run([str(RENDERER), "--write-init-patch", str(self.patch)], check=True, timeout=10)
        self.index = 0

    def replay(self, contents, options=(), success=False):
        self.index += 1
        source = self.path / f"events-{self.index}.txt"
        output = self.path / f"audio-{self.index}.wav"
        source.write_bytes(contents if isinstance(contents, bytes) else contents.encode("ascii"))
        command = [str(RENDERER), "--syx", str(self.patch), "--events", str(source),
                   "--output", str(output), "--tail", "0", *options]
        result = subprocess.run(command, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0 if success else 1, result.stderr.decode(errors="replace"))
        for sanitizer in (b"AddressSanitizer", b"UndefinedBehaviorSanitizer", b"runtime error:"):
            self.assertNotIn(sanitizer, result.stderr)
        if success:
            self.assertTrue(output.exists())
            return json.loads(result.stdout), output.read_bytes()
        self.assertFalse(output.exists(), "Rejected input must not leave a partial WAV")
        return result

    def test_rejects_invalid_replay_before_creating_wav(self):
        for timestamp in ("-0", "+0", "-1", "18446744073709551616", "1.5"):
            with self.subTest(timestamp=timestamp):
                self.replay(f"SEPTUM_RENDER_EVENTS 1 {timestamp}\n")
                self.replay(f"SEPTUM_RENDER_EVENTS 1 100\n{timestamp} midi 903c64\n")
        for event in ("90+140", "90-040", "903g64", "003c64", "f03c64", "903c80",
                      "c03c00", "b06500", "903c6400"):
            with self.subTest(event=event):
                self.replay(f"SEPTUM_RENDER_EVENTS 1 100\n0 midi 903c64\n50 midi {event}\n")
        for tempo in ("nan", "inf", "-inf", "1e9999", "4.999", "300.001", "120junk"):
            self.replay(f"SEPTUM_RENDER_EVENTS 1 100\n0 tempo {tempo}\n")
        for body in ("101 midi 903c64", "5 midi 903c64\n4 midi 803c00",
                     "0 unknown 120", "0 midi 903c64 extra", "0 midi " + "a" * 100000):
            self.replay(f"SEPTUM_RENDER_EVENTS 1 100\n{body}\n")
        self.replay("SEPTUM_RENDER_EVENTS 1 158760001\n")

    def test_seeded_replay_line_mutations_never_crash(self):
        rng = random.Random(0x201)
        for _ in range(100):
            # Preserve a valid first event to expose late validation/partial WAVs.
            payload = rng.randbytes(rng.randrange(0, 128)).replace(b"\n", b"x")
            self.replay(b"SEPTUM_RENDER_EVENTS 1 100\n0 midi 903c64\n50 midi " + payload + b"\n")

    def test_numeric_option_fuzz_is_rejected_cleanly(self):
        for option, values in (("--sample-rate", ("nan", "inf", "-1", "7999", "192001", "44100.5")),
                               ("--master-level", ("-1", "128", "1e100", "nan")),
                               ("--tail", ("-1", "121", "inf", "nan"))):
            for value in values:
                self.replay("SEPTUM_RENDER_EVENTS 1 0\n", (option, value))

    def test_same_sample_order_changes_sound_and_repeats_exactly(self):
        header = "SEPTUM_RENDER_EVENTS 1 4410\n"
        silence, _ = self.replay(header + "0 midi 903c64\n0 midi b07800\n", success=True)
        note, first = self.replay(header + "0 midi b07800\n0 midi 903c64\n", success=True)
        _, second = self.replay(header + "0 midi b07800\n0 midi 903c64\n", success=True)
        self.assertEqual(silence["peak"], 0)
        self.assertGreater(note["peak"], 0.001)
        self.assertEqual(first, second)


class DemoParallelTests(unittest.TestCase):
    def test_parallel_smoke_matches_serial_audio(self):
        if DEMOS is None:
            self.skipTest("Pass --demos to exercise independent rendering workers")
        with tempfile.TemporaryDirectory(prefix="septum-parallel-smoke-") as folder:
            result = subprocess.run([str(DEMOS), "--smoke", "--jobs", "4", folder],
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("smoke test passed", result.stdout)
            self.assertFalse(list(Path(folder).glob("*.wav")))

    def test_invalid_worker_counts_and_options_fail_without_creating_directories(self):
        if DEMOS is None:
            self.skipTest("Pass --demos to exercise argument validation")
        for arguments in (("--jobs", "0"), ("--jobs", "12"), ("--jobs", "-1"),
                          ("--jobs", "1.5"), ("--jobs", "nan"), ("--jobs",), ("--unknown",)):
            result = subprocess.run([str(DEMOS), *arguments], capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 1, result.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--renderer", type=Path)
    parser.add_argument("--demos", type=Path)
    args, remaining = parser.parse_known_args()
    RENDERER = args.renderer.resolve() if args.renderer else None
    DEMOS = args.demos.resolve() if args.demos else None
    unittest.main(argv=[__file__, *remaining])
