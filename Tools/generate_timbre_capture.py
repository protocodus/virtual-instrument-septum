#!/usr/bin/env python3
"""Generate offline SH-201 timbre-calibration patches, MIDI and capture manifests.

Requires only Python's standard library and either a built SeptumRenderMidi
(--write-init-patch) or an explicitly supplied complete INIT SysEx. Nothing is
sent to a device. Existing output directories are never overwritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "septum.timbre-capture.v1"
BLOCK_SIZES = (33, 64, 64, 5, 10, 8) + (66,) * 16
WAVES = {"saw": 0, "square": 1, "pulse": 2, "triangle": 3, "sine": 4,
         "noise": 5, "feedback": 6, "supersaw": 7}
# Roland MIDI Implementation v1.00, Patch Tone, pp. 4–5. Values below are
# wire values; signed controls retain their explicit 64 bias in the manifest.
TONE_FIELDS = {
    "osc1_wave": (0x00, 0, 8), "osc1_wide": (0x01, 0, 1),
    "osc1_coarse": (0x02, 28, 100), "osc1_fine": (0x03, 14, 114),
    "osc1_pw": (0x04, 0, 127), "osc1_pitch_depth": (0x05, 1, 127),
    "osc2_wave": (0x06, 0, 8), "osc2_wide": (0x07, 0, 1),
    "osc2_coarse": (0x08, 28, 100), "osc2_fine": (0x09, 14, 114),
    "osc2_pw": (0x0A, 0, 127), "osc2_pitch_depth": (0x0B, 1, 127),
    "pitch_attack": (0x0C, 0, 127), "pitch_decay": (0x0D, 0, 127),
    "mix_type": (0x0E, 0, 2), "balance": (0x0F, 1, 127),
    "low_freq": (0x10, 0, 2), "filter_type": (0x11, 0, 3),
    "filter_slope": (0x12, 0, 1), "cutoff": (0x13, 0, 127),
    "key_follow": (0x14, 44, 84), "filter_velocity": (0x15, 1, 127),
    "resonance": (0x16, 0, 127), "filter_attack": (0x17, 0, 127),
    "filter_decay": (0x18, 0, 127), "filter_sustain": (0x19, 0, 127),
    "filter_release": (0x1A, 0, 127), "filter_depth": (0x1B, 1, 127),
    "overdrive": (0x1C, 0, 1), "drive": (0x1D, 0, 127),
    "level": (0x1E, 0, 127), "level_velocity": (0x1F, 1, 127),
    "pan": (0x20, 0, 127), "amp_attack": (0x21, 0, 127),
    "amp_decay": (0x22, 0, 127), "amp_sustain": (0x23, 0, 127),
    "amp_release": (0x24, 0, 127), "delay_depth": (0x25, 0, 127),
    "reverb_depth": (0x26, 0, 127), "bend_range": (0x3B, 0, 24),
    "octave_shift": (0x3C, 61, 67), "portamento": (0x3D, 0, 1),
    "portamento_time": (0x3E, 0, 127), "mono": (0x3F, 0, 2),
}
for lfo, base in ((1, 0x27), (2, 0x31)):
    for field, offset, maximum in (("shape", 0, 6), ("rate", 1, 127),
                                 ("sync", 2, 1), ("sync_note", 3, 19),
                                 ("fade", 4, 127), ("trigger", 5, 1),
                                 ("dest1", 6, 3), ("depth1", 7, 127),
                                 ("dest2", 8, 2), ("depth2", 9, 127)):
        TONE_FIELDS[f"lfo{lfo}_{field}"] = (base + offset,
                                          1 if field.startswith("depth") else 0, maximum)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def nibbles(data):
    if any(value > 15 for value in data):
        raise ValueError("non-nibble value in a nibbled parameter")
    result = 0
    for value in data:
        result = result * 16 + value
    return result


def validate_blocks(blocks):
    if len(blocks) != len(BLOCK_SIZES):
        raise ValueError("a complete patch must contain all 22 blocks")
    for block, size in zip(blocks, BLOCK_SIZES):
        if len(block) != size or any(value > 127 for value in block):
            raise ValueError("invalid block length or non-7-bit parameter")
    for block in blocks[1:3]:
        for name, (offset, low, high) in TONE_FIELDS.items():
            if not low <= block[offset] <= high:
                raise ValueError(f"out-of-range tone parameter {name}")
    common = blocks[0]
    ranges = {0x0D: (1, 127), 0x11: (0, 2), 0x12: (0, 1), 0x13: (21, 108),
              0x14: (0, 2), 0x15: (0, 2), 0x16: (0, 2), 0x17: (0, 2),
              0x18: (0, 2), 0x1E: (0, 7), 0x1F: (0, 36), 0x20: (0, 1)}
    ranges.update({offset: (0, 1) for offset in range(0x19, 0x1E)})
    if any(not 32 <= value <= 126 for value in common[:12]):
        raise ValueError("invalid patch name")
    for offset, (low, high) in ranges.items():
        if not low <= common[offset] <= high:
            raise ValueError("out-of-range patch common parameter")
    if not 5 <= nibbles(common[14:17]) <= 300:
        raise ValueError("out-of-range tempo")
    if blocks[3][1] > 98 or blocks[3][2] > 17:
        raise ValueError("out-of-range delay parameter")
    for offset, maximum in ((1, 125), (2, 7), (3, 20), (6, 19), (7, 36), (8, 5), (9, 36)):
        if blocks[4][offset] > maximum:
            raise ValueError("out-of-range reverb parameter")
    arp = blocks[5]
    if not (arp[0] <= 8 and arp[1] <= 9 and arp[2] <= 11 and 61 <= arp[3] <= 67
            and arp[4] <= 100 and 1 <= nibbles(arp[6:8]) <= 32):
        raise ValueError("out-of-range arpeggio common parameter")
    for block in blocks[6:]:
        if any(nibbles(block[i:i+2]) > 128 for i in range(0, 66, 2)):
            raise ValueError("out-of-range arpeggio pattern parameter")


def decode_syx(data):
    """Read exactly one complete temporary-patch dump; reject partial/duplicate packets."""
    blocks = [None] * len(BLOCK_SIZES)
    cursor = 0
    while cursor < len(data):
        end = data.find(b"\xf7", cursor)
        if end < 0:
            raise ValueError("unterminated SysEx packet")
        packet = data[cursor:end+1]
        if len(packet) < 13 or packet[:2] != b"\xf0\x41" or packet[3:7] != b"\x00\x00\x16\x12":
            raise ValueError("expected SH-201 DT1 packet")
        if not 0x10 <= packet[2] <= 0x17 or any(value > 127 for value in packet[1:-1]):
            raise ValueError("invalid device ID or data byte")
        address = packet[7:11]
        if address[:2] != b"\x10\x00" or address[3] != 0 or address[2] >= len(blocks):
            raise ValueError("expected a complete temporary-patch block address")
        index = address[2]
        if blocks[index] is not None or len(packet) != BLOCK_SIZES[index] + 13:
            raise ValueError("duplicate, partial or incorrectly sized block")
        if sum(packet[7:-1]) & 127:
            raise ValueError("invalid Roland checksum")
        blocks[index] = bytearray(packet[11:-2])
        cursor = end + 1
    if any(block is None for block in blocks):
        raise ValueError("a complete patch must contain all 22 blocks")
    validate_blocks(blocks)
    return blocks


def encode_syx(blocks, device_id=0x10):
    validate_blocks(blocks)
    if not 0x10 <= device_id <= 0x17:
        raise ValueError("wire device ID must be 16–23 (hardware display 17–24)")
    result = bytearray()
    for index, block in enumerate(blocks):
        payload = bytes((0x10, 0, index, 0)) + bytes(block)
        result += bytes((0xF0, 0x41, device_id, 0, 0, 0x16, 0x12)) + payload
        result += bytes(((-sum(payload)) & 127, 0xF7))
    return bytes(result)


def base_tone():
    result = dict(osc1_wave=0, osc2_wave=0, osc1_wide=0, osc2_wide=0,
                  osc1_coarse=64, osc2_coarse=64, osc1_fine=64, osc2_fine=64,
                  osc1_pw=64, osc2_pw=64, osc1_pitch_depth=64, osc2_pitch_depth=64,
                  pitch_attack=0, pitch_decay=0, mix_type=0, balance=1, low_freq=0,
                  filter_type=0, filter_slope=1, cutoff=64, key_follow=64,
                  filter_velocity=64, resonance=0, filter_attack=0, filter_decay=49,
                  filter_sustain=127, filter_release=0, filter_depth=64,
                  overdrive=0, drive=0, level=96, level_velocity=64, pan=64,
                  amp_attack=0, amp_decay=0, amp_sustain=127, amp_release=0,
                  delay_depth=0, reverb_depth=0, bend_range=2, octave_shift=64,
                  portamento=0, portamento_time=0, mono=0)
    for lfo in (1, 2):
        result.update({f"lfo{lfo}_{field}": value for field, value in
                       (("shape", 0), ("rate", 0), ("sync", 0), ("sync_note", 17),
                        ("fade", 0), ("trigger", 1), ("dest1", 0), ("depth1", 64),
                        ("dest2", 0), ("depth2", 64))})
    return result


def make_patch(original, spec, device_id):
    blocks = [bytearray(block) for block in original]
    overrides = []
    common = {0x0C: 127, 0x0D: 64, 0x11: 0, 0x12: 0, 0x19: 0,
              0x1A: 0, 0x1B: 0, 0x1C: 0, 0x1D: 0}
    for offset, value in common.items():
        blocks[0][offset] = value
        overrides.append({"address": f"10 00 00 {offset:02X}", "raw": value})
    for part in (1, 2):
        values = base_tone()
        if part == 1:
            values.update(spec["tone"])
        for name, value in sorted(values.items()):
            offset, low, high = TONE_FIELDS[name]
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"out-of-range {name}: {value}")
            blocks[part][offset] = value
            overrides.append({"address": f"10 00 {part:02X} {offset:02X}",
                              "parameter": ("upper." if part == 1 else "lower.") + name,
                              "raw": value})
    return encode_syx(blocks, device_id), overrides


def case(identifier, suite, purpose, tone=None, note=60, gate=2000, repeats=1, gap=500, tail=500):
    notes = [{"note": note, "velocity": 100, "on_ms": 500 + i * (gate + gap),
              "off_ms": 500 + i * (gate + gap) + gate} for i in range(repeats)]
    return {"id": identifier, "suite": suite, "purpose": purpose, "tone": tone or {},
            "notes": notes, "duration_ms": notes[-1]["off_ms"] + tail + 100,
            "release_observation_ms": tail}


def fixtures(suite):
    result = []
    if suite in ("filter", "all", "quick"):
        result.append(case("filter-bypass-noise", "filter", "Noise-source and capture-path reference; average spectra, not sample-null.",
                           {"osc1_wave": 5}, gate=4000))
        for slope in ((1,) if suite == "quick" else (0, 1)):
            for cutoff in ((64,) if suite == "quick" else (32, 64, 96)):
                for resonance in ((40,) if suite == "quick" else (0, 40, 80)):
                    result.append(case(f"filter-lp{12 if slope == 0 else 24}-c{cutoff}-r{resonance}", "filter",
                                       "Static noise-excited LPF response relative to the bypass reference.",
                                       {"osc1_wave": 5, "filter_type": 1, "filter_slope": slope,
                                        "cutoff": cutoff, "resonance": resonance}, gate=4000))
    if suite in ("envelopes", "all", "quick"):
        env = {"filter_type": 1, "filter_slope": 1, "cutoff": 30, "filter_depth": 95,
               "filter_sustain": 0, "resonance": 40}
        for decay in ((49,) if suite == "quick" else (37, 49, 58, 61, 64)):
            for sustain in ((0,) if suite == "quick" else (0, 64, 127)):
                result.append(case(f"envelope-d{decay}-s{sustain}", "envelopes",
                                   "Observe complete decay and held plateau; duration is not a presumed Roland time constant.",
                                   dict(env, filter_decay=decay, filter_sustain=sustain), gate=4500))
        if suite != "quick":
            for attack in (0, 32, 64, 96):
                result.append(case(f"envelope-a{attack}", "envelopes", "Filter attack trajectory with sustain at peak.",
                                   dict(env, filter_attack=attack, filter_sustain=127), gate=3000))
            for release in (0, 37, 64, 96):
                result.append(case(f"envelope-r{release}", "envelopes",
                                   "Filter release under long amp release; analyze spectral shape separately from falling amplitude.",
                                   dict(env, filter_sustain=127, filter_release=release, amp_release=127),
                                   gate=1500, tail=5000))
    if suite in ("waveforms", "all", "quick"):
        for wave in (("triangle",) if suite == "quick" else ("saw", "square", "triangle", "sine")):
            for oscillator in ((1,) if suite == "quick" else (1, 2)):
                result.append(case(f"wave-{wave}-osc{oscillator}", "waveforms",
                                   "Isolated oscillator harmonic shape and level; compare repeated notes for phase variability.",
                                   {f"osc{oscillator}_wave": WAVES[wave], "balance": 1 if oscillator == 1 else 127},
                                   note=48, gate=1000, repeats=3))
        if suite != "quick":
            for width in (0, 64, 127):
                result.append(case(f"wave-pulse-pw{width}", "waveforms", "PW-SQR endpoint and middle duty-cycle measurements.",
                                   {"osc1_wave": 2, "osc1_pw": width}, note=48, gate=1000, repeats=3))
            for other in ("square", "triangle", "sine"):
                result.append(case(f"phase-saw-{other}", "waveforms",
                                   "Unison relative-phase/cancellation distribution; phase is observed, never assumed reset or settable.",
                                   {"osc1_wave": 0, "osc2_wave": WAVES[other], "balance": 64},
                                   note=48, gate=1000, repeats=5))
    if suite in ("supersaw", "all", "quick"):
        for width in ((41,) if suite == "quick" else (0, 41, 64, 127)):
            for note in ((48,) if suite == "quick" else (48, 72)):
                result.append(case(f"supersaw-pw{width}-n{note}", "supersaw",
                                   "Resolve detuned clusters, center/side levels and beating across repeated phase realizations.",
                                   {"osc1_wave": 7, "osc1_pw": width}, note=note, gate=4000,
                                   repeats=1 if suite == "quick" else 3))
    if suite in ("aliasing", "all", "quick"):
        for wave in (("saw",) if suite == "quick" else ("saw", "square", "pulse")):
            for note in ((96,) if suite == "quick" else (60, 84, 108)):
                for fine in ((17,) if suite == "quick" else (-17, 0, 17)):
                    result.append(case(f"alias-{wave}-n{note}-f{fine:+d}", "aliasing",
                                       "Track nonharmonic components across register/fine tuning; separate aliases from noise and capture distortion.",
                                       {"osc1_wave": WAVES[wave], "osc1_fine": fine + 64, "osc1_pw": 96},
                                       note=note, gate=2000))
    return result


def vlq(value):
    result = [value & 127]
    while value > 127:
        value >>= 7
        result.insert(0, (value & 127) | 128)
    return bytes(result)


def make_midi(spec, channel=1):
    if not 1 <= channel <= 16:
        raise ValueError("MIDI channel must be 1–16")
    cc = 0xB0 + channel - 1
    events = [(0, bytes((cc, number, value))) for number, value in
              ((120, 0), (123, 0), (121, 0), (64, 0), (66, 0), (1, 0),
               (7, 127), (10, 64), (11, 127))]
    events.append((0, bytes((0xE0 + channel - 1, 0, 64))))
    for note in spec["notes"]:
        if not (0 <= note["note"] <= 127 and 1 <= note["velocity"] <= 127
                and 0 <= note["on_ms"] < note["off_ms"] < spec["duration_ms"] - 100):
            raise ValueError("invalid capture note or gate")
        events += [(note["on_ms"], bytes((0x90 + channel - 1, note["note"], note["velocity"]))),
                   (note["off_ms"], bytes((0x80 + channel - 1, note["note"], 0)))]
    events += [(spec["duration_ms"] - 100, bytes((cc, 120, 0)))]
    # 1000 PPQ and 60 BPM make one tick exactly one millisecond.
    track = bytearray(b"\x00\xff\x51\x03\x0f\x42\x40")
    previous = 0
    for tick, message in sorted(events, key=lambda event: event[0]):
        track += vlq(tick - previous) + message
        previous = tick
    track += vlq(spec["duration_ms"] - previous) + b"\xff\x2f\x00"
    return (b"MThd" + struct.pack(">IHHH", 6, 0, 1, 1000)
            + b"MTrk" + struct.pack(">I", len(track)) + track)


def generate(output, suite="quick", renderer=None, init_syx=None, channel=1, device_id=16):
    output = Path(output)
    if output.exists():
        raise FileExistsError(f"output already exists; choose a new directory: {output}")
    if suite not in ("quick", "filter", "envelopes", "waveforms", "supersaw", "aliasing", "all"):
        raise ValueError("unknown capture suite")
    if not 1 <= channel <= 16 or not 16 <= device_id <= 23:
        raise ValueError("channel must be 1–16 and wire device ID 16–23")
    if init_syx is not None:
        original = Path(init_syx).read_bytes()
        origin = {"kind": "supplied-init", "filename": Path(init_syx).name,
                  "claim": "Caller-supplied complete INIT; original hardware provenance is not authenticated."}
    else:
        renderer = Path(renderer or ROOT / "build-fidelity/SeptumRenderMidi").resolve()
        with tempfile.TemporaryDirectory(prefix="septum-capture-init-") as temp:
            exported = Path(temp) / "init.syx"
            subprocess.run([str(renderer), "--write-init-patch", str(exported)], check=True,
                           capture_output=True, text=True)
            original = exported.read_bytes()
        origin = {"kind": "septum-init-export", "filename": renderer.name,
                  "executable_sha256": digest(renderer.read_bytes()),
                  "claim": "Exporter INIT derives from Roland Editor defaults; not a new hardware dump."}
    blocks = decode_syx(original)
    if bytes(blocks[0][:12]).decode("ascii").strip() != "INIT PATCH":
        raise ValueError("source patch must be named INIT PATCH")
    specs = fixtures(suite)
    files = {"original-init.syx": original}
    entries = []
    for spec in specs:
        syx, overrides = make_patch(blocks, spec, device_id)
        midi = make_midi(spec, channel)
        prefix = spec["id"]
        files[prefix + ".syx"] = syx
        files[prefix + ".mid"] = midi
        entries.append({**{key: value for key, value in spec.items() if key != "tone"},
                        "schema": SCHEMA, "patch": prefix + ".syx", "midi": prefix + ".mid",
                        "patch_sha256": digest(syx), "midi_sha256": digest(midi),
                        "original_init_sha256": digest(original), "overrides": overrides,
                        "channel": channel, "wire_device_id": device_id,
                        "analysis_start_ms": 750 if spec["suite"] in ("filter", "aliasing") else 500,
                        "capture": {"status": "not-recorded", "audio_file": None,
                                    "audio_sha256": None, "sample_rate": None,
                                    "hardware_serial": None, "system_dump_sha256": None}})
    manifest = {
        "schema": SCHEMA, "suite": suite, "fixture_count": len(entries),
        "total_midi_duration_seconds": sum(x["duration_ms"] for x in specs) / 1000,
        "initial_patch": {**origin, "path": "original-init.syx", "sha256": digest(original)},
        "generator_sha256": digest(Path(__file__).read_bytes()),
        "sources": {"parameter_map": "https://static.roland.com/assets/media/pdf/SH-201_MI.pdf#page=5",
                    "control_descriptions": "https://static.roland.com/assets/media/pdf/SH-201_OM.pdf#page=60",
                    "init_defaults": "https://static.roland.com/assets/media/dmg/SH201_Editor110_osx.dmg"},
        "system_requirements": {"receive_channel": channel, "wire_device_id": device_id,
                                "device_id_panel_display": device_id + 1,
                                "remote_keyboard": "OFF / DIRECT", "master_tune_hz": 440,
                                "master_key_shift": 0, "keyboard_octave": 0, "transpose": 0,
                                "patch_remain": "OFF", "master_level_raw": 100,
                                "external_input": "disconnected; no direct monitor signal",
                                "d_beam": "OFF", "host_effects": "OFF"},
        "protocol": [
            "This package writes no device or MIDI port. Load each fixture .syx into the temporary edit buffer using your MIDI librarian; do not write a user-bank slot.",
            "Use the device ID and receive channel above. Allow at least 20 ms between DT1 packets and 500 ms after the final packet before starting its separate .mid.",
            "Apply and record the system requirements; patch SysEx does not contain these system settings. All fixtures use SINGLE UPPER, key follow zero, neutral pitch and velocity modulation, with effects/drive/arp off.",
            "Record stereo line output as unprocessed 24-bit PCM at 96 kHz or higher when available; retain the actual interface rate and clock metadata. Avoid clipping by setting interface input gain once, then hold hardware VOLUME and interface gain fixed for a suite.",
            "Start audio capture before MIDI. MIDI has a 500 ms lead-in, explicit note-offs, pedal/controller reset at its beginning, and final All Sound Off only after the declared release observation window.",
            "Keep original captures untouched. Put measured onset/latency, capture gain, sample rate, hardware identity, system settings, source hashes and any clipping observations in a separate result manifest.",
            "Replay the same .syx and .mid in Septum with neutral system settings. Do not expect random noise, Super Saw phases or free oscillator phases to be sample-identical across runs; compare spectra and repeated-note distributions.",
            "The sparse matrix identifies calibration candidates; it is not a complete knob table. If a hardware segment exceeds the declared window, extend a new fixture rather than infer its endpoint from a truncated trace."],
        "software_replay_template": ["python3", "Tools/render_midi.py", "--renderer", "<SeptumRenderMidi>",
                                     "--syx", "<fixture.syx>", "--midi", "<fixture.mid>", "--output", "<new.wav>",
                                     "--channel", str(channel), "--sample-rate", "96000", "--master-level", "100",
                                     "--tempo-policy", "preserve-patch", "--tail", "0", "--strict"],
        "fixtures": entries}
    files["manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    # Validate everything before creating output; mkdir plus exclusive files
    # makes both accidental reuse and races fail instead of replacing data.
    output.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        with (output / name).open("xb") as stream:
            stream.write(data)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--suite", choices=("quick", "filter", "envelopes", "waveforms", "supersaw", "aliasing", "all"), default="quick")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--renderer", type=Path, help="SeptumRenderMidi exporter; default build-fidelity/SeptumRenderMidi")
    source.add_argument("--init-syx", type=Path, help="complete caller-supplied INIT PATCH; provenance recorded as unauthenticated")
    parser.add_argument("--channel", type=int, default=1)
    parser.add_argument("--device-id", type=int, default=16, help="decimal wire device ID 16–23; hardware panel displays 17–24")
    args = parser.parse_args(argv)
    try:
        manifest = generate(args.output, args.suite, args.renderer, args.init_syx, args.channel, args.device_id)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"generate_timbre_capture: {error}\n")
    print(json.dumps({"output": str(args.output), "fixtures": manifest["fixture_count"],
                      "midi_seconds": manifest["total_midi_duration_seconds"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
