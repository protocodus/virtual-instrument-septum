#!/usr/bin/env python3
"""Source-independent stereo-transfer feasibility, with current-engine controls.

No network fitting, DSP edits, performance reconstruction or channel-gain fit.
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

from extract_reference_patch import read_bank,parse_bank,encode_syx

ROOT=Path(__file__).resolve().parents[1]
SR=44100
IDS=["pad-01","lead-03","lead-06","lead-01"]
STIMULI=["white_seed_A","white_seed_B","fixed_chord_phase_A","fixed_chord_phase_B","impulse_at4","impulse_at12"]
NATIVE_WAV_SHA256={
    "pad-01":"9c05ef61182c5a3b72ddbf33330b344ef4b1bfa5e5b72e4a7b40f6f2e7a57ec1",
    "lead-03":"53e8c6900e06dbc831145ce236ab7789f8800dac180e1334a61ef94166ee3be4",
    "lead-06":"152674cde45b99737c24382d8156331dc1060656d02d3250397e01018ed45878",
    "lead-01":"32c418c77f476d52427d5c01f6dea7316de91378323814982741cb50eead78f1",
}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,obj):path.write_text(json.dumps(obj,indent=2,allow_nan=False)+"\n")
def read(path):
    sr,y=wavfile.read(path)
    assert sr==SR and y.dtype==np.float32 and y.ndim==2 and y.shape[1]==2 and np.isfinite(y).all()
    return y.astype(float)


def estimate(y,interval,duration,route):
    lo,hi=[round(t*SR) for t in interval];n=round(duration*SR);hop=round(n/4)
    assert 0<=lo<hi<=len(y) and hi-lo>=n
    z=y[lo:hi];a,b=(z[:,0],z[:,1]) if route=="LR" else ((z[:,0]+z[:,1])/2,(z[:,0]-z[:,1])/2)
    starts=np.arange(0,len(z)-n+1,hop);w=np.hanning(n+1)[:-1]
    ax=np.array([a[s:s+n]*w for s in starts]);bx=np.array([b[s:s+n]*w for s in starts])
    ax=np.fft.rfft(ax,axis=1);bx=np.fft.rfft(bx,axis=1)
    px=np.mean(abs(ax)**2,axis=0);py=np.mean(abs(bx)**2,axis=0);cross=np.mean(np.conj(ax)*bx,axis=0)
    h=cross/np.maximum(px,1e-100)
    coherence=np.clip(abs(cross)**2/np.maximum(px*py,1e-200),0,1)
    f=np.fft.rfftfreq(n,1/SR);keep=(f>=80)&(f<=8000)
    f,px,py,h,coherence=[v[keep] for v in [f,px,py,h,coherence]]
    active=(px>=px.max()*1e-5)&(py>=py.max()*1e-5)
    if route=="MS":active&=py>=px*10**(-35/10)
    good=active&(coherence>=.9)
    summary=dict(interval_seconds=interval,window_seconds=duration,window_samples=n,hop_samples=hop,
        frames=len(starts),minimum_frame_guard=len(starts)>=8,route=route,frequency_bins=len(f),
        excited_bins=int(active.sum()),coherent_excited_bins=int(good.sum()),
        excited_bin_fraction=float(active.mean()),
        coherent_fraction_of_excited_bins=float(good.sum()/active.sum()) if active.any() else None,
        target_power_weighted_coherence=float(np.dot(py[active],coherence[active])/py[active].sum()) if active.any() else None,
        coherent_fraction_of_excited_target_power=float(py[good].sum()/py[active].sum()) if active.any() else None,
        excited_coherence_median=float(np.median(coherence[active])) if active.any() else None)
    return dict(f=f,px=px,py=py,h=h,coherence=coherence,active=active,good=good,summary=summary)


def compare(a,b,truth=False):
    assert np.array_equal(a["f"],b["f"])
    active=a["active"]&b["active"];good=a["good"]&b["good"]
    answer={}
    for name,mask in [("common_excited",active),("common_coherent_excited",good)]:
        if not mask.any():answer[name]=dict(bins=0);continue
        ah,bh=a["h"][mask],b["h"][mask]
        relative=abs(ah-bh)/np.maximum(abs(bh),1e-100)
        magnitude=20*np.log10(np.maximum(abs(ah),1e-100)/np.maximum(abs(bh),1e-100))
        phase=np.angle(ah*np.conj(bh))*180/np.pi
        answer[name]=dict(bins=int(mask.sum()),complex_relative_error_median=float(np.median(relative)),
            complex_relative_error_p95=float(np.percentile(relative,95)),
            magnitude_difference_db_median=float(np.median(magnitude)),
            absolute_magnitude_difference_db_p95=float(np.percentile(abs(magnitude),95)),
            absolute_phase_difference_degrees_p95=float(np.percentile(abs(phase),95)))
    frame_guard=all(v.get("summary",{}).get("minimum_frame_guard",True) for v in [a,b])
    return dict(second_is_impulse_truth=truth,minimum_frame_guard=frame_guard,**answer)


def folded_truth(y,on,duration,route):
    x=y[round(on*SR):];n=round(duration*SR)
    target=np.zeros((int(np.ceil(len(x)/n))*n,2));target[:len(x)]=x
    folded=target.reshape(-1,n,2).sum(axis=0)
    z=np.fft.rfft(folded,axis=0)
    a,b=(z[:,0],z[:,1]) if route=="LR" else ((z[:,0]+z[:,1])/2,(z[:,0]-z[:,1])/2)
    f=np.fft.rfftfreq(n,1/SR);keep=(f>=80)&(f<=8000)
    assert np.all(abs(a[keep])>1e-100)
    return dict(f=f[keep],h=b[keep]/a[keep],active=np.ones(keep.sum(),dtype=bool),good=np.ones(keep.sum(),dtype=bool))


def build_controls(out,patches):
    verification=ROOT/"build-fidelity/hardware-benchmark/reverb-return-integration/run-01/verification.json"
    source_hashes=json.loads(verification.read_text())["render_verification"]["protocol"]["source"]["current_sha256"]
    frozen=out/"frozen-source"
    for name,want in source_hashes.items():
        source=ROOT/name;assert sha(source)==want
        target=frozen/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target);assert sha(target)==want
    source=(ROOT/"Tools/RenderMidi.cpp").read_text()
    reader=source[source.index("septum::Patch readCompletePatch ("):source.index("std::string patchSummary (")]
    code=r'''#include "DSP/SeptumEngine.h"
#include "DSP/SeptumSysEx.h"
#include "DSP/SeptumPresets.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <vector>
using Bytes=std::vector<std::uint8_t>;
Bytes readBytes(const std::filesystem::path&p){std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("missing patch");return Bytes(std::istreambuf_iterator<char>(f),{});}
READER
int main(int argc,char**argv){
 if(argc!=3)return 2;
 const auto original=readCompletePatch(argv[1]);const bool cotton=original.upper.delayDepth==0;
 if((cotton&&(original.reverb.time!=104||original.upper.reverbDepth!=35))||(!cotton&&(original.reverb.time!=86||original.upper.delayDepth!=35||original.upper.reverbDepth!=88)))return 3;
 constexpr int rate=44100,block=256,frames=rate*32,driven=rate*22;const double pi=std::acos(-1.);
 std::fprintf(stderr,"{\"delay_send\":%d,\"reverb_send\":%d,\"reverb_time_raw\":%d,\"delay_modulation_depth\":%d}\n",original.upper.delayDepth,original.upper.reverbDepth,original.reverb.time,original.delay.modulationDepth);
 for(int shape=0;shape<(cotton?6:2);++shape){
  septum::Engine engine;engine.prepare(rate,block);septum::Patch patch;
  patch.reverb=original.reverb;patch.delay=original.delay;patch.reverbOn=original.reverbOn;patch.delayOn=original.delayOn;
  patch.upper.osc1.wave=septum::Waveform::ExtIn;patch.upper.balance=-63;patch.upper.filterType=septum::FilterType::Bypass;patch.upper.level=80;
  patch.upper.ampEnvAttack=patch.upper.ampEnvRelease=0;patch.upper.ampEnvSustain=127;patch.upper.delayDepth=original.upper.delayDepth;patch.upper.reverbDepth=original.upper.reverbDepth;
  engine.setPatch(patch);septum::ExternalInput external;external.inputVolume=127;engine.setExternalInput(external);engine.reset();engine.noteOn(60,100);
  std::vector<float> left(frames),right(frames),input(frames);std::uint32_t random=shape==1?0x87654321u:0x12345678u;
  if(shape>=4)input[(shape==4?4:12)*rate]=.1f;
  else for(int i=0;i<driven;++i){
   random^=random<<13;random^=random>>17;random^=random<<5;
   double x=double(random)/4294967295.*2-1;
   if(shape>=2){x=0;int ni=0;for(int note:{48,52,55}){const double f=440*std::exp2((note-69)/12.);for(int h=1;h*f<8000;++h)x+=.10/h*std::sin(2*pi*h*f*i/rate+(shape==2?.37:.91)*h*h+ni*.23);++ni;}}
   const double fade=std::min({1.,i/(rate*.1),(driven-1-i)/(rate*.1)});input[i]=static_cast<float>(.1*std::max(0.,fade)*x);
  }
  for(int i=0;i<frames;i+=block)engine.process(left.data()+i,right.data()+i,std::min(block,frames-i),input.data()+i,input.data()+i);
  std::ofstream file(std::filesystem::path(argv[2])/(std::to_string(shape)+".raw"),std::ios::binary);
  for(int i=0;i<frames;++i){file.write(reinterpret_cast<char*>(&left[i]),4);file.write(reinterpret_cast<char*>(&right[i]),4);}
 }
}
'''.replace("READER",reader)
    fixture=out/"transfer-controls.cpp";fixture.write_text(code);binary=out/"transfer-controls"
    command=["c++","-O2","-std=c++17","-I",str(frozen/"Source"),str(fixture),
        *[str(frozen/"Source/DSP"/n) for n in ["SeptumEngine.cpp","SeptumPresets.cpp","SeptumSysEx.cpp"]],"-o",str(binary)]
    subprocess.run(command,check=True)
    results={};sounds={}
    for id in ["pad-01","lead-03"]:
        directory=out/id;directory.mkdir();process=subprocess.run([str(binary),str(patches[id]),str(directory)],check=True,capture_output=True,text=True)
        results[id]=dict(parameters=json.loads(process.stderr),audio=[]);sounds[id]={}
        for i,name in enumerate(STIMULI[:6 if id=="pad-01" else 2]):
            raw=directory/f"{i}.raw";y=np.fromfile(raw,dtype=np.float32).reshape(-1,2)
            assert len(y)==SR*32 and np.isfinite(y).all() and abs(y).max()<.9
            wav=directory/f"{name}.wav";wavfile.write(wav,SR,y);sounds[id][name]=y.astype(float)
            full=np.mean(y.astype(float)**2);terminal=np.mean(y[-SR:].astype(float)**2)
            results[id]["audio"].append(dict(id=name,wav_sha256=sha(wav),raw_sha256=sha(raw),peak=float(abs(y).max()),
                terminal_second_below_full_power_db=float(10*np.log10(max(terminal,1e-100)/full)),terminal_100db_guard=bool(terminal<=full*1e-10)))
    return sounds,dict(source_sha256=source_hashes,integration_sha256=sha(verification),
        reader_sha256=hashlib.sha256(reader.encode()).hexdigest(),fixture_sha256=sha(fixture),binary_sha256=sha(binary),compile_command=command,cases=results)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--protocol",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    p.add_argument("--reuse-controls",type=Path,help="Reuse fully hash-verified controls from an earlier completed run of this protocol")
    a=p.parse_args();protocol=json.loads(a.protocol.read_text());assert sha(a.protocol)=="cd8f5cdded181e3c8b93534cb6a06a63681f334974c18fbd68b748dec3c78bc8"
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);shutil.copyfile(a.protocol,out/"protocol-before-analysis.json")
    catpath=ROOT/"Docs/fidelity/hardware-reference-catalog.json";cat=json.loads(catpath.read_text())
    records={r["id"]:r for r in cat["recordings"]};banks={r["id"]:r for r in cat["banks"]}
    invpath=ROOT/"Docs/fidelity/source-audits/static-filter-reference-inventory-2026-09-15.json";inv={r["id"]:r for r in json.loads(invpath.read_text())["references"]}
    decoder=Path(shutil.which("ffmpeg")).resolve()
    decoder_receipt=dict(path=str(decoder),sha256=sha(decoder),
        version=subprocess.run([str(decoder),"-version"],check=True,capture_output=True,text=True).stdout.splitlines()[0],
        policy="Original native 44100 Hz stereo decoded to float32 PCM, without resampling or channel conversion")
    original_dir=out/"originals";original_dir.mkdir()
    patches={};originals={};references={}
    for id in IDS:
        rec=records[id];bank=banks[rec["bank_id"]];source=ROOT/"build-fidelity/hardware-benchmark/sources"
        archive=source/bank["local_filename"];assert sha(archive)==bank["sha256"]
        data,member=read_bank(archive);assert hashlib.sha256(data).hexdigest()==bank["bank_sha256"] and member==bank["archive_member"]
        name,blocks=parse_bank(data)[rec["patch_number"]-1];syx=encode_syx(blocks)
        assert name==rec["patch_name"] and hashlib.sha256(syx).hexdigest()==inv[id]["unmodified_sysex_sha256"]
        path=out/f"{id}.syx";path.write_bytes(syx);patches[id]=path
        mp3=source/rec["local_filename"];assert sha(mp3)==rec["sha256"]
        wav=original_dir/f"{id}.wav"
        decode_command=[str(decoder),"-hide_banner","-loglevel","error","-nostdin","-i",str(mp3),"-c:a","pcm_f32le",str(wav)]
        subprocess.run(decode_command,check=True)
        assert sha(wav)==NATIVE_WAV_SHA256[id],"Native decode changed; investigate decoder rather than silently replacing frozen audio"
        originals[id]=read(wav);decoded=inv[id]["decoded"]
        for part in ["upper","lower"]:
            decoded[part].pop("model_base_cutoff_hz_diagnostic",None);decoded[part].pop("model_base_cutoff_status",None)
        references[id]=dict(recording=rec,bank=bank,patch_name=name,decoded=decoded,sysex_sha256=sha(path),
            raw_delay=list(blocks[3]),raw_reverb=list(blocks[4]),wav_sha256=sha(wav),
            native_wav=str(wav.relative_to(out)),decode_command=decode_command,duration_seconds=len(originals[id])/SR)
    control_dir=out/"controls";control_dir.mkdir()
    if a.reuse_controls:
        previous=json.loads((a.reuse_controls/"results.json").read_text())
        assert previous["protocol"]==protocol
        receipt=previous["controls_receipt"]
        for name,want in receipt["source_sha256"].items():assert sha(ROOT/name)==want
        shutil.copytree(a.reuse_controls/"controls",control_dir,dirs_exist_ok=True)
        assert sha(control_dir/"transfer-controls.cpp")==receipt["fixture_sha256"]
        assert sha(control_dir/"transfer-controls")==receipt["binary_sha256"]
        for name,want in receipt["source_sha256"].items():assert sha(control_dir/"frozen-source"/name)==want
        sounds={}
        for id,case in receipt["cases"].items():
            assert previous["references"][id]["sysex_sha256"]==sha(patches[id])
            sounds[id]={}
            for i,record in enumerate(case["audio"]):
                wav=control_dir/id/(record["id"]+".wav");raw=control_dir/id/f"{i}.raw"
                assert sha(wav)==record["wav_sha256"] and sha(raw)==record["raw_sha256"]
                sounds[id][record["id"]]=read(wav)
        receipt["reused_from"]=dict(path=str(a.reuse_controls),results_sha256=sha(a.reuse_controls/"results.json"),
            reason="Identical frozen protocol, current source, complete patch, fixture, binary, raw and WAV hashes; only estimator/report work reruns.")
    else:
        sounds,receipt=build_controls(control_dir,patches)
    save(out/"controls-receipt.json",receipt)
    result=dict(schema_version=1,protocol=protocol,protocol_sha256=sha(a.protocol),tool_sha256=sha(__file__),
        catalog_sha256=sha(catpath),inventory_sha256=sha(invpath),decoder=decoder_receipt,
        references=references,controls_receipt=receipt,model={},hardware={},synthetic=[])
    spectra_dir=out/"spectra";spectra_dir.mkdir();cached={}
    def record_estimate(key,y,interval,duration,route):
        v=estimate(y,interval,duration,route);path=spectra_dir/(key+".npz")
        np.savez_compressed(path,**{k:x for k,x in v.items() if k!="summary"})
        v["summary"]["spectra_file"]=str(path.relative_to(out));v["summary"]["spectra_sha256"]=sha(path)
        return v
    for id,signals in sounds.items():
        result["model"][id]={}
        for name,y in signals.items():
            if name.startswith("impulse"):continue
            result["model"][id][name]=[]
            for duration in protocol["window_seconds"]:
                for route in ["LR","MS"]:
                    train=record_estimate(f"{id}-{name}-{duration}-{route}-train",y,[4,12],duration,route)
                    check=record_estimate(f"{id}-{name}-{duration}-{route}-check",y,[12,20],duration,route)
                    cached[(id,name,duration,route)]=(train,check)
                    row=dict(window_seconds=duration,route=route,training=train["summary"],check=check["summary"],time_stability=compare(train,check))
                    if id=="pad-01":
                        truth=folded_truth(signals["impulse_at4"],4,duration,route)
                        other=folded_truth(signals["impulse_at12"],12,duration,route)
                        truth_guard=all(r["terminal_100db_guard"] for r in receipt["cases"]["pad-01"]["audio"] if r["id"].startswith("impulse"))
                        row.update(impulse_truth_terminal_guard=truth_guard,training_vs_impulse=compare(train,truth,True),check_vs_impulse=compare(check,truth,True),impulse_launch_invariance=compare(other,truth,True))
                    result["model"][id][name].append(row)
                    print("MODEL",id,name,duration,route,"coherence",round(train["summary"]["target_power_weighted_coherence"],4),"coherent bins",train["summary"]["coherent_excited_bins"],flush=True)
    result["source_change_controls"]=[]
    for first,second in [("white_seed_A","white_seed_B"),("fixed_chord_phase_A","fixed_chord_phase_B")]:
        for duration in protocol["window_seconds"]:
            for route in ["LR","MS"]:
                aa=cached[("pad-01",first,duration,route)][0];bb=cached[("pad-01",second,duration,route)][0]
                result["source_change_controls"].append(dict(first=first,second=second,window_seconds=duration,route=route,comparison=compare(aa,bb)))
    # Known short FIR and unrelated-channel controls establish estimator scope.
    rng=np.random.default_rng(5917)
    for name in ["white_A","white_B","unrelated"]:
        x=rng.normal(0,.02,SR*24);l=signal.lfilter([1]+[0]*12+[.3],[1],x)
        r=signal.lfilter([1]+[0]*41+[-.2],[1],x) if name!="unrelated" else rng.normal(0,.02,len(x))
        y=np.column_stack([l,r])
        for duration in protocol["window_seconds"]:
            v=estimate(y,[4,12],duration,"LR");f=v["f"]
            truth=dict(f=f,h=(1-.2*np.exp(-2j*np.pi*f*42/SR))/(1+.3*np.exp(-2j*np.pi*f*13/SR)),active=np.ones(len(f),bool),good=np.ones(len(f),bool))
            result["synthetic"].append(dict(id=name,window_seconds=duration,estimate=v["summary"],against_known_fir=compare(v,truth,True) if name!="unrelated" else None))
    # Original measurements follow control computation; no source intervals are altered.
    for id,y in originals.items():
        result["hardware"][id]={}
        variants={"raw":y}
        if id=="pad-01":variants["fixed_R_minus_0p6dB"]=y*np.array([1,10**(-.6/20)])
        support=protocol["hardware_source_intervals"][id]
        for name,z in variants.items():
            result["hardware"][id][name]=[]
            for duration in protocol["window_seconds"]:
                for route in ["LR","MS"]:
                    train=record_estimate(f"hardware-{id}-{name}-{duration}-{route}-train",z,support["train"],duration,route)
                    check=record_estimate(f"hardware-{id}-{name}-{duration}-{route}-check",z,support["check"],duration,route)
                    result["hardware"][id][name].append(dict(window_seconds=duration,route=route,training=train["summary"],check=check["summary"],time_stability=compare(train,check)))
                    print("HARDWARE",id,name,duration,route,"coherence",round(train["summary"]["target_power_weighted_coherence"],4),"coherent bins",train["summary"]["coherent_excited_bins"],flush=True)
    save(out/"results.json",result)
    fig,axs=plt.subplots(2,2,figsize=(12,7),layout="constrained")
    for row,route in enumerate(["LR","MS"]):
        for col,duration in enumerate([.5,2.]):
            for id,name,label,color in [("pad-01","white_seed_A","Cotton white","#20578a"),("pad-01","fixed_chord_phase_A","Cotton chord","#d68127"),("lead-03","white_seed_A","Air white / active delay","#388e74")]:
                v=cached[(id,name,duration,route)][0];a=v["active"]
                # Keep gaps: joining separate harmonic lobes would visually
                # imply broadband coverage that the chord does not provide.
                axs[row,col].plot(v["f"],np.where(a,v["coherence"],np.nan),lw=.5,alpha=.6,label=label,color=color)
            axs[row,col].axhline(.9,ls=":",color="gray");axs[row,col].set(xlim=(80,8000),ylim=(0,1.02),xscale="log",title=f"{route}, {duration:g} s windows",xlabel="Hz",ylabel="Magnitude-squared coherence")
    axs[0,0].legend(fontsize=8);fig.suptitle("Known mono engine inputs: coherence can fail or conceal finite-window transfer bias")
    fig.savefig(out/"control-coherence.png",dpi=160);plt.close(fig)


if __name__=="__main__":main()
