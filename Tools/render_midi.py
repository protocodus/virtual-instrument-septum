#!/usr/bin/env python3
"""Render a real Standard MIDI File through Septum's shipping DSP engine.

No third-party Python packages. SMF formats 0/1, PPQ tempo maps and SMPTE time
division are decoded before replay. Unsupported sound-changing events fail by
default; explicit omissions are retained in the JSON manifest.
"""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import tempfile


class MidiError(ValueError):
    """An invalid or unsupported Standard MIDI File."""


class Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.position = 0

    def take(self, count: int) -> bytes:
        if count < 0 or self.position + count > len(self.data):
            raise MidiError("Truncated MIDI data")
        result = self.data[self.position:self.position + count]
        self.position += count
        return result

    def byte(self) -> int:
        return self.take(1)[0]

    def vlq(self) -> int:
        result = 0
        for _ in range(4):
            value = self.byte()
            result = (result << 7) | (value & 127)
            if value < 128:
                return result
        raise MidiError("SMF variable-length quantity exceeds four bytes")


def nearest(value: Fraction) -> int:
    """Round nonnegative rational timestamps to nearest sample, ties upward."""
    return (2 * value.numerator + value.denominator) // (2 * value.denominator)


def parse_smf(data: bytes, sample_rate: int = 44100) -> dict:
    if not 8000 <= sample_rate <= 192000:
        raise MidiError("Sample rate must be 8000–192000")
    if len(data) > 64 * 1024 * 1024:
        raise MidiError("MIDI file exceeds 64 MiB")
    source = Reader(data)
    if source.take(4) != b"MThd":
        raise MidiError("Expected an SMF MThd header")
    header_size = int.from_bytes(source.take(4), "big")
    if header_size < 6:
        raise MidiError("MIDI header is shorter than six bytes")
    header = source.take(header_size)
    fmt, tracks, division = struct.unpack(">HHH", header[:6])
    if fmt not in (0, 1) or tracks < 1 or tracks > 256 or (fmt == 0 and tracks != 1):
        raise MidiError("Only format 0 (one track) and format 1 (1–256 tracks) are supported")
    if division & 0x8000:
        frames_code = (division >> 8) - 256
        ticks_per_frame = division & 255
        if frames_code not in (-24, -25, -29, -30) or ticks_per_frame == 0:
            raise MidiError("Invalid SMPTE MIDI division")
        fps = Fraction(30000, 1001) if frames_code == -29 else Fraction(-frames_code)
        seconds_per_tick = 1 / (fps * ticks_per_frame)
        timing = {"mode": "smpte", "frames_code": frames_code,
                  "ticks_per_frame": ticks_per_frame, "frames_per_second": float(fps)}
    else:
        if division == 0:
            raise MidiError("Ticks per quarter note must be nonzero")
        seconds_per_tick = None
        timing = {"mode": "ppq", "ticks_per_quarter": division}

    events: list[dict] = []
    end_tick = 0
    for track_index in range(tracks):
        if source.take(4) != b"MTrk":
            raise MidiError("Expected an MTrk chunk")
        track = Reader(source.take(int.from_bytes(source.take(4), "big")))
        tick = 0
        running_status = None
        ended = False
        sequence = 0
        while track.position < len(track.data):
            tick += track.vlq()
            if len(events) >= 1000000:
                raise MidiError("MIDI file contains more than one million events")
            status = track.byte()
            first_data = None
            if status < 128:
                if running_status is None:
                    raise MidiError("Running status without a preceding channel status")
                first_data, status = status, running_status
            event = {"tick": tick, "track": track_index, "order": sequence}
            sequence += 1
            if 0x80 <= status <= 0xef:
                running_status = status
                count = 1 if (status & 0xf0) in (0xc0, 0xd0) else 2
                payload = (bytes([first_data]) if first_data is not None else b"")
                payload += track.take(count - len(payload))
                if any(value >= 128 for value in payload):
                    raise MidiError("Status byte where channel data was expected")
                event.update(kind="midi", hex=(bytes([status]) + payload).hex(),
                             channel=(status & 15) + 1)
            elif status == 0xff:
                running_status = None
                meta_type = track.byte()
                payload = track.take(track.vlq())
                event.update(kind="meta", meta_type=meta_type, hex=payload.hex())
                if meta_type == 0x2f:
                    if payload or track.position != len(track.data):
                        raise MidiError("Invalid End-of-Track or data following it")
                    ended = True
                elif meta_type == 0x51:
                    if len(payload) != 3 or int.from_bytes(payload, "big") == 0:
                        raise MidiError("Invalid Set Tempo meta event")
                    if fmt == 1 and track_index != 0:
                        raise MidiError("Format 1 tempo map must be in its conductor track (track 0)")
                    event.update(kind="tempo", microseconds_per_quarter=int.from_bytes(payload, "big"))
            elif status in (0xf0, 0xf7):
                running_status = None
                payload = track.take(track.vlq())
                event.update(kind="sysex", hex=(bytes([status]) + payload).hex())
            else:
                raise MidiError(f"Invalid SMF event status 0x{status:02x}")
            events.append(event)
        if not ended:
            raise MidiError(f"Track {track_index} has no End-of-Track meta event")
        end_tick = max(end_tick, tick)
    if source.position != len(data):
        raise MidiError("Unexpected chunks or bytes after the declared tracks")

    events.sort(key=lambda event: (event["tick"], event["track"], event["order"]))
    seconds = Fraction(0)
    previous_tick = 0
    microseconds = 500000  # SMF's specified default: 120 BPM.
    tempo_map = [{"tick": 0, "sample": 0, "microseconds_per_quarter": 500000,
                  "bpm": 120.0, "implicit_default": True}]
    for event in events:
        tick_delta = event["tick"] - previous_tick
        seconds += tick_delta * (seconds_per_tick if seconds_per_tick is not None
                                 else Fraction(microseconds, division * 1000000))
        previous_tick = event["tick"]
        event["sample"] = nearest(seconds * sample_rate)
        if event["kind"] == "tempo":
            microseconds = event["microseconds_per_quarter"]
            tempo_map.append({"tick": event["tick"], "sample": event["sample"],
                              "microseconds_per_quarter": microseconds,
                              "bpm": 60000000 / microseconds, "implicit_default": False})
    return {"format": fmt, "track_count": tracks, "timing": timing,
            "events": events, "tempo_map": tempo_map, "end_tick": end_tick,
            "end_sample": nearest(seconds * sample_rate), "sample_rate": sample_rate,
            "same_tick_order": "track number, then event order within track",
            "sample_rounding": "nearest sample, exact rational timing, ties upward"}


PERFORMANCE_CCS = {1, 2, 4, 7, 10, 11, 64, 66, 84, 120, 121, 123, 124, 125, 126, 127}
PANEL_CCS = {3, 8, 9, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24,
             25, 26, 27, 28, 29, 30, 31, 70, 71, 72, 73, 74, 75, 76, 77, 78,
             79, 80, 81, 82, 83, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95,
             102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113,
             114, 115, 116, 117, 118, 119}


def replay_events(parsed: dict, channel: int = 1, allow_unsupported: bool = False,
                  ignore_program_changes: bool = False, tempo_policy: str = "follow-midi") -> tuple[list, list]:
    if not 0 <= channel <= 16:
        raise MidiError("Channel must be 1–16, or 0 for explicit ALL-channel replay")
    replay, ignored = [], []
    if tempo_policy == "follow-midi":
        replay.append({"sample": 0, "kind": "tempo", "value": "120"})
    elif tempo_policy != "preserve-patch":
        raise MidiError("Invalid tempo policy")
    for event in parsed["events"]:
        kind = event["kind"]
        reason = None
        if kind == "tempo":
            if tempo_policy == "follow-midi":
                bpm = Fraction(60000000, event["microseconds_per_quarter"])
                if not 5 <= bpm <= 300:
                    raise MidiError("SMF tempo exceeds the documented 5–300 BPM clock range")
                replay.append({"sample": event["sample"], "kind": "tempo",
                               "value": format(float(bpm), ".17g")})
            continue
        if kind == "meta":
            # Routing/device and sequencer-specific meta events cannot safely
            # be dismissed as labels when claiming exact event playback.
            if event["meta_type"] in (0x20, 0x21, 0x7f):
                reason = "unsupported routing or sequencer-specific meta event"
            else:
                continue
        elif kind == "sysex":
            reason = "embedded SysEx/escape event; the supplied .syx is the patch authority"
        elif channel != 0 and event["channel"] != channel:
            ignored.append({**event, "reason": "outside selected MIDI channel", "degrades_replay": False})
            continue
        else:
            message = bytes.fromhex(event["hex"])
            status = message[0] & 0xf0
            if status == 0xc0 or (status == 0xb0 and message[1] in (0, 32)):
                reason = "program/bank metadata; fixed supplied patch retained"
                if not ignore_program_changes:
                    raise MidiError("Program/bank selection found; use --ignore-program-changes to explicitly retain the supplied patch")
                ignored.append({**event, "reason": reason, "degrades_replay": True})
                continue
            if status in (0x80, 0x90, 0xe0) or (status == 0xb0 and message[1] in PERFORMANCE_CCS | PANEL_CCS):
                replay.append({"sample": event["sample"], "kind": "midi", "value": event["hex"]})
                continue
            reason = f"unsupported MIDI status/CC: {event['hex']}"
        if not allow_unsupported:
            raise MidiError(f"Strict replay refused {reason} at sample {event['sample']}; --allow-unsupported records and omits it")
        ignored.append({**event, "reason": reason, "degrades_replay": True})
    return replay, ignored


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def render(args: argparse.Namespace) -> dict:
    midi_path, patch_path, binary = args.midi.resolve(), args.syx.resolve(), args.renderer.resolve()
    output = args.output.resolve()
    manifest_path = args.manifest.resolve() if args.manifest else output.with_suffix(".render.json")
    if output.exists() or manifest_path.exists():
        raise MidiError("Output WAV or manifest already exists; choose unused filenames")
    if output == manifest_path:
        raise MidiError("WAV and manifest must have different filenames")
    if not math.isfinite(args.tail) or not 0 <= args.tail <= 120:
        raise MidiError("Tail must be finite and between 0 and 120 seconds")
    if not 0 <= args.master_level <= 127:
        raise MidiError("Master level must be 0–127")
    midi_bytes = midi_path.read_bytes()
    patch_bytes = patch_path.read_bytes()
    parsed = parse_smf(midi_bytes, args.sample_rate)
    replay, ignored = replay_events(parsed, args.channel, args.allow_unsupported,
                                    args.ignore_program_changes, args.tempo_policy)
    inputs = {"midi": {"path": str(midi_path), "sha256": hashlib.sha256(midi_bytes).hexdigest()},
              "sysex": {"path": str(patch_path), "sha256": hashlib.sha256(patch_bytes).hexdigest()},
              "renderer": {"path": str(binary), "sha256": sha256(binary)}}
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="septum-midi-") as folder:
        event_file = Path(folder) / "events.txt"
        event_file.write_text(
            f"SEPTUM_RENDER_EVENTS 1 {parsed['end_sample']}\n" +
            "".join(f"{event['sample']} {event['kind']} {event['value']}\n" for event in replay),
            encoding="ascii")
        staged_wav = Path(folder) / "render.wav"
        staged_patch = Path(folder) / "patch.syx"
        staged_patch.write_bytes(patch_bytes)
        command = [str(binary), "--syx", str(staged_patch), "--events", str(event_file),
                   "--output", str(staged_wav), "--sample-rate", str(args.sample_rate),
                   "--tail", str(args.tail), "--master-level", str(args.master_level)]
        if args.keyboard_mode:
            command.append("--keyboard-mode")
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode:
            raise MidiError(completed.stderr.strip() or "Renderer failed")
        measured = json.loads(completed.stdout)
        for identity in inputs.values():
            if sha256(Path(identity["path"])) != identity["sha256"]:
                raise MidiError("An input changed while the render was running; take rejected")
        # Copy only complete renders to the requested destination.
        with staged_wav.open("rb") as source, output.open("xb") as destination:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                destination.write(chunk)
    counts = Counter()
    for event in replay:
        if event["kind"] == "midi":
            message = bytes.fromhex(event["value"])
            status = message[0] & 0xf0
            if status == 0x90 and message[2] != 0:
                counts["note_on"] += 1
            elif status == 0x80 or status == 0x90:
                counts["note_off"] += 1
            elif status == 0xe0:
                counts["pitch_bend"] += 1
            else:
                counts[f"cc_{message[1]}"] += 1
    manifest = {
        "schema_version": 1,
        "claim": "Deterministic Septum replay of the identified MIDI and patch; hardware matching requires independently verified source performance provenance.",
        "inputs": inputs,
        "output": {"path": str(output), "sha256": sha256(output),
                   "encoding": "IEEE float32 stereo WAV", "normalised": False,
                   "latency_compensated": False, **measured},
        "settings": {"sample_rate": args.sample_rate, "tail_seconds": args.tail,
                     "master_level": args.master_level, "midi_channel": args.channel,
                     "tempo_policy": args.tempo_policy,
                     "tempo_to_patch_mapping": "none; stored patch tempo is preserved",
                     "tempo_clock_mapping": "fractional BPM from SMF microseconds/quarter, 5–300; timestamps retain rational SMF timing",
                     "note_semantics": "Engine keyboard/arpeggiator replay" if args.keyboard_mode else "arpeggio-off patch required",
                     "automatic_note_offs_at_end": False,
                     "unsupported_policy": "omit with audit" if args.allow_unsupported else "reject",
                     "program_bank_policy": "omit with audit, supplied patch retained" if args.ignore_program_changes else "reject"},
        "midi": {key: value for key, value in parsed.items() if key != "events"},
        "metadata": [event for event in parsed["events"] if event["kind"] == "meta"],
        "replay_event_counts": dict(sorted(counts.items())),
        "replay_events": replay,
        "ignored_events": ignored,
        "degraded_replay": any(event["degrades_replay"] for event in ignored),
    }
    with manifest_path.open("x", encoding="utf-8") as output_manifest:
        json.dump(manifest, output_manifest, indent=2, ensure_ascii=False)
        output_manifest.write("\n")
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--renderer", required=True, type=Path, help="SeptumRenderMidi executable")
    parser.add_argument("--midi", required=True, type=Path)
    parser.add_argument("--syx", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", type=Path, help="default: OUTPUT.render.json")
    parser.add_argument("--sample-rate", type=int, default=44100)
    parser.add_argument("--tail", type=float, default=2.0)
    parser.add_argument("--master-level", type=int, default=100)
    parser.add_argument("--channel", type=int, default=1, help="1–16; 0 explicitly combines all channels")
    parser.add_argument("--tempo-policy", choices=("follow-midi", "preserve-patch"), default="follow-midi")
    parser.add_argument("--keyboard-mode", action="store_true", help="explicitly permit keyboard/arpeggiator replay")
    parser.add_argument("--allow-unsupported", action="store_true", help="omit unsupported messages and mark replay degraded")
    parser.add_argument("--ignore-program-changes", action="store_true", help="record program/bank messages but retain supplied patch")
    parser.add_argument("--strict", action="store_true", help="explicit default: reject unsupported events")
    args = parser.parse_args(argv)
    try:
        if args.strict and args.allow_unsupported:
            raise MidiError("--strict and --allow-unsupported are mutually exclusive")
        manifest = render(args)
        print(json.dumps({"output": manifest["output"], "degraded_replay": manifest["degraded_replay"]}, indent=2))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"render_midi: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
