#!/usr/bin/env python3
"""One frozen W4 candidate versus all ten unchanged official preset excerpts.

No coefficient, waveform phase, frequency, event or patch fitting. Prepare
pins the existing production transforms before any candidate is rendered.
"""
import argparse
import hashlib
import html
import json
import math
import os
from pathlib import Path
import shutil
import sys

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
import numpy as np
import scipy
from scipy import signal
from scipy.io import wavfile

import assess_hardware_equivalence as assess
import build_saw_w4_experiment as engine
import score_moogie_envelope_candidates as moogie

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT/"Docs/fidelity/source-audits/saw-w4-official-inputs-2026-09-15.json"
INVENTORY_SHA = "9bf636d72ff15b00135258f5924798af9c2ecd81556534d485a0a0e4a700402e"
SR = 44100


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pin(path,expected=None):
    path = Path(path).resolve()
    actual = sha(path)
    if expected is not None and actual!=expected:
        raise ValueError("Changed pinned file: "+str(path))
    return dict(path=str(path),sha256=actual)


def save(path,value):
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+"\n")


def verify_item(item):
    return pin(item["path"],item["sha256"])


def measure(reference,candidate):
    result = assess.measure(reference,candidate,SR)
    n = 1024
    magnitude = []
    for audio in (reference,candidate):
        _,_,z = signal.stft(audio,fs=SR,window="hann",nperseg=n,noverlap=3*n//4,
                            boundary=None,padded=False,axis=0)
        magnitude.append(abs(z))
    a,b = magnitude
    peak = float(a.max())
    floor = max(peak*10**(assess.FLOOR_DB/20),1e-30)
    active = np.maximum(a,b)>=max(peak*10**(assess.ACTIVE_DB/20),1e-30)
    difference = abs(20*np.log10(np.maximum(b,floor)/np.maximum(a,floor)))
    result["multi_resolution_stft"].append(dict(window_samples=n,hop_samples=n//4,frames=int(a.shape[-1]),
        frequency_resolution_hz=SR/n,spectral_convergence=float(np.linalg.norm(b-a)/max(np.linalg.norm(a),1e-30)),
        log_spectral_error_db_mean=float(np.mean(difference[active])),
        log_spectral_error_db_p95=float(np.percentile(difference[active],95)),
        active_time_frequency_channel_bins=int(np.count_nonzero(active))))
    result["multi_resolution_stft"].sort(key=lambda x:x["window_samples"])
    result["summary"]["spectral_convergence_short_512_1024_2048_mean"] = float(np.mean([
        r["spectral_convergence"] for r in result["multi_resolution_stft"] if r["window_samples"]!=8192]))
    for item in result["multi_resolution_stft"]:
        n,hop,frames = item["window_samples"],item["hop_samples"],item["frames"]
        item["first_frame_relative_samples"] = [0,n]
        item["last_frame_relative_samples"] = [(frames-1)*hop,(frames-1)*hop+n]
        if item["last_frame_relative_samples"][1]>len(reference):
            raise AssertionError("STFT crossed evaluated boundary")
    return result


def channels(audio):
    return dict(stereo=audio,mid=audio.mean(axis=1)[:,None],side=((audio[:,0]-audio[:,1])/2)[:,None])


def channel_metrics(hardware,candidate):
    h,c = channels(hardware),channels(candidate)
    result = {}
    for name in h:
        if assess.rms(h[name])<=1e-12:
            result[name] = dict(status="insufficient_reference_power",reference_rms=assess.rms(h[name]),candidate_rms=assess.rms(c[name]))
        else:
            result[name] = measure(h[name],c[name])
    return result


def verify_inputs(row):
    for key in ("current_wav","current_receipt","hardware","original_comparison"):
        verify_item(row[key])
    for value in row["source_files"].values():
        verify_item(value)
    receipt = json.loads(Path(row["current_receipt"]["path"]).read_text())
    sr,hardware = assess.read_audio(row["hardware"]["path"])
    cr,production = assess.read_audio(row["current_wav"]["path"])
    if sr!=SR or cr!=SR or hardware.shape[1]!=2 or production.shape[1]!=2:
        raise ValueError("Unexpected frozen stereo/rate layout")
    a,b = row["calibration_reference_samples"]
    ca,cb = row["calibration_candidate_samples"]
    lag = row["lag_samples"]
    if [ca,cb]!=[a+lag,b+lag]:
        raise ValueError("Calibration timing changed")
    prefix = assess.rms(hardware[a:b])/assess.rms(production[ca:cb])
    if abs(prefix-row["fixed_current_production_gain"])>1e-12:
        raise ValueError("Current production prefix gain did not reproduce")
    if receipt["settings"]!=row["preserved_settings"] or receipt["ignored_events"]:
        raise ValueError("Frozen factory replay settings changed")
    return hardware,production,receipt


def prepare(args):
    out = args.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    inventory_pin = pin(args.inventory,INVENTORY_SHA)
    inventory = json.loads(args.inventory.read_text())
    build,manifest = engine.checked_build(args.build)
    if manifest["revision"]!=engine.REVISION:
        raise ValueError("Wrong canonical build")
    dependencies = {name:pin(ROOT/"Tools"/name) for name in (
        "compare_saw_w4_official_presets.py","build_saw_w4_experiment.py",
        "assess_hardware_equivalence.py","score_moogie_envelope_candidates.py")}
    harmonic_sources = {}
    for policy in ("estimated","nominal"):
        path = ROOT/f"Docs/fidelity/source-audits/cutoff-taper-moogie-{policy}-2026-09-15.json"
        harmonic_sources[policy] = pin(path)
    protocol = dict(status="prepared_before_candidate_rendering",source_revision=engine.REVISION,
        inventory=inventory_pin,build_manifest=pin(build/"manifest.json"),dependencies=dependencies,
        source_cases=inventory["cases"],case_count=10,
        candidate_count=1,candidate_selection="one externally frozen actual-engine W4 fit; no selection from these ten cases",
        timing="Exact saved production-only first-quarter lag and evaluated sample ranges; no fresh delay or phase fit",
        primary_gain="Current-half-return production scalar, verified from its frozen prefix; shared by both models",
        sensitivity="One RMS scalar from exactly the same frozen prefix of the candidate; no note/event gain or other fit",
        stereo_metrics="Existing512/2048/8192 STFT metrics plus1024; legacy mean unchanged;10/50ms RMS; stereo statistics and separate Mid/Side measures",
        spectral_mask="Existing pairwise union at-60dB reference peak and-80dB floor; active-bin counts retained. No comparison chosen from changing masks.",
        frame_policy="Measure only the exact evaluated slice, no boundary padding or STFT crossing calibration",
        controls="All10 native-disabled W4-renderer outputs must byte-match existing current production; five no-active-classic-Saw W4 outputs must also byte-match",
        replay="Original full SysEx and frozen reconstructed MIDI, identical full settings/event ordering/tail/master/channel/tempo; no parameter edits",
        harmonics=dict(source_receipts=harmonic_sources,
            policy="Moogie only: inherited3notes x3offsets x3shifts,80ms/96harmonics, mean stereo, frozen hardware/production frequencies. Also retain frozen nominal-frequency sensitivity. Existing+93sample renderer convention, distinct from whole-excerpt lag. No frequency fitting, selection or new masks.",
            limitations="Moogie is an unchanged-waveform control. Other wet/multiple-oscillator excerpts have no established independent harmonic acceptance protocol; none invented here."),
        listening="Full common aligned excerpt including prefix, fixed primary scalar and one common attenuation across original/current/W4; no raw WAV edits",
        equivalence_status="not_established")
    save(out/"protocol.json",protocol)
    baseline = []
    for row in inventory["cases"]:
        h,p,_ = verify_inputs(row)
        a,b = row["evaluation_samples"]
        lag,gain = row["lag_samples"],row["fixed_current_production_gain"]
        baseline.append(dict(id=row["id"],channels=channel_metrics(h[a:b],p[a+lag:b+lag]*gain)))
    save(out/"baseline-before-candidate.json",dict(protocol_sha256=sha(out/"protocol.json"),results=baseline))
    print(out/"protocol.json",flush=True)


def verify_render(row,reference,receipt,rendered):
    sidecar_path = Path(rendered["render_receipt"]["path"])
    verify_item(rendered["render_receipt"])
    actual = json.loads(sidecar_path.read_text())
    for key in ("settings","replay_events","replay_event_counts","ignored_events"):
        if actual[key]!=receipt[key]:
            raise ValueError(f"{row['id']}: preserved {key} changed")
    for key in ("sysex","midi"):
        if actual["inputs"][key]["sha256"]!=receipt["inputs"][key]["sha256"]:
            raise ValueError("Candidate changed original patch/performance")
    if actual["output"]["initial_patch"]!=receipt["output"]["initial_patch"] or actual["output"]["latency_samples"]!=93:
        raise ValueError("Initial patch or output latency changed")
    if actual["output"]["active_voices_at_end"]!=0:
        raise ValueError("Unexpected remaining voices")
    verify_item(rendered["wav"])
    sr,audio = assess.read_audio(rendered["wav"]["path"])
    if sr!=SR or audio.shape!=reference.shape:
        raise ValueError("Candidate full output dimensions changed")
    return audio


def moogie_diagnostic(row,original,production,candidate,protocol):
    results = []
    if row["source_files"]["original-patch.syx"]["sha256"]!=moogie.EXPECTED_SYSEX or row["source_files"]["reconstructed-performance.mid"]["sha256"]!=moogie.EXPECTED_MIDI:
        raise ValueError("Inherited Moogie inputs changed")
    for policy,info in protocol["harmonics"]["source_receipts"].items():
        verify_item(info)
        prior = json.loads(Path(info["path"]).read_text())
        if row["hardware"]["sha256"]!=prior["inputs"]["hardware"]["sha256"]:
            raise ValueError("Inherited harmonic hardware changed")
        hardware = original.mean(axis=1)
        models = dict(production=production.mean(axis=1),w4=candidate.mean(axis=1))
        observed = []
        for reference in prior["hardware_measurements"]:
            fresh = moogie.measure(hardware,SR,reference["center_seconds"],prior["frequency_estimates"][str(reference["note_index"])]["hardware_hz"])
            if moogie.hardware_eligibility(fresh)!=reference["eligible"] or not np.allclose(fresh["relative_h1_db"],reference["relative_h1_db"],rtol=0,atol=1e-9):
                raise ValueError("Frozen original harmonic masks/values changed")
            row_result = dict(reference=reference,models={})
            frequency = prior["frequency_estimates"][str(reference["note_index"])]["production_hz"]
            center = reference["center_seconds"]+93/SR
            for name,audio in models.items():
                m = moogie.measure(audio,SR,center,frequency)
                row_result["models"][name] = dict(observation=m,error_db=moogie.difference(m,reference,reference["eligible"]),
                    fit_under1percent=m["residual_power_fraction"]<=.01,
                    qualification="Original eligible harmonics retained even if candidate weak or residual fails")
            observed.append(row_result)
        summaries = {}
        for name in models:
            rows = [dict(shift_seconds=r["reference"]["shift_seconds"],role=r["reference"]["role"],error_db=r["models"][name]["error_db"]) for r in observed]
            summaries[name] = moogie.summarize(rows)
        results.append(dict(frequency_policy=policy,source=info,frequencies=prior["frequency_estimates"],windows=observed,summary=summaries))
    return dict(status="inherited_conditional_diagnostic_no_selection",policies=results)


def compare(args):
    prepared = args.prepared.resolve()
    protocol = json.loads((prepared/"protocol.json").read_text())
    for item in protocol["dependencies"].values():
        verify_item(item)
    verify_item(protocol["inventory"])
    verify_item(protocol["build_manifest"])
    out = args.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    selection_pin = pin(args.selection)
    selected = json.loads(args.selection.read_text())
    vector = selected["candidate_coefficients"]
    if selected["canonical_phase_cycles"]!=0 or len(vector)!=32 or not np.isfinite(vector).all():
        raise ValueError("Invalid frozen vector/canonical phase")
    build = Path(protocol["build_manifest"]["path"]).parent
    engine.checked_build(build)
    candidate_config = engine.config(vector[:16],vector[16:],phase=0.,ramp=1.,enabled=True)
    baseline_before = json.loads((prepared/"baseline-before-candidate.json").read_text())
    if baseline_before["protocol_sha256"]!=sha(prepared/"protocol.json"):
        raise ValueError("Prepared baseline protocol mismatch")
    receipt = dict(status="one_frozen_candidate_all_ten_presets_no_selection",protocol=protocol,
        prepared_protocol=pin(prepared/"protocol.json"),prepared_baseline=pin(prepared/"baseline-before-candidate.json"),
        selection=selection_pin,candidate_config=candidate_config,script=pin(__file__),
        libraries=dict(numpy=np.__version__,scipy=scipy.__version__),cases=[],equivalence_status="not_established")
    save(out/"frozen-inputs.json",receipt)
    # Native controls all run before the enabled candidate is rendered.
    sounds = {}
    for row in protocol["source_cases"]:
        h,p,original_receipt = verify_inputs(row)
        path = out/"cases"/row["id"]
        patch = row["source_files"]["original-patch.syx"]["path"]
        midi = row["source_files"]["reconstructed-performance.mid"]["path"]
        control = engine.render_vector(build,patch,midi,engine.config(enabled=False),path/"native",allow_unsupported=False)
        native = verify_render(row,p,original_receipt,control)
        identical = control["wav"]["sha256"]==row["current_wav"]["sha256"]
        if not identical or not np.array_equal(native,p):
            save(out/"native-control-failure.json",dict(id=row["id"],control=control,expected=row["current_wav"]))
            raise ValueError("Native baseline identity failed: "+row["id"])
        sounds[row["id"]] = (h,p,original_receipt,control)
        print(row["id"]+": native byte identity passed",flush=True)
    pages = []
    for row in protocol["source_cases"]:
        name = row["id"]
        h,p,original_receipt,control = sounds[name]
        path = out/"cases"/name
        rendered = engine.render_vector(build,row["source_files"]["original-patch.syx"]["path"],
             row["source_files"]["reconstructed-performance.mid"]["path"],candidate_config,path/"w4",allow_unsupported=False)
        c = verify_render(row,p,original_receipt,rendered)
        identical = rendered["wav"]["sha256"]==row["current_wav"]["sha256"]
        if row["byte_identity_control"] and not identical:
            save(out/"waveform-control-failure.json",dict(id=name,render=rendered,expected=row["current_wav"]))
            raise ValueError("Non-Saw waveform changed: "+name)
        a,b = row["evaluation_samples"]
        lag,gain = row["lag_samples"],row["fixed_current_production_gain"]
        ca,cb = row["calibration_reference_samples"]
        training_gain = assess.rms(h[ca:cb])/assess.rms(c[ca+lag:cb+lag])
        base = channel_metrics(h[a:b],p[a+lag:b+lag]*gain)
        pre = next(r["channels"] for r in baseline_before["results"] if r["id"]==name)
        if base!=pre:
            raise ValueError("Prepared baseline changed before candidate scoring")
        model = channel_metrics(h[a:b],c[a+lag:b+lag]*gain)
        sensitivity = channel_metrics(h[a:b],c[a+lag:b+lag]*training_gain)
        record = dict(id=name,input=row,native_control=control,candidate_render=rendered,
             native_byte_identity=True,w4_byte_identical=identical,required_w4_byte_identity=row["byte_identity_control"],
             fixed_gain=gain,candidate_prefix_gain_sensitivity=training_gain,
             evaluated_reference_samples=[a,b],evaluated_candidate_samples=[a+lag,b+lag],
             production=base,w4=model,candidate_prefix_gain=sensitivity,
             difference={k:model["stereo"]["summary"][k]-base["stereo"]["summary"][k]
                         for k in base["stereo"]["summary"] if base["stereo"]["summary"][k] is not None})
        if name=="moogie-1":
            record["harmonics"] = moogie_diagnostic(row,h,p,c,protocol)
        else:
            record["harmonics"] = dict(status="no_established_isolated_harmonic_mask_for_this_wet_excerpt",reason=protocol["harmonics"]["limitations"])
        start,end = max(0,-lag),min(len(h),len(p)-lag,len(c)-lag)
        aligned = dict(original=h[start:end],production=p[start+lag:end+lag]*gain,w4=c[start+lag:end+lag]*gain)
        scale = min(.1/assess.rms(aligned["original"]),.98/max(float(abs(y).max()) for y in aligned.values()))
        listening = {}
        for label,y in aligned.items():
            wave = path/(label+"-listen.wav")
            wavfile.write(wave,SR,(y*scale).astype(np.float32))
            listening[label] = pin(wave)
        record["listening"] = dict(reference_samples=[start,end],evaluated_relative_seconds=[(a-start)/SR,(b-start)/SR],
             common_attenuation=scale,frames=end-start,files=listening,primary_fixed_gain_only=True)
        save(path/"result.json",record)
        receipt["cases"].append(record)
        players = "".join(f'<p>{html.escape(label)}<br><audio controls preload="none" src="cases/{name}/{label}-listen.wav"></audio></p>' for label in aligned)
        pages.append(f'<section><h2>{html.escape(row["case"]["title"])}</h2><p>Evaluation {((a-start)/SR):.3f}–{((b-start)/SR):.3f}s; fixed production gain. Reconstructed MIDI; exact recorded patch revision unverified.</p>{players}</section>')
        print(name+f": SC {base['stereo']['summary']['spectral_convergence_mean']:.6f} -> {model['stereo']['summary']['spectral_convergence_mean']:.6f}; identity={identical}",flush=True)
        save(out/"progress.json",receipt)
    receipt["all_native_byte_identical"] = all(r["native_byte_identity"] for r in receipt["cases"])
    receipt["all_five_non_saw_byte_identical"] = all(r["w4_byte_identical"] for r in receipt["cases"] if r["required_w4_byte_identity"])
    save(out/"results.json",receipt)
    (out/"index.html").write_text('<!doctype html><meta charset="utf-8"><title>Full-engine W4 preset comparison</title><style>body{font:16px system-ui;max-width:900px;margin:40px auto;padding:20px}section{border-top:1px solid #bbb;margin-top:32px}audio{width:100%}</style><h1>One frozen W4 candidate · all ten presets</h1><p>Original / current production / experimental W4. Same fixed timing and production gain; one common per-case attenuation. No coefficient selection from these recordings. All regressions retained.</p>'+''.join(pages))
    print(out/"results.json",flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest="stage",required=True)
    q = commands.add_parser("prepare")
    q.add_argument("--inventory",type=Path,default=INVENTORY)
    q.add_argument("--build",type=Path,required=True)
    q.add_argument("--output",type=Path,required=True)
    q = commands.add_parser("compare")
    q.add_argument("--prepared",type=Path,required=True)
    q.add_argument("--selection",type=Path,required=True)
    q.add_argument("--output",type=Path,required=True)
    args = p.parse_args()
    prepare(args) if args.stage=="prepare" else compare(args)


if __name__=="__main__":
    main()
