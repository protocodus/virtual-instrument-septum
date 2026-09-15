#!/usr/bin/env python3
"""Replay historical reverb prefix fits against an updated alignment assessor."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np
from scipy import signal

ROOT = Path(__file__).resolve().parents[1]
OLD_SHA = "b6ca63fa02ff11f3154cf34c1233cfe460fd4447be403fe4c0695646ccb74631"
RUNS = (
    "reverb-width-candidates/run-01", "reverb-gain-candidates/run-01",
    "reverb-new-preset-validation/run-01", "reverb-articulation-followup/run-01",
    "reverb-mode-damping-followup/run-01", "dual-reverb-phase/run-01",
    "dual-layer-phase/run-01",
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def selected_statistics(assess, reference, candidate, sr, calibration, lags):
    """Direct centered dot products independently check selected FFT scores."""
    cal, bound = calibration["calibration_frames"], round(calibration["max_lag_seconds"] * sr)
    window = max(1, round(.01 * sr))
    a = assess.rms_envelope(reference[:cal], window)
    b = assess.rms_envelope(candidate[:cal], window)
    fixed = a[bound:len(a)-bound]
    centered = fixed - fixed.mean()
    ref_var, size = float(np.dot(centered, centered)), len(fixed)
    sums = np.concatenate(([0.0], np.cumsum(b)))
    squares = np.concatenate(([0.0], np.cumsum(b * b)))
    variances = np.maximum(squares[size:] - squares[:-size]
                           - (sums[size:] - sums[:-size]) ** 2 / size, 0)
    correlations = signal.correlate(b, centered, mode="valid", method="fft")
    rows = {}
    for lag in sorted(set(lags)):
        index = lag + bound
        piece = b[index:index+size]
        bc = piece - piece.mean()
        direct_var = float(np.dot(bc, bc))
        direct_den = np.sqrt(ref_var * direct_var)
        fft_den = np.sqrt(ref_var * variances[index])
        rows[str(lag)] = dict(
            direct_pearson=float(np.dot(centered, bc)/direct_den) if direct_den else None,
            unguarded_fft_normalized=float(correlations[index]/fft_den) if fft_den else None,
            direct_candidate_centered_variance=direct_var,
            cumulative_candidate_centered_variance=float(variances[index]),
            candidate_variance_fraction_of_maximum=float(variances[index]/variances.max()) if variances.max() else None,
            candidate_window_peak=float(abs(piece).max()),
            maximum_candidate_centered_variance=float(variances.max()),
        )
    return rows


def inventory(bench):
    records = []
    for relative in RUNS:
        directory = bench/relative
        result_path = directory/"results.json"
        result = json.loads(result_path.read_text())
        phase = "comparisons" in result
        if phase:
            expected = result["protocol"]["source_sha256"]["Tools/assess_hardware_equivalence.py"]
        elif "tools" in result["protocol"]:
            expected = result["protocol"]["tools"]["assess_hardware_equivalence.py"]
        else:
            manifest_path = directory/"source-manifest.json"
            if sha(manifest_path) != result["source_manifest_sha256"]:
                raise ValueError("Historical source manifest changed")
            expected = json.loads(manifest_path.read_text())["input_sha256"]["Tools/assess_hardware_equivalence.py"]
        if expected != OLD_SHA:
            raise ValueError("Unexpected historical assessor revision")
        for row in result["comparisons" if phase else "cases"]:
            if phase:
                item = next(x for x in result["protocol"]["inputs"] if x["id"] == row["id"])
                reference = Path(item["input_directory"])/"hardware-excerpt-raw.wav"
                reference_hash = item["hardware_excerpt_sha256"]
                n = item["comparison_frames"]
                baseline = row["models"]["1.0"]
            elif "comparison" in row:
                reference = directory/"baseline-corpus"/row["id"]/"hardware-excerpt-raw.wav"
                reference_hash = row["comparison"]["files"]["hardware-excerpt-raw.wav"]
                n = row["comparison"]["comparison_frames"]
                baseline = row["models"]["gain-1"]
            else:
                reference = directory/"cases"/row["id"]/"hardware-excerpt-raw.wav"
                reference_hash = row["input_sha256"]["hardware-excerpt-raw.wav"]
                n = None
                baseline = row["models"]["width-1" if relative.startswith("reverb-width") else "gain-1"]
            models = []
            for name, model in row["models"].items():
                command = model["command"]
                wav = Path(command[command.index("--output")+1]) if command else directory/"cases"/row["id"]/(name+".wav")
                expected_wav = model.get("wav_sha256", model.get("raw_sha256"))
                if sha(wav) != expected_wav or sha(wav.with_suffix(".render.json")) != model["receipt_sha256"]:
                    raise ValueError("Historical model WAV or receipt changed")
                models.append(dict(name=name, path=str(wav), sha256=expected_wav, receipt_sha256=model["receipt_sha256"]))
                if model is baseline:
                    baseline_path = wav
            if sha(reference) != reference_hash:
                raise ValueError("Historical reference WAV changed")
            records.append(dict(run=relative, id=row["id"],
                                phase={k:row[k] for k in ("phase_cycles", "upper_phase_cycles", "lower_phase_cycles") if k in row},
                                source_result_sha256=sha(result_path), reference_path=str(reference), reference_sha256=reference_hash,
                                baseline_path=str(baseline_path), comparison_frames=n, models=models, historical_fit=row["calibration"]))
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-root", type=Path, required=True)
    parser.add_argument("--assessor", type=Path, default=ROOT/"Tools/assess_hardware_equivalence.py")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    bench, out = args.benchmark_root.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    old_path = bench/"dual-reverb-phase/run-01/frozen-source/Tools/assess_hardware_equivalence.py"
    if sha(old_path) != OLD_SHA or sha(args.assessor) == OLD_SHA:
        raise ValueError("Need pinned old assessor and a distinct updated assessor")
    for name, source in (("historical_assessor.py", old_path), ("updated_assessor.py", args.assessor)):
        shutil.copyfile(source, out/name)
    old = load_module(out/"historical_assessor.py", "historical_alignment")
    new = load_module(out/"updated_assessor.py", "updated_alignment")
    records = inventory(bench)
    protocol = dict(scope="75 historical previous-return prefix transforms across seven reverb experiments; all original frozen model WAVs checked, no rerenders or historical overwrites.",
                    historical_assessor_sha256=OLD_SHA, updated_assessor_sha256=sha(out/"updated_assessor.py"),
                    tool_sha256=sha(__file__), runs=RUNS, inventory=records,
                    policy="Compare identical calibration audio under frozen old and updated fit_transform. Reproduce each historical fit exactly first. Direct centered dot products verify selected lag correlations; uniform gain controls are diagnostic, not fitted models.")
    save(out/"protocol-before-replay.json", protocol)
    output = []
    for item in records:
        sr, reference = old.read_audio(item["reference_path"])
        rate, candidate = old.read_audio(item["baseline_path"])
        if sr != rate:
            raise ValueError("Sample-rate mismatch")
        n = item["comparison_frames"] or len(reference)
        reference, candidate = reference[:n], candidate[:n]
        prior = item["historical_fit"]
        arguments = (sr, prior["calibration_frames"], prior["max_lag_seconds"])
        reproduced = old.fit_transform(reference, candidate, *arguments)
        if reproduced != prior:
            raise ValueError("Historical fit failed exact replay: "+item["id"])
        updated = new.fit_transform(reference, candidate, *arguments)
        lags = [prior["candidate_lag_samples"], updated["candidate_lag_samples"]]
        output.append(dict(**item, updated_fit=updated,
                           lag_changed=lags[0] != lags[1], gain_changed=prior["candidate_gain"] != updated["candidate_gain"],
                           direct_statistics=selected_statistics(old, reference, candidate, sr, prior, lags)))
        print(item["run"], item["id"], item["phase"], *lags, flush=True)
    controls = []
    for item in output:
        if item["run"] != "reverb-mode-damping-followup/run-01":
            continue
        sr, reference = old.read_audio(item["reference_path"])
        _, candidate = old.read_audio(item["baseline_path"])
        prior = item["historical_fit"]
        for scale in (.0001, .01, 1., 100., 10000.):
            fit = new.fit_transform(reference, candidate * scale, sr, prior["calibration_frames"], prior["max_lag_seconds"])
            controls.append(dict(id=item["id"], uniform_candidate_scale=scale, fit=fit,
                                 lag_equal_unscaled=fit["candidate_lag_samples"] == item["updated_fit"]["candidate_lag_samples"],
                                 gain_compensation_relative_error=fit["candidate_gain"] * scale / item["updated_fit"]["candidate_gain"] - 1))
    summary = {run:dict(rows=sum(r["run"] == run for r in output),
                       changed_lags=sum(r["run"] == run and r["lag_changed"] for r in output),
                       changed_gains=sum(r["run"] == run and r["gain_changed"] for r in output)) for run in RUNS}
    save(out/"results.json", dict(protocol=protocol, comparisons=output, per_run=summary,
                                  model_wavs_and_receipts_revalidated=sum(len(r["models"]) for r in records),
                                  uniform_gain_controls=controls, no_audio_rerenders=True, historical_results_unchanged=True))
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
