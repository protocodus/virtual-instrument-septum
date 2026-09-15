#!/usr/bin/env python3
"""Plot the bounded hardware and planted-zero smoothing diagnostics."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--results",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():
        raise ValueError("Choose a new plot path")
    r=json.loads(args.results.read_text())
    fig,axes=plt.subplots(1,2,figsize=(12,4.8),sharey=True)
    labels={"neighbors-clean":"Fixed neighbors, clean",
            "neighbors-opus128":"Fixed neighbors, Opus",
            "neighbors-phase-quarter":"Quarter-cycle phase change"}
    for condition in labels:
        rows=[x for x in r["hardware_comparisons"] if x["condition"]==condition]
        axes[0].plot([x["tau_ms"] for x in rows],[x["later_normalized_rmse"] for x in rows],
                     marker="o",ms=4,label=labels[condition])
    for control in r["planted_controls"]:
        if control["planted_tau_ms"]:
            continue
        rows=control["scores"]
        axes[1].plot([x["tau_ms"] for x in rows],[x["later_normalized_rmse"] for x in rows],
                     marker="o",ms=4,label=labels[control["condition"]])
    axes[0].set_title("Hardware: model preference changes with phase")
    axes[1].set_title("Known zero smoothing: phase can imply 0.5 ms")
    for ax in axes:
        ax.set_xlabel("Tested smoothing time constant (ms)")
        ax.set_xlim(-.15,5.15)
        ax.grid(alpha=.2)
        ax.legend(fontsize=8,loc="upper left")
    axes[0].set_ylabel("Later-edge RMSE / observed step size")
    fig.suptitle("Public S&H pitch: sub-ms smoothing is not identified",fontsize=14)
    fig.text(.5,.01,"One time shift fitted on four early edges; 19 later checks. Synthetic phase/codec controls are not a complete hardware model.",ha="center",fontsize=9)
    fig.tight_layout(rect=(0,.04,1,.94))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(args.output,dpi=150)


if __name__=="__main__":
    main()
