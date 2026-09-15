#!/usr/bin/env python3
"""Preserve every frozen table model; summarize without selecting a model."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "high-note-wavetable-models-2026-09-15"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = json.loads(args.results.read_text())
    protocol = args.results.parent/"protocol-before-fit.json"
    if result["protocol"] != json.loads(protocol.read_text()):
        raise ValueError("Declared protocol changed")
    if result["protocol"]["tool_sha256"] != sha(ROOT/"Tools/fit_high_note_wavetable_models.py"):
        raise ValueError("Fitting tool changed")
    models = result["models"]
    if len(models) != 48 or any(not m["training"]["valid_full_rank"] for m in models):
        raise ValueError("Missing or invalid declared model")
    recovery = result["controls"]["cross_pitch_recovery"]
    recovery_error = max(r["different_pitch"]["relative_error_power"] for r in recovery)
    if recovery_error > 1e-12:
        raise ValueError("Planted cross-pitch waveform not recovered")
    old_path = ROOT/"Docs/fidelity/source-audits/high-note-saw-fir-aliases-2026-09-15.json"
    old = json.loads(old_path.read_text())
    old_control = next(m for m in old["results"] if m["fir_length"] == 13 and m["blep_correction"] == 1)
    new_control = next(m for m in models if m["model"]["id"] == "polyblep_control")
    differences = []
    for new, previous in zip(new_control["passages"], old_control["passages"]):
        if new["passage"]["samples_sha256"] != previous["passage"]["sample_sha256"]:
            raise ValueError("Prior control sample mismatch")
        for a, b in zip(new["aliases"]["lines"], previous["comparisons"]):
            if a["parent_harmonic"] != b["parent_harmonic"]:
                raise ValueError("Prior control hardware mask mismatch")
            differences.append(abs(a["error_db"]-b["model_minus_hardware_db"]))
    if len(differences) != 50 or max(differences) > 1e-8:
        raise ValueError("Prior polyBLEP/FIR comparison did not reproduce")
    summary = dict(
        model_count=len(models), selected_model=None,
        training_rank_all=14,
        maximum_training_condition=max(m["training"]["condition"] for m in models),
        minimum_training_waveform_error_power=min(m["training"]["relative_error_power"] for m in models),
        minimum_training_alias_rms_db=min(m["passages"][0]["aliases"]["rms_error_db"] for m in models),
        minimum_across_models_of_worst_different_pitch_alias_rms_db=min(
            max(p["aliases"]["rms_error_db"] for p in m["passages"][2:]) for m in models),
        aggregate_qualification="Descriptive range extrema, not model selection or acceptance thresholds. Unresolved bins are residual upper-bound proxies.",
        maximum_planted_cross_pitch_waveform_error_power=recovery_error,
        historical_polyblep_control=dict(source_path=str(old_path.relative_to(ROOT)), source_sha256=sha(old_path),
                                        compared_lines=len(differences), maximum_alias_error_difference_db=max(differences)),
        full_model_summary=[dict(id=m["model"]["id"], training_power_percent=100*m["training"]["relative_error_power"],
                                 waveform_power_percent=[100*p["fit"]["relative_error_power"] for p in m["passages"]],
                                 harmonic_rmse_db=[p["harmonic_rmse_db"] for p in m["passages"]],
                                 alias_rms_db=[p["aliases"]["rms_error_db"] for p in m["passages"]],
                                 resolved_alias_count=[p["aliases"]["candidate_resolved_lines"] for p in m["passages"]],
                                 passing_alias_count=[sum(q["candidate_passes_threshold"] for q in p["aliases"]["lines"]) for p in m["passages"]]) for m in models])
    args.output.mkdir(parents=True, exist_ok=True)
    summary_path = args.output/f"{PREFIX}.json"
    summary_path.write_text(json.dumps(dict(schema_version=1, input_results_sha256=sha(args.results),
                                           protocol_before_fit_sha256=sha(protocol), summary_tool_sha256=sha(__file__),
                                           summary=summary, **result), indent=2, allow_nan=False)+"\n")
    # All 48 declared models, in frozen declaration order. Gray cells have no
    # line passing the complete detector; their residual floors are not levels.
    matrix = np.array([r["alias_rms_db"] for r in summary["full_model_summary"]])
    passes = np.array([r["passing_alias_count"] for r in summary["full_model_summary"]])
    labels = []
    for m in models:
        d = m["model"]
        label = d["id"].replace("sampled_ramp", "Ramp").replace("finite_fourier", "Fourier")
        label = label.replace("fourier_output_nyquist-n1024", "Pitch cap Fs/2, N1024")
        label = label.replace("fourier_output_rate-n1024", "Pitch cap Fs, N1024")
        labels.append(label.replace("cubic_lagrange", "cubic").replace("_control", " control"))
    fig, ax = plt.subplots(figsize=(10, 16), layout="constrained")
    fig.get_layout_engine().set(rect=(0, .035, 1, .965))
    cmap = plt.get_cmap("magma").copy()
    cmap.set_bad("#b8bdc3")
    im = ax.imshow(np.ma.array(matrix, mask=passes == 0), cmap=cmap, vmin=0, vmax=45, aspect="auto")
    for i in range(len(models)):
        for j in range(5):
            ax.text(j, i, "below threshold" if passes[i, j] == 0 else f"{matrix[i, j]:.1f}",
                    ha="center", va="center", fontsize=7,
                    color="black" if passes[i, j] == 0 or matrix[i, j] > 29 else "white")
    ax.set_xticks(range(5), ["91 +100ms\ntrain", "91 +160ms", "93 +100ms", "88 +100ms", "86 +100ms"])
    ax.xaxis.tick_top()
    ax.set_yticks(range(len(labels)), labels, fontsize=8)
    ax.set_title("Frozen wavetable hypotheses: alias-level RMS error (dB)\nAll models share one waveform-trained 13-tap FIR; no model selected", pad=44)
    fig.colorbar(im, ax=ax, shrink=.5, label="Hardware-mask bin RMS dB error")
    fig.text(.5, .008, "Mixed resolved/unresolved bins remain in numeric cells; inspect per-line flags. Gray: no full-threshold lines.\nPreviously examined LP12 recordings; coefficients frozen after first window. This is not full-engine equivalence.",
             ha="center", fontsize=8)
    fig.savefig(args.output/f"{PREFIX}.png", dpi=140)
    plt.close(fig)
    print(json.dumps({k: v for k, v in summary.items() if k != "full_model_summary"}, indent=2))


if __name__ == "__main__":
    main()
