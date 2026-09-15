#!/usr/bin/env python3
"""Replay frozen envelope candidates against unchanged public preset excerpts.

Candidates must be selected elsewhere using the declared training note. This
tool does not select or tune a model. It freezes each production-derived lag
and fits only a single gain on the first quarter of each recording.
"""
import argparse
import hashlib
import html
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np
from scipy.io import wavfile

import assess_hardware_equivalence as assess

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison-root", type=Path, required=True)
    parser.add_argument("--candidate", action="append", required=True, help="id=renderer_path")
    parser.add_argument("--selection-record", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    candidates = {}
    for text in args.candidate:
        name, renderer = text.split("=", 1)
        if not name or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-._" for c in name):
            parser.error("Candidate id must be a plain lowercase slug")
        if name in candidates or name == "production":
            parser.error("Duplicate or reserved candidate id")
        renderer = Path(renderer).resolve()
        manifest = renderer.parent / "manifest.json"
        metadata = json.loads(manifest.read_text())
        if sha(renderer) != metadata["renderer"]["sha256"]:
            raise ValueError("Renderer does not match its frozen build manifest")
        candidates[name] = {"renderer": str(renderer), "renderer_sha256": sha(renderer),
                            "build_manifest": str(manifest), "build_manifest_sha256": sha(manifest)}
    selected = {}
    for path in args.selection_record:
        selection = json.loads(path.read_text())
        name = selection["selection"]["candidate_id"]
        if name in selected:
            raise ValueError("Duplicate selection for candidate: " + name)
        selected[name] = selection["inputs"]["candidates"][name]["sha256"]
    if set(selected) != set(candidates):
        raise ValueError("Renderers must exactly match the frozen selected candidate ids")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    for path in (Path(__file__), ROOT / "Tools/render_midi.py", ROOT / "Tools/assess_hardware_equivalence.py"):
        shutil.copyfile(path, out / path.name)
    selections = []
    for i, path in enumerate(args.selection_record):
        shutil.copyfile(path, out / f"selection-{i}.json")
        selections.append({"path": str(path.resolve()), "sha256": sha(path)})
    save(out / "protocol.json", {"experimental": True, "acceptance": "not_established",
        "candidates": candidates, "selection_records": selections,
        "alignment": "Production only: envelope correlation over first25%, bounded50ms; shared by all candidates",
        "gain": "One RMS gain per complete candidate, first25% only; exact production gain as sensitivity",
        "evaluation": "Remaining75%, same sample coverage for all candidates; no frame crosses calibration boundary",
        "limitations": "Published same-name preset bytes unchanged; original performance MIDI and exact recorded patch revision unverified"})
    results, sections = [], []
    for comparison in sorted(args.comparison_root.glob("*/comparison.json")):
        source = comparison.parent
        meta = json.loads(comparison.read_text())
        case_id = meta["case"]["id"]
        target = out / case_id
        target.mkdir()
        files = ("hardware-excerpt-raw.wav", "septum-raw.wav", "original-patch.syx", "reconstructed-performance.mid")
        for name in files:
            if sha(source / name) != meta["files"][name]:
                raise ValueError("Baseline comparison input changed: " + str(source / name))
            shutil.copyfile(source / name, target / name)
        sr, h = assess.read_audio(target / "hardware-excerpt-raw.wav")
        bs, base = assess.read_audio(target / "septum-raw.wav")
        n = meta["comparison_frames"]
        if sr != 44100 or bs != sr or len(h) != n or len(base) < n:
            raise ValueError("Invalid baseline audio dimensions")
        base = base[:n]
        cal = round(n * .25)
        transform = assess.fit_transform(h, base, sr, cal, .05)
        lag = transform["candidate_lag_samples"]
        start, end = max(cal, cal-lag), min(n, n-lag)
        ca, cb = max(0, -lag), min(cal, cal-lag)
        sounds = {"production": base}
        record = {"id": case_id, "comparison_sha256": sha(comparison),
                  "inputs_sha256": {f: sha(source / f) for f in files},
                  "calibration": transform, "evaluation_samples": [start, end],
                  "qualification": meta["comparison_limits"], "models": {}}
        for name, item in candidates.items():
            wav = target / (name + ".wav")
            command = [sys.executable, str(out / "render_midi.py"), "--renderer", item["renderer"],
                       "--midi", str(target / "reconstructed-performance.mid"),
                       "--syx", str(target / "original-patch.syx"), "--output", str(wav),
                       "--tempo-policy", "preserve-patch"]
            subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
            cs, c = assess.read_audio(wav)
            receipt = json.loads(wav.with_suffix(".render.json").read_text())
            if cs != sr or c.shape[1] != h.shape[1] or len(c) < n or receipt["ignored_events"]:
                raise ValueError("Candidate replay differs from required audio/MIDI layout")
            if receipt["output"]["active_voices_at_end"] != 0:
                raise ValueError("Candidate has stuck voices")
            if case_id == "moogie-1" and sha(wav) != selected[name]:
                raise ValueError("Moogie output differs from the candidate used for selection")
            sounds[name] = c[:n]
            record["models"][name] = {"raw_sha256": sha(wav), "peak": float(abs(c).max()),
                "samples_at_or_above_full_scale": int(np.count_nonzero(abs(c) >= 1)),
                "identical_to_production": sha(wav) == sha(target / "septum-raw.wav"), "command": command}
        listening = {"hardware": h[start:end]}
        for name, c in sounds.items():
            gain = assess.rms(h[ca:cb]) / assess.rms(c[ca+lag:cb+lag])
            row = record["models"].setdefault(name, {})
            row.update({"training_gain": gain, "training_gain_db": 20*math.log10(gain),
                        "measurements": assess.measure(h[start:end], c[start+lag:end+lag]*gain, sr),
                        "fixed_production_gain": assess.measure(h[start:end],
                                c[start+lag:end+lag]*transform["candidate_gain"], sr)})
            listening[name] = c[start+lag:end+lag]*gain
        scale = min(.1 / assess.rms(listening["hardware"]),
                    .98 / max(float(abs(y).max()) for y in listening.values()))
        for name, y in listening.items():
            wavfile.write(target / (name + "-listen.wav"), sr, (y*scale).astype(np.float32))
        record["listening"] = {"segment": "held-out interval only", "common_gain": scale,
                               "candidate_gain": "the same training-only gain as measurements"}
        save(target / "result.json", record)
        results.append(record)
        players = "".join(f'<p>{html.escape(name)}<br><audio controls preload="none" src="{case_id}/{name}-listen.wav"></audio></p>'
                          for name in listening)
        sections.append(f'<section><h2>{html.escape(case_id)}</h2>{players}</section>')
        print(case_id + " " + " ".join(f'{k}:{v["measurements"]["summary"]["spectral_convergence_mean"]:.5f}'
                                      for k,v in record["models"].items()), flush=True)
    save(out / "results.json", {"acceptance": "not_established", "candidates": candidates,
                              "selection_records": selections, "cases": results})
    (out / "index.html").write_text('<!doctype html><meta charset="utf-8"><title>Envelope hypotheses</title>'
        '<style>body{font:16px system-ui;max-width:900px;margin:40px auto;padding:20px}section{border-top:1px solid #bbb;margin-top:32px}audio{width:100%}</style>'
        '<h1>Experimental envelope comparison</h1><p>Unchanged published presets; reconstructed performance MIDI. '
        'Timing is fixed from production; one training gain per file. Players contain only the evaluation interval. '
        'These hypotheses have not established hardware equivalence.</p>' + ''.join(sections))


if __name__ == "__main__":
    main()
