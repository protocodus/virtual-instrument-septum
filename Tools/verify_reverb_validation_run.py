#!/usr/bin/env python3
"""Independently verify the 12-case/36-render prospective reverb run.

No DSP/render is run and no source performance is revised. Spectral and stereo
metrics are recalculated from WAVs; envelope averages use FFT convolution,
independent of the scorer's cumulative-sum implementation. Activity masks
deliberately reproduce the documented pairwise masks, not a new acceptance law.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np
from scipy import signal
from scipy.io import wavfile
from assess_hardware_equivalence import fit_transform
from render_midi import parse_smf, replay_events

ROOT = Path(__file__).resolve().parents[1]
MODELS = ("gain-1", "gain-0.5", "gain-0.25")
ANCHOR = "            wetReverbL = reverb_.highCutStateL;\n            wetReverbR = reverb_.highCutStateR;"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(p):
    sr, x = wavfile.read(p)
    require(sr == 44100 and x.dtype == np.float32 and x.ndim == 2 and x.shape[1] == 2, str(p))
    require(np.isfinite(x).all(), "Nonfinite audio")
    return x.astype(np.float64)


def rms(x):
    return float(np.sqrt(np.mean(x*x)))


def stereo(x):
    l, r = x.T
    mp, sp = np.mean(((l+r)/2)**2), np.mean(((l-r)/2)**2)
    lp, rp = np.mean(l*l), np.mean(r*r)
    floor = max(np.mean(x*x)*1e-8, 1e-30)
    return {"side_fraction":float(sp/max(mp+sp,1e-30)),
            "side_to_mid_db":float(10*np.log10(max(sp,floor)/max(mp,floor))),
            "balance_db":float(10*np.log10(max(lp,floor)/max(rp,floor))),
            "uncentered_channel_correlation":float(np.clip(np.mean(l*r)/max(np.sqrt(lp*rp),1e-30),-1,1))}


def independent_metrics(a, b, sr=44100):
    require(a.shape == b.shape and len(a) >= sr/4, "Measurement support")
    rows=[]
    for n in (512,2048,8192):
        if n>len(a): continue
        spectra=[np.abs(signal.stft(x,fs=sr,window="hann",nperseg=n,noverlap=3*n//4,
                                    boundary=None,padded=False,axis=0)[2]) for x in (a,b)]
        x,y=spectra;peak=float(x.max());floor=max(peak*1e-4,1e-30)
        mask=np.maximum(x,y)>=max(peak*.001,1e-30)
        delta=np.abs(20*np.log10(np.maximum(y,floor)/np.maximum(x,floor)))
        rows.append({"window_samples":n,"hop_samples":n//4,"frames":x.shape[-1],
                     "frequency_resolution_hz":sr/n,
                     "spectral_convergence":float(np.sqrt(np.sum((y-x)**2)/max(np.sum(x*x),1e-60))),
                     "log_spectral_error_db_mean":float(delta[mask].mean()),
                     "log_spectral_error_db_p95":float(np.percentile(delta[mask],95)),
                     "active_time_frequency_channel_bins":int(mask.sum())})
    envelopes=[];floor=max(float(np.max(abs(a)))*1e-4,1e-30)
    for duration in (.01,.05):
        n,hop=round(duration*sr),round(.005*sr)
        values=[np.sqrt(np.maximum(signal.fftconvolve(np.mean(x*x,axis=1),np.ones(n)/n,mode="valid"),0))[::hop] for x in (a,b)]
        x,y=values;mask=np.maximum(x,y)>=max(float(x.max())*.001,1e-30)
        delta=np.abs(20*np.log10(np.maximum(y,floor)/np.maximum(x,floor)))
        envelopes.append({"window_samples":n,"hop_samples":hop,"error_db_mean":float(delta[mask].mean()),"error_db_p95":float(np.percentile(delta[mask],95))})
    sa,sb=stereo(a),stereo(b);residual=rms(b-a)/rms(a)
    return {"summary":{"spectral_convergence_mean":float(np.mean([r["spectral_convergence"] for r in rows])),
                       "log_spectral_error_db_mean":float(np.mean([r["log_spectral_error_db_mean"] for r in rows])),
                       "envelope_error_db_p95_max":max(e["error_db_p95"] for e in envelopes),
                       "stereo_side_fraction_error":abs(sb["side_fraction"]-sa["side_fraction"]),
                       "stereo_balance_error_db":abs(sb["balance_db"]-sa["balance_db"])},
            "multi_resolution_stft":rows,"rms_envelope":envelopes,"stereo":{"reference":sa,"candidate":sb},
            "raw_level_difference_db":20*math.log10(max(rms(b),1e-30)/rms(a)),
            "waveform_diagnostic":{"normalized_rms_residual":residual,"residual_db_relative_to_reference":20*math.log10(max(residual,1e-30)),"used_for_bounds":False}}


def compare_numeric(actual, expected, errors, path="", tolerance=1e-7):
    if isinstance(actual,dict):
        for k,v in actual.items(): compare_numeric(v,expected[k],errors,path+"/"+k,tolerance)
    elif isinstance(actual,list):
        require(len(actual)==len(expected),"List length "+path)
        for i,(a,b) in enumerate(zip(actual,expected)): compare_numeric(a,b,errors,path+"/"+str(i),tolerance)
    elif isinstance(actual,bool): require(actual==expected,path)
    elif isinstance(actual,(float,int)):
        delta=abs(float(actual)-float(expected));errors[path]=max(errors.get(path,0),delta)
        require(delta<=tolerance,"Numeric mismatch "+path+": "+str(delta))
    else: require(actual==expected,path)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    result_path=a.run/"results.json";data=json.loads(result_path.read_text());protocol=data["protocol"]
    require(protocol==json.loads((a.run/"protocol-before-rendering.json").read_text()),"Pre-render protocol differs")
    require(len(data["cases"])==12 and len(protocol["cases"])==12,"Expected12cases")
    for n,h in protocol["tools"].items(): require(sha(ROOT/"Tools"/n)==h,"Tool changed "+n)
    require(sha(a.run/"evaluate_reverb_validation_cases.py")==protocol["tools"]["evaluate_reverb_validation_cases.py"],"Frozen evaluator")
    model_root=Path(protocol["models"]["gain-1"]["directory"]).parents[1]
    require(sha(model_root/"results.json")==protocol["model_result_sha256"],"Prior model run changed")
    old=json.loads((model_root/"results.json").read_text())
    require(sha(model_root/"source-manifest.json")==old["source_manifest_sha256"],"Source manifest changed")
    source=json.loads((model_root/"source-manifest.json").read_text())
    originals={}
    for name,h in source["input_sha256"].items():
        raw=subprocess.check_output(["git","show","b0f6c03:"+name],cwd=ROOT)
        require(hashlib.sha256(raw).hexdigest()==h and sha(model_root/"frozen-source"/name)==h,"Git source anchor "+name)
        originals[name]=raw
    build_checks=[]
    for name in MODELS:
        build=Path(protocol["models"][name]["directory"]);m=json.loads((build/"manifest.json").read_text())
        require(sha(build/"manifest.json")==protocol["models"][name]["manifest_sha256"],"Build manifest")
        require(m["status"]=="complete" and m["frozen_inputs_verified"] and not m["profile"]["enabled_sections"],"Unexpected build/profile")
        require(sha(build/"SeptumRenderMidi")==m["renderer"]["sha256"]==protocol["models"][name]["renderer_sha256"],"Renderer hash")
        for filename,h in m["frozen_sha256"].items(): require(sha(build/filename)==h,"Frozen input "+filename)
        for filename,h in m["source"]["input_sha256"].items():
            expected=originals[filename]
            if filename=="Source/DSP/SeptumEngine.cpp" and name!="gain-1":
                gain=float(name.split("-",1)[1])
                addition="\n            // Experimental equal-channel return gain; FDN and wet width unchanged.\n            wetReverbL *= "+format(gain,".17g")+";\n            wetReverbR *= "+format(gain,".17g")+";"
                s=expected.decode();require(s.count(ANCHOR)==1,"Anchor count");expected=s.replace(ANCHOR,ANCHOR+addition).encode()
            require(hashlib.sha256(expected).hexdigest()==h,"Unexpected variant source "+name+" "+filename)
            checkpath=build/("original/Tools/RenderMidi.cpp" if filename=="Tools/RenderMidi.cpp" else filename)
            require(checkpath.read_bytes()==expected,"Variant copied bytes")
        build_checks.append({"id":name,"git_source_and_only_expected_gain_mutation_verified":True,"renderer_sha256":m["renderer"]["sha256"]})
    inputs={i["case"]["id"]:i for i in protocol["cases"]};errors={};records=[];listen_count=0;metric_count=0
    for record in data["cases"]:
        identity=record["id"];spec=inputs[identity];case=spec["case"]
        cp=a.run/(identity+"-frozen-reconstruction.json");mp=cp.with_suffix(".mid")
        require(sha(cp)==spec["sha256"]==sha(spec["path"]) and json.loads(cp.read_text())==case,"Frozen case")
        require(sha(mp)==spec["midi_sha256"],"Frozen MIDI")
        # Source-only cases and all sensitivity derivatives were committed before
        # this run; assert their immutable Git bytes, not merely current files.
        rel=str(Path(spec["path"]).relative_to(ROOT))
        committed=subprocess.check_output(["git","show","b483c45:"+rel],cwd=ROOT)
        require(hashlib.sha256(committed).hexdigest()==spec["sha256"],"Pre-score reconstruction commit")
        base=a.run/"baseline-corpus"/identity;directory=a.run/"cases"/identity
        require(sha(base/"comparison.json")==record["comparison_sha256"],"Comparison manifest")
        for filename,h in record["comparison"]["files"].items(): require(sha(base/filename)==h,"Baseline artifact")
        require(sha(base/"original-patch.syx")==spec["sysex_sha256"] and sha(base/"reconstructed-performance.mid")==spec["midi_sha256"],"Original replay inputs")
        reference=read(base/"hardware-excerpt-raw.wav");full_reference=read(base/"hardware-decoded-full.wav")
        require(np.array_equal(reference,full_reference[:len(reference)]),"Native source excerpt")
        baseline=read(base/"septum-raw.wav");cal=round(case["calibration_end_seconds"]*44100)
        transform=fit_transform(reference,baseline[:len(reference)],44100,cal,.05)
        compare_numeric(transform,record["calibration"],errors,"calibration",1e-10)
        lag=transform["candidate_lag_samples"];n=len(reference)
        ca,cb=max(0,-lag),min(cal,cal-lag);start,end=max(cal,cal-lag),min(n,n-lag)
        require([ca,cb]==record["calibration_reference_samples"] and [ca+lag,cb+lag]==record["calibration_candidate_samples"] and [start,end]==record["evaluation_samples"],"Pairing indices")
        require(cb<=cal and cb+lag<=cal and start>=cal and start+lag>=cal,"Calibration/evaluation overlap")
        expected_events,ignored=replay_events(parse_smf(mp.read_bytes(),44100),tempo_policy="preserve-patch")
        require(not ignored,"Unexpected ignored input event")
        sounds={"hardware":reference[start:end]};model_rows=[]
        for name in MODELS:
            model=record["models"][name];wav=directory/(name+".wav");receiptp=wav.with_suffix(".render.json")
            require(sha(wav)==model["wav_sha256"] and sha(receiptp)==model["receipt_sha256"],"Render/receipt hash")
            receipt=json.loads(receiptp.read_text());x=read(wav)
            require(x.shape==baseline.shape and not receipt["ignored_events"] and not receipt["degraded_replay"] and receipt["output"]["active_voices_at_end"]==0,"Replay completion")
            require(receipt["output"]["sha256"]==sha(wav),"Receipt output identity")
            for key,h in (("midi",spec["midi_sha256"]),("sysex",spec["sysex_sha256"]),("renderer",protocol["models"][name]["renderer_sha256"])):
                require(receipt["inputs"][key]["sha256"]==h,"Receipt input "+key)
            settings=receipt["settings"]
            require(settings["sample_rate"]==44100 and settings["tail_seconds"]==2 and settings["master_level"]==100 and settings["midi_channel"]==1 and settings["tempo_policy"]=="preserve-patch" and not settings["automatic_note_offs_at_end"],"Replay settings")
            require(receipt["replay_events"]==expected_events,"Exact MIDI replay stream")
            require(np.max(abs(x))==model["peak"] and int(np.count_nonzero(abs(x)>=1))==model["samples_at_or_above_full_scale"],"Peak/clipping diagnostic")
            if name=="gain-1": require(np.array_equal(x,baseline),"Baseline copied identity")
            gain=rms(reference[ca:cb])/rms(x[ca+lag:cb+lag]);require(abs(gain-model["fitted_prefix_gain"])<1e-10,"Candidate prefix gain")
            fixed=x[start+lag:end+lag]*transform["candidate_gain"];fitted=x[start+lag:end+lag]*gain
            measured=independent_metrics(reference[start:end],fixed)
            compare_numeric(measured,model["measurements"],errors,"metrics")
            compare_numeric(independent_metrics(reference[start:end],fitted),model["candidate_prefix_gain_sensitivity"],errors,"metrics");metric_count+=2
            for label,diagnostic in model["predeclared_diagnostics"].items():
                lo,hi=diagnostic["reference_samples"];bounds=case["benchmark_protocol"]["diagnostic_regions_seconds"][label]
                require([lo,hi]==[max(start,round(bounds[0]*44100)),min(end,round(bounds[1]*44100))] and diagnostic["candidate_samples"]==[lo+lag,hi+lag],"Diagnostic support")
                compare_numeric(independent_metrics(reference[lo:hi],x[lo+lag:hi+lag]*transform["candidate_gain"]),diagnostic["measurements"],errors,"metrics");metric_count+=1
            sounds[name]=fixed;model_rows.append({"model":name,"wav_sha256":sha(wav),"receipt_sha256":sha(receiptp),"all_receipt_and_metric_checks_pass":True,"primary_summary":measured["summary"]})
        scale=min(.1/rms(sounds["hardware"]),.98/max(float(abs(x).max()) for x in sounds.values()))
        require(abs(scale-record["listening_common_gain"])<1e-12,"Common listening scalar")
        for name,x in sounds.items():
            actual=read(directory/(name+"-listen.wav"));expected=(x*scale).astype(np.float32).astype(np.float64)
            require(np.array_equal(actual,expected),"Listening transformation "+name);listen_count+=1
        records.append({"id":identity,"lag_samples":lag,"alignment_at_boundary":transform["alignment_at_search_boundary"],"frozen_input_hashes_verified":True,"models":model_rows,"listening_all_four_float32_arrays_exact":True})
        print(identity,"verified",flush=True)
    require(sum(len(r["models"]) for r in records)==36 and listen_count==48 and metric_count==108,"Expected verification counts")
    report={"schema_version":1,"run":str(a.run),"result_sha256":sha(result_path),"verifier_sha256":sha(__file__),"all_pass":True,"builds":build_checks,"cases":records,"counts":{"cases":12,"render_receipts":36,"exact_listening_arrays":48,"full_metric_recomputations":metric_count},"maximum_absolute_numeric_errors":errors,"largest_numeric_difference":max(errors.values()),"source_anchor":"All original copied source hashes checked directly against Git b0f6c03; candidate DSP differs only by the expected final equal-channel return gain insertion.","input_anchor":"All case JSON bytes checked against pre-score commit b483c45, plus pre-render protocol, rendered MIDI/SysEx and replay stream.","metric_method":"Independent WAV-based STFT/stereo formulas and FFT-convolution envelopes; same documented pairwise activity masks, floor and windows. This verifies reported values, not candidate-independent active-bin support.","qualification":"Six Ambient early/nominal cases hit the -50ms calibration lag bound. No gate scenario or new delay is selected. This is conditional validation with reconstructed inputs, not hardware equivalence."}
    (a.out/"results.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print("36 receipts,48 listening arrays,108 measurements verified; max difference",max(errors.values()),flush=True)


if __name__=="__main__":
    main()
