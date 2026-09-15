#!/usr/bin/env python3
"""Render a frozen W4 vector and audit its full-engine training prediction."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.io import wavfile
import build_saw_w4_experiment as engine


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pin(path):
    return {"path": str(Path(path).resolve()), "sha256": sha(path)}


def save(path, data):
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False)+"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--lp12-patch", type=Path, required=True)
    parser.add_argument("--lp24-patch", type=Path, required=True)
    parser.add_argument("--midi", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    selection = json.loads(args.selection.read_text())
    identity = selection["identity"]
    for path, key in ((args.build/"manifest.json", "build_manifest_sha256"),
                      (args.lp12_patch, "lp12_patch_sha256"), (args.lp24_patch, "lp24_patch_sha256"),
                      (args.midi, "midi_sha256"), (Path(engine.__file__), "builder_sha256")):
        if sha(path) != identity[key]:
            raise ValueError(f"Frozen fit input changed: {path}")
    coefficient = selection["candidate_coefficients"]
    if len(coefficient) != 32 or not np.isfinite(coefficient).all() or selection["canonical_phase_cycles"] != 0:
        raise ValueError("Invalid frozen source vector or canonical phase")
    manifest = {"selection": pin(args.selection), "tool": pin(__file__),
                "builder": pin(engine.__file__), "build": pin(args.build/"manifest.json"),
                "scope": "same selected vector; complete dry MIDI and fitted-phase linearity audit",
                "status": "rendering", "hardware_equivalence": "not_established"}
    save(out/"manifest.json", manifest)
    jobs = [("lp12", args.lp12_patch, 0.0), ("lp24", args.lp24_patch, 0.0),
            ("training-phase", args.lp12_patch, selection["best"]["phase_cycles"])]

    def render(job):
        name, patch, phase = job
        wave = engine.render_source(args.build, patch, args.midi, coefficient, phase=phase,
                                    output_dir=out/name, phase_note=91, tail=2.0)
        return name, Path(wave)

    with ThreadPoolExecutor(max_workers=2) as pool:
        rendered = dict(pool.map(render, jobs))
    rate, raw = wavfile.read(rendered["training-phase"])
    if rate != 44100 or raw.dtype != np.float32 or raw.ndim != 2 or raw.shape[1] != 2:
        raise ValueError("Unexpected independently rendered training format")
    if not np.isfinite(raw).all():
        raise ValueError("Nonfinite independent training output")
    first, last = selection["protocol"]["engine_samples"]
    gain = selection["protocol"]["fixed_gain"]
    dc = selection["best"]["output_dc"]
    prediction_path = args.selection.parent/"fit/best-prediction.npy"
    prediction = np.load(prediction_path)
    search = json.loads((args.selection.parent/"fit/search.json").read_text())
    if sha(prediction_path) != search["prediction_sha256"]:
        raise ValueError("Stored training prediction changed")
    actual = gain*raw[first:last, 0].astype(float)+dc
    hrate, hardware = wavfile.read(args.selection.parent/"hardware-lp12.wav")
    x0, x1 = selection["protocol"]["hardware_samples"]
    target = hardware[x0:x1].astype(float)
    if hrate != 44100 or target.shape != prediction.shape or actual.shape != prediction.shape:
        raise ValueError("Training audit support changed")
    if hashlib.sha256(target.astype("<f8").tobytes()).hexdigest() != search["target_float64_sha256"]:
        raise ValueError("Original training PCM changed")
    stats = {name: json.loads(wave.with_name("state-stats.json").read_text()) for name, wave in rendered.items()}
    relative_rms = float(np.sqrt(np.mean((actual-prediction)**2)/np.var(target)))
    max_error = float(np.max(np.abs(actual-prediction)))
    limit_free = not any(row["filter_limit_calls"] or row["output_limit_calls"] for row in stats.values())
    audit = {"prediction": pin(prediction_path), "independent_training_wav": pin(rendered["training-phase"]),
             "linear_prediction_relative_error_power": selection["best"]["relative_error_power"],
             "actual_engine_relative_error_power": float(np.mean((target-actual)**2)/np.var(target)),
             "actual_vs_linear_relative_rms": relative_rms, "actual_vs_linear_max_absolute": max_error,
             "states": stats, "all_dry_renders_limit_free": limit_free,
             "linear_prediction_confirmed": bool(limit_free and relative_rms < 1e-6 and max_error < gain*2e-6),
             "interpretation": "Actual canonical audio remains the benchmark; nonlinear prediction failures are retained, never hidden."}
    save(out/"training-prediction-audit.json", audit)
    manifest.update(status="complete", renders={name: pin(wave) for name, wave in rendered.items()},
                    training_prediction_audit=pin(out/"training-prediction-audit.json"))
    save(out/"manifest.json", manifest)
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
