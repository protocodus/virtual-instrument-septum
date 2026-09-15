#!/usr/bin/env python3
"""Retain sinc experiment controls, amendments and every completed model."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
PREFIX="high-note-sinc-models-2026-09-15"
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    p.add_argument("--history",type=Path,default=ROOT/"Docs/fidelity/source-audits"/f"{PREFIX}.json",
                   help="Retained audit supplies source-free failure receipts when original scratch runs are absent")
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    controls=json.loads((a.run/"controls.json").read_text())
    protocol=json.loads((a.run/"protocol-before-controls.json").read_text())
    full=a.run/"results.json"
    if full.exists():
        run=json.loads(full.read_text())
        if not controls["passed"] or len(run["models"])!=24:raise ValueError("Incomplete run")
    else:
        if controls["passed"]:raise ValueError("Hardware results still pending")
        run=dict(**protocol,controls=controls,models=[],hardware_fit_performed=False,
                 selected_model=None,production_dsp_changed=False)
    retained=[]
    for name in ("sinc-v1/rejected-continuity-guard.json","sinc-v2/controls.json"):
        path=a.run.parent/name
        if path.exists():
            retained.append(dict(path=str(path),sha256=sha(path),receipt=json.loads(path.read_text())))
        else:
            old=json.loads(a.history.read_text())
            entry=next(r for r in old["source_free_failed_controls"]if r["path"].endswith(name))
            encoded=(json.dumps(entry["receipt"],indent=2,allow_nan=False)+"\n").encode()
            if hashlib.sha256(encoded).hexdigest()!=entry["sha256"]:raise ValueError("Historical failure receipt changed")
            retained.append(entry)
    independent=ROOT/"Docs/fidelity/source-audits/windowed-sinc-math-independent-review-2026-09-15.json"
    review=dict(path=str(independent),sha256=sha(independent),receipt=json.loads(independent.read_text()))
    if run["tool_sha256"]!=sha(ROOT/"Tools/fit_high_note_sinc_models.py") or review["receipt"]["tested_tool_sha256"]!=run["tool_sha256"]:
        raise ValueError("Current/reviewed fitting tool mismatch")
    rows=[]
    for model in run["models"]:
        valid=model["training"]["valid_full_rank"]
        rows.append(dict(model=model["model"],valid_training=valid,
                         rejection=None if valid else dict(rank=model["training"]["rank"],condition=model["training"]["condition"]),
                         training_power_percent=model["training"]["relative_error_power"]*100,
                         waveform_error_power_percent=[r["fit"]["relative_error_power"]*100 for r in model["passages"]],
                         main_harmonic_rmse_db=[r["harmonic_rmse_db"]for r in model["passages"]],
                         original_alias_rms_db=[r["aliases"]["rms_error_db"]for r in model["passages"]],
                         joint_alias_rms_db=[r["joint_first_second"]["rms_error_db"]for r in model["passages"]],
                         full_threshold_line_count=[sum(q["candidate_passes_threshold"]for q in r["aliases"]["lines"])for r in model["passages"]]))
    valid_rows=[r for r in rows if r["valid_training"]]
    summary=dict(model_rows=rows,models=len(rows),valid_models=len(valid_rows),
                 invalid_model_ids=[r["model"]["id"]for r in rows if not r["valid_training"]],
                 range_policy="Descriptive extrema include valid training rows only. Invalid rows remain in report and plot without replacement.",selected_model=None,
                 maximum_planted_cross_pitch_power_error=max(r["fit"]["relative_error_power"]for row in controls["planted_recovery"]for r in row["checks"]))
    if rows:
        summary.update(minimum_training_alias_rms_db=min((r["original_alias_rms_db"][0]for r in valid_rows),default=None),
                       minimum_across_models_of_worst_other_pitch_alias_rms_db=min((max(r["original_alias_rms_db"][2:])for r in valid_rows),default=None))
        fig,axes=plt.subplots(1,2,figsize=(15,11),layout="constrained",sharey=True)
        fig.get_layout_engine().set(rect=(0,.04,1,.96))
        names=[]
        for row in rows:
            m=row["model"]
            names.append(" / ".join(("Ramp"if m["content"]=="sampled_ramp"else"Fourier",
                "fixed"if m["cutoff"]=="constant_half"else"bank",
                "cont"if m["lookup"]=="continuous"else"64bin",
                {"normalized_direct":"norm","unnormalized_direct":"raw","unnormalized_forced_base":"forced"}[m["weight_mode"]])))
        for axis,key,title in zip(axes,("original_alias_rms_db","joint_alias_rms_db"),("Original residual/Hann detector","Joint first + second fold sensitivity")):
            matrix=np.array([r[key]if r["valid_training"]else [np.nan]*5 for r in rows])
            counts=np.array([r["full_threshold_line_count"]if r["valid_training"]else [0]*5 for r in rows])
            masked=np.ma.array(matrix,mask=counts==0);cmap=plt.get_cmap("magma").copy();cmap.set_bad("#b8bdc3")
            im=axis.imshow(masked,vmin=0,vmax=60,aspect="auto",cmap=cmap)
            for i in range(len(rows)):
                for j in range(5):
                    label="invalid fit"if not rows[i]["valid_training"]else "below\nthreshold"if counts[i,j]==0 else f"{matrix[i,j]:.1f}"
                    axis.text(j,i,label,ha="center",va="center",fontsize=7,color="black"if counts[i,j]==0 or matrix[i,j]>39 else "white")
            axis.set_xticks(range(5),["91train","91later","93","88","86"]);axis.xaxis.tick_top();axis.set_title(title,pad=24)
            axis.set_yticks(range(len(names)),names,fontsize=7)
        fig.colorbar(im,ax=axes,shrink=.65,label="Hardware-mask alias-bin RMS error / dB")
        fig.suptitle("All 24 frozen source-sample sinc models; equal 13-tap nuisance FIR; no selected winner")
        fig.text(.5,.01,"All bins remain in scores. Gray uses original detector threshold; unresolved residuals are not precise line levels.\nCheck pitches were previously inspected. This is exploratory transfer testing, not engine equivalence.",ha="center",fontsize=8)
        fig.savefig(a.output/f"{PREFIX}.png",dpi=140);plt.close(fig)
    result=dict(schema_version=1,summary_tool_sha256=sha(__file__),input_run_path=str(a.run),hardware_fit_performed=bool(rows),
                input_results_sha256=sha(full)if full.exists()else None,source_free_failed_controls=retained,
                independent_math_review=review,summary=summary,run=run)
    (a.output/f"{PREFIX}.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps({k:v for k,v in summary.items()if k!="model_rows"},indent=2))


if __name__=="__main__":main()
