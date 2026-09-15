#!/usr/bin/env python3
"""Fit one unit-ramp W4 source through the frozen complete-engine operator.

The operator, phase-search controls and full-performance comparisons are
separate evidence. No downstream filter, gain, recipe or event timing is fit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
import numpy as np
from scipy.io import wavfile
from scipy.optimize import minimize_scalar

SAMPLES = 3528
COEFFICIENTS = 32
CONDITION_LIMIT = 1e6
PHASE_GRID = 256
PHASE_BASINS = 16
PHASE_XATOL = 1e-10


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def protocol():
    return {
        "family": "unit ramp + independent negative16/positive16 W4 cubic C1 half-splines",
        "normalization": "analytic continuous-phase zero mean of each correction; no window normalization",
        "source_coefficients": COEFFICIENTS,
        "fitted_nuisance": "phase of MIDI91 only; one output-window DC",
        "fixed_gain": 4.137125725839024,
        "fixed_lag_samples": -1406,
        "hardware_samples": [829521, 833049],
        "engine_samples": [828115, 831643],
        "phase_policy": "prior notes canonical; training note91 nuisance phase; benchmark audio all canonical",
        "phase_search": {
            "coarse_points": PHASE_GRID,
            "basins": PHASE_BASINS,
            "seeds": "lowest strict cyclic local coarse minima plus the global coarse minimum",
            "refinement": "bounded scalar minimization in one coarse step on either side; retain coarse fallback",
            "xatol": PHASE_XATOL,
            "maxiter_per_basin": 64,
            "selection": "training residual only; finite search, no global-optimality claim",
        },
        "linear_solve": "unregularized float64 SVD, 32 source coefficients plus output DC; fixed unit ramp",
        "conditioning": {"full_rank": 33, "maximum_unscaled_condition": CONDITION_LIMIT},
        "invalid_phases": "retain all scores and reasons; do not select rank-deficient or ill-conditioned solutions",
        "forbidden": ["gain fitting", "downstream filter fitting", "recipe fitting", "validation-driven coefficient selection"],
        "control_gate": "independent planted complete-engine audio must recover and transfer at canonical phase before hardware is loaded",
        "hardware_equivalence": "not established by this fit",
    }


class MatrixCache:
    """Preserve requested raw operator matrices and their identities on disk."""

    def __init__(self, backend, directory, previous=None):
        self.backend = backend
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.records = {}
        if previous is not None:
            old = json.loads(Path(previous).read_text())
            for record in old["records"]:
                path = Path(old["directory"]) / record["file"]
                if sha(path) != record["sha256"]:
                    raise ValueError("Prior operator-cache file changed")
                copied = dict(record, file=str(path.resolve()))
                self.records[float(record["phase_cycles"]).hex()] = copied

    def get(self, phase):
        phase = float(phase % 1.0)
        key = phase.hex()
        if key in self.records:
            record = self.records[key]
            with np.load(self.directory / record["file"]) as data:
                return data["matrix"], data["offset"]
        started = time.monotonic()
        matrix = np.asarray(self.backend.matrix(phase), dtype=np.float64)
        offset = np.asarray(self.backend.offset(phase), dtype=np.float64)
        stats = self.backend.requests[-1]["stats"]
        if stats["filter_limit_calls"] or stats["output_limit_calls"]:
            raise ValueError("An operator column triggered nonlinear limiting; composition is not qualified")
        if matrix.shape != (SAMPLES, 33) or offset.shape != (SAMPLES,):
            raise ValueError(f"Unexpected complete-engine operator shape: {matrix.shape}, {offset.shape}")
        if not np.isfinite(matrix).all() or not np.isfinite(offset).all():
            raise ValueError("Non-finite complete-engine operator")
        name = f"phase-{len(self.records):05d}.npz"
        path = self.directory / name
        np.savez_compressed(path, matrix=matrix, offset=offset)
        self.records[key] = {
            "phase_cycles": phase, "file": name, "sha256": sha(path),
            "matrix_float64_sha256": hashlib.sha256(matrix.astype("<f8").tobytes()).hexdigest(),
            "offset_float64_sha256": hashlib.sha256(offset.astype("<f8").tobytes()).hexdigest(),
            "engine_stats": stats,
            "seconds": time.monotonic() - started,
        }
        return matrix, offset

    def receipt(self):
        return {"count": len(self.records), "directory": str(self.directory.resolve()),
                "records": list(self.records.values())}


def solve_at_phase(target, gain, matrix, offset):
    """Account explicitly for any affine zero-source engine contribution."""
    target = np.asarray(target, dtype=np.float64)
    if target.shape != (SAMPLES,) or not np.isfinite(target).all():
        raise ValueError("Target must be the frozen finite 3528-sample window")
    power = float(np.var(target))
    if power <= 1e-20 or not np.isfinite(gain) or gain <= 0:
        raise ValueError("Invalid target variance or frozen gain")
    # A source is ramp + sum(c_j*b_j), so each non-ramp response must have
    # its zero-source contribution removed before adding it to the ramp.
    base = gain * matrix[:, 0]
    source = gain * (matrix[:, 1:] - offset[:, None])
    design = np.column_stack((source, np.ones(SAMPLES)))
    coefficient, _, rank, singular = np.linalg.lstsq(design, target-base, rcond=None)
    condition = float(singular[0]/singular[-1]) if singular[-1] > 0 else None
    prediction = base + design @ coefficient
    error = float(np.mean((target-prediction)**2)/power)
    valid = int(rank) == 33 and condition is not None and condition < CONDITION_LIMIT
    return {
        "relative_error_power": error, "source_coefficients": coefficient[:-1].tolist(),
        "output_dc": float(coefficient[-1]), "rank": int(rank), "condition": condition,
        "valid": valid, "singular_values": singular.tolist(),
        "invalid_reason": None if valid else "rank or unscaled condition guard failed",
        "prediction": prediction,
    }


def fit(target, gain, cache, output):
    """Search only training phase; save every visited outcome, including failures."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    scores = {}
    best = None
    started = time.monotonic()

    def evaluate(phase):
        nonlocal best
        phase = float(phase % 1.0)
        key = phase.hex()
        if key in scores:
            row = scores[key]
            return row["relative_error_power"] if row["valid"] else np.inf
        matrix, offset = cache.get(phase)
        row = solve_at_phase(target, gain, matrix, offset)
        prediction = row.pop("prediction")
        row["phase_cycles"] = phase
        row["operator_record"] = cache.records[key]
        scores[key] = row
        if row["valid"] and (best is None or row["relative_error_power"] < best["relative_error_power"]):
            best = row
            np.save(output / "best-prediction.npy", prediction)
            save(output / "best.json", best)
        if len(scores) % 16 == 0:
            save(output / "search-progress.json", {"evaluations": len(scores), "best": best,
                 "elapsed_seconds": time.monotonic()-started})
            print(f"phase evaluations {len(scores)}; best "
                  f"{None if best is None else best['relative_error_power']}", flush=True)
        return row["relative_error_power"] if row["valid"] else np.inf

    grid = np.arange(PHASE_GRID)/PHASE_GRID
    values = np.array([evaluate(p) for p in grid])
    if not np.isfinite(values).any():
        save(output / "search.json", {"status": "no_valid_phase", "scores": list(scores.values())})
        raise ValueError("No full-rank, well-conditioned phase; hardware fit not selected")
    minima = [i for i in range(PHASE_GRID)
              if values[i] < values[(i-1) % PHASE_GRID] and values[i] < values[(i+1) % PHASE_GRID]]
    global_index = int(np.argmin(values))
    seeds = sorted(set(minima + [global_index]), key=lambda i: (values[i], i))[:PHASE_BASINS]
    refinements = []
    for index in seeds:
        result = minimize_scalar(evaluate, bounds=(grid[index]-1/PHASE_GRID, grid[index]+1/PHASE_GRID),
                                 method="bounded", options={"xatol": PHASE_XATOL, "maxiter": 64})
        refinements.append({"seed": index, "success": bool(result.success), "message": str(result.message),
                            "phase_cycles": float(result.x % 1),
                            "loss": float(result.fun) if np.isfinite(result.fun) else None,
                            "evaluations": int(result.nfev)})
    receipt = {"status": "fit_selected", "protocol": protocol(), "fixed_gain": gain,
               "target_float64_sha256": hashlib.sha256(np.asarray(target, dtype="<f8").tobytes()).hexdigest(),
               "best": best, "coarse_seed_indices": seeds, "refinements": refinements,
               "scores": list(scores.values()), "valid_evaluations": sum(r["valid"] for r in scores.values()),
               "invalid_evaluations": sum(not r["valid"] for r in scores.values()),
               "elapsed_seconds": time.monotonic()-started, "prediction_sha256": sha(output / "best-prediction.npy")}
    save(output / "search.json", receipt)
    return receipt


def read_engine(path):
    rate, value = wavfile.read(path)
    if rate != 44100 or value.dtype != np.float32 or value.ndim != 2 or value.shape[1] != 2:
        raise ValueError("Expected native 44.1 kHz float32 stereo engine output")
    if not np.isfinite(value).all():
        raise ValueError("Non-finite engine audio")
    return value


def independent_transfer(reference, candidate):
    """Keep full support and each of the five independently rendered windows."""
    a, b = read_engine(reference).astype(float), read_engine(candidate).astype(float)
    if a.shape != b.shape:
        raise ValueError("Planted full-performance output lengths differ")
    windows = [("full_performance", 0, len(a))]
    frozen = json.loads((Path(__file__).resolve().parents[1] /
                         "Docs/fidelity/source-audits/production-high-note-saw-2026-09-15.json").read_text())
    for row in frozen["slopes"][0]["windows"]:
        passage = row["passage"]
        windows.append((f"note{passage['note']}+{passage['offset_seconds']}", *row["engine_samples"]))
    rows = []
    for label, start, end in windows:
        power = float(np.mean(a[start:end]**2))
        error = float(np.mean((a[start:end]-b[start:end])**2)/power)
        rows.append({"support": label, "samples": [start, end], "relative_error_power": error,
                     "passes": bool(error < 1e-8)})
    return {"reference": str(Path(reference).resolve()), "reference_sha256": sha(reference),
            "candidate": str(Path(candidate).resolve()), "candidate_sha256": sha(candidate),
            "rows": rows, "passed": all(row["passes"] for row in rows)}


def main():
    import build_saw_w4_experiment as engine
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("controls", "hardware"), required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--patch", type=Path, required=True)
    parser.add_argument("--lp24-patch", type=Path, required=True)
    parser.add_argument("--midi", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sources", type=Path, help="Pinned original MP3 cache; hardware stage only")
    parser.add_argument("--control-receipt", type=Path, help="Successful source-free phase/control receipt")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    identity = {"tool_sha256": sha(__file__), "builder_sha256": sha(engine.__file__),
                "build_manifest_sha256": sha(args.build / "manifest.json"),
                "lp12_patch_sha256": sha(args.patch), "lp24_patch_sha256": sha(args.lp24_patch),
                "midi_sha256": sha(args.midi)}
    save(out / "protocol-before-input.json", {"stage": args.stage, "protocol": protocol(), "identity": identity})
    previous_cache = None
    if args.stage == "hardware":
        if args.control_receipt is None or args.sources is None:
            raise ValueError("Hardware fit requires passed controls and pinned original cache")
        control = json.loads(args.control_receipt.read_text())
        if control["identity"] != identity or control["passed"] is not True:
            raise ValueError("Control identity changed or source recovery failed")
        previous_cache = Path(control["operator_cache_receipt"])
        if sha(previous_cache) != control["operator_cache_receipt_sha256"]:
            raise ValueError("Control operator-cache receipt changed")
    backend = engine.open_backend(args.build, args.patch, args.midi, output_dir=out / "backend")
    prewarm = backend.ready["prewarm_stats"]
    if prewarm["filter_limit_calls"] or prewarm["output_limit_calls"]:
        backend.close()
        raise ValueError("Source-column prehistory triggered nonlinear limiting")
    cache = MatrixCache(backend, out / "matrices", previous_cache)
    gain = protocol()["fixed_gain"]
    a, b = protocol()["engine_samples"]

    def render(coefficients, phase, patch, name):
        return Path(engine.render_source(args.build, patch, args.midi, coefficients,
                    phase=phase, phase_note=91, output_dir=out / name, tail=2.0))

    try:
        if args.stage == "controls":
            nested = np.r_[1.0, 2/3, 5/12, 1/12, np.zeros(12)]
            index = np.arange(16)
            coefficient = np.r_[-nested + .075*np.sin(.37+index*.53),
                                 nested + .065*np.cos(.29+index*.41)]
            planted_phase = .321
            save(out / "planted-source.json", {"coefficients": coefficient.tolist(),
                 "phase_cycles": planted_phase, "output_dc": .013,
                 "selection": "fixed before hardware; ordinary polyBLEP plus bounded asymmetric perturbation"})
            truth_path = render(coefficient.tolist(), planted_phase, args.patch, "planted-training")
            target = gain*read_engine(truth_path)[a:b, 0].astype(float) + .013
            recovery = fit(target, gain, cache, out / "recovery")
            fitted = recovery["best"]["source_coefficients"]
            transfers = []
            for slope, patch in ((12, args.patch), (24, args.lp24_patch)):
                reference = render(coefficient.tolist(), 0.0, patch, f"planted-canonical-lp{slope}")
                candidate = render(fitted, 0.0, patch, f"recovered-canonical-lp{slope}")
                transfers.append({"slope": slope, **independent_transfer(reference, candidate)})
            passed = bool(recovery["best"]["relative_error_power"] < 1e-8 and
                          all(row["passed"] for row in transfers))
            save(out / "operator-cache.json", cache.receipt())
            result = {"stage": "source_free_controls", "passed": passed, "identity": identity,
                      "training_reference": str(truth_path), "training_reference_sha256": sha(truth_path),
                      "training_best": recovery["best"], "canonical_transfers": transfers,
                      "operator_cache_receipt": str(out / "operator-cache.json"),
                      "operator_cache_receipt_sha256": sha(out / "operator-cache.json"),
                      "training_loss_gate": 1e-8, "each_transfer_support_gate": 1e-8,
                      "hardware_opened": False}
            save(out / "controls.json", result)
            if not passed:
                raise ValueError("Complete-engine planted source recovery or canonical transfer failed")
        else:
            import subprocess
            original = args.sources / "roland_sh-201_-_filter_demo_-_lpf12_q000.mp3"
            expected = "28e241247a0efb217eb4cb7154cc3b69713fcebca781639c45b8904b3dc8615b"
            if sha(original) != expected:
                raise ValueError("Original LP12 recording changed")
            decoded = out / "hardware-lp12.wav"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(original),
                            "-c:a", "pcm_f32le", str(decoded)], check=True)
            rate, audio = wavfile.read(decoded)
            if rate != 44100 or audio.dtype != np.float32 or audio.ndim != 1 or not np.isfinite(audio).all():
                raise ValueError("Original decode format changed")
            x0, x1 = protocol()["hardware_samples"]
            target = audio[x0:x1].astype(float)
            frozen = json.loads((root / "Docs/fidelity/source-audits/production-high-note-saw-2026-09-15.json").read_text())
            expected_pcm = frozen["slopes"][0]["windows"][0]["hardware_float64_sample_sha256"]
            if hashlib.sha256(target.astype("<f8").tobytes()).hexdigest() != expected_pcm:
                raise ValueError("Frozen original training samples changed")
            fitted = fit(target, gain, cache, out / "fit")
            save(out / "operator-cache.json", cache.receipt())
            result = {"stage": "hardware_training_only", "identity": identity, "protocol": protocol(),
                      "original_mp3_sha256": expected, "decoded_sha256": sha(decoded),
                      "control_receipt": str(args.control_receipt.resolve()),
                      "control_receipt_sha256": sha(args.control_receipt), "best": fitted["best"],
                      "candidate_coefficients": fitted["best"]["source_coefficients"],
                      "canonical_phase_cycles": 0.0, "hardware_equivalence": "not_established"}
            # Freeze coefficients before any validation audio is rendered.
            save(out / "candidate.json", result)
    finally:
        save(out / "operator-cache.json", cache.receipt())
        backend.close()


if __name__ == "__main__":
    main()
