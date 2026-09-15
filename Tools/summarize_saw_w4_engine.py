#!/usr/bin/env python3
"""Summarize the complete, frozen W4 dry comparison without selecting a model."""
import argparse
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--results", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    result = json.loads(a.results.read_text())
    fig, axes = plt.subplots(2, 5, figsize=(15, 6.6), sharex=True, sharey=True, constrained_layout=True)
    colors = {"production": "#b15a3b", "w4": "#008e93"}
    rows = []
    for i, slope in enumerate(result["slopes"]):
        for j, window in enumerate(slope["exploratory_five_windows"]):
            ax = axes[i, j]
            observed = window["models"]["production"]["harmonics"]["hardware_relative_h1_db"]
            ax.plot(range(1, 9), observed, "o-", color="#202124", label="Hardware", linewidth=1.5, markersize=4)
            errors = []
            for name in ("production", "w4"):
                h = window["models"][name]["harmonics"]
                errors.append(h["h2_to_h8_rms_error_db"])
                ax.plot(range(1, 9), h["model_relative_h1_db"], "o-", color=colors[name],
                        label="Production" if name == "production" else "Frozen W4", linewidth=1.3, markersize=3)
            note, offset = window["passage"]["note"], window["passage"]["offset_seconds"]
            ax.set_title(f"MIDI {note} +{round(offset*1000)} ms\nH2–H8: {errors[0]:.2f} → {errors[1]:.2f} dB", fontsize=9.5)
            ax.set_xticks(range(1, 9)); ax.set_ylim(-65, 2); ax.grid(alpha=.2)
            if j == 0:
                ax.set_ylabel(f"LP{slope['slope']} · dB relative to H1")
            if i == 1:
                ax.set_xlabel("Harmonic")
        for name, model in slope["models"].items():
            for support, value in model["primary_fixed_gain"].items():
                rows.append({"slope": slope["slope"], "model": name, "support": support,
                             "spectral_convergence": [v["spectral_convergence"] for v in value["stft"]],
                             "hardware_log_error_mean_db": [v["hardware_only_log_error"]["mean_db"] for v in value["stft"]],
                             "rms_error_mean_db": [v["hardware_only_error"]["mean_db"] for v in value["rms"]]})
    axes[0, 0].legend(fontsize=8)
    fig.suptitle("Frozen W4 source through the complete engine · unchanged gain and timing\n"
                 "All five windows are exploratory; LP12 MIDI 91 +100 ms trained the coefficients. Later 91 overlaps it.", fontsize=11.5)
    fig.savefig(a.output/"high-note-harmonics.png", dpi=150)
    plt.close(fig)
    summary = {"results": {"path": str(a.results.resolve()), "sha256": sha(a.results)},
               "tool_sha256": sha(__file__), "metrics": rows,
               "plot_sha256": sha(a.output/"high-note-harmonics.png"),
               "selection": "none; all outcomes retained in the full results",
               "hardware_equivalence": "not_established"}
    (a.output/"summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False)+"\n")


if __name__ == "__main__":
    main()
