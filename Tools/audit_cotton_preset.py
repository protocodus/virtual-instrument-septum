#!/usr/bin/env python3
"""Independently verify the Cotton Wool benchmark against Roland's PAD bank.

Downloads nothing. Rebuilds a small native decoder directly from the current
shipping codec sources; stores hashes and factual parameter values, not banks.
The source MIDI and the exact patch revision used for the MP3 remain unknown.
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SIZES = [33, 64, 64, 5, 10, 8] + [66] * 16
FIELDS = []


def field(path, block, offset, conversion="identity", labels=None, width=1):
    FIELDS.append(dict(path=path, block=block, offset=offset, width=width,
                       conversion=conversion, labels=labels))


field("name", 0, 0, "ASCII, trailing spaces removed", width=12)
for path, offset, conversion, labels, width in [
    ("patchLevel", 12, "identity", None, 1),
    ("toneBalance", 13, "raw - 64", None, 1),
    ("tempo", 14, "three big-endian nibbles, BPM", None, 3),
    ("keyboardMode", 17, "enum", ["SINGLE", "DUAL", "SPLIT"], 1),
    ("keyboardPart", 18, "enum", ["UPPER", "LOWER"], 1),
    ("splitPoint", 19, "MIDI note number", None, 1),
    ("arpeggio.splitArpeggio", 20, "enum", ["UPPER", "LOWER", "BOTH"], 1),
    ("modulationDestination", 21, "enum", ["UPPER", "LOWER", "BOTH"], 1),
    ("dBeamDestination", 22, "enum", ["UPPER", "LOWER", "BOTH"], 1),
    ("pitchBendDestination", 23, "enum", ["UPPER", "LOWER", "BOTH"], 1),
    ("expressionDestination", 24, "enum", ["UPPER", "LOWER", "BOTH"], 1),
    ("activeExpression", 25, "boolean", ["OFF", "ON"], 1),
    ("arpeggio.on", 26, "boolean", ["OFF", "ON"], 1),
    ("arpeggio.hold", 27, "boolean", ["OFF", "ON"], 1),
    ("delayOn", 28, "boolean", ["OFF", "ON"], 1),
    ("reverbOn", 29, "boolean", ["OFF", "ON"], 1),
    ("modulationAssign", 30, "enum", ["OSC1+2", "OSC1", "OSC2", "PW1", "PW2", "FILTER", "AMP", "AUDIO FILTER"], 1),
    ("dBeamAssign", 31, "enum; stored, D Beam not modeled", None, 1),
    ("dBeamPolarity", 32, "enum", ["PLUS", "MINUS"], 1),
]:
    field(path, 0, offset, conversion, labels, width)

for block, tone in [(1, "upper"), (2, "lower")]:
    for osc, base in [("osc1", 0), ("osc2", 6)]:
        for path, offset, conversion, labels in [
            ("wave", 0, "enum", ["SAW", "SQUARE", "PULSE SQUARE", "TRIANGLE", "SINE", "NOISE", "FB OSC", "SUPER SAW", "EXT IN"]),
            ("pitchWide", 1, "boolean", ["OFF", "ON"]),
            ("coarse", 2, "WIDE off: round((raw-64)/3); WIDE on: raw-64 semitones", None),
            ("fine", 3, "raw - 64 cents", None),
            ("pulseWidth", 4, "PW / feedback / Super Saw spread, by waveform", None),
            ("pitchEnvDepth", 5, "raw - 64", None),
        ]:
            field(f"{tone}.{osc}.{path}", block, base + offset, conversion, labels)
    tone_paths = [
        ("pitchEnvAttack", 12), ("pitchEnvDecay", 13), ("mixType", 14),
        ("balance", 15), ("lowFreq", 16), ("filterType", 17),
        ("filterSlope", 18), ("cutoff", 19), ("keyFollow", 20),
        ("cutoffVelocitySens", 21), ("resonance", 22),
        ("filterEnvAttack", 23), ("filterEnvDecay", 24),
        ("filterEnvSustain", 25), ("filterEnvRelease", 26),
        ("filterEnvDepth", 27), ("overdrive", 28), ("drive", 29),
        ("level", 30), ("levelVelocitySens", 31), ("pan", 32),
        ("ampEnvAttack", 33), ("ampEnvDecay", 34),
        ("ampEnvSustain", 35), ("ampEnvRelease", 36),
        ("delayDepth", 37), ("reverbDepth", 38),
        ("bendRange", 59), ("octaveShift", 60),
        ("portamento", 61), ("portamentoTime", 62), ("mono", 63),
    ]
    signed = {"balance", "cutoffVelocitySens", "filterEnvDepth", "levelVelocitySens", "pan", "octaveShift"}
    enums = {"mixType": ["MIX", "SYNC", "RING"], "lowFreq": ["FLAT", "BOOST", "CUT"],
             "filterType": ["BYPASS", "LPF", "HPF", "BPF"], "filterSlope": ["12 dB/oct", "24 dB/oct"],
             "overdrive": ["OFF", "ON"], "portamento": ["OFF", "ON"],
             "mono": ["POLY", "SOLO LEGATO", "SOLO"]}
    for path, offset in tone_paths:
        conversion = "raw - 64" if path in signed else "identity"
        if path == "keyFollow": conversion = "(raw - 64) × 10 percent"
        if path in enums: conversion = "enum"
        field(f"{tone}.{path}", block, offset, conversion, enums.get(path))
    for lfo, base in [("lfo1", 39), ("lfo2", 49)]:
        for offset, path in enumerate(["shape", "rate", "tempoSync", "tempoSyncNote", "fadeTime", "keyTrigger", "destination1", "depth1", "destination2", "depth2"]):
            labels = {"shape": ["TRIANGLE", "SINE", "SAW", "SQUARE", "TRAPEZOID", "SAMPLE HOLD", "RANDOM"],
                      "tempoSync": ["OFF", "ON"], "keyTrigger": ["OFF", "ON"],
                      "destination1": ["OSC1 PITCH", "OSC1 PW", "FILTER", "AUDIO FILTER"],
                      "destination2": ["OSC2 PITCH", "OSC2 PW", "AMP"]}.get(path)
            conversion = "raw - 64" if path.startswith("depth") else "enum" if labels else "identity / documented table index"
            field(f"{tone}.{lfo}.{path}", block, base + offset, conversion, labels)

for offset, path in enumerate(["time", "feedback", "hfDamp", "modulationRate", "modulationDepth"]):
    conversion = "(raw - 49) × 2 percent" if path == "feedback" else "documented frequency index" if path == "hfDamp" else "identity"
    field(f"delay.{path}", 3, offset, conversion)
for offset, path in enumerate(["time", "preDelay", "size", "highCut", "density", "diffusion", "lfDampFrequency", "lfDampGain", "hfDampFrequency", "hfDampGain"]):
    conversion = "raw - 36 dB" if path.endswith("Gain") else "documented table index" if path in ["preDelay", "highCut", "lfDampFrequency", "hfDampFrequency"] else "displayed as native + 1" if path == "size" else "identity"
    field(f"reverb.{path}", 4, offset, conversion)
for offset, path in enumerate(["grid", "duration", "motif", "octaveRange", "accent", "velocity"]):
    field(f"arpeggio.{path}", 5, offset, "raw - 64" if path == "octaveRange" else "identity / documented enum")
field("arpeggio.style.endStep", 5, 6, "two big-endian nibbles", width=2)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def independent_first_patch(bank):
    require(bank[:20] == b"SH2LibrarianFile0000", "Not an SH-201 librarian bank")
    require(struct.unpack_from(">I", bank, 32)[0] == 100, "Expected the official 100-patch PAD bank")
    end = 164 + struct.unpack_from(">I", bank, 160)[0]
    require(end <= len(bank), "Truncated first record")
    pos, blocks = 164, []
    for size in SIZES:
        require(pos + 4 <= end, "Truncated block header")
        n = struct.unpack_from(">I", bank, pos)[0]
        pos += 4
        require(n == size and pos + n <= end, "Unexpected SHL block size")
        blocks.append(bank[pos:pos+n])
        require(max(blocks[-1]) < 128, "Non-MIDI parameter byte")
        pos += n
    require(blocks[0][:12].decode("ascii").rstrip() == "Cotton Wool", "PAD patch 1 is not Cotton Wool")
    return blocks


def frame(blocks):
    out = bytearray()
    for number, payload in enumerate(blocks):
        addressed = bytes([16, 0, number, 0]) + payload
        out += bytes([240, 65, 16, 0, 0, 22, 18]) + addressed
        out += bytes([(-sum(addressed)) & 127, 247])
    return bytes(out)


def parse_frames(data):
    blocks, pos = [], 0
    for number, size in enumerate(SIZES):
        packet = data[pos:pos + size + 13]
        require(len(packet) == size + 13, "Incomplete DT1 frame")
        require(packet[:11] == bytes([240,65,16,0,0,22,18,16,0,number,0]) and packet[-1] == 247, "Unexpected DT1 framing/order/address")
        require(sum(packet[7:-1]) % 128 == 0, "DT1 checksum mismatch")
        blocks.append(packet[11:-2])
        pos += len(packet)
    require(pos == len(data), "Extra bytes or packets after full patch")
    return blocks


def utility_source():
    lines = ['#include "DSP/SeptumSysEx.h"', '#include <fstream>', '#include <iomanip>', '#include <iostream>',
             '#include <iterator>', 'int main(int argc,char** argv) {',
             'if(argc!=3) return 2; std::ifstream in(argv[1],std::ios::binary);',
             'std::vector<std::uint8_t> b((std::istreambuf_iterator<char>(in)),{});',
             'std::vector<septum::NamedPatch> patches;',
             'if(!septum::sysex::parseSyxBankFile(b.data(),b.size(),patches)||patches.size()!=1) return 3;',
             'const auto& p=patches.front().patch; std::cout << "{";']
    for i, f in enumerate(FIELDS):
        value = f'std::quoted(p.{f["path"]})' if f["path"] == "name" else f'static_cast<long long>(p.{f["path"]})'
        prefix = ("," if i else "") + json.dumps(f["path"]) + ":"
        lines.append(f'std::cout << {json.dumps(prefix)} << {value};')
    lines += ['std::cout << "}\\n";',
              'const auto encoded=septum::sysex::encodePatchToSyxBuffer(p);',
              'std::ofstream out(argv[2],std::ios::binary); out.write(reinterpret_cast<const char*>(encoded.data()),encoded.size());',
              'return out ? 0 : 4; }']
    return "\n".join(lines) + "\n"


def read_native(executable, syx, roundtrip):
    result = subprocess.run([str(executable), str(syx), str(roundtrip)], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def value_text(row):
    value = row["native_value"]
    label = row.get("display_label")
    return f"{value} ({label})" if label is not None else str(value)


def report_markdown(report):
    identity = report["identity"]
    lines = ["# Cotton Wool preset verification", "",
             "The current comparison uses **the same published Cotton Wool preset** as patch 1 of Roland’s official PAD bank. All 22 blocks and 1,240 parameter bytes match. A freshly compiled native decoder returns the same values for the published and benchmark files, and native export reproduces the entire original SysEx exactly.", "",
             "This does **not** prove that the MP3 used precisely this edit revision, nor that the reconstruction reproduces the original note lengths, velocities, controller movements, or system settings. Roland associates the audio and downloadable preset by name; original performance MIDI and an authenticated recorded patch dump are unavailable.", "",
             f"Official [PAD page]({report['sources']['page_url']}), [bank download]({report['sources']['bank_url']}), [Cotton Wool recording]({report['sources']['audio_url']}). Parameter addresses and enum values follow the [Roland MIDI Implementation](https://static.roland.com/assets/media/pdf/SH-201_MI.pdf), pp. 3–5.", "",
             "## Identity and method", "",
             "The audit independently reads the first SHL record, validates every block size, constructs DT1 frames, checks the benchmark framing/checksums, and compares their payloads. It does not import the benchmark’s extraction module. Its native utility compiles `SeptumSysEx.cpp` and `SeptumPresets.cpp` directly from the current source; no previously built DSP archive is used. Source, utility, input, and output hashes are recorded in the companion JSON.", "",
             "| Object | SHA-256 |", "|---|---|",
             f"| Official PAD ZIP | `{report['sources']['zip_sha256']}` |",
             f"| Official 100_PAD.shl | `{report['sources']['shl_sha256']}` |",
             f"| Independent extraction = benchmark = native export | `{identity['sysex_sha256']}` |",
             f"| Concatenated 22 block payloads, in address order | `{identity['payload_sha256']}` |",
             f"| Native parameter JSON, sorted compact encoding | `{identity['native_fields_sha256']}` |", "",
             f"Benchmark: `{report['benchmark']['directory']}`. The recorded render manifest’s SysEx hash also matches. The manifest’s initial patch summary is checked against native fields; all {report['benchmark']['summary_fields_checked']} available entries agree.", "",
             "## Active path and envelope implications", "",
             "SINGLE / UPPER is selected. The lower tone is stored and verified but does not sound in this replay. Upper OSC1 is Super Saw, spread 41; OSC2 is sine, fine −7 cents; their balance is 0. OSC2’s received coarse byte is 28 (signed −36), with WIDE off; the current decoder interprets it as **−12 physical semitones**. The original byte remains unchanged. The one-octave endpoint interpretation is corroborated by the recording; interior WIDE-off rounding remains an empirical model choice.", "",
             "Upper FILTER is LPF, 24 dB/oct, cutoff 0, resonance 0, key follow +60%, cutoff velocity sensitivity +18, envelope A/D/S/R = **10/58/87/105**, depth **+39**. AMP A/D/S/R = **0/0/127/39**; its level is **70**, and amp velocity sensitivity is **0**. Both effects switches are on, but the active tone’s delay send is **0**; its reverb send is **35**. All four upper LFO modulation depths are **0**. The envelopes and reverb can produce an overlapping tail; the reconstruction’s note-off times affect filter and amp release. Raw ADSR values are controller units, not milliseconds, and do not validate the modeled time or depth curves.", "",
             "The replay uses velocity 100 throughout and no controller events. That is a declared reconstruction choice, not a measured hardware velocity. Because filter velocity sensitivity is +18, equal raw preset values do not imply equal cutoff trajectories if the original velocities differed. The note gates are also reconstructed; matching their original values is especially important with filter release 105.", "",
             "## Complete common, tone, effect, and arpeggio-common values", "",
             "Every row matches the official SHL and benchmark. `Raw` means received decimal wire bytes, before signed or enum conversion. `Native` is printed by the newly compiled shipping decoder. Table indexes are retained as indexes, not represented as a measured physical response. Sixteen inactive arpeggio pattern blocks are checked byte-for-byte and hashed separately in the JSON; they are omitted from this readable table.", ""]
    for title, blockset in [("Common", {0}), ("Upper — active", {1}), ("Lower — stored, inactive", {2}), ("Delay and reverb", {3,4}), ("Arpeggio — off", {5})]:
        lines += [f"### {title}", "", "| Parameter | Address | Raw | Native | Conversion |", "|---|---|---|---|---|"]
        for row in report["fields"]:
            if row["block"] not in blockset:
                continue
            lines.append(f"| `{row['path']}` | `{row['address']}` | {', '.join(map(str,row['raw_bytes']))} | {value_text(row)} | {row['conversion']} |")
        lines.append("")
    lines += ["## What this resolves", "",
              "There is no detected wrong-bank selection, altered Cotton Wool preset byte, dropped tone/effect block, cutoff sign error, or manifest/native decode disagreement in the current comparison. WIDE coarse conversion is deliberate and canonical export is byte-identical for this patch. This audit verifies data identity and current interpretation; it does not establish that Septum’s filter, envelopes, oscillators, or effects reproduce the SH-201 DSP.", "",
              "MASTER level, global tuning/transpose, output path, and live controllers are not carried in these 22 patch blocks. The renderer’s master level is 100; the hardware recording’s corresponding setting is unknown. The full MIDI provenance and replay settings are retained in the companion JSON.", "",
              "Reproduce locally with the already downloaded official ZIP:", "", "```sh",
              "python3 Tools/audit_cotton_preset.py \\",
              "  --bank /tmp/septum-hw-benchmark/research-official/SH-201_Patch_PAD.zip \\",
              "  --benchmark build-fidelity/hardware-benchmark/brightness-investigation/production-after/cotton-wool",
              "```", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank", type=Path, required=True)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "Docs/fidelity/source-audits/cotton-preset-verification.json")
    parser.add_argument("--cxx", default="c++")
    args = parser.parse_args()
    catalog = json.loads((ROOT / "Docs/fidelity/hardware-reference-catalog.json").read_text())
    source = next(b for b in catalog["banks"] if b["id"] == "pad")
    archive_data = args.bank.read_bytes()
    require(sha(archive_data) == source["sha256"], "Official ZIP hash disagrees with catalog")
    with zipfile.ZipFile(args.bank) as archive:
        bank = archive.read(source["archive_member"])
    require(sha(bank) == source["bank_sha256"], "Official SHL hash disagrees with catalog")
    blocks = independent_first_patch(bank)
    independent = frame(blocks)
    benchmark_path = args.benchmark / "original-patch.syx"
    benchmark = benchmark_path.read_bytes()
    benchmark_blocks = parse_frames(benchmark)
    require(blocks == benchmark_blocks and independent == benchmark, "Published and benchmark patch differ")
    generated_source = utility_source()
    with tempfile.TemporaryDirectory(prefix="septum-cotton-preset-audit-") as temporary:
        work = Path(temporary)
        cpp, executable = work / "decode.cpp", work / "decode"
        cpp.write_text(generated_source)
        command = [args.cxx, "-std=c++20", "-O2", "-I", str(ROOT / "Source"), str(cpp), str(ROOT / "Source/DSP/SeptumSysEx.cpp"), str(ROOT / "Source/DSP/SeptumPresets.cpp"), "-o", str(executable)]
        subprocess.run(command, check=True, capture_output=True, text=True)
        extracted_path = work / "official.syx"
        extracted_path.write_bytes(independent)
        official_values = read_native(executable, extracted_path, work / "official-export.syx")
        values = read_native(executable, benchmark_path.resolve(), work / "benchmark-export.syx")
        require(values == official_values, "Native decoded values differ")
        require((work / "official-export.syx").read_bytes() == independent, "Native official re-export changed bytes")
        require((work / "benchmark-export.syx").read_bytes() == independent, "Native benchmark re-export changed bytes")
        utility_hash = sha(executable.read_bytes())
    rows = []
    for f in FIELDS:
        row = {k:v for k,v in f.items() if k != "labels"}
        row["address"] = f"10 00 {f['block']:02X} {f['offset']:02X}"
        row["raw_bytes"] = list(blocks[f["block"]][f["offset"]:f["offset"]+f["width"]])
        row["native_value"] = values[f["path"]]
        row["matches_official"] = True
        if f["labels"]:
            row["display_label"] = f["labels"][row["native_value"]]
        if f["path"].endswith(".coarse"):
            row["signed_raw"] = row["raw_bytes"][0] - 64
        rows.append(row)
    manifest_path = args.benchmark / "septum-raw.render.json"
    manifest = json.loads(manifest_path.read_text())
    require(manifest["inputs"]["sysex"]["sha256"] == sha(benchmark), "Render manifest identifies different SysEx")
    require(manifest["inputs"]["midi"]["sha256"] == sha((args.benchmark / "reconstructed-performance.mid").read_bytes()), "Render manifest identifies different reconstructed MIDI")
    replay_bytes = [bytes.fromhex(event["value"]) for event in manifest["replay_events"] if event["kind"] == "midi"]
    require(all((event[0] & 240) in (128, 144) for event in replay_bytes), "Replay has additional synthesis-affecting MIDI events")
    require({event[2] for event in replay_bytes if event[0] & 240 == 144 and event[2]} == {100}, "Note-on velocity differs from declared reconstruction")
    summary = manifest["output"]["initial_patch"]
    expected_summary = {"name":values["name"], "tempo":values["tempo"], "keyboard_mode":["single","dual","split"][values["keyboardMode"]], "single_part":["upper","lower"][values["keyboardPart"]], "split_point":values["splitPoint"], "patch_level":values["patchLevel"], "tone_balance":values["toneBalance"], "arpeggio_on":bool(values["arpeggio.on"]), "delay_on":bool(values["delayOn"]), "reverb_on":bool(values["reverbOn"])}
    checked = len(expected_summary)
    for tone in ["upper", "lower"]:
        expected_summary[tone] = {key:values[f"{tone}.{path}"] for key,path in [("mono_mode","mono"),("octave_shift","octaveShift"),("level","level"),("level_velocity_sensitivity","levelVelocitySens"),("cutoff_velocity_sensitivity","cutoffVelocitySens"),("oscillator_balance","balance")]}
        checked += len(expected_summary[tone])
        for osc in ["osc1", "osc2"]:
            expected_summary[tone][osc] = {key:values[f"{tone}.{osc}.{path}"] for key,path in [("wave","wave"),("pitch_wide","pitchWide"),("coarse_semitones","coarse"),("fine_cents","fine"),("pw_feedback","pulseWidth")]}
            checked += len(expected_summary[tone][osc])
    require(summary == expected_summary, "Render manifest initial parameters disagree with fresh native decoding")
    comparison_path = args.benchmark / "comparison.json"
    comparison = json.loads(comparison_path.read_text())
    source_paths = ["Source/DSP/SeptumSysEx.cpp", "Source/DSP/SeptumSysEx.h", "Source/DSP/SeptumPresets.cpp", "Source/DSP/SeptumPresets.h", "Source/DSP/SeptumPatch.h"]
    report = dict(schema_version=1, claim="Same published preset and current native decoded values verified; exact recorded patch revision and original performance remain unverified.",
        sources=dict(page_url=source["source_page_url"],bank_url=source["url"],audio_url="https://www.rolandus.com/go/sh-201_patches/mp3/PAD/TOP8_Cotton_Wool.mp3",zip_sha256=sha(archive_data),archive_member=source["archive_member"],shl_sha256=sha(bank),patch_number=1),
        identity=dict(sysex_sha256=sha(independent),sysex_size=len(independent),payload_sha256=sha(b"".join(blocks)),parameter_bytes=sum(SIZES),blocks_checked=len(blocks),native_export_byte_identical=True,native_fields_sha256=sha(json.dumps(values,sort_keys=True,separators=(",",":")).encode()),native_fields_checked=len(FIELDS),all_fields_match=True),
        native_utility=dict(source_sha256=sha(generated_source.encode()),executable_sha256=utility_hash,compiler=subprocess.run([args.cxx,"--version"],check=True,capture_output=True,text=True).stdout.splitlines()[0],compile_command=[s.replace(str(ROOT),"REPO").replace(temporary,"SCRATCH") for s in command],sources={p:sha((ROOT/p).read_bytes()) for p in source_paths}),
        benchmark=dict(directory=str(args.benchmark),sysex_path=str(benchmark_path),manifest_sha256=sha(manifest_path.read_bytes()),summary_fields_checked=checked,initial_patch_summary=summary,settings=manifest["settings"],midi=manifest["midi"],replay_event_counts=manifest["replay_event_counts"],note_on_velocities=[100],controller_events_present=False,inputs=manifest["inputs"],output_audio=manifest["output"],comparison_metadata=comparison),
        block_identity=[dict(block=i,address=f"10 00 {i:02X} 00",size=len(b),sha256=sha(b),matches_official=True) for i,b in enumerate(blocks)],fields=rows,
        limitations=["Published name/category association does not authenticate the exact recorded patch revision.","No original performance MIDI: notes, gates, and velocity100 are reconstructed, not original values.","Live controller moves and hardware system/output settings are undocumented.","Byte and decoder identity do not establish the accuracy of DSP parameter-to-sound curves.","Native WIDE-off coarse decoding is deliberate; the one-octave Cotton endpoint is supported by recordings, interior rounding remains provisional."])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    args.output.with_suffix(".md").write_text(report_markdown(report))
    print(json.dumps(report["identity"],indent=2))


if __name__ == "__main__":
    main()
