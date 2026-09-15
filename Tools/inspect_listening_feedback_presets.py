#!/usr/bin/env python3
"""Read exact frozen preset controls associated with the latest listening notes."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMES = {"vangelead": "Vangelead", "moogie-1": "Moogie 1", "dist-bs-1": "Dist Bs 1", "cotton-wool": "Cotton Wool"}
FIELDS = dict(lowFreq=(0x10, 0), filterType=(0x11, 0), filterSlope=(0x12, 0), cutoff=(0x13, 0),
    keyFollow=(0x14, 64), cutoffVelocitySens=(0x15, 64), resonance=(0x16, 0),
    filterEnvAttack=(0x17, 0), filterEnvDecay=(0x18, 0), filterEnvSustain=(0x19, 0),
    filterEnvRelease=(0x1a, 0), filterEnvDepth=(0x1b, 64), overdrive=(0x1c, 0), drive=(0x1d, 0),
    level=(0x1e, 0), levelVelocitySens=(0x1f, 64), pan=(0x20, 64), ampEnvAttack=(0x21, 0),
    ampEnvDecay=(0x22, 0), ampEnvSustain=(0x23, 0), ampEnvRelease=(0x24, 0), delayDepth=(0x25, 0), reverbDepth=(0x26, 0))


def pin(path):
    path = Path(path).resolve()
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inputs_path = ROOT/"Docs/fidelity/source-audits/saw-w4-official-inputs-2026-09-15.json"
    inventory_path = ROOT/"Docs/fidelity/source-audits/static-filter-reference-inventory-2026-09-15.json"
    if pin(inputs_path)["sha256"] != "9bf636d72ff15b00135258f5924798af9c2ecd81556534d485a0a0e4a700402e":
        raise ValueError("Frozen inputs changed")
    inputs = json.loads(inputs_path.read_text())
    inventory = json.loads(inventory_path.read_text())
    result = dict(status="read_only_exact_preset_feedback_context_no_fit_or_edits", tool=pin(__file__),
        inputs=pin(inputs_path), prior_native_decode_inventory=pin(inventory_path),
        decoding="Validate all22 Roland DT1 packets, checksum, addresses and seven-bit payload. Re-decode filter/AMP/level/drive/sends from raw tone offsets; compare with prior native decode. Signed fields subtract64, key-follow then multiplies10.",
        field_offsets={key:dict(hex_offset=hex(offset), signed_bias=bias) for key, (offset, bias) in FIELDS.items()},
        scope="Same published presets; exact recorded patch revisions and original performance remain unverified. Listening feedback is directional context, not parameter measurement.", cases=[])
    for name, title in NAMES.items():
        source = next(c for c in inputs["cases"] if c["id"] == name)
        prior = next(c for c in inventory["references"] if c["name"] == title)
        patch = source["source_files"]["original-patch.syx"]
        if pin(patch["path"]) != patch or patch["sha256"] != prior["unmodified_sysex_sha256"]:
            raise ValueError("Original published SysEx hash mismatch")
        blocks = []
        data = Path(patch["path"]).read_bytes()
        for index, packet in enumerate(data.split(b"\xf7")[:-1]):
            if packet[:7] != bytes.fromhex("f0411000001612") or packet[7:11] != bytes([16, 0, index, 0]) or sum(packet[7:]) % 128:
                raise ValueError("Invalid DT1 framing/address/checksum")
            block = packet[11:-1]
            if any(b > 127 for b in block):
                raise ValueError("Invalid MIDI payload")
            blocks.append(block)
        if len(blocks) != 22 or not data.endswith(b"\xf7") or len(blocks[1]) != 64 or len(blocks[2]) != 64:
            raise ValueError("Unexpected complete patch structure")
        row = dict(id=name, name=title, patch=patch, active_parts=prior["active_parts"],
            keyboard_mode=("single", "dual", "split")[prior["decoded"]["keyboardMode"]],
            patch_level=prior["decoded"]["patchLevel"], tone_balance=prior["decoded"]["toneBalance"],
            delay_on=bool(prior["decoded"]["delayOn"]), reverb_on=bool(prior["decoded"]["reverbOn"]),
            reconstructed_velocities=sorted({n["velocity"] for n in source["case"]["notes"]}), tones={})
        for part, index in (("upper", 1), ("lower", 2)):
            tone = {}
            for key, (offset, bias) in FIELDS.items():
                value = blocks[index][offset]-bias
                if key == "keyFollow":
                    value *= 10
                if value != prior["decoded"][part][key]:
                    raise ValueError("Raw/native mismatch: " + name + "/" + part + "/" + key)
                tone[key] = value
            tone["raw_block_hex"] = blocks[index].hex()
            tone["active"] = part in prior["active_parts"]
            tone["oscillators"] = {key: prior["decoded"][part][key] for key in ("osc1", "osc2")}
            tone["balance"] = blocks[index][0xf]-64
            tone["filter_lfo_depths"] = [blocks[index][offset+1]-64 if blocks[index][offset] == 2 else 0 for offset in (0x2d, 0x37)]
            row["tones"][part] = tone
        result["cases"].append(row)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(args.output)


if __name__ == "__main__":
    main()
