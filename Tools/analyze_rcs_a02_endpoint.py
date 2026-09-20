#!/usr/bin/env python3
"""Characterize A02's late hardware harmonic content; never reads a renderer."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.linalg import lstsq
from scipy.optimize import minimize_scalar


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def harmonic_fit(x, t, frequency, count=16):
    phase = 2 * np.pi * t[:, None] * frequency * np.arange(1, count + 1)
    matrix = np.column_stack((np.ones(len(t)), t / np.ptp(t),
                              np.cos(phase), np.sin(phase)))
    coefficients, _, rank, _ = lstsq(matrix, x, lapack_driver="gelsy")
    if rank != matrix.shape[1]:
        raise ValueError("Rank-deficient harmonic measurement")
    amplitude = np.hypot(coefficients[2:2 + count], coefficients[2 + count:])
    angle = np.arctan2(-coefficients[2 + count:], coefficients[2:2 + count])
    relative = np.angle(np.exp(1j * (angle - np.arange(1, count + 1) * angle[0])))
    residual = np.mean((x - matrix @ coefficients) ** 2) / np.var(x)
    return float(residual), amplitude, np.rad2deg(relative)


def measure(audio, rate, center, width, origin, channel, frequency_bounds, harmonic_count):
    start = round((center - origin - width / 2) * rate)
    end = round((center - origin + width / 2) * rate)
    if not 0 <= start < end <= len(audio):
        raise ValueError("Window outside source")
    samples = audio[start:end]
    x = samples.mean(axis=1) if channel == "mid" else samples[:, {"left": 0, "right": 1}[channel]]
    t = np.arange(start, end) / rate - (center - origin)
    result = minimize_scalar(lambda frequency: harmonic_fit(x, t, frequency, harmonic_count)[0],
                             bounds=frequency_bounds, method="bounded",
                             options={"xatol": 1e-5})
    if not result.success or not frequency_bounds[0] + .01 < result.x < frequency_bounds[1] - .01:
        raise ValueError("Frequency estimate failed or reached search boundary")
    residual, amplitude, phase = harmonic_fit(x, t, result.x, harmonic_count)
    sine = minimize_scalar(lambda frequency: harmonic_fit(x, t, frequency, 1)[0],
                           bounds=frequency_bounds, method="bounded")
    return {
        "source_center_seconds": center,
        "width_seconds": width,
        "channel": channel,
        "frequency_search_bounds_hz": frequency_bounds,
        "harmonic_count": harmonic_count,
        "frequency_hz": float(result.x),
        "harmonic_peak_amplitude": amplitude.tolist(),
        "harmonic_db_relative_h1": (20 * np.log10(np.maximum(amplitude, 1e-15) / amplitude[0])).tolist(),
        "harmonic_phase_minus_n_times_h1_degrees": phase.tolist(),
        "nonfundamental_fraction_of_periodic_power": float(np.sum(amplitude[1:] ** 2) / np.sum(amplitude ** 2)),
        "harmonic_model_residual_fraction": residual,
        "best_sine_model_residual_fraction": float(sine.fun),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    audit_path = root / "Docs/fidelity/source-audits/rcs-a02-hardware-observations-2026-09-20.json"
    audit = json.loads(audit_path.read_text())
    timing_path = root / audit["sources"]["parent_cross_platform_timing"]["path"]
    if digest(timing_path) != audit["sources"]["parent_cross_platform_timing"]["sha256"]:
        raise ValueError("Cross-platform timing provenance changed")
    offsets = [row["offset_seconds"] for row in json.loads(timing_path.read_text())["rows"]]
    if np.ptp(offsets) > 1 / 44100:
        raise ValueError("Ambiguous platform offset")
    offset = float(np.median(offsets))
    rows = []
    sources = {}
    windows = [(21.661, .040, "early"), (21.740, .040, "closing"),
               (21.770, .040, "closing"), (21.800, .040, "closing")]
    windows += [(center, width, "late") for center in (21.830, 21.840, 21.850)
                for width in (.030, .040, .060) if center + width / 2 <= 21.880001]
    windows += [(21.210 + elapsed, .040, "first_note_training") for elapsed in (.080, .090, .100)]
    for platform, source_key, origin, shift in (
            ("youtube", "youtube_crop_float_wav", 19.0, 0.0),
            ("soundcloud", "soundcloud_decoded_wav", 0.0, offset)):
        source = audit["sources"][source_key]
        path = root / source["path"]
        if digest(path) != source["sha256"]:
            raise ValueError(f"Source hash mismatch: {platform}")
        rate, audio = wavfile.read(path)
        if rate != 44100 or audio.ndim != 2 or audio.shape[1] != 2 or audio.dtype.kind != "f":
            raise ValueError(f"Unexpected source PCM: {platform}")
        if not np.isfinite(audio).all() or np.max(np.abs(audio)) < 1e-6:
            raise ValueError(f"Invalid or silent source: {platform}")
        if platform == "youtube" and len(audio) != 7 * rate:
            raise ValueError("Unexpected YouTube crop duration")
        sources[platform] = {**source, "sample_rate": rate, "channels": 2,
                             "frames": len(audio), "youtube_to_source_offset_seconds": shift}
        audio = audio.astype(np.float64)
        for center, width, stage in windows:
            for channel in ("left", "right", "mid"):
                bounds = (46.0, 57.0) if stage == "first_note_training" else (95.0, 110.0)
                count = 40 if stage == "first_note_training" else 16
                row = measure(audio, rate, center + shift, width, origin, channel, bounds, count)
                rows.append({"platform": platform, "youtube_center_seconds": center,
                             "stage": stage, **row})
    late = [row for row in rows if row["stage"] == "late"]
    def span(values):
        return {"min": float(np.min(values)), "median": float(np.median(values)),
                "max": float(np.max(values))}
    summary = {
        "late_observation_count": len(late),
        "h2_db_relative_h1": span([r["harmonic_db_relative_h1"][1] for r in late]),
        "h3_db_relative_h1": span([r["harmonic_db_relative_h1"][2] for r in late]),
        "h4_db_relative_h1": span([r["harmonic_db_relative_h1"][3] for r in late]),
        "h2_relative_phase_degrees": span([r["harmonic_phase_minus_n_times_h1_degrees"][1] for r in late]),
        "nonfundamental_fraction_of_periodic_power": span([r["nonfundamental_fraction_of_periodic_power"] for r in late]),
        "harmonic_model_residual_fraction": span([r["harmonic_model_residual_fraction"] for r in late]),
        "best_sine_model_residual_fraction": span([r["best_sine_model_residual_fraction"] for r in late]),
        "frequency_hz": span([r["frequency_hz"] for r in late]),
    }
    result = {
        "status": "Hardware-only endpoint characterization; within-performance validation, not an untouched holdout.",
        "sources": sources,
        "script_sha256": digest(Path(__file__).resolve()),
        "input_audit_sha256": digest(audit_path),
        "cross_platform_timing_sha256": digest(timing_path),
        "method": "Joint DC, linear trend and harmonic cosine/sine least squares, rectangular windows; 16 harmonics and frequency search 95–110 Hz for long fourth note, 40 harmonics and search 46–57 Hz for first note. Fundamental minimizes normalized residual. Sine-only control separately optimizes frequency. Relative phase is phi_n minus n*phi_1. No renderer, engine law or candidate parameter read or fitted.",
        "summary": summary,
        "observations": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
