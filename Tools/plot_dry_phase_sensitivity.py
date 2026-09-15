#!/usr/bin/env python3
"""Plot measured phase-control ranges; ranges are not confidence intervals."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    if args.output.exists():parser.error("Choose a new output image")
    data=json.loads(args.results.read_text())
    low_notes=[];self_env=[];hardware_env=[]
    for row in data["results"]:
        post=next(i for i in row["intervals"] if i["label"]=="after_training")
        hardware_env.append([r["error_db_p95"] for r in post["hardware_training_gain"]["rms_envelope"]])
        if row["phase_cycles"]==0:continue
        selected=[i for i in row["intervals"] if i["label"]=="isolated" and i["note"]["note"]==24]
        low_notes.append(np.mean([[s["spectral_convergence"] for s in i["self_fixed_gain1"]["multi_resolution_stft"]] for i in selected],axis=0))
        self_env.append([r["error_db_p95"] for r in post["self_fixed_gain1"]["rms_envelope"]])
    low_notes=np.array(low_notes);self_env=np.array(self_env);hardware_env=np.array(hardware_env)
    fig,axes=plt.subplots(1,2,figsize=(10.8,4.7),gridspec_kw={"width_ratios":[1.2,1]})
    fig.patch.set_facecolor("#faf9f5")
    for ax in axes:
        ax.set_facecolor("#faf9f5");ax.spines[["top","right"]].set_visible(False);ax.grid(axis="y",alpha=.2)
    windows=np.array([512,1024,2048,8192]);positions=np.arange(4)
    axes[0].vlines(positions,low_notes.min(axis=0),low_notes.max(axis=0),color="#175c88",linewidth=8)
    axes[0].plot(positions,low_notes.mean(axis=0),"o-",color="#175c88",linewidth=1.5)
    cycles=windows*(440*2**((24-69)/12))/44100
    axes[0].set_xticks(positions,[f"{n}\n{c:.2f} cycles" for n,c in zip(windows,cycles)])
    axes[0].set(xlabel="STFT window samples / cycles of MIDI 24",ylabel="Spectral convergence (phase variant vs phase 0)",ylim=(0,.9),title="Low bass: same patch, different phase")
    for i,label in enumerate(["10 ms","50 ms"]):
        for values,offset,color in [(self_env,-.13,"#175c88"),(hardware_env,.13,"#b75b35")]:
            axes[1].vlines(i+offset,values[:,i].min(),values[:,i].max(),color=color,linewidth=9)
            axes[1].plot(i+offset,values[:,i].mean(),"o",color=color)
    axes[1].plot([],[],color="#175c88",linewidth=5,label="Phase-only self-comparison")
    axes[1].plot([],[],color="#b75b35",linewidth=5,label="Hardware comparison, all 4 phases")
    axes[1].set_xticks([0,1],["10 ms","50 ms"])
    axes[1].set(xlabel="RMS window",ylabel="Full-sequence envelope error P95 (dB)",ylim=(0,30),title="Envelope statistics also depend on phase")
    axes[1].legend(frameon=False,fontsize=8,loc="upper right")
    fig.suptitle("Phase alone moves short-window audio scores",fontsize=15,x=.08,ha="left")
    fig.text(.08,.015,"Bars show observed ranges, not confidence intervals. No best phase was selected; self-distance is not subtracted from hardware error.",fontsize=8,color="#444444")
    fig.tight_layout(rect=(0,.035,1,.92))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(args.output,dpi=170)
    print(args.output)


if __name__=="__main__":main()
