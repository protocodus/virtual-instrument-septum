#!/usr/bin/env python3
"""Check Saw alias measurement cross-talk without refitting a DSP candidate.

Compare the frozen residual/Hann detector with simultaneous main-harmonic and
alias-branch regression. Center amplitudes and window averages are distinct
estimands for a moving signal; their difference is not a correction factor.
"""
import argparse
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import subprocess

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np
from scipy.io import wavfile
import analyze_deepsonic_saw_aliases as aliases
import fit_high_note_saw_asymmetric_kernels as kernels

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "Docs/fidelity/source-audits/deepsonic-saw-asymmetric-kernels-2026-09-15.json"
SR, SIZE = 44100, 3528


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(x):
    return hashlib.sha256(np.asarray(x, dtype="<f8").tobytes()).hexdigest()


@lru_cache(maxsize=12)
def basis(note, folds):
    base = aliases.f0(note)
    t = (np.arange(SIZE) - (SIZE-1)/2) / SR
    u = t / .04
    columns = [np.ones(SIZE), u, u*u]
    components = []
    for h in range(1, int(20000/base)+1):
        components.append(dict(kind="harmonic", harmonic=h, frequency_hz=h*base,
                               index=len(columns)))
        co, si = np.cos(2*np.pi*h*base*t), np.sin(2*np.pi*h*base*t)
        columns.extend((co, si, u*co, u*si, u*u*co, u*u*si))
    for fold in range(1, folds+1):
        for h in range(1, int((fold*SR+20000)/base)+1):
            f = abs(fold*SR-h*base)
            if not 100 <= f < 20000:
                continue
            if min(abs(f-c["frequency_hz"]) for c in components) < 1.:
                raise ValueError("Coincident components require a different protocol")
            components.append(dict(kind="alias", fold=fold, harmonic=h,
                                   frequency_hz=f, index=len(columns)))
            co, si = np.cos(2*np.pi*f*t), np.sin(2*np.pi*f*t)
            columns.extend((co, si, u*co, u*si))
    matrix = np.column_stack(columns)
    left, singular, right = np.linalg.svd(matrix, full_matrices=False)
    condition = float(singular[0]/singular[-1])
    if condition > 100:
        raise ValueError(f"Ill-conditioned joint model: {condition}")
    return matrix, (right.T/singular)@left.T, condition, components


def joint(x, note, folds, targets):
    matrix, inverse, condition, components = basis(note, folds)
    coefficient = inverse @ x
    residual = x-matrix@coefficient
    h1 = np.hypot(coefficient[3], coefficient[4])
    noise_variance = float(np.dot(residual, residual)/(len(x)-len(coefficient)))
    inverse_power = np.sum(inverse*inverse, axis=1)
    rows = []
    for h, expected in targets:
        c = next(c for c in components if c["kind"] == "alias"
                 and c["fold"] == 1 and c["harmonic"] == h)
        if abs(c["frequency_hz"]-expected) > 1e-7:
            raise ValueError("Target line changed")
        i = c["index"]
        amplitude = float(np.hypot(coefficient[i], coefficient[i+1]))
        noise = np.sqrt(noise_variance*(inverse_power[i]+inverse_power[i+1]))
        rows.append(dict(parent_harmonic=h, expected_hz=expected,
            relative_h1_db=float(20*np.log10(max(amplitude, 1e-30)/h1)),
            coefficient_snr_proxy_db=float(20*np.log10(max(amplitude, 1e-30)/max(noise, 1e-30)))))
    return dict(condition=condition, columns=matrix.shape[1],
                residual_power_fraction=float(np.mean(residual**2)/np.var(x)),
                lines=rows), coefficient


def original_detector(x, note, targets):
    # The frozen detector accepts a complete clip and extracts a window around
    # onset+offset. Supply exactly one window, without modifying its contents.
    measurement = aliases.measure(x, 0., note, .04)
    rows = []
    for h, expected in targets:
        found = next(r for r in measurement["tested_alias_lines"]
                     if r["rate_hypothesis_hz"] == SR and r["parent_harmonic"] == h)
        rows.append(dict(parent_harmonic=h, expected_hz=expected,
            relative_h1_db=found["relative_h1_db"],
            passes_line_threshold=found["passes_line_threshold"]))
    return dict(lines=rows)


def controls(note, targets, source_coefficients):
    base = aliases.f0(note)
    t = (np.arange(SIZE)-(SIZE-1)/2)/SR
    h1 = .1
    _, _, _, first_components = basis(note, 1)
    first_lookup = {(c["kind"], c.get("fold"), c["harmonic"]): c for c in first_components}
    original_h1 = np.hypot(source_coefficients[3], source_coefficients[4])
    rows = []
    for phase in (.137, .713):
        for extra_fold in (False, True):
            x = np.zeros(SIZE)
            truth = {}
            # Generate tones directly, independently of the regression matrix
            # construction and its sine/cosine-column coefficient indexing.
            for h in range(1, int(20000/base)+1):
                prior = first_lookup[("harmonic", None, h)]["index"]
                amplitude = h1*np.hypot(source_coefficients[prior], source_coefficients[prior+1])/original_h1
                x += amplitude*np.cos(2*np.pi*(h*base*t+phase*h))
            for fold in (1, 2):
                for h in range(1, int((fold*SR+20000)/base)+1):
                    f = abs(fold*SR-h*base)
                    if not 100 <= f < 20000:
                        continue
                    if fold == 1:
                        prior = first_lookup[("alias", 1, h)]["index"]
                        amplitude = h1*np.hypot(source_coefficients[prior], source_coefficients[prior+1])/original_h1
                        truth[h] = float(20*np.log10(max(amplitude, 1e-30)/h1))
                    else:
                        amplitude = h1*10**(-45/20) if extra_fold else 0.
                    x += amplitude*np.cos(2*np.pi*(f*t+phase*h)+.31*fold)
            estimates = {"original": original_detector(x, note, targets),
                         "joint_first": joint(x, note, 1, targets)[0],
                         "joint_first_second": joint(x, note, 2, targets)[0]}
            for method, estimate in estimates.items():
                for line in estimate["lines"]:
                    line["truth_dbc"] = truth[line["parent_harmonic"]]
                    line["error_db"] = line["relative_h1_db"]-line["truth_dbc"]
            recovery = max(abs(r["error_db"]) for r in estimates["joint_first_second"]["lines"])
            if recovery > 1e-7:
                raise ValueError("Planted simultaneous-regression recovery failed")
            rows.append(dict(note=note, phase_cycles=phase, second_fold_stress=extra_fold,
                             sample_sha256=digest(x), estimates=estimates))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    baseline = json.loads(BASELINE.read_text())
    if baseline["script_sha256"] != sha(kernels.__file__):
        raise ValueError("Frozen candidate fitter changed")
    for name, expected in baseline["dependency_sha256"].items():
        if sha(ROOT/"Tools"/name) != expected:
            raise ValueError("Frozen candidate helper changed: "+name)
    model = next(m for m in baseline["models"] if m["id"] == "asymmetric-W4")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    protocol = dict(status="measurement_cross_talk_audit_not_candidate_fit",
        passages=[s["passage"] for s in model["scores"]],
        policy="Keep exact prior LP12 hardware-only line masks for LP12, LP24 and frozen W4. Compare unchanged residual/Hann detector with joint quadratic main harmonics and linear complex first-branch aliases, then additionally second-fold aliases. No frequency, phase, gain, coefficient or mask refit of W4.",
        controls="Two fixed phase patterns per passage. Stationary harmonics and both first branches use LP12 joint magnitudes as planted known values. Add or omit a second-fold stress family at -45 dB/H1 per line. This stress amplitude does not estimate hardware second-fold levels.",
        limitation="Center complex amplitudes and Hann-averaged magnitudes differ for moving signals. Differences are sensitivity diagnostics, not a corrected hardware truth. Residual-based coefficient SNR is a model-error proxy, not a confidence interval. Prior passages have been explored; no blind holdout claim.")
    (out/"protocol.json").write_text(json.dumps(protocol, indent=2)+"\n")
    previous, passages, low_signals, command, wav = kernels.load_inputs(args.sources, out)
    catalog = json.loads(aliases.CATALOG.read_text())
    asset = next(a for a in catalog["assets"] if Path(a["path"]).name == "roland_sh-201_-_filter_demo_-_lpf24_q000.mp3")
    mp3 = args.sources/Path(asset["path"]).name
    if sha(mp3) != asset["sha256"]:
        raise ValueError("LP24 original changed")
    high_wav = out/"hardware-lp24.wav"
    high_command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(mp3), "-c:a", "pcm_f32le", str(high_wav)]
    subprocess.run(high_command, check=True)
    rate, high = wavfile.read(high_wav)
    if rate != SR or high.ndim != 1 or not np.isfinite(high).all():
        raise ValueError("Unexpected LP24 decode")
    result = dict(schema_version=1, protocol=protocol, script_sha256=sha(__file__),
        baseline_sha256=sha(BASELINE), catalog_sha256=sha(aliases.CATALOG),
        dependencies={Path(m.__file__).name: sha(m.__file__) for m in (aliases, kernels, kernels.symmetric, kernels.fir)},
        sources=[dict(original=previous["source"], decode_command=command, decoded_sha256=sha(wav)),
                 dict(original=asset, decode_command=high_command, decoded_sha256=sha(high_wav))],
        original_midi=previous["original_midi"], windows=[], controls=[])
    for p, low, score, fit in zip(passages, low_signals, model["scores"], [model["training"]]+model["evaluations"]):
        if p != score["passage"]:
            raise ValueError("Frozen passage changed")
        note = p["note"]
        targets = [(r["parent_harmonic"], r["expected_hz"]) for r in score["aliases"]["lines"]]
        prediction = kernels.design(fit["phase"], note, 4.)@np.array(model["training"]["coefficients"])
        for name, x in (("hardware_lp12", low), ("hardware_lp24", high[p["start_sample"]:p["end_sample"]].astype(float)), ("frozen_W4", prediction)):
            if len(x) != SIZE:
                raise ValueError("Window coverage changed")
            first, coefficient = joint(x, note, 1, targets)
            estimates = dict(original=original_detector(x, note, targets), joint_first=first,
                             joint_first_second=joint(x, note, 2, targets)[0])
            if name == "hardware_lp12":
                error = max(abs(r["relative_h1_db"]-old["hardware_dbc"]) for r, old in zip(estimates["original"]["lines"], score["aliases"]["lines"]))
                if error > 1e-8:
                    raise ValueError("Frozen detector no longer reproduces baseline")
                result["controls"].extend(controls(note, targets, coefficient))
            elif name == "frozen_W4":
                expected_error = score["relative_error_power"]
                actual_error = np.mean(((low-low.mean())-(x-x.mean()))**2)/np.var(low)
                if abs(expected_error-actual_error) > 1e-12:
                    raise ValueError("Frozen candidate waveform no longer reproduces baseline")
            result["windows"].append(dict(id=name, passage=p, sample_sha256=digest(x), estimates=estimates))
        print(note, p["offset_seconds"], "complete", flush=True)
    (out/"results.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(out/"results.json")


if __name__ == "__main__":
    main()
