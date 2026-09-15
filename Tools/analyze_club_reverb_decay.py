#!/usr/bin/env python3
"""Frozen low-band Club tail comparison and actual shipping-FDN bias controls.

No damping/return candidate, performance modification, alignment or gain fit.
The source-selected intervals and estimator protocol must predate this run.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
SR=44100
EDGES=np.array([80,160,320,640])


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path,obj):path.write_text(json.dumps(obj,indent=2,allow_nan=False)+"\n")


def read(path):
    sr,y=wavfile.read(path)
    assert sr==SR and y.dtype==np.float32 and y.ndim==2 and y.shape[1]==2 and np.isfinite(y).all()
    return y.astype(float)


def window(y,start,duration,shift=0,gain=1.):
    lo,hi=round(start*SR)+shift,round((start+duration)*SR)+shift
    assert 0<=lo<hi<=len(y)
    x=y[lo:hi]*gain;hann=np.hanning(len(x));r={}
    for name,z in {"stereo":x,"side":((x[:,0]-x[:,1])/2)[:,None]}.items():
        ft=np.fft.rfft(z*hann[:,None],axis=0)
        p=np.mean(abs(ft)**2,axis=1)/(len(z)*np.sum(hann*hann))
        p[1:-1 if len(z)%2==0 else None]*=2
        f=np.fft.rfftfreq(len(z),1/SR)
        b=np.array([p[(f>=a)&(f<c)].sum() for a,c in zip(EDGES[:-1],EDGES[1:])])
        r[name]=dict(broadband_dbfs=float(10*np.log10(max(np.mean(z*z),1e-30))),
            band_dbfs=(10*np.log10(np.maximum(b,1e-30))).tolist(),
            band_power_fractions=(b/max(p.sum(),1e-30)).tolist(),
            band_level_guard=(b>=1e-12).tolist(),band_fraction_guard=(b>=p.sum()*.001).tolist())
    return dict(start_seconds=start,end_seconds=start+duration,center_seconds=start+duration/2,
        audio_samples=[lo,hi],sample_count=len(x),frequency_resolution_hz=SR/len(x),channels=r)


def fit(train,check,ta,tb):
    origin=float(ta[0]);a=np.column_stack([np.ones(len(ta)),np.array(ta)-origin])
    c=np.linalg.lstsq(a,train,rcond=None)[0]
    residual=np.array(train)-a@c;predicted=c[0]+c[1]*(np.array(tb)-origin)
    error=np.array(check)-predicted
    return dict(origin_seconds=origin,intercept_db=float(c[0]),slope_db_per_second=float(c[1]),
        training_rmse_db=float(np.sqrt(np.mean(residual**2))),training_residual_db=residual.tolist(),
        later_prediction_db=predicted.tolist(),later_error_db=error.tolist(),
        later_rmse_db=float(np.sqrt(np.mean(error**2))),later_max_absolute_error_db=float(abs(error).max()))


def analyze(y,train,check,specs,shift=0,gain=1.):
    groups=[]
    for spec in specs:
        duration,hop=spec["duration_seconds"],spec["hop_seconds"]
        rows=[]
        for lo,hi in [train,check]:
            starts=lo+np.arange(int(np.floor((hi-lo-duration+1e-9)/hop))+1)*hop
            rows.append([window(y,float(t),duration,shift,gain) for t in starts])
        a,b=rows;assert min(len(a),len(b))>=3
        ta=[r["center_seconds"] for r in a];tb=[r["center_seconds"] for r in b]
        output={}
        for name in ["stereo","side"]:
            def values(rows,key,index=None):
                return [r["channels"][name][key] if index is None else r["channels"][name][key][index] for r in rows]
            bands=[]
            for i,(lo,hi) in enumerate(zip(EDGES[:-1],EDGES[1:])):
                bands.append(dict(hz=[int(lo),int(hi)],
                    all_level_guards=all(values(a+b,"band_level_guard",i)),
                    all_fraction_guards=all(values(a+b,"band_fraction_guard",i)),
                    minimum_power_fraction=float(min(values(a+b,"band_power_fractions",i))),
                    **fit(values(a,"band_dbfs",i),values(b,"band_dbfs",i),ta,tb)))
            output[name]=dict(broadband=fit(values(a,"broadband_dbfs"),values(b,"broadband_dbfs"),ta,tb),bands=bands)
        groups.append(dict(spec=spec,training=a,later_check=b,fit=output))
    return groups


def controls(out,syx,source_hashes):
    frozen=out/"frozen-source";frozen.mkdir()
    for name,want in source_hashes.items():
        path=ROOT/name
        if sha(path)!=want:raise ValueError("Shipping source changed: "+name)
        target=frozen/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    source=(ROOT/"Tools/RenderMidi.cpp").read_text()
    reader=source[source.index("septum::Patch readCompletePatch ("):source.index("std::string patchSummary (")]
    code=r'''#include "DSP/SeptumEngine.h"
#include "DSP/SeptumSysEx.h"
#include "DSP/SeptumPresets.h"
#include "DSP/ReverbDamping.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <complex>
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
 const auto original=readCompletePatch(argv[1]);const auto&r=original.reverb;
 if(r.time!=77||r.preDelay!=10||r.size!=7||r.highCut!=19||r.density!=127||r.diffusion!=127||r.lfDampFrequency!=19||r.lfDampGain!=0||r.hfDampFrequency!=0||r.hfDampGain!=-36)return 3;
 constexpr int rate=44100,block=256,frames=rate*4,burst=rate/5;
 const double pi=std::acos(-1.);
 std::fprintf(stderr,"{\"time_raw\":77,\"hf_gain_db\":-36,\"hf_corner_hz\":4000,\"modeled_time_seconds\":%.17g,\"shelf_response\":[",septum::mapping::reverbSeconds(r.time,r.size));
 bool first=true;
 for(double f:{80.,std::sqrt(80.*160.),160.,std::sqrt(160.*320.),320.,std::sqrt(320.*640.),640.,4000.,22050.}){
   const double coefficient=septum::detail::reverbDampingCoefficient(4000.,rate);
   septum::detail::ReverbDampingState state;std::complex<double> response{};
   for(int i=0;i<16384;++i){const double v=septum::detail::reverbHighShelf(i==0?1.:0.,std::pow(10.,-36./20),coefficient,state);response+=v*std::polar(1.,-2*pi*f*i/rate);}
   std::fprintf(stderr,"%s{\"hz\":%.17g,\"amplitude_db_per_pass\":%.17g}",first?"":",",f,20*std::log10(std::abs(response)));first=false;
 }
 std::fprintf(stderr,"]}\n");
 for(int shape=0;shape<4;++shape){
   septum::Engine engine;engine.prepare(rate,block);septum::Patch patch;
   patch.reverb=original.reverb;patch.reverbOn=true;patch.delayOn=false;
   patch.upper.osc1.wave=septum::Waveform::ExtIn;patch.upper.balance=-63;
   patch.upper.filterType=septum::FilterType::Bypass;patch.upper.level=80;
   patch.upper.ampEnvAttack=patch.upper.ampEnvRelease=0;patch.upper.ampEnvSustain=127;patch.upper.reverbDepth=127;
   engine.setPatch(patch);septum::ExternalInput external;external.inputVolume=127;engine.setExternalInput(external);engine.reset();engine.noteOn(60,100);
   std::vector<float> left(frames),right(frames),input(frames);
   std::uint32_t random=0x12345678u;double low=0;
   for(int i=0;i<burst;++i){
     random^=random<<13;random^=random>>17;random^=random<<5;
     const double white=double(random)/4294967295.*2-1;low+=.08*(white-low);
     double x=shape==0?white:shape==1?low:0.;
     if(shape>=2){const double f=440*std::exp2((38-69)/12.);
       for(int h=1;h*f<16000&&(shape==2||h==1);++h)x+=.36/h*std::sin(2*pi*h*f*i/rate+.37*h*h);}
     input[i]=static_cast<float>(.1*(.5-.5*std::cos(2*pi*i/(burst-1)))*x);
   }
   for(int i=0;i<frames;i+=block)engine.process(left.data()+i,right.data()+i,std::min(block,frames-i),input.data()+i,input.data()+i);
   std::ofstream file(std::filesystem::path(argv[2])/(std::to_string(shape)+".raw"),std::ios::binary);
   for(int i=0;i<frames;++i){file.write(reinterpret_cast<char*>(&left[i]),4);file.write(reinterpret_cast<char*>(&right[i]),4);}
 }
}
'''.replace("READER",reader)
    fixture=out/"club-fdn-burst.cpp";fixture.write_text(code);binary=out/"club-fdn-burst"
    command=["c++","-O2","-std=c++17","-I",str(frozen/"Source"),str(fixture),
        *[str(frozen/"Source/DSP"/name) for name in ["SeptumEngine.cpp","SeptumPresets.cpp","SeptumSysEx.cpp"]],"-o",str(binary)]
    subprocess.run(command,check=True)
    process=subprocess.run([str(binary),str(syx),str(out)],check=True,capture_output=True,text=True)
    signals={};receipts=[]
    for i,name in enumerate(["white_noise","dark_noise","d2_harmonic","d2_sine"]):
        path=out/f"{i}.raw";y=np.fromfile(path,dtype=np.float32).reshape(-1,2)
        assert len(y)==SR*4 and np.isfinite(y).all() and abs(y).max()<.9
        wav=out/f"{name}.wav";wavfile.write(wav,SR,y);signals[name]=y.astype(float)
        receipts.append(dict(id=name,raw_sha256=sha(path),wav_sha256=sha(wav),peak=float(abs(y).max())))
    return signals,dict(source_sha256=source_hashes,reader_sha256=hashlib.sha256(reader.encode()).hexdigest(),
        fixture_sha256=sha(fixture),binary_sha256=sha(binary),compile_command=command,parameters=json.loads(process.stderr),audio=receipts)


def scalar_control(y,groups,protocol,shift,gain):
    scaled=analyze(y,protocol["train_seconds"],protocol["check_seconds"],protocol["window_specs"],shift,gain*.5)
    slope_delta=[];intercept_delta=[]
    for a,b in zip(groups,scaled):
        for channel in ["stereo","side"]:
            ar=[a["fit"][channel]["broadband"]]+a["fit"][channel]["bands"]
            br=[b["fit"][channel]["broadband"]]+b["fit"][channel]["bands"]
            for av,bv in zip(ar,br):
                slope_delta.append(abs(av["slope_db_per_second"]-bv["slope_db_per_second"]))
                intercept_delta.append(abs(bv["intercept_db"]-av["intercept_db"]-20*np.log10(.5)))
    assert max(slope_delta)<1e-8 and max(intercept_delta)<1e-8
    return dict(scale=.5,expected_intercept_change_db=float(20*np.log10(.5)),
        maximum_slope_change_db_per_second=max(slope_delta),maximum_intercept_error_db=max(intercept_delta))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--protocol",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    a=p.parse_args();protocol=json.loads(a.protocol.read_text())
    assert sha(a.protocol)=="ccf98d8bb77949c76906da94ecb134d4da032c6b6d83c08276d475148524a2b4"
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);shutil.copyfile(a.protocol,out/"protocol-before-fit.json")
    support=ROOT/"Docs/fidelity/source-audits/damped-reverb-tail-support-2026-09-15.json"
    assert sha(support)==protocol["source_support_sha256"]
    prior_path=ROOT/protocol["calibration_source_results"]["path"]
    assert sha(prior_path)==protocol["calibration_source_results"]["sha256"]
    prior=next(r for r in json.loads(prior_path.read_text())["cases"] if r["id"]=="club-bass")
    assert prior["calibration"]==protocol["gain_and_alignment"]
    shipping_path=ROOT/protocol["shipping_wav"]["path"];assert sha(shipping_path)==protocol["shipping_wav"]["sha256"]
    integration_path=ROOT/"build-fidelity/hardware-benchmark/reverb-return-integration/run-01/verification.json"
    integration=json.loads(integration_path.read_text())["render_verification"]
    verified=next(r for r in integration["results"] if r["id"]=="club-bass")
    assert verified["wav_sha256"]==sha(shipping_path) and verified["byte_identical_to_candidate"]
    receipt_path=shipping_path.with_suffix(".render.json");assert sha(receipt_path)==verified["receipt_sha256"]
    for name,key in [("original-patch.syx","sysex"),("reconstructed-performance.mid","midi")]:
        assert sha(shipping_path.parent/name)==verified["preserved_input_sha256"][key]
    source_audit_path=ROOT/"Docs/fidelity/source-audits/damped-reverb-tail-feasibility-2026-09-15.json"
    source_audit=json.loads(source_audit_path.read_text());source=source_audit["cases"]["bass-05"]
    hardware_path=ROOT/"build-fidelity/reverb-damped-tail-feasibility/run-01/bass-05/hardware-full.wav"
    assert sha(hardware_path)==source["decoded_sha256"]
    mp3=ROOT/"build-fidelity/hardware-benchmark/sources/TOP8_ClubBass.mp3"
    assert sha(mp3)==source["recording"]["sha256"]
    h,m=read(hardware_path),read(shipping_path)
    lag=protocol["gain_and_alignment"]["candidate_lag_samples"];gain=protocol["gain_and_alignment"]["candidate_gain"]
    train,check,specs=protocol["train_seconds"],protocol["check_seconds"],protocol["window_specs"]
    # Controls are built before model/hardware slope output is inspected.
    control_dir=out/"controls";control_dir.mkdir()
    signals,control_receipt=controls(control_dir,shipping_path.parent/"original-patch.syx",integration["protocol"]["source"]["current_sha256"])
    groups_h=analyze(h,train,check,specs);groups_m=analyze(m,train,check,specs,lag,gain)
    result=dict(schema_version=1,status="Conditional low-band descriptive decay comparison; no new DSP model.",
        protocol=protocol,protocol_sha256=sha(a.protocol),tool_sha256=sha(__file__),
        inputs=dict(source_audit_sha256=sha(source_audit_path),integration_sha256=sha(integration_path),
            hardware_sha256=sha(hardware_path),shipping_sha256=sha(shipping_path),shipping_receipt_sha256=sha(receipt_path)),
        hardware=groups_h,shipping=groups_m,
        hardware_late_diagnostic=analyze(h,train,protocol["late_diagnostic_seconds"],specs),
        shipping_late_diagnostic=analyze(m,train,protocol["late_diagnostic_seconds"],specs,lag,gain),
        scalar_invariance=scalar_control(m,groups_m,protocol,lag,gain),
        fdn_control_receipt=control_receipt,fdn_controls={},synthetic_exponential=[])
    fc=protocol["fdn_controls"]
    for name,y in signals.items():
        result["fdn_controls"][name]=dict(
            early=analyze(y,fc["early_train_seconds"],fc["early_check_seconds"],specs,93),
            settled=analyze(y,fc["settled_train_seconds"],fc["settled_check_seconds"],specs,93))
    t=np.arange(SR*4)/SR
    for shape in ["sine113","harmonics73"]:
        z=np.sin(2*np.pi*113*t+.3) if shape=="sine113" else sum(np.sin(2*np.pi*(440*2**((38-69)/12))*k*t+.37*k*k)/k for k in range(1,80))
        z*=.05*np.exp(-20*np.log(10)/20*t)
        y=np.column_stack([z,-.7*z])
        result["synthetic_exponential"].append(dict(shape=shape,planted_slope_db_per_second=-20.,
            measurements=analyze(y,train,check,specs)))
    save(out/"results.json",result)
    for i,spec in enumerate(specs):
        print("WINDOW",spec)
        for ch in ["stereo","side"]:
            for j,label in enumerate(["broadband","80-160","160-320","320-640"]):
                hh=[groups_h[i]["fit"][ch]["broadband"]]+groups_h[i]["fit"][ch]["bands"]
                mm=[groups_m[i]["fit"][ch]["broadband"]]+groups_m[i]["fit"][ch]["bands"]
                print(ch,label,"H/M slopes",round(hh[j]["slope_db_per_second"],3),round(mm[j]["slope_db_per_second"],3),
                    "H/M check RMSE",round(hh[j]["later_rmse_db"],3),round(mm[j]["later_rmse_db"],3))
    fig,axs=plt.subplots(2,4,figsize=(15,6.5),layout="constrained")
    for row,ch in enumerate(["stereo","side"]):
        for col,label in enumerate(["broadband","80–160Hz","160–320Hz","320–640Hz"]):
            ax=axs[row,col]
            for groups,color,name in [(groups_h,"#17456d","Original"),(groups_m,"#d27732","Shipping; frozen gain")]:
                rows=groups[0]["training"]+groups[0]["later_check"]
                values=[r["channels"][ch]["broadband_dbfs"] if col==0 else r["channels"][ch]["band_dbfs"][col-1] for r in rows]
                times=[r["center_seconds"] for r in rows];ax.plot(times,values,"o-",ms=3,color=color,label=name)
                f=[groups[0]["fit"][ch]["broadband"]]+groups[0]["fit"][ch]["bands"]
                predicted=f[col]["intercept_db"]+f[col]["slope_db_per_second"]*(np.array(times)-f[col]["origin_seconds"])
                ax.plot(times,predicted,"--",color=color,lw=1)
            ax.axvline(check[0],ls=":",color="gray");ax.set(title=ch+" "+label,xlabel="Source time / s",ylabel="dBFS")
    axs[0,0].legend(fontsize=8);fig.suptitle("Club Bass frozen low-band tails: training lines and later checks; no damping candidate")
    fig.savefig(out/"club-tail-comparison.png",dpi=160);plt.close(fig)


if __name__=="__main__":main()
