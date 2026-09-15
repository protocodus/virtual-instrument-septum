#!/usr/bin/env python3
"""Test predeclared triangle conventions against four named hardware demos.

Dist's first note selects the candidate. Later Dist notes and other presets
remain holdouts. Builds use the public calibration API and frozen DSP copies;
original SysEx/MIDI and production source are never changed. No media download.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np
from scipy.io import wavfile
from scipy.optimize import minimize_scalar

from build_timbre_candidate import build_candidate

ROOT = Path(__file__).resolve().parents[1]
# Discrete hypotheses declared before rendering. Triangle amplitude and its
# half-cycle polarity are alternatives to a quadrature phase convention.
PROFILES = {
    "baseline": (0.0, 1.0),
    "triangle-quarter": (0.25, 1.0),
    "triangle-half": (0.5, 1.0),
    "triangle-three-quarter": (0.75, 1.0),
    "triangle-half-gain": (0.0, 0.5),
    "triangle-double-gain": (0.0, 2.0),
    "triangle-inverted-half-gain": (0.5, 0.5),
    "triangle-inverted-double-gain": (0.5, 2.0),
}
# Physical offsets below are from the current WIDE-dependent imported patch,
# including tone octave. Do not use obsolete raw/display -36 as semitones.
# These select the lowest oscillator's harmonic family, not the loudest peak.
CASES = {
    "dist-bs-1": {"offset": -12, "indices": [0, 1, 2]},
    "moogie-1": {"offset": -12, "indices": [0, 4, 8]},
    "pedal-bs-1": {"offset": -24, "indices": [1, 2]},
    "club-bass": {"offset": -12, "indices": [0, 1, 2, 3]},
}
SHIFTS = (-0.01, 0.0, 0.01)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fit(y, sr, start, end, frequency):
    first, last = round(start * sr), round(end * sr)
    if first < 0 or last > len(y) or last <= first:
        raise ValueError("Harmonic window outside the audio")
    x = y[first:last:4]
    t = np.arange(first, last, 4) / sr - (start + end) / 2
    columns = [np.ones(len(t)), t / (end - start)]
    for n in range(1, 13):
        columns.extend((np.cos(2 * np.pi * n * frequency * t),
                        np.sin(2 * np.pi * n * frequency * t)))
    basis = np.column_stack(columns)
    coefficients, _, _, singular = np.linalg.lstsq(basis, x, rcond=None)
    condition = float(singular[0] / singular[-1])
    if condition > 100:
        raise ValueError(f"Ill-conditioned harmonic measurement: {condition}")
    amplitude = np.hypot(coefficients[2::2], coefficients[3::2])
    if amplitude[0] < 1e-10 or np.var(x) < 1e-16:
        raise ValueError("Cannot normalize a silent harmonic window")
    return {"amplitude": amplitude.tolist(),
            "relative_h1_db": (20 * np.log10(np.maximum(amplitude / amplitude[0], 1e-15))).tolist(),
            "residual_power_fraction": float(np.mean((x - basis @ coefficients) ** 2) / np.var(x)),
            "condition_number": condition}


def self_check():
    sr, f = 44100, 41.37
    t = np.arange(sr) / sr
    amplitudes = np.array([0.5, .13, .27, .011, .037, .09, .012, .029, .023, .004, .018, .007])
    y = .01 + .004 * t
    for n, amplitude in enumerate(amplitudes, 1):
        y += amplitude * np.cos(2 * np.pi * n * f * t + n * n * .123)
    measured = fit(y, sr, .035, .115, f)
    error = float(np.max(np.abs(np.array(measured["amplitude"]) - amplitudes)))
    if error > 1e-12:
        raise ValueError(f"Synthetic harmonic estimator failed: {error}")
    return {"maximum_absolute_amplitude_error": error,
            "residual_power_fraction": measured["residual_power_fraction"]}


def read_audio(path):
    sr, audio = wavfile.read(path)
    if sr != 44100 or audio.dtype.kind != "f" or not np.isfinite(audio).all():
        raise ValueError("Expected finite 44.1 kHz floating PCM")
    y = audio.astype(float)
    return sr, y.mean(axis=1) if y.ndim == 2 else y


def observe(path, case, spec, latency, frequencies=None):
    sr, y = read_audio(path)
    result = []
    for index in spec["indices"]:
        note = case["notes"][index]
        on, off = note["on"] + latency, note["off"] + latency
        nominal = 440 * 2 ** ((note["note"] + spec["offset"] - 69) / 12)
        if frequencies is None:
            objective = lambda f: fit(y, sr, on + .035, on + .115, f)["residual_power_fraction"]
            frequency = float(minimize_scalar(objective, method="bounded",
                              bounds=(nominal * .97, nominal * 1.03)).x)
        else:
            frequency = frequencies[index]
        windows = []
        for shift in SHIFTS:
            for name, start, end in (("early", on + .035, on + .115),
                                      ("late", off - .105, off - .025)):
                windows.append({"name": name, "shift_seconds": shift,
                    "start_seconds": start + shift, "end_seconds": end + shift,
                    **fit(y, sr, start + shift, end + shift, frequency)})
        result.append({"index": index, "played_midi_note": note["note"],
                       "nominal_family_hz": nominal, "measured_family_hz": frequency,
                       "windows": windows})
    return {"wav_sha256": digest(path), "notes": result}


def compare(actual, reference):
    records = []
    for test, ref in zip(actual["notes"], reference["notes"]):
        rows = []
        for shift in SHIFTS:
            difference, odd, even = [], [], []
            residual = []
            for a, b in zip(test["windows"], ref["windows"]):
                if a["shift_seconds"] != shift:
                    continue
                x, y = np.array(a["relative_h1_db"]), np.array(b["relative_h1_db"])
                difference.extend((x[1:8] - y[1:8]).tolist())
                odd.extend((x[[2, 4, 6]] - y[[2, 4, 6]]).tolist())
                # Normalizing even harmonics to H2 isolates Moogie's
                # unresolved pulse problem from triangle's H1 interference.
                even.extend(((x[[3, 5, 7]] - x[1]) - (y[[3, 5, 7]] - y[1])).tolist())
                residual.append(b["residual_power_fraction"])
            rms = lambda values: float(np.sqrt(np.mean(np.square(values))))
            rows.append({"shift_seconds": shift, "h2_h8_rmse_db": rms(difference),
                         "odd_h3_h5_h7_rmse_db": rms(odd), "even_h4_h6_h8_over_h2_rmse_db": rms(even),
                         "maximum_hardware_fit_residual": max(residual)})
        records.append({"note_index": test["index"], "measurements": rows})
    return records


def aggregate(records, metric, indices=None, shift=0.0):
    values = [row[metric] ** 2 for record in records
              if indices is None or record["note_index"] in indices
              for row in record["measurements"] if row["shift_seconds"] == shift]
    return float(np.sqrt(np.mean(values)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=ROOT,
                        help="Source tree matching benchmark DSP; frozen once before parallel builds")
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.jobs <= 4:
        raise ValueError("jobs must be 1..4")
    estimator = self_check()
    args.output.mkdir(parents=True, exist_ok=False)
    frozen = args.output / "source-snapshot"
    shutil.copytree(args.source_root / "Source/DSP", frozen / "Source/DSP")
    (frozen / "Tools").mkdir()
    shutil.copy2(args.source_root / "Tools/RenderMidi.cpp", frozen / "Tools/RenderMidi.cpp")
    source_hashes = {path.relative_to(frozen).as_posix(): digest(path)
                     for path in frozen.rglob("*") if path.is_file()}
    inputs = {}
    for name, spec in CASES.items():
        folder = args.comparison_root / name
        comparison = json.loads((folder / "comparison.json").read_text())
        for path, expected in comparison["source_code_sha256"].items():
            if source_hashes[path] != expected:
                raise ValueError("Source does not match benchmark snapshot: " + path)
        hardware = folder / "hardware-excerpt-raw.wav"
        baseline = folder / "septum-raw.wav"
        latency = comparison["retained_engine_latency_samples"] / 44100
        case = comparison["case"]
        inputs[name] = {"comparison": comparison, "folder": str(folder), "latency": latency,
            "sha256": {f: digest(folder / f) for f in ("comparison.json", "original-patch.syx",
                "reconstructed-performance.mid", "hardware-excerpt-raw.wav", "septum-raw.wav")},
            "hardware": observe(hardware, case, spec, 0),
            "baseline": observe(baseline, case, spec, latency)}

    def candidate(name):
        phase, gain = PROFILES[name]
        profile = {"version": 1, "id": "waveform-convention-" + name,
            "evidence": "Experimental predeclared triangle convention; selected on Dist first note only. No hardware-match claim."}
        if name != "baseline":
            profile["waves"] = {"phase_cycles": [0, 0, 0, phase, 0],
                                "wave_gain": [1, 1, 1, gain, 1]}
        profile_path = args.output / (name + ".json")
        profile_path.write_text(json.dumps(profile, indent=2) + "\n")
        folder = args.output / name
        build = build_candidate(profile_path, folder, source_root=frozen)
        result = {"profile": profile, "renderer_sha256": build["renderer"]["sha256"],
                  "build_manifest_sha256": digest(folder / "manifest.json"), "cases": {}}
        for case_name, entry in inputs.items():
            source = Path(entry["folder"])
            wav = folder / (case_name + ".wav")
            command = [sys.executable, str(ROOT / "Tools/render_midi.py"), "--renderer",
                str(folder / build["renderer"]["path"]), "--syx", str(source / "original-patch.syx"),
                "--midi", str(source / "reconstructed-performance.mid"), "--output", str(wav),
                "--tempo-policy", "preserve-patch", "--strict"]
            subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
            frequencies = {r["index"]: r["measured_family_hz"] for r in entry["baseline"]["notes"]}
            measured = observe(wav, entry["comparison"]["case"], CASES[case_name], entry["latency"], frequencies)
            actual_sr, actual = read_audio(wav)
            base_sr, base = read_audio(source / "septum-raw.wav")
            if len(actual) != len(base) or actual_sr != base_sr:
                raise ValueError("Candidate replay duration/rate differs from baseline")
            result["cases"][case_name] = {"measurements": measured,
                "comparison": compare(measured, entry["hardware"]), "render_command": command,
                "maximum_sample_difference_from_baseline": float(np.max(np.abs(actual - base))),
                "render_manifest_sha256": digest(wav.with_suffix(".render.json"))}
        print("completed " + name, flush=True)
        return name, result

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        candidates = dict(pool.map(candidate, PROFILES))
    ranking = []
    for name, candidate_result in candidates.items():
        row = {"name": name}
        for case_name, entry in candidate_result["cases"].items():
            records = entry["comparison"]
            row[case_name] = {"all_rmse_db": aggregate(records, "h2_h8_rmse_db"),
                "odd_rmse_db": aggregate(records, "odd_h3_h5_h7_rmse_db"),
                "even_over_h2_rmse_db": aggregate(records, "even_h4_h6_h8_over_h2_rmse_db"),
                "timing_rmse_db": [aggregate(records, "h2_h8_rmse_db", shift=s) for s in SHIFTS]}
        row["training_rmse_db"] = aggregate(candidate_result["cases"]["dist-bs-1"]["comparison"],
                                            "h2_h8_rmse_db", indices=[0])
        row["dist_holdout_rmse_db"] = aggregate(candidate_result["cases"]["dist-bs-1"]["comparison"],
                                                "h2_h8_rmse_db", indices=[1, 2])
        ranking.append(row)
    selected = min(ranking, key=lambda row: row["training_rmse_db"])["name"]
    result = {"schema_version": 1, "status": "experimental; no shipping DSP changes", "self_check": estimator,
        "source_snapshot_sha256": source_hashes,
        "analysis_tool_sha256": digest(__file__), "candidate_selection": "minimum Dist first-note H2-H8/H1 RMSE at nominal timing; holdouts never select",
        "selected": selected, "cases": CASES, "profiles_predeclared": PROFILES,
        "inputs": inputs, "candidates": candidates, "summary": ranking,
        "limits": ["Same named published patches; original performance MIDI and recorded patch revision remain unverified.",
            "Velocities/controllers and capture processing are unknown. Harmonic metrics are conditional features, not hardware identity.",
            "Moogie even-harmonic mismatch cannot be identified by changing symmetric triangle phase alone.",
            "Pedal has no triangle and is a neutrality check; supersaw and detuned sine prevent a strictly stationary harmonic model.",
            "Club retains its published reverb. Short onset windows reduce but do not certify absence of wet-signal contamination.",
            "All cases use independent hardware and baseline frequency estimates within 3% of current physical note families; candidates inherit baseline frequencies."]}
    (args.output / "results.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"selected": selected, "summary": ranking}, indent=2))


if __name__ == "__main__":
    main()
