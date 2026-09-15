#!/usr/bin/env python3
"""Replay all frozen reverb-gain cases through freshly built shipping DSP.

This is a provenance/PCM integration check, not another hardware score fit.
Build and run CTest separately; their receipts accompany the render result.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import numpy as np
from scipy.io import wavfile

ROOT = Path(__file__).resolve().parents[1]
REVISION = "b0f6c03"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")


def check_source():
    files = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", REVISION, "Source/DSP"], cwd=ROOT, text=True).splitlines()
    files.append("Tools/RenderMidi.cpp")
    hashes, deltas = {}, []
    for name in files:
        previous = subprocess.check_output(["git", "show", f"{REVISION}:{name}"], cwd=ROOT)
        current = (ROOT/name).read_bytes()
        hashes[name] = sha(ROOT/name)
        if previous == current:
            continue
        if name != "Source/DSP/SeptumEngine.h":
            raise ValueError("Unexpected DSP/renderer source change: "+name)
        def uncomment(value):
            return re.sub(r"\s+", "", re.sub(r"//[^\n]*|/\*[\s\S]*?\*/", "", value))
        old = previous.decode()
        new = current.decode()
        if new.count("reverbWetReturn = 0.4;") != 1:
            raise ValueError("Missing sole intended return correction")
        restored = new.replace("reverbWetReturn = 0.4;", "reverbWetReturn = 0.8;")
        if uncomment(restored) != uncomment(old):
            raise ValueError("Unexpected semantic header changes beyond return constant")
        deltas.append(name)
    if deltas != ["Source/DSP/SeptumEngine.h"]:
        raise ValueError("Unexpected source difference set")
    return dict(reference_revision=REVISION, current_sha256=hashes, changed_files=deltas,
                check="All DSP and native renderer files equal frozen reference bytes except header; after removing comments/whitespace and restoring reverbWetReturn0.4→0.8, header is identical.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--renderer", type=Path, required=True)
    parser.add_argument("--legacy-run", type=Path, required=True)
    parser.add_argument("--new-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    renderer = args.renderer.resolve()
    source = check_source()
    renderer_hash = sha(renderer)
    wrapper = ROOT/"Tools/render_midi.py"
    protocol = dict(status="shipping_half_return_integration_check_not_hardware_equivalence",
                    source=source, renderer=dict(path=str(renderer), sha256=renderer_hash), wrapper_sha256=sha(wrapper),
                    preservation="Complete original SysEx and frozen reconstructed MIDI copied unchanged; exact source receipt sample rate/tail/master/channel/tempo policy replayed; no audio alignment, gain, crop or normalization.",
                    candidate_arithmetic="Frozen candidate scales wet double by0.5 before its original0.8 return multiplication; shipping uses0.4 at the original return multiply. Full PCM equality is tested, not assumed.",
                    source_results={}, cases=[])
    jobs = []
    for cohort, directory, expected_count in (("legacy", args.legacy_run.resolve(), 10), ("prospective", args.new_run.resolve(), 12)):
        result_path = directory/"results.json"
        result = json.loads(result_path.read_text())
        if len(result["cases"]) != expected_count:
            raise ValueError("Changed frozen scenario count")
        protocol["source_results"][cohort] = dict(path=str(result_path), sha256=sha(result_path))
        for case in result["cases"]:
            name = case["id"]
            candidate = directory/"cases"/name/"gain-0.5.wav"
            previous = directory/"cases"/name/"gain-1.wav"
            candidate_meta = case["models"]["gain-0.5"]
            previous_meta = case["models"]["gain-1"]
            audio_key = "raw_sha256" if cohort == "legacy" else "wav_sha256"
            receipt_path = candidate.with_suffix(".render.json")
            if sha(candidate) != candidate_meta[audio_key] or sha(previous) != previous_meta[audio_key] or sha(receipt_path) != candidate_meta["receipt_sha256"]:
                raise ValueError("Frozen audio/receipt pin changed: "+name)
            receipt = json.loads(receipt_path.read_text())
            inputs_dir = directory/("cases" if cohort == "legacy" else "baseline-corpus")/name
            dst = out/cohort/name
            dst.mkdir(parents=True)
            for filename, key in (("original-patch.syx", "sysex"), ("reconstructed-performance.mid", "midi")):
                src = inputs_dir/filename
                if sha(src) != receipt["inputs"][key]["sha256"]:
                    raise ValueError("Frozen input changed: "+name)
                shutil.copyfile(src, dst/filename)
            settings = receipt["settings"]
            if settings["automatic_note_offs_at_end"] or settings["unsupported_policy"] != "reject" or settings["program_bank_policy"] != "reject":
                raise ValueError("Unexpected replay policy")
            wav = dst/"shipping.wav"
            command = [sys.executable, str(wrapper), "--renderer", str(renderer),
                       "--midi", str(dst/"reconstructed-performance.mid"), "--syx", str(dst/"original-patch.syx"),
                       "--output", str(wav), "--sample-rate", str(settings["sample_rate"]), "--tail", str(settings["tail_seconds"]),
                       "--master-level", str(settings["master_level"]), "--channel", str(settings["midi_channel"]),
                       "--tempo-policy", settings["tempo_policy"]]
            protocol["cases"].append(dict(cohort=cohort, id=name, candidate_sha256=sha(candidate), baseline_sha256=sha(previous),
                                          candidate_receipt_sha256=sha(receipt_path), input_sha256={key:receipt["inputs"][key]["sha256"] for key in ("midi", "sysex")},
                                          settings=settings, command=command))
            jobs.append((cohort, name, candidate, previous, receipt, wav, command))
    save(out/"protocol-before-rendering.json", protocol)
    results = []
    for cohort, name, candidate, previous, receipt, wav, command in jobs:
        start = time.monotonic()
        process = subprocess.run(command, check=True, capture_output=True, text=True)
        wav.with_suffix(".stdout.log").write_text(process.stdout+process.stderr)
        current = json.loads(wav.with_suffix(".render.json").read_text())
        if current["inputs"]["renderer"]["sha256"] != renderer_hash:
            raise ValueError("Fresh renderer identity changed")
        for key in ("settings", "midi", "replay_event_counts", "replay_events", "ignored_events", "degraded_replay"):
            if current[key] != receipt[key]:
                raise ValueError("Replay semantics changed: "+name+"/"+key)
        for key in ("frames", "sample_rate", "latency_samples", "master_level", "initial_patch", "patch_tempo_at_end", "clock_tempo_at_end", "patch_load_warning"):
            if current["output"][key] != receipt["output"][key]:
                raise ValueError("Output/input settings changed: "+name+"/"+key)
        for key in ("midi", "sysex"):
            if current["inputs"][key]["sha256"] != receipt["inputs"][key]["sha256"]:
                raise ValueError("Fresh replay input changed")
        sr, y = wavfile.read(wav)
        cr, c = wavfile.read(candidate)
        pr, p = wavfile.read(previous)
        if sr != cr or sr != pr or y.shape != c.shape or y.shape != p.shape or y.dtype != np.float32:
            raise ValueError("Unexpected complete render dimensions")
        if not np.isfinite(y).all() or abs(y).max() >= 1 or current["output"]["active_voices_at_end"] != 0 or current["ignored_events"]:
            raise ValueError("Invalid complete fresh render")
        delta = y.astype(float)-c.astype(float)
        row = dict(cohort=cohort, id=name, wav_sha256=sha(wav), receipt_sha256=sha(wav.with_suffix(".render.json")),
                   candidate_wav_sha256=sha(candidate), baseline_wav_sha256=sha(previous),
                   byte_identical_to_candidate=sha(wav)==sha(candidate), pcm_identical_to_candidate=bool(np.array_equal(y, c)),
                   max_absolute_pcm_difference=float(abs(delta).max()), rms_pcm_difference=float(np.sqrt(np.mean(delta*delta))),
                   changed_float_samples=int(np.count_nonzero(delta)), frames=len(y), sample_rate=sr,
                   byte_identical_to_baseline=sha(wav)==sha(previous), frozen_candidate_identical_to_baseline=sha(candidate)==sha(previous),
                   finite=True, peak=float(abs(y).max()), samples_at_or_above_full_scale=0, active_voices_at_end=0,
                   preserved_settings=current["settings"], preserved_input_sha256={key:current["inputs"][key]["sha256"] for key in ("midi", "sysex")},
                   elapsed_seconds=time.monotonic()-start)
        results.append(row)
        save(out/"results-partial.json", dict(protocol=protocol, results=results))
        print(cohort, name, "byte-identical" if row["byte_identical_to_candidate"] else f"maxdiff={row['max_absolute_pcm_difference']:.9g}", flush=True)
    if check_source() != source or sha(renderer) != renderer_hash:
        raise ValueError("Source or binary changed during verification")
    unchanged = [r["id"] for r in results if r["cohort"] == "legacy" and r["frozen_candidate_identical_to_baseline"]]
    if len(unchanged) != 5:
        raise ValueError("Unexpected dry/zero-send control count")
    result = dict(protocol=protocol, tool_sha256=sha(__file__), results=results,
                  summary=dict(cases=len(results), all_candidate_wavs_byte_identical=all(r["byte_identical_to_candidate"] for r in results),
                               maximum_absolute_pcm_difference=max(r["max_absolute_pcm_difference"] for r in results),
                               unchanged_legacy_ids=unchanged,
                               unchanged_legacy_wavs_byte_identical=all(r["byte_identical_to_baseline"] for r in results if r["id"] in unchanged),
                               all_finite_unclipped_zero_active_voices=True), equivalence_status="not_established")
    save(out/"results.json", result)
    if not result["summary"]["all_candidate_wavs_byte_identical"]:
        raise SystemExit("PCM differences retained for arithmetic review; equivalence not assumed")


if __name__ == "__main__":
    main()
