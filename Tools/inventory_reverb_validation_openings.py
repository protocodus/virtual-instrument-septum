#!/usr/bin/env python3
"""Inspect unscored official presets for reverb validation coverage.

No MIDI reconstruction, parameter fitting or candidate-error selection. Extracts
unchanged banks and privately decodes all14remaining original recordings.
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

from extract_reference_patch import read_bank,parse_bank,encode_syx
import assess_hardware_equivalence as assess

ROOT=Path(__file__).resolve().parents[1]
EXISTING={"Moogie 1","So Juno 1","Dist Bs 1","Pedal Bs 1","Club Bass",
          "Cotton Wool","Air Lead 1","Vangelead","SupaJuce 1","Brassy Ld 1"}
OPENING_REVIEWS={
    "lead-01": dict(rank=1,status="Preferred neutral-damping case",
        inspection_seconds=[.03,4.],
        finding="Single melodic family with rapid early plateaus before a longer held tone around.9s; do not collapse its whole opening run into three notes. First isolated plateau roughly.05–.20s. No stored pitch modulation, portamento or drive; octave-related saws and fast AMP simplify reconstruction. Original gate/velocity and filter envelope remain uncertain."),
    "lead-07": dict(rank=2,status="Preferred contrasting-damping case, qualified",
        inspection_seconds=[.05,.80],
        finding="First three obvious rising pitched plateaus roughly.08–.38,.45–.58,.64–.76s. These are inspection interiors, not recovered MIDI gates. Dual layers, slow Lower AMP, Upper drive and legato/portamento make wet/dry assignment conditional despite clear pitch structure."),
    "pad-06": dict(rank=3,status="Backup contrasting-damping case; weaker isolation",
        inspection_seconds=[.28,1.2],
        finding="Low-note sequence begins around.30s; a lower family enters around.42s while earlier energy persists. Polyphonic Super Saws, AMP release61 and cutoff LFO34 obscure early gates. Requires a credible note-overlap model before scoring; no isolated three-note protocol frozen here."),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sources",type=Path,required=True)
    p.add_argument("--inventory",type=Path,default=ROOT/"Docs/fidelity/source-audits/static-filter-reference-inventory-2026-09-15.json")
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    inv=json.loads(a.inventory.read_text())
    catalog_path=ROOT/"Docs/fidelity/hardware-reference-catalog.json"
    if sha(catalog_path)!=inv["catalog_sha256"]: raise ValueError("Catalog changed")
    catalog=json.loads(catalog_path.read_text());banks={}
    for b in catalog["banks"]:
        if b["id"]=="fx": continue
        path=a.sources/b["local_filename"]
        if sha(path)!=b["sha256"]: raise ValueError("Bank ZIP changed")
        data,member=read_bank(path)
        if hashlib.sha256(data).hexdigest()!=b["bank_sha256"] or member!=b["archive_member"]:
            raise ValueError("Bank member changed")
        banks[b["id"]]=parse_bank(data)
    ffmpeg=shutil.which("ffmpeg")
    if not ffmpeg: raise ValueError("ffmpeg required")
    result=dict(schema_version=1,status="Unscored source feasibility inventory; no new MIDI or parameter estimates.",
        inventory_sha256=sha(a.inventory),catalog_sha256=sha(catalog_path),
        tools={n:sha(ROOT/"Tools"/n) for n in (Path(__file__).name,"extract_reference_patch.py","assess_hardware_equivalence.py")},
        decoder=dict(path=ffmpeg,sha256=sha(ffmpeg),version=subprocess.check_output([ffmpeg,"-version"],text=True).splitlines()[0]),
        excluded_existing_case_names=sorted(EXISTING),
        selection_policy="Screen all14remaining named originals. Rank by simple active routing, no arpeggio, clear note/gap structure and contrasting stored damping; never consult candidate audio scores.",references=[])
    sounds={}
    for r in inv["references"]:
        if r["name"] in EXISTING: continue
        case=r["id"];directory=out/case;directory.mkdir()
        name,blocks=banks[case.split("-")[0]][r["patch_number"]-1]
        if name!=r["name"]: raise ValueError("Name mismatch")
        patch=directory/"original-patch.syx";patch.write_bytes(encode_syx(blocks))
        if sha(patch)!=r["unmodified_sysex_sha256"]: raise ValueError("SysEx differs from native inventory")
        mp3=a.sources/r["recording"]["local_filename"]
        if sha(mp3)!=r["recording"]["sha256"]: raise ValueError("Original recording changed")
        wav=directory/"hardware-full.wav"
        command=[ffmpeg,"-hide_banner","-loglevel","error","-nostdin","-i",str(mp3),"-ar","44100","-ac","2","-c:a","pcm_f32le",str(wav)]
        subprocess.run(command,check=True)
        sr,y=assess.read_audio(wav)
        if sr!=44100: raise ValueError("Unexpected sample rate")
        raw=blocks[4];d=r["decoded"]
        active=r["active_parts"]
        has_reverb=bool(d["reverbOn"] and (any(d[p]["reverbDepth"]>0 for p in active)
                      or (d["delayOn"] and any(d[p]["delayDepth"]>0 for p in active))))
        n=round(.025*sr);opening=y[:min(len(y),round(5*sr))]
        rms=np.sqrt(np.mean(opening[:len(opening)//n*n].reshape(-1,n,2)**2,axis=(1,2)))
        record=dict(r,patch_path=str(patch),patch_sha256=sha(patch),original_mp3_path=str(mp3.resolve()),
            decoded_path=str(wav),decoded_sha256=sha(wav),decode_command=command,
            duration_seconds=len(y)/sr,peak=float(abs(y).max()),
            raw_delay=list(blocks[3]),raw_reverb=list(raw),
            reverb_controls=dict(time=raw[0],pre_delay=raw[1],size=raw[2],high_cut=raw[3],density=raw[4],diffusion=raw[5],
                                 lf_frequency=raw[6],lf_gain_db=raw[7]-36,hf_frequency=raw[8],hf_gain_db=raw[9]-36),
            active_reverb_path_in_current_routing=has_reverb,
            damping_group="neutral" if raw[7]==raw[9]==36 else "nonneutral",
            opening_rms_25ms=dict(midpoints_seconds=((np.arange(len(rms))+.5)*n/sr).tolist(),
                                  rms_dbfs=(20*np.log10(np.maximum(rms,1e-30))).tolist()))
        record["opening_review"]=OPENING_REVIEWS.get(case)
        result["references"].append(record)
        if has_reverb: sounds[case]=y
    if len(result["references"])!=14: raise ValueError("Expected14remaining sources")
    selected=[r for r in result["references"] if r["active_reverb_path_in_current_routing"]]
    fig,axs=plt.subplots(4,2,figsize=(14,12),layout="constrained")
    for ax,r in zip(axs.flat,selected):
        y=sounds[r["id"]][:round(4*sr)]
        f,t,z=signal.stft(y,sr,nperseg=2048,noverlap=1536,axis=0,boundary=None,padded=False)
        power=np.mean(abs(z)**2,axis=1)
        ax.pcolormesh(t,f,10*np.log10(np.maximum(power,1e-20)),vmin=-80,vmax=-20,cmap="magma",shading="auto")
        ax.set(ylim=(50,8000),yscale="log",xlim=(0,4),xlabel="Recording time / s",ylabel="Hz",
               title=r["name"]+"; HF"+str(r["reverb_controls"]["hf_gain_db"])+"dB")
    fig.suptitle("Unscored official reverb openings: structural inspection only",fontsize=15)
    fig.savefig(out/"openings.png",dpi=140);plt.close(fig)
    (out/"results.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(out/"results.json")


if __name__=="__main__":
    main()
