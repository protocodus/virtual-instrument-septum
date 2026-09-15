#!/usr/bin/env python3
"""Add an original-only spectral mask diagnostic to the frozen W4 preset run.

Read-only measurement: no render, coefficient/input changes, or nuisance fits.
The legacy pair-union metrics are verified and retained without overwriting them.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
import numpy as np
import scipy
from scipy import signal

import assess_hardware_equivalence as assess

EXPECTED_RUN_SHA = "db2703598678513b3c0a26618d62605f199d722477d51f5c51bfd3908bbf8505"
SR = 44100
WINDOWS = (512, 1024, 2048, 8192)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pin(path, expected=None):
    path = Path(path).resolve()
    actual = sha(path)
    if expected is not None and actual != expected:
        raise ValueError("Changed pinned input: " + str(path))
    return dict(path=str(path), sha256=actual)


def read(info):
    pin(info["path"], info["sha256"])
    sr, audio = assess.read_audio(info["path"])
    if sr != SR or audio.shape[1] != 2:
        raise ValueError("Unexpected source rate/channel layout")
    return audio


def masked_errors(difference, mask):
    return dict(mean_db=float(np.mean(difference[mask])),
                p95_db=float(np.percentile(difference[mask], 95)),
                bins=int(np.count_nonzero(mask)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = pin(args.comparison, EXPECTED_RUN_SHA)
    run = json.loads(args.comparison.read_text())
    if len(run["cases"]) != 10 or not run["all_native_byte_identical"] or not run["all_five_non_saw_byte_identical"]:
        raise ValueError("Expected complete native/control-verified ten-case run")
    if assess.ACTIVE_DB != -60 or assess.FLOOR_DB != -80:
        raise ValueError("Inherited analysis constants changed")
    pin(run["protocol"]["dependencies"]["assess_hardware_equivalence.py"]["path"],
        run["protocol"]["dependencies"]["assess_hardware_equivalence.py"]["sha256"])
    args.output.mkdir(parents=True, exist_ok=False)
    result = dict(status="additional_original_only_mask_diagnostic_no_selection", source=source,
        script=pin(__file__), libraries=dict(numpy=np.__version__, scipy=scipy.__version__),
        protocol=dict(requested_after_legacy_results=True,
            timing_gain_coverage="Exact primary fixed production gain, lag and evaluation samples from frozen run; no fitting",
            mask="Original magnitude >= original peak * 10^(-60/20), shared by both models; -80 dB original-peak magnitude floor",
            stft="Stereo channel powers are not downmixed; periodic Hann, hop N/4, no padding or boundary extension",
            resolutions_samples=list(WINDOWS),
            limitation="Original-only mask omits candidate-only artifacts. Retain legacy union metrics alongside it. Neither metric is a perceptual threshold.",
            old_results="Read-only; every legacy union count, mean, P95 and unmasked spectral convergence must reproduce before reporting"),
        cases=[])
    verified = 0
    for row in run["cases"]:
        ref = read(row["input"]["hardware"])
        production = read(row["input"]["current_wav"])
        candidate = read(row["candidate_render"]["wav"])
        start, end = row["evaluated_reference_samples"]
        cstart, cend = row["evaluated_candidate_samples"]
        lag = row["input"]["lag_samples"]
        gain = row["fixed_gain"]
        if [cstart, cend] != [start + lag, end + lag] or gain != row["input"]["fixed_current_production_gain"]:
            raise ValueError("Unexpected timing/gain drift")
        sounds = dict(original=ref[start:end], production=production[cstart:cend] * gain,
                      w4=candidate[cstart:cend] * gain)
        if len({audio.shape for audio in sounds.values()}) != 1 or not all(np.isfinite(a).all() for a in sounds.values()):
            raise ValueError("Paired coverage/finiteness mismatch")
        item = dict(id=row["id"], hardware=row["input"]["hardware"], production=row["input"]["current_wav"],
                    candidate=row["candidate_render"]["wav"], reference_samples=[start, end],
                    candidate_samples=[cstart, cend], lag_samples=lag, fixed_gain=gain, resolutions=[])
        for n in WINDOWS:
            mags = {name: abs(signal.stft(audio, fs=SR, window="hann", nperseg=n,
                        noverlap=3*n//4, boundary=None, padded=False, axis=0)[2]) for name, audio in sounds.items()}
            original = mags["original"]
            peak = float(original.max())
            floor = max(peak * 10**(-80/20), 1e-30)
            threshold = max(peak * 10**(-60/20), 1e-30)
            mask = original >= threshold
            if not mask.any():
                raise ValueError("No original-active bins")
            frames = original.shape[-1]
            last_end = (frames - 1)*(n//4) + n
            if last_end > end-start:
                raise ValueError("STFT straddled evaluated support")
            observation = dict(window_samples=n, hop_samples=n//4, frames=frames,
                magnitude_shape=list(original.shape), original_peak=peak, magnitude_floor=floor,
                active_threshold=threshold, original_active_bins=int(mask.sum()),
                original_active_bins_by_channel=[int(mask[:, c, :].sum()) for c in range(2)],
                mask_packbits_sha256=hashlib.sha256(np.packbits(mask).tobytes()).hexdigest(),
                first_frame_samples=[start, start+n], last_frame_samples=[start+last_end-n, start+last_end], models={})
            for name in ("production", "w4"):
                model = mags[name]
                difference = abs(20*np.log10(np.maximum(model, floor)/np.maximum(original, floor)))
                union = np.maximum(original, model) >= threshold
                union_errors = masked_errors(difference, union)
                convergence = float(np.linalg.norm(model-original)/np.linalg.norm(original))
                prior = next(r for r in row[name]["stereo"]["multi_resolution_stft"] if r["window_samples"] == n)
                for actual, expected in ((union_errors["mean_db"], prior["log_spectral_error_db_mean"]),
                    (union_errors["p95_db"], prior["log_spectral_error_db_p95"]),
                    (convergence, prior["spectral_convergence"]),
                    (union_errors["bins"], prior["active_time_frequency_channel_bins"]), (frames, prior["frames"])):
                    if abs(actual-expected) > 1e-10:
                        raise ValueError(f"Legacy metric did not reproduce: {row['id']} / {n} / {name}")
                    verified += 1
                observation["models"][name] = dict(original_only=masked_errors(difference, mask),
                    legacy_pair_union=union_errors, candidate_only_bins=int(np.count_nonzero(union & ~mask)),
                    spectral_convergence=convergence)
            observation["delta_w4_minus_production"] = {
                policy: {metric: observation["models"]["w4"][policy][metric] - observation["models"]["production"][policy][metric]
                         for metric in ("mean_db", "p95_db", "bins")}
                for policy in ("original_only", "legacy_pair_union")}
            item["resolutions"].append(observation)
        item["summary_legacy_512_2048_8192"] = {}
        for name in ("production", "w4"):
            item["summary_legacy_512_2048_8192"][name] = {
                policy: float(np.mean([o["models"][name][policy]["mean_db"] for o in item["resolutions"] if o["window_samples"] != 1024]))
                for policy in ("original_only", "legacy_pair_union")}
        result["cases"].append(item)
        print(row["id"], item["summary_legacy_512_2048_8192"], flush=True)
    result["verified_legacy_metric_values"] = verified
    result["all_original_masks_shared"] = all(o["delta_w4_minus_production"]["original_only"]["bins"] == 0 for r in result["cases"] for o in r["resolutions"])
    (args.output/"results.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(args.output/"results.json", flush=True)


if __name__ == "__main__":
    main()
