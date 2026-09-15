#!/usr/bin/env python3
"""Frozen 24-row source-sample sinc hypothesis; no production DSP edits."""
import argparse
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np
from scipy.io import wavfile
import fit_high_note_wavetable_models as prior
import audit_saw_alias_separation as separation

ROOT=Path(__file__).resolve().parents[1]
PROTOCOL=ROOT/"Docs/fidelity/source-audits/windowed-sinc-interpolation-proposal-2026-09-15.json"
BASELINE=ROOT/"Docs/fidelity/source-audits/high-note-wavetable-models-2026-09-15.json"
SR,SIZE=44100,3528
OFFSETS=np.arange(-6,7)
SOURCE_OFFSETS=np.arange(-3,5)


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(x):return hashlib.sha256(np.asarray(x,dtype="<f8").tobytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+"\n")


@lru_cache(maxsize=2)
def table(content):
    t=np.arange(32)/32
    if content=="sampled_ramp":return 2*t-1
    h=np.arange(1,16)
    return -2/np.pi*np.sum(np.sin(2*np.pi*t[:,None]*h)/h,axis=1)


def cutoff(note,model):
    rho=32*prior.aliases.f0(note)/SR
    if model["cutoff"]=="constant_half":return .5
    if rho<=1:return .5
    if rho<=1.5:return 1/3
    if rho<=2:return .25
    raise ValueError("Unspecified pitch-bank region")


def weights(u,q,lookup):
    if lookup=="floor_64":u=np.floor(64*u)/64
    t=SOURCE_OFFSETS-u[...,None]
    window=np.where(abs(t)<4,.5*(1+np.cos(np.pi*t/4)),0.)
    return 2*q*np.sinc(2*q*t)*window


def combine(values,a,mode):
    total=a.sum(axis=-1)
    if np.min(abs(total))<.1:raise ValueError("Unsafe coefficient sum")
    if mode=="normalized_direct":return np.sum(values*a,axis=-1)/total
    if mode=="unnormalized_direct":return np.sum(values*a,axis=-1)
    cumulative=np.cumsum(a[...,::-1],axis=-1)[...,::-1]
    return values[...,0]+np.sum(np.diff(values,axis=-1)*cumulative[...,1:],axis=-1)


def waveform(phase,note,model,indices):
    position=32*(phase+np.asarray(indices)*prior.aliases.f0(note)/SR)
    integer=np.floor(position).astype(np.int64)
    u=position-integer
    values=table(model["content"])[(integer[...,None]+SOURCE_OFFSETS)%32]
    return combine(values,weights(u,cutoff(note,model),model["lookup"]),model["weight_mode"])


def design(phase,note,model):
    # One extended waveform supplies every shifted FIR column. This avoids
    # computing identical interpolation samples 13 times at each search point.
    y=waveform(phase,note,model,np.arange(SIZE+12)-6)
    return np.lib.stride_tricks.sliding_window_view(y,13)[:,::-1]


def search(loss,count=256):
    cache={}
    def evaluate(p):
        p=float(p%1)
        if p not in cache:cache[p]=float(loss(p))
        return p,cache[p]
    scores=[evaluate(p) for p in np.arange(count)/count]
    global_index=min(range(count),key=lambda i:scores[i][1])
    minima=[i for i in range(count)if scores[i][1]<scores[(i-1)%count][1] and scores[i][1]<scores[(i+1)%count][1]]
    seeds=sorted(set(minima+[global_index]),key=lambda i:(scores[i][1],i))[:16]
    for index in seeds:
        best=scores[index];spacing=1/count
        for _ in range(3):
            local=[evaluate(p) for p in np.linspace(best[0]-spacing,best[0]+spacing,65)]
            best=min([best]+local,key=lambda p:p[1]);spacing/=32
    best=min(cache.items(),key=lambda p:p[1])
    return best[0],dict(unique_evaluations=len(cache),coarse_points=count,refinements=3,
                        seed_coarse_indices=seeds,seed_policy="16lowest strict cyclic coarse minima plus global minimum, training loss only",final_grid_spacing_cycles=spacing)


def train(x,note,model,count=256):
    x=x-x.mean();power=np.mean(x*x)
    def solve(p):
        matrix=np.column_stack((design(p,note,model),np.ones(SIZE)))
        coefficient,_,rank,s=np.linalg.lstsq(matrix,x,rcond=None)
        y=matrix@coefficient
        return float(np.mean((x-y)**2)/power),coefficient,int(rank),float(s[0]/s[-1])
    phase,search_info=search(lambda p:solve(p)[0],count)
    loss,coefficient,rank,condition=solve(phase)
    return dict(phase_cycles=phase,relative_error_power=loss,taps=coefficient[:-1].tolist(),dc=float(coefficient[-1]),
                rank=rank,condition=condition,valid_full_rank=rank==14 and condition<1e6,phase_search=search_info)


def evaluate(x,note,model,taps,count=256):
    x=x-x.mean();power=np.mean(x*x)
    def prediction(p):
        y=design(p,note,model)@taps
        return y-y.mean()
    phase,search_info=search(lambda p:np.mean((x-prediction(p))**2)/power,count)
    y=prediction(phase)
    return dict(phase_cycles=phase,relative_error_power=float(np.mean((x-y)**2)/power),
                phase_search=search_info,gain_refitted=False),y


def scalar_value(phase,note,model,index):
    # Independent scalar reconstruction with math.sinc expanded, explicit
    # circular lookup and direct sums; never calls weights/combine/waveform.
    import math
    p=32*(phase+index*440*2**((note-69)/12)/44100)
    i=math.floor(p);u=p-i
    if model["lookup"]=="floor_64":u=math.floor(64*u)/64
    rho=32*440*2**((note-69)/12)/44100
    q=.5 if model["cutoff"]=="constant_half" or rho<=1 else 1/3 if rho<=1.5 else .25
    a=[];y=[]
    for j in range(-3,5):
        t=j-u;sinc=1 if t==0 else math.sin(math.pi*2*q*t)/(math.pi*2*q*t)
        a.append(2*q*sinc*(.5*(1+math.cos(math.pi*t/4)) if abs(t)<4 else 0))
        n=(i+j)%32
        y.append(2*n/32-1 if model["content"]=="sampled_ramp" else -2/math.pi*sum(math.sin(2*math.pi*h*n/32)/h for h in range(1,16)))
    raw=sum(v*w for v,w in zip(y,a))
    if model["weight_mode"]=="normalized_direct":return raw/sum(a)
    if model["weight_mode"]=="unnormalized_direct":return raw
    return raw+(1-sum(a))*y[0]


def independent_planted(phase,note,model,taps):
    extended=np.array([scalar_value(phase,note,model,index)for index in range(-6,SIZE+6)])
    return np.convolve(extended,taps,mode="valid")


def controls(models,out):
    rows=[];rng=np.random.default_rng(4715257)
    algebra=[]
    for q in (.5,1/3,.25):
        for lookup in ("continuous","floor_64"):
            u=np.r_[np.arange(64)/64,(np.arange(64)+.371)/64]
            a=weights(u,q,lookup);values=rng.normal(size=a.shape)
            direct=np.sum(a*values,axis=1);cumulative=np.cumsum(a[:,::-1],axis=1)[:,::-1]
            reconstructed=values[:,0]*a.sum(axis=1)+np.sum(np.diff(values,axis=1)*cumulative[:,1:],axis=1)
            forced=combine(values,a,"unnormalized_forced_base")
            algebra.append(dict(q=q,lookup=lookup,sum_min=float(a.sum(axis=1).min()),sum_max=float(a.sum(axis=1).max()),
                                direct_cumulative_error=float(max(abs(direct-reconstructed))),
                                forced_error_identity=float(max(abs(forced-direct-(1-a.sum(axis=1))*values[:,0]))),
                                constant_normalization_error=float(max(abs(combine(np.ones_like(values)*.37,a,"normalized_direct")-.37)))))
    algebra_max=max(max(r[k]for k in ("direct_cumulative_error","forced_error_identity","constant_normalization_error"))for r in algebra)
    if algebra_max>1e-12:raise ValueError("Algebra control failed")
    scalar_error=0.;column_error=0.;continuity_error=0.;bin_error=0.;boundaries=[]
    for model in models:
        for note in (69,91,96):
            for phase in (.321,.217,-.043):
                indices=np.array([-41,-1,0,1,37,122])
                actual=waveform(phase,note,model,indices)
                expected=np.array([scalar_value(phase,note,model,int(i))for i in indices])
                scalar_error=max(scalar_error,float(max(abs(actual-expected))))
        vector=design(.321,91,model)
        explicit=waveform(.321,91,model,np.arange(SIZE)[:,None]-OFFSETS[None,:])
        column_error=max(column_error,float(abs(vector-explicit).max()))
        for integer in (0,31):
            phases=np.array([(integer+k/64)/32+epsilon for k in range(64)for epsilon in (-1e-12,0.,1e-12)])
            actual=waveform(phases,91,model,np.zeros(len(phases)))
            expected=np.array([scalar_value(float(p),91,model,0)for p in phases])
            bin_error=max(bin_error,float(abs(actual-expected).max()))
        if model["lookup"]=="continuous":
            # Same source knot approached from both sides, including periodic wrap.
            for knot in (0,1,16,31):
                x=waveform(knot/32-1e-10,91,model,np.array([0]))
                y=waveform(knot/32+1e-10,91,model,np.array([0]))
                expected=0.
                if model["weight_mode"]=="unnormalized_forced_base":
                    total=float(weights(np.array(0.),cutoff(91,model),"continuous").sum())
                    values=table(model["content"])
                    expected=(1-total)*(values[(knot-3)%32]-values[(knot-4)%32])
                error=float(abs(y[0]-x[0]-expected))
                continuity_error=max(continuity_error,error)
                boundaries.append(dict(model=model["id"],knot=knot,right_minus_left=float(y[0]-x[0]),expected_jump=float(expected),error=error))
    result=dict(algebra=algebra,scalar_maximum_error=scalar_error,shifted_column_maximum_error=column_error,
                scalar_bin_boundary_maximum_error=bin_error,continuous_boundary_identity_maximum_error=continuity_error,boundary_checks=boundaries,planted_recovery=rows,passed=False)
    save(out/"controls.json",result)
    if scalar_error>1e-11 or column_error>1e-11 or bin_error>1e-11 or continuity_error>1e-6:raise ValueError("Lookup/indexing control failed")
    taps=np.array([0,0,0,0,-.03,.11,.33,.09,-.01,0,0,0,0])
    # Every weight evaluation, both table contents, and both lookup policies;
    # banked policy includes q1/3 on train and q1/2 orq1/4 on check.
    for model in models:
        if model["cutoff"]!="pitch_bank":continue
        x=independent_planted(.321,91,model,taps)
        trained=train(x,91,model)
        checked=[]
        for note,phase in ((93,.217),(88,-.043),(96,.217)):
            truth=independent_planted(phase,note,model,taps)
            fit,_=evaluate(truth,note,model,np.array(trained["taps"]))
            checked.append(dict(note=note,planted_phase=phase,fit=fit))
        row=dict(model=model,training=trained,checks=checked)
        # Off-grid floor64 cases additionally compare a much denser independent
        # coarse search. This gate precedes loading any hardware samples.
        if model["lookup"]=="floor_64":
            dense=train(x,91,model,4096)
            row["dense_training"]=dense
            if trained["relative_error_power"]>dense["relative_error_power"]+1e-6:
                row["phase_guard_failed"]=True
        rows.append(row);save(out/"controls.json",result)
        print("control",model["id"],trained["relative_error_power"],[r["fit"]["relative_error_power"]for r in checked],flush=True)
        if (not trained["valid_full_rank"] or trained["relative_error_power"]>1e-6
                or any(r["fit"]["relative_error_power"]>1e-6 for r in checked)or row.get("phase_guard_failed")):
            raise ValueError("Planted recovery/phase-search gate failed; hardware not loaded")
    result["passed"]=True;save(out/"controls.json",result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--sources",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    protocol=json.loads(PROTOCOL.read_text())
    if len(protocol["models"])!=24:raise ValueError("Expected24frozenrows")
    for name,expected in {**protocol["source_receipts"],**protocol["dependency_sha256"]}.items():
        if sha(ROOT/name)!=expected:raise ValueError("Pinned dependency changed: "+name)
    run=dict(protocol=protocol,proposal_sha256=sha(PROTOCOL),tool_sha256=sha(__file__),
             extra_helper_sha256={Path(separation.__file__).name:sha(separation.__file__)})
    save(a.output/"protocol-before-controls.json",run)
    started=time.monotonic();control=controls(protocol["models"],a.output)
    baseline=json.loads(BASELINE.read_text());sources=[]
    historical=[]
    for model in baseline["models"]:
        if model["model"]["id"]not in protocol["historical_comparators"]:continue
        for i,row in enumerate(model["passages"]):
            y=prior.design(row["fit"]["phase_cycles"],row["passage"]["note"],model["model"])@np.array(model["training"]["taps"])
            if i:y-=y.mean()
            if digest(y)!=row["predicted_pcm_float64_sha256"]:raise ValueError("Frozen historical prediction changed")
            historical.append(dict(model=model["model"]["id"],passage=row["passage"],verified_prediction_sha256=digest(y)))
    if len(historical)!=20:raise ValueError("Missing historical comparator")
    for entry in baseline["protocol"]["source_records"]:
        path=a.sources/Path(entry["path"]).name
        if sha(path)!=entry["sha256"]:raise ValueError("Original input changed")
        sources.append(entry)
    mp3=a.sources/"roland_sh-201_-_filter_demo_-_lpf12_q000.mp3";wav=a.output/"hardware-lp12.wav"
    command=["ffmpeg","-v","error","-nostdin","-i",str(mp3),"-c:a","pcm_f32le",str(wav)]
    subprocess.run(command,check=True);rate,audio=wavfile.read(wav)
    if rate!=SR or audio.ndim!=1 or not np.isfinite(audio).all():raise ValueError("Invalid decode")
    passages=[baseline["protocol"]["training"]]+baseline["protocol"]["validation"]
    signals=[];references=[];joint_references=[]
    for i,passage in enumerate(passages):
        x=audio[passage["start_sample"]:passage["end_sample"]].astype(float)
        if digest(x)!=passage["samples_sha256"]:raise ValueError("Hardware sample identity changed")
        reference=prior.aliases.measure(x,.04,passage["note"],0.)
        if reference!=baseline["references"][i]:raise ValueError("Hardware mask/detector changed")
        targets=[(r["parent_harmonic"],r["expected_hz"])for r in reference["tested_alias_lines"]if r["rate_hypothesis_hz"]==SR and r["passes_line_threshold"]]
        joint_references.append(separation.joint(x,passage["note"],2,targets)[0]);signals.append(x);references.append(reference)
    result=dict(schema_version=1,**run,controls=control,source_records=sources,decode_command=command,
                decoded_sha256=sha(wav),references=references,joint_references=joint_references,
                historical_prediction_checks=historical,
                historical_comparators=[r for r in baseline["models"]if r["model"]["id"]in protocol["historical_comparators"]],
                models=[],selected_model=None,production_dsp_changed=False)
    for model in protocol["models"]:
        fit=train(signals[0],91,model);rows=[]
        if fit["valid_full_rank"]:
            taps=np.array(fit["taps"])
            for i,(passage,x,reference,joint_reference)in enumerate(zip(passages,signals,references,joint_references)):
                if i==0:
                    metrics=dict(phase_cycles=fit["phase_cycles"],relative_error_power=fit["relative_error_power"],gain_refitted=True)
                    y=design(fit["phase_cycles"],passage["note"],model)@taps
                else:metrics,y=evaluate(x,passage["note"],model,taps)
                alias=prior.compare_lines(reference,y,passage["note"])
                targets=[(r["parent_harmonic"],r["expected_hz"])for r in alias["lines"]]
                joint=separation.joint(y,passage["note"],2,targets)[0]
                for line,hardware in zip(joint["lines"],joint_reference["lines"]):
                    line["hardware_db"]=hardware["relative_h1_db"];line["error_db"]=line["relative_h1_db"]-line["hardware_db"]
                joint["rms_error_db"]=float(np.sqrt(np.mean([r["error_db"]**2 for r in joint["lines"]])))
                harmonic_error=prior.harmonic_ratios(y,passage["note"])[1:]-prior.harmonic_ratios(x,passage["note"])[1:]
                rows.append(dict(passage=passage,fit=metrics,aliases=alias,joint_first_second=joint,
                                 harmonic_error_h2_h8_db=harmonic_error.tolist(),harmonic_rmse_db=float(np.sqrt(np.mean(harmonic_error**2))),predicted_float64_sha256=digest(y)))
        result["models"].append(dict(model=model,training=fit,passages=rows))
        save(a.output/"results-partial.json",result)
        print("model",model["id"],fit["relative_error_power"],[round(r["aliases"]["rms_error_db"],3)for r in rows],flush=True)
    result["elapsed_seconds"]=time.monotonic()-started
    if sha(__file__)!=run["tool_sha256"]or sha(PROTOCOL)!=run["proposal_sha256"]:raise ValueError("Run definition changed")
    save(a.output/"results.json",result)


if __name__=="__main__":main()
