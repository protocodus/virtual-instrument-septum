#!/usr/bin/env python3
"""Source-pinned late-tail stereo trajectory; no reverb parameter estimation.

Tail ranges were selected by inspection of the complete-file spectrogram and
50-ms RMS history, before band/coherence calculations. Hardware note-off times
are not known. Model tails have different excitation histories and are controls,
not a matched performance. Every window, including failed guards, is retained.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
from scipy import signal
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import assess_hardware_equivalence as assess
from assess_official_stereo_feasibility import stereo

ROOT=Path(__file__).resolve().parents[1]
CONFIG={
    "air-lead-1": dict(mp3="TOP8_AirLead1.mp3",sha256="eda084781108d6de6961f6b6807fff283eac097173b5675dc52c678dc2ad3d3b",
                       last_obvious_pitch_onset_range=[8.70,8.85],last_excitation_upper_bound=9.95,
                       hardware_starts=[10.45,10.95,11.45],model_starts=[4.445,4.945],
                       model_last_off=3.445,preview=[8.5,12.4]),
    "cotton-wool": dict(mp3="TOP8_Cotton_Wool.mp3",sha256="abf9d3ad400119ab0546fd724ab7a7442ea724bb164f8e9d024c642c791a1379",
                        last_obvious_pitch_onset_range=[15.60,15.80],last_excitation_upper_bound=16.20,
                        hardware_starts=[17.25+.5*i for i in range(10)],model_starts=[5.75,6.25],
                        model_last_off=4.75,preview=[14.5,22.4]),
}
BANDS=np.array([80,160,320,640,1280,2560,5120,10240])


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def psd(y,sr):
    f,t,z=signal.stft(y,sr,nperseg=4096,noverlap=3072,axis=0,boundary=None,padded=False)
    return f,z,np.mean(abs(z)**2,axis=(1,2))


def distribution(y,sr):
    f,_,p=psd(y,sr)
    x=np.array([p[(f>=lo)&(f<hi)].sum() for lo,hi in zip(BANDS[:-1],BANDS[1:])])
    return x/max(x.sum(),1e-30)


def measure(y,sr):
    result=stereo(y,1.)
    result["rms_dbfs"]=float(20*np.log10(max(result["rms"],1e-30)))
    half=len(y)//2
    a,b=distribution(y[:half],sr),distribution(y[half:],sr)
    rise=float(10*np.log10(max(np.mean(y[half:]**2),1e-30)/max(np.mean(y[:half]**2),1e-30)))
    cosine=float(np.dot(a,b)/max(np.linalg.norm(a)*np.linalg.norm(b),1e-30))
    result["stationarity"]=dict(first_half_octave_power_fraction=a.tolist(),second_half_octave_power_fraction=b.tolist(),
        half_distribution_cosine=cosine,half_distribution_L1=float(abs(a-b).sum()),second_over_first_rms_db=rise,
        level_guard=result["rms_dbfs"]>=-65.,no_half_window_level_rise_guard=rise<=1.,coarse_shape_guard=cosine>=.90)
    f,z,_=psd(y,sr)
    ll=np.mean(abs(z[:,0,:])**2,axis=1);rr=np.mean(abs(z[:,1,:])**2,axis=1)
    lr=np.mean(z[:,0,:]*np.conj(z[:,1,:]),axis=1)
    coherence=abs(lr)**2/np.maximum(ll*rr,1e-50)
    mid=np.mean(abs((z[:,0,:]+z[:,1,:])/2)**2,axis=1)
    side=np.mean(abs((z[:,0,:]-z[:,1,:])/2)**2,axis=1)
    weights=(ll+rr)/2
    result["stft_frames"]=z.shape[-1]
    result["bands"]=[]
    for lo,hi in zip(BANDS[:-1],BANDS[1:]):
        mask=(f>=lo)&(f<hi);w=weights[mask];power=w.sum()
        result["bands"].append(dict(hz=[int(lo),int(hi)],total_power_fraction=float(power/max(weights.sum(),1e-30)),
            side_over_mid_db=float(10*np.log10(max(side[mask].sum(),1e-30)/max(mid[mask].sum(),1e-30))),
            power_weighted_magnitude_squared_coherence=float(np.dot(w,coherence[mask])/max(power,1e-30))))
    return result


def plot(result,sounds,sr,out):
    fig,ax=plt.subplots(2,2,figsize=(12.8,7.0),layout="constrained")
    for row,(case,record) in enumerate(result["cases"].items()):
        config=CONFIG[case];start,end=config["preview"]
        y=sounds[case][round(start*sr):round(end*sr)]
        f,t,z=signal.stft(y,sr,nperseg=2048,noverlap=1536,axis=0,boundary=None,padded=False)
        p=np.mean(abs(z)**2,axis=1)
        ax[row,0].pcolormesh(t+start,f,10*np.log10(np.maximum(p,1e-20)),vmin=-95,vmax=-25,cmap="magma",shading="auto")
        ax[row,0].set(yscale="log",ylim=(50,6000),title=case+": complete-file ending",xlabel="Recording time / s",ylabel="Hz")
        ax[row,0].axvline(config["last_excitation_upper_bound"],color="cyan",ls="--",lw=1,label="Excitation upper bound")
        ax[row,0].legend(fontsize=8,loc="upper right")
        rows=record["hardware"];times=[r["seconds"][0]+.25 for r in rows]
        ax[row,1].plot(times,[r["raw"]["side_over_mid_db"] for r in rows],"o-",label="Hardware raw",color="#173d67")
        if case=="cotton-wool":
            ax[row,1].plot(times,[r["right_minus_0p6_db"]["side_over_mid_db"] for r in rows],"x--",label="Hardware R −0.6 dB",color="#159c91")
        for i,r in enumerate(record["production_tail"]):
            ax[row,1].axhline(r["raw"]["side_over_mid_db"],color="#df8c36",ls=("--" if i else ":"),
                              label="Model tail range; different notes" if i==0 else None)
        ax[row,1].set(title="Late stereo: higher = more side energy",xlabel="Hardware window midpoint / s",ylabel="Side / mid power, dB",ylim=(-8,0))
        ax[row,1].legend(fontsize=8,loc="lower right")
    fig.suptitle("Official endings constrain late stereo; early-gap width is not a reverb-width estimate",fontsize=13)
    fig.savefig(out/"tail-feasibility.png",dpi=160)
    plt.close(fig)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--corpus",type=Path,required=True)
    p.add_argument("--sources",type=Path,required=True)
    p.add_argument("--controls",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    ffmpeg=shutil.which("ffmpeg")
    if not ffmpeg: raise ValueError("ffmpeg required")
    control=json.loads((a.controls/"results.json").read_text())
    result=dict(schema_version=1,claim="Descriptive complete-file tail stereo; no width fit or hardware equivalence claim.",
        configuration=CONFIG,window_seconds=.5,octave_band_edges_hz=BANDS.tolist(),
        latency_compensation="Production only: exactly93samples; hardware unshifted. Different excitation histories are not time aligned.",
        guard_policy="Exploratory descriptive flags: RMS>=−65dBFS, second-half RMS rise<=1dB, half-window normalized octave-power cosine>=.90. These are neither perceptual thresholds nor a proof that no new notes occurred. All windows retained; exclude visibly edited endings beyond the chosen ranges.",
        source_inspection="Last obvious new pitch/excitation ranges are coarse manual spectrogram/RMS observations, not recovered MIDI. Hardware analysis begins>=1s after latest possible obvious note onset; first Air window is only.5s after the conservative excitation upper bound and is labeled sensitivity.",
        channel_sensitivity="Cotton only: divide right channel by10^(.6/20), fixed from early recording imbalance; does not change DSP. Air early excerpt is already wet and supplies no clean capture-gain estimate.",
        coherence="Power-weighted per-bin magnitude-squared coherence,18overlapping4096sampleHannSTFTframes per0.5swindow. Not independent trials; no confidence intervals. Very weak bands are retained without a hardware interpretation.",
        controls_result_sha256=sha(a.controls/"results.json"),
        tool_sha256={name:sha(ROOT/"Tools"/name) for name in
            (Path(__file__).name,"assess_official_stereo_feasibility.py","assess_hardware_equivalence.py")},
        decoder=dict(path=ffmpeg,sha256=sha(ffmpeg),version=subprocess.check_output([ffmpeg,"-version"],text=True).splitlines()[0]),cases={})
    sounds={}
    for case,c in CONFIG.items():
        mp3=a.sources/c["mp3"]
        if sha(mp3)!=c["sha256"]: raise ValueError("Original MP3 changed")
        directory=out/case;directory.mkdir();wav=directory/"hardware-full.wav"
        command=[ffmpeg,"-hide_banner","-loglevel","error","-nostdin","-i",str(mp3),"-ar","44100","-ac","2","-c:a","pcm_f32le",str(wav)]
        subprocess.run(command,check=True)
        sr,y=assess.read_audio(wav);sounds[case]=y
        model=a.controls/case/"original.wav"
        if sha(model)!=control["cases"][case]["controls"]["original"]["wav_sha256"]:
            raise ValueError("Production identity control changed")
        cs,z=assess.read_audio(model)
        if sr!=44100 or sr!=cs: raise ValueError("Unexpected audio format")
        meta=json.loads((a.corpus/case/"comparison.json").read_text())
        r=dict(reference=meta["reference"],comparison_limits=meta["comparison_limits"],
            decoded_sha256=sha(wav),decode_command=command,production_sha256=sha(model),
            duration_seconds=len(y)/sr,full_file_peak=float(abs(y).max()),hardware=[],production_tail=[])
        for t in c["hardware_starts"]:
            begin,end=round(t*sr),round((t+.5)*sr)
            cut=y[begin:end]
            record=dict(seconds=[t,t+.5],samples=[begin,end],raw=measure(cut,sr),
                        at_least_one_second_after_excitation_upper_bound=t>=c["last_excitation_upper_bound"]+1)
            if case=="cotton-wool":
                corrected=cut.copy();corrected[:,1]/=10**(.6/20)
                record["right_minus_0p6_db"]=measure(corrected,sr)
            r["hardware"].append(record)
        for t in c["model_starts"]:
            begin,end=round(t*sr)+93,round((t+.5)*sr)+93
            if end>len(z): raise ValueError("Model tail too short")
            r["production_tail"].append(dict(midi_clock_seconds=[t,t+.5],samples=[begin,end],raw=measure(z[begin:end],sr)))
        result["cases"][case]=r
    (out/"results.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    plot(result,sounds,sr,out)
    print(out/"results.json")


if __name__=="__main__":
    main()
