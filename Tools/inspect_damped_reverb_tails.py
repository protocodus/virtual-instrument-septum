#!/usr/bin/env python3
"""Original Club/Ambient tail band coverage; no DSP render or decay fit.

Intervals were frozen from complete source RMS/spectrogram inspection before
band calculations. This follows known damped-preset envelope counterexamples.
It does not constitute independent preset selection or identify a damping law.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
from scipy import signal
from scipy.io import wavfile
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from extract_reference_patch import read_bank, parse_bank, encode_syx

ROOT = Path(__file__).resolve().parents[1]
CONFIG = {
    "bass-05": dict(name="Club Bass", bank="BASS", number=5,
        mp3="TOP8_ClubBass.mp3", mp3_sha256="4376b5196eb9be233e85a4dc528dda1bdb6e4f8ba01a7163aa298c8ebbdb68a4",
        preview=[1.6,3.45]),
    "lead-07": dict(name="Ambient SQR", bank="LEAD", number=7,
        mp3="TOP8_AmbientSQR.mp3", mp3_sha256="d113bb3d65c34bb6827d29561e29dd9c9d4a6236143d5528685643f84a86e565",
        preview=[10.6,14.628571428571428]),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def db(power):
    return float(10*np.log10(max(float(power),1e-30)))


def crop(y, sr, times):
    lo, hi = [round(t*sr) for t in times]
    assert 0 <= lo < hi <= len(y)
    return y[lo:hi]


def channels(y):
    return {"stereo": y, "mid": y.mean(axis=1,keepdims=True),
            "side": ((y[:,0]-y[:,1])/2)[:,None]}


def bands(y, sr, edges):
    # Density scaling followed by df integration gives a band mean-square
    # estimate. Identical fixed 1024-sample Welch windows apply to quiet/tail.
    assert len(y) >= 1024
    f, p = signal.welch(y, sr, window="hann", nperseg=1024,
        noverlap=768, detrend=False, axis=0, scaling="density")
    p = p.mean(axis=1)*(f[1]-f[0])
    return np.array([p[(f>=lo)&(f<hi)].sum() for lo,hi in zip(edges[:-1],edges[1:])])


def history(y, sr, width=.01):
    n=round(width*sr); x=y[:len(y)//n*n].reshape(-1,n,2)
    return dict(width_samples=n,midpoints_seconds=((np.arange(len(x))+.5)*n/sr).tolist(),
        rms_dbfs=(10*np.log10(np.maximum(np.mean(x*x,axis=(1,2)),1e-30))).tolist())


def describe(y, sr, times, noise, edges):
    x=crop(y,sr,times); result=dict(seconds=times,samples=[round(t*sr) for t in times],
        peak=float(abs(x).max()),exact_zero_sample_values=int(np.count_nonzero(x==0)),channels={})
    for name,z in channels(x).items():
        p=bands(z,sr,edges); floor=noise[name]
        rows=[]
        for lo,hi,v,n in zip(edges[:-1],edges[1:],p,floor):
            rows.append(dict(hz=[lo,hi],band_power_dbfs=db(v),quiet_band_power_dbfs=db(n),
                above_opening_quiet_db=db(v)-db(n),coverage_20db_guard=db(v)-db(n)>=20))
        half=len(z)//2
        result["channels"][name]=dict(rms_dbfs=db(np.mean(z*z)),bands=rows,
            second_over_first_half_level_db=db(np.mean(z[half:]**2))-db(np.mean(z[:half]**2)))
    result["side_over_mid_db"]=result["channels"]["side"]["rms_dbfs"]-result["channels"]["mid"]["rms_dbfs"]
    return result


def repetition(y,sr):
    # A source-duplication check only; never used to choose analysis support.
    # Search later gaps for a .60s template from the first gap, then report
    # both-channel fixed-scale cosine/residual. No gain/decay is fitted.
    template=crop(y,sr,[2.30,2.90]); rows=[]
    for region in [[5.85,6.80],[9.60,10.49]]:
        search=crop(y,sr,region)
        a=template.mean(axis=1); b=search.mean(axis=1)
        dot=signal.correlate(b,a,mode="valid",method="fft")
        energy=signal.convolve(b*b,np.ones(len(a)),mode="valid",method="fft")
        cos=dot/np.sqrt(np.maximum(energy*np.dot(a,a),1e-60))
        best=int(np.argmax(cos)); z=search[best:best+len(template)]
        rows.append(dict(search_seconds=region,best_start_seconds=region[0]+best/sr,
            stereo_waveform_cosine=float(np.sum(template*z)/np.sqrt(np.sum(template**2)*np.sum(z**2))),
            fixed_gain_relative_residual=float(np.linalg.norm(template-z)/np.linalg.norm(z))))
    return dict(template_seconds=[2.30,2.90],checks=rows,
        limitation="Only tests close waveform duplication inside the declared gaps; a low cosine does not prove independent performances or eliminate common phrase/excitation structure.")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources",type=Path,required=True)
    parser.add_argument("--support",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    a=parser.parse_args(); support=json.loads(a.support.read_text()); edges=support["band_edges_hz"]
    assert sha(a.support)=="1e3ce551394718f52082261d8f613bdc2be781c21142148fbcf57b9dfabecda1"
    catalog_path=ROOT/"Docs/fidelity/hardware-reference-catalog.json"
    catalog=json.loads(catalog_path.read_text()); records={r["id"]:r for r in catalog["recordings"]}
    banks_by_id={r["id"]:r for r in catalog["banks"]}
    inv_path=ROOT/"Docs/fidelity/source-audits/static-filter-reference-inventory-2026-09-15.json"
    inv=json.loads(inv_path.read_text()); refs={r["id"]:r for r in inv["references"]}
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(a.support,out/"predeclared-support.json")
    ffmpeg=shutil.which("ffmpeg"); assert ffmpeg
    result=dict(schema_version=1,status="Source-only coverage; no decay slope or damping-model fit.",
        support=support,support_sha256=sha(a.support),catalog_sha256=sha(catalog_path),inventory_sha256=sha(inv_path),
        tool_sha256=sha(__file__),patch_helper_sha256=sha(ROOT/"Tools/extract_reference_patch.py"),
        decoder=dict(path=ffmpeg,sha256=sha(ffmpeg),version=subprocess.check_output([ffmpeg,"-version"],text=True).splitlines()[0]),
        analysis_policy="Native44.1k stereo float32 decode, no resampling/gain/downmix mutation.1024sample periodicHann Welch75%overlap,detrendFalse,density integrated perband; mid/side descriptive channels. Quiet references are short same-file opening samples, not stationary calibrated noise; no noise subtraction.",cases={})
    fig,axs=plt.subplots(2,3,figsize=(15,7.2),layout="constrained")
    for row,(id,c) in enumerate(CONFIG.items()):
        reference=refs[id]; rec=records[id]; bank=banks_by_id[rec["bank_id"]]
        mp3=a.sources/c["mp3"]; archive=a.sources/f'SH-201_Patch_{c["bank"]}.zip'
        assert sha(mp3)==c["mp3_sha256"]==rec["sha256"]
        assert sha(archive)==bank["sha256"]
        raw,member=read_bank(archive)
        assert hashlib.sha256(raw).hexdigest()==bank["bank_sha256"] and member==bank["archive_member"]
        name,blocks=parse_bank(raw)[c["number"]-1]; syx=encode_syx(blocks)
        assert name==c["name"] and hashlib.sha256(syx).hexdigest()==reference["unmodified_sysex_sha256"]
        directory=out/id;directory.mkdir();(directory/"original-patch.syx").write_bytes(syx)
        wav=directory/"hardware-full.wav"
        cmd=[ffmpeg,"-hide_banner","-loglevel","error","-nostdin","-i",str(mp3.resolve()),"-c:a","pcm_f32le",str(wav)]
        subprocess.run(cmd,check=True);sr,y=wavfile.read(wav)
        assert sr==44100 and y.ndim==2 and y.shape[1]==2 and y.dtype==np.float32 and np.isfinite(y).all()
        y=y.astype(float); selection=support["cases"][id]
        quiet=crop(y,sr,selection["quiet"]); noise={k:bands(v,sr,edges) for k,v in channels(quiet).items()}
        decoded=reference["decoded"]
        for part in ["upper","lower"]:
            decoded[part].pop("model_base_cutoff_hz_diagnostic",None);decoded[part].pop("model_base_cutoff_status",None)
        r=dict(name=name,recording=rec,bank=bank,decoded=decoded,unmodified_sysex_sha256=hashlib.sha256(syx).hexdigest(),
            raw_delay=list(blocks[3]),raw_reverb=list(blocks[4]),
            physical_reverb=dict(time_raw=blocks[4][0],pre_delay_ms=1,size=8,high_cut_hz=12500,
                density=127,diffusion=127,lf_frequency_hz=4000,lf_gain_db=0,hf_frequency_hz=4000,hf_gain_db=blocks[4][9]-36),
            decode_command=cmd,decoded_sha256=sha(wav),sample_rate=sr,sample_count=len(y),duration_seconds=len(y)/sr,
            quiet_reference_seconds=selection["quiet"],quiet_reference_rms_dbfs=db(np.mean(quiet*quiet)),
            full_history_25ms=history(y,sr,.025),last_10_stereo_samples=y[-10:].tolist(),
            windows={key:describe(y,sr,times,noise,edges) for key,times in selection.items() if key!="quiet"})
        if id=="bass-05":r["source_gap_duplication_check"]=repetition(y,sr)
        result["cases"][id]=r
        lo,hi=c["preview"];z=crop(y,sr,[lo,hi])
        for col,mono in enumerate([z.mean(axis=1),(z[:,0]-z[:,1])/2]):
            f,t,s=signal.stft(mono,sr,nperseg=2048,noverlap=1792,boundary=None,padded=False)
            axs[row,col].pcolormesh(t+lo,f,20*np.log10(np.maximum(abs(s),1e-20)),vmin=-110,vmax=-35,cmap="magma",shading="auto")
            axs[row,col].axhline(4000,color="cyan",ls=":",lw=1)
            axs[row,col].set(xlim=(lo,hi),yscale="log",ylim=(60,16000),title=name+" "+["mid","side"][col],xlabel="Recording time / s",ylabel="Hz")
        hist=history(z,sr)
        axs[row,2].plot(np.array(hist["midpoints_seconds"])+lo,hist["rms_dbfs"],color="#17456d")
        axs[row,2].axhline(r["quiet_reference_rms_dbfs"],color="gray",ls=":")
        axs[row,2].set(xlim=(lo,hi),ylim=(-100,0),title="10 ms stereo RMS; no slope fit",xlabel="Recording time / s",ylabel="dBFS")
        for key,color in [("training","#198b60"),("later_check","#2877be")]:
            begin,end=selection[key]
            for ax in axs[row]:ax.axvspan(begin,end,color=color,alpha=.17)
        print(name,"quiet",r["quiet_reference_rms_dbfs"])
        for key in ["training","later_check","late_sensitivity"]:
            w=r["windows"][key]
            print(key,w["seconds"],"RMS",w["channels"]["stereo"]["rms_dbfs"],"side/mid",w["side_over_mid_db"],
                "side SNR",[round(b["above_opening_quiet_db"],2) for b in w["channels"]["side"]["bands"]])
    fig.suptitle("Damped presets: conditional source-tail coverage, not isolated damping measurements")
    fig.savefig(out/"tail-coverage.png",dpi=160);plt.close(fig)
    (out/"results.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")


if __name__=="__main__":main()
