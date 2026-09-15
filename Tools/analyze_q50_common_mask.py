#!/usr/bin/env python3
"""Check Q50 LP12 log errors on identical post-training spectral bins.

Consumes a completed compare_deepsonic_q50_engine.py experiment. No gains,
delays, patch settings or activity thresholds are fitted here. The common
mask is the union of hardware and all three frozen, gain-adjusted candidates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import scipy
from scipy import signal
from scipy.io import wavfile


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.experiment_dir.resolve()
    result_path = root / "results.json"
    result = json.loads(result_path.read_text())
    for filename, key in (("source-manifest.json", "source_manifest_sha256"),
                          ("source-cache/decode-manifest.json", "decode_manifest_sha256")):
        if digest(root / filename) != result[key]:
            raise ValueError("Changed experiment manifest: " + filename)
    decode = json.loads((root / "source-cache/decode-manifest.json").read_text())
    hardware_path = root / "source-cache/roland_sh-201_-_filter_demo_-_lpf12_q050.wav"
    item = next(row for row in decode["files"]
                if Path(row["command"][-1]).name == hardware_path.name)
    if digest(hardware_path) != item["decoded_sha256"]:
        raise ValueError("Changed decoded hardware")
    sr, hardware = wavfile.read(hardware_path)
    if sr != 44100 or hardware.ndim != 1 or not np.isfinite(hardware).all():
        raise ValueError("Expected finite mono 44.1 kHz hardware")
    hardware = hardware.astype(np.float64)
    keys = (("checkpoint", 63), ("checkpoint", 64), ("lp12-stronger", 64))
    records, candidates, inputs = {}, {}, {}
    interval = lag = None
    for family, raw in keys:
        row = next(r for r in result["results"] if r["slope"] == 12
                   and r["family"] == family and r["raw_resonance"] == raw)
        label = f"{family}-lp12-raw{raw}"
        path = root / "renders" / label / "raw.wav"
        if digest(path) != row["receipt"]["render_sha256"]:
            raise ValueError("Changed render: " + label)
        rate, audio = wavfile.read(path)
        if rate != sr or audio.ndim != 2 or audio.shape[1] != 2 or not np.isfinite(audio).all():
            raise ValueError("Invalid render: " + label)
        pair = row["metrics"]["after_training"]["reference_samples"]
        if interval is None:
            interval, lag = pair, row["lag_samples"]
        if pair != interval or row["lag_samples"] != lag:
            raise ValueError("Candidates do not share exact evaluation coverage and lag")
        a, b = pair
        if a != 2 * sr or b > len(hardware) or a + lag < 0 or b + lag > len(audio):
            raise ValueError("Unexpected post-training slice")
        gain = row["gain"]
        if not np.isfinite(gain) or gain <= 0:
            raise ValueError("Invalid frozen gain")
        candidates[label] = audio[a + lag:b + lag, 0].astype(np.float64) * gain
        records[label] = row
        inputs[label] = {"render_sha256": digest(path), "training_gain": gain,
                         "training_gain_db": row["gain_db"]}
    reference = hardware[interval[0]:interval[1]]
    resolutions = []
    summaries = {label: {"pairwise_log_errors": [], "common_log_errors": []}
                 for label in candidates}
    for nfft in (512, 2048, 8192):
        def spectrum(audio):
            return np.abs(signal.stft(audio, fs=sr, window="hann", nperseg=nfft,
                          noverlap=nfft * 3 // 4, boundary=None, padded=False)[2])
        a = spectrum(reference)
        values = {label: spectrum(audio) for label, audio in candidates.items()}
        peak = float(np.max(a))
        floor, threshold = max(peak * 1e-4, 1e-30), max(peak * 1e-3, 1e-30)
        common = a >= threshold
        for value in values.values():
            common |= value >= threshold
        measured = {}
        for label, b in values.items():
            pairwise = np.maximum(a, b) >= threshold
            error = np.abs(20 * np.log10(np.maximum(b, floor) / np.maximum(a, floor)))
            pair_mean, common_mean = float(np.mean(error[pairwise])), float(np.mean(error[common]))
            original = next(r for r in records[label]["metrics"]["after_training"]["training_gain"]
                            ["multi_resolution_stft"] if r["window_samples"] == nfft)
            if not np.isclose(pair_mean, original["log_spectral_error_db_mean"], rtol=0, atol=1e-10):
                raise ValueError("Original pairwise metric did not reproduce: " + label)
            if int(np.count_nonzero(pairwise)) != original["active_time_frequency_channel_bins"]:
                raise ValueError("Original pairwise activity mask did not reproduce")
            measured[label] = {"pairwise_active_bins": int(np.count_nonzero(pairwise)),
                               "pairwise_log_error_db_mean": pair_mean,
                               "common_log_error_db_mean": common_mean,
                               "common_log_error_db_p95": float(np.percentile(error[common], 95))}
            summaries[label]["pairwise_log_errors"].append(pair_mean)
            summaries[label]["common_log_errors"].append(common_mean)
        resolutions.append({"window_samples": nfft, "hop_samples": nfft // 4,
                            "common_active_bins": int(np.count_nonzero(common)),
                            "common_mask_sha256": hashlib.sha256(np.packbits(common).tobytes()).hexdigest(),
                            "models": measured})
    summary = {label: {"pairwise_log_spectral_error_db_mean": float(np.mean(v["pairwise_log_errors"])),
                       "common_log_spectral_error_db_mean": float(np.mean(v["common_log_errors"]))}
               for label, v in summaries.items()}
    output = {"schema_version": 1, "status": "fixed_mask_sensitivity_not_equivalence",
              "experiment_results_sha256": digest(result_path), "tool_sha256": digest(__file__),
              "numpy_version": np.__version__, "scipy_version": scipy.__version__,
              "decoded_hardware_sha256": digest(hardware_path), "inputs": inputs,
              "source_revision": result["protocol"]["source_revision"],
              "recipe_policy": result["protocol"]["recipe_policy"],
              "reference_samples": interval, "lag_samples": lag,
              "gain_policy": "Exact per-whole-render training gain inherited from experiment; no refit",
              "mask_policy": "At each resolution use identical union of hardware, raw63, raw64 and stronger candidate bins at >= -60 dB relative to hardware spectral peak; -80 dB floor",
              "original_pairwise_metrics_reproduced": True,
              "summary": summary, "resolutions": resolutions}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
