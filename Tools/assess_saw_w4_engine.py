#!/usr/bin/env python3
"""Fixed full-engine W4 evaluation; no render, source/phase/frequency fit or selection.

Dry candidate layout: ROOT/manifest.json and ROOT/lp{12,24}/candidate.wav,
candidate.render.json, patch.syx, performance.mid. Omitting --candidate-root
runs the pinned production baseline and deterministic masking controls only.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
import numpy as np
import scipy
from scipy import signal
from scipy.io import wavfile

import assess_hardware_equivalence as assess
import assess_production_high_note_saw as high
import analyze_deepsonic_filter as harmonics
import analyze_deepsonic_chord_envelope as chords
from render_midi import parse_smf

ROOT = Path(__file__).resolve().parents[1]
REVISION = "545b3d37d9cc1f80bf39bc5d0bf49c0cced1d9f6"
SR, LAG = 44100, -1406
EXCLUDED = (round(18.75*SR), round(19.25*SR))
TRAIN = (66150, 85444)
GAINS = {12: 4.137125725839024, 24: 3.870462967942607}
FFT_WINDOWS = (512, 1024, 2048, 8192)
RMS_WINDOWS = (441, 2205)
OFFSETS = (.10, .18, .26, .34)
FACTORY_SAW = {"air-lead-1", "brassy-ld-1", "dist-bs-1", "so-juno-1", "vangelead"}
FACTORY_CONTROL = {"club-bass", "cotton-wool", "moogie-1", "pedal-bs-1", "supa-juce-1"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")


def artifact(path, expected=None):
    path = Path(path).resolve()
    actual = sha(path)
    if expected is not None and actual != expected:
        raise ValueError(f"Input hash mismatch: {path}")
    return dict(path=str(path), sha256=actual)


def subtract(segments, exclusion=EXCLUDED):
    result = []
    left, right = exclusion
    for a, b in segments:
        if b <= left or a >= right:
            result.append([a, b])
        else:
            if a < left:
                result.append([a, left])
            if b > right:
                result.append([right, b])
    return result


def paired_support(segments, h_length, c_length, lag=LAG):
    return [[max(a, 0, -lag), min(b, h_length, c_length-lag)] for a, b in segments
            if min(b, h_length, c_length-lag) > max(a, 0, -lag)]


def arrays(reference, candidate, segments, lag):
    for a, b in segments:
        if not (0 <= a < b <= len(reference) and 0 <= a+lag < b+lag <= len(candidate)):
            raise ValueError("Invalid exact paired support")
        yield reference[a:b], candidate[a+lag:b+lag]


def log_stats(delta, active):
    x = delta[active]
    return dict(bins=int(x.size), mean_db=float(np.mean(x)) if x.size else None,
                p95_db=float(np.percentile(x, 95)) if x.size else None)


def measure_segments(reference, candidate, segments, gain, lag=LAG):
    """Restart STFT/RMS at each support; aggregate only measured bins afterward."""
    pairs = [(x, y*gain) for x, y in arrays(reference, candidate, segments, lag)]
    if not pairs:
        return dict(status="no_supported_samples", reference_segments=segments)
    reference_power = sum(float(x@x) for x, _ in pairs)
    model_power = sum(float(y@y) for _, y in pairs)
    if reference_power <= 1e-24:
        return dict(status="silent_reference", reference_segments=segments)
    spectra = []
    for window in FFT_WINDOWS:
        values = [[], []]
        coverage = []
        for (start, end), pair in zip(segments, pairs):
            if end-start < window:
                coverage.append(dict(reference_segment=[start,end], frames=0, reason="shorter_than_window"))
                continue
            for i, x in enumerate(pair):
                _, _, z = signal.stft(x, fs=SR, window="hann", nperseg=window,
                                      noverlap=3*window//4, boundary=None, padded=False)
                values[i].append(np.abs(z))
            frames = values[0][-1].shape[-1]
            last_start = start+(frames-1)*(window//4)
            if last_start+window > end:
                raise AssertionError("STFT frame crossed declared boundary")
            coverage.append(dict(reference_segment=[start,end], frames=frames,
                                 first_frame_samples=[start,start+window],
                                 last_frame_samples=[last_start,last_start+window]))
        if not values[0]:
            spectra.append(dict(window_samples=window, frames=0, coverage=coverage))
            continue
        a, b = [np.concatenate(x, axis=-1) for x in values]
        peak = float(a.max())
        floor = max(peak*10**(assess.FLOOR_DB/20), 1e-30)
        active = a >= max(peak*10**(assess.ACTIVE_DB/20), 1e-30)
        union = np.maximum(a,b) >= max(peak*10**(assess.ACTIVE_DB/20), 1e-30)
        delta = abs(20*np.log10(np.maximum(b,floor)/np.maximum(a,floor)))
        spectra.append(dict(window_samples=window, hop_samples=window//4,
             frames=int(a.shape[-1]), coverage=coverage,
             spectral_convergence=float(np.linalg.norm(b-a)/max(np.linalg.norm(a),1e-30)),
             hardware_only_log_error=log_stats(delta,active), pair_union_log_error_sensitivity=log_stats(delta,union),
             reference_peak=peak, absolute_magnitude_floor=floor))
    envelopes = []
    peak = max(float(np.max(abs(x))) for x, _ in pairs)
    floor = max(peak*10**(assess.FLOOR_DB/20),1e-30)
    for window in RMS_WINDOWS:
        values = [[], []]
        coverage = []
        for (start,end), pair in zip(segments,pairs):
            if end-start < window:
                coverage.append(dict(reference_segment=[start,end], frames=0))
                continue
            for i,x in enumerate(pair):
                values[i].append(assess.rms_envelope(x[:,None],window,220))
            count = len(values[0][-1])
            last_start = start+(count-1)*220
            if last_start+window > end:
                raise AssertionError("RMS frame crossed declared boundary")
            coverage.append(dict(reference_segment=[start,end],frames=count,
                                 first_frame_samples=[start,start+window],last_frame_samples=[last_start,last_start+window]))
        if not values[0]:
            envelopes.append(dict(window_samples=window,frames=0,coverage=coverage))
            continue
        a,b = [np.concatenate(v) for v in values]
        active = a >= max(float(a.max())*10**(assess.ACTIVE_DB/20),1e-30)
        union = np.maximum(a,b) >= max(float(a.max())*10**(assess.ACTIVE_DB/20),1e-30)
        delta = abs(20*np.log10(np.maximum(b,floor)/np.maximum(a,floor)))
        envelopes.append(dict(window_samples=window,hop_samples=220,frames=len(a),coverage=coverage,
                              hardware_only_error=log_stats(delta,active), pair_union_error_sensitivity=log_stats(delta,union)))
    residual = sum(float((y-x)@(y-x)) for x,y in pairs)/reference_power
    sc = {s["window_samples"]: s["spectral_convergence"] for s in spectra if s["frames"]}
    return dict(status="measured_not_equivalence", reference_segments=segments,
                candidate_segments=[[a+lag,b+lag] for a,b in segments],
                samples=sum(b-a for a,b in segments), fixed_gain=gain, lag_samples=lag,
                stft=spectra,rms=envelopes,
                spectral_convergence_legacy_mean=float(np.mean([sc[w] for w in (512,2048,8192) if w in sc])),
                spectral_convergence_short_mean=float(np.mean([sc[w] for w in (512,1024,2048) if w in sc])),
                level_difference_db=float(10*np.log10(max(model_power,1e-30)/reference_power)),
                raw_fixed_phase_residual_power=residual,
                waveform_qualification="Unfitted oscillator phase; not a perceptual percentage or equivalence gate")


def frame_guard_control(production):
    supports = subtract([[max(0,-LAG),round(1.45*SR)],[2*SR,min(len(production),30*SR)]])
    # Shifted candidate support is tested too: corruption is inserted only in
    # excluded candidate-time samples and cannot leak through a transform.
    corrupted = production.copy()
    corrupted[EXCLUDED[0]+LAG:EXCLUDED[1]+LAG] += 100
    identity = measure_segments(production,production,supports,1.,0)
    # For zero-lag self control, use the corresponding unshifted exclusion.
    corruption_zero = production.copy()
    corruption_zero[EXCLUDED[0]:EXCLUDED[1]] += 100
    hidden = measure_segments(production,corruption_zero,supports,1.,0)
    if identity != hidden or identity["raw_fixed_phase_residual_power"] != 0:
        raise AssertionError("Excluded training corruption affected validation")
    shifted_reference = np.r_[np.zeros(-LAG),production[:LAG]]
    shift_hidden = measure_segments(shifted_reference,corrupted,supports,1.,LAG)
    shift_identity = measure_segments(shifted_reference,production,supports,1.,LAG)
    if shift_hidden != shift_identity or shift_identity["raw_fixed_phase_residual_power"] != 0:
        raise AssertionError("Excluded paired candidate-time corruption leaked")
    visible = production.copy()
    visible[EXCLUDED[1]+100] += .1
    retained = measure_segments(production,visible,supports,1.,0)
    if retained["raw_fixed_phase_residual_power"] <= 0 or not all(r.get("spectral_convergence",0)>0 for r in retained["stft"]):
        raise AssertionError("Retained support mutation was not detected")
    return dict(status="passed", identity=identity,
                excluded_100_amplitude_corruption_invisible=True,
                shifted_candidate_exclusion_corruption_invisible=True,
                retained_single_sample_corruption_detected=True,
                retained_corruption_residual_power=retained["raw_fixed_phase_residual_power"])


def observe(audio, start, spec):
    center = start+spec["width"]*SR/2
    try:
        if spec["type"] == "single":
            m = harmonics.measure(audio,SR,center/SR,spec["width"],440*2**((spec["note"]-69)/12))
        else:
            m = chords.measure_chord(audio,SR,center/SR,spec["width"],spec["notes"],spec["target"])
        reasons = []
        if m["fit_residual_power"] > .01:
            reasons.append("over_1_percent_unexplained_power")
        if m["condition_number"] > 100:
            reasons.append("condition_over100")
        if not np.isfinite(m["amplitude"]).all() or m["amplitude"][0] <= 1e-15:
            reasons.append("nonfinite_or_negligible_fundamental")
        return dict(valid=not reasons,rejections=reasons,observation=m)
    except ValueError as error:
        return dict(valid=False,rejections=[str(error)],observation=None)


def harmonic_rows(hardware,models,specs):
    rows = []
    for spec in specs:
        start = round((spec["on"]+spec["offset"]-spec["width"]/2)*SR)
        end = start+round(spec["width"]*SR)
        if spec["role"] == "validation" and start < EXCLUDED[1] and end > EXCLUDED[0]:
            raise AssertionError("Coefficient-training interval reached harmonic validation")
        original = observe(hardware,start,spec)
        hm = original["observation"]
        eligible = []
        if hm:
            for i,h in enumerate(hm["harmonics"]):
                valid = original["valid"] and h <= 16 and (h==1 or hm["harmonic_ratio_db"][i]>-45)
                if spec["type"] == "chord":
                    valid &= hm["snr_proxy_db"][i]>=20
                eligible.append(bool(valid))
        row = dict(spec=spec,hardware_samples=[start,end],candidate_samples=[start+LAG,end+LAG],
                   hardware=original,hardware_only_eligible=eligible,models={})
        for name,item in models.items():
            observed = observe(item["audio"],start+LAG,spec)
            m = observed["observation"]
            output = dict(measurement=observed)
            if hm and m:
                if hm["harmonics"] != m["harmonics"]:
                    raise ValueError("Changed nominal harmonic IDs")
                amplitude = 20*np.log10(np.maximum(m["amplitude"],1e-30)/np.maximum(hm["amplitude"],1e-30))
                output.update(ratio_difference_db=(np.array(m["harmonic_ratio_db"])-hm["harmonic_ratio_db"]).tolist(),
                              fixed_gain_amplitude_difference_db=(amplitude+20*np.log10(item["fixed_gain"])).tolist(),
                              note36_gain_amplitude_sensitivity_db=(amplitude+20*np.log10(item["training_gain"])).tolist(),
                              candidate_under_minus45_dbc=[bool(x<=-45) for x in m["harmonic_ratio_db"]])
            row["models"][name] = output
        rows.append(row)
    return rows


def stats(values):
    return dict(observations=len(values),rms_db=float(np.sqrt(np.mean(np.square(values)))) if values else None,
                signed_mean_db=float(np.mean(values)) if values else None,
                maximum_absolute_db=float(np.max(abs(np.asarray(values)))) if values else None)


def summarize_harmonics(rows,names):
    summaries = []
    for role in ("calibration","validation"):
        for kind in ("single","chord"):
            selected = [r for r in rows if r["spec"]["role"]==role and r["spec"]["type"]==kind]
            if not selected:
                continue
            for name in names:
                result = dict(id=name,role=role,type=kind,attempted_windows=len(selected),
                     hardware_valid_windows=sum(r["hardware"]["valid"] for r in selected),
                     candidate_invalid_on_hardware_valid_windows=sum(r["hardware"]["valid"] and not r["models"][name]["measurement"]["valid"] for r in selected),bands={})
                for label,lo,hi in (("H1",1,1),("H2_H8",2,8),("H9_H16",9,16),("H2_H16",2,16)):
                    errors = {k:[] for k in ("ratio_difference_db","fixed_gain_amplitude_difference_db","note36_gain_amplitude_sensitivity_db")}
                    required,missing,weak = 0,0,0
                    for row in selected:
                        hm = row["hardware"]["observation"]
                        if not hm:
                            continue
                        model = row["models"][name]
                        for i,h in enumerate(hm["harmonics"]):
                            if not row["hardware_only_eligible"][i] or not lo<=h<=hi:
                                continue
                            required += 1
                            if "ratio_difference_db" not in model:
                                missing += 1
                                continue
                            weak += model["candidate_under_minus45_dbc"][i]
                            for key in errors:
                                errors[key].append(model[key][i])
                    result["bands"][label] = dict(required_original_only_bins=required,missing_candidate_bins=missing,
                          weak_candidate_bins=weak,
                          complete_mask_proxy_statistics={k:stats(v) for k,v in errors.items()} if not missing else None,
                          available_bin_diagnostic_if_incomplete={k:stats(v) for k,v in errors.items()} if missing else None,
                          qualification="Every hardware-eligible bin retained regardless candidate fit/weak flag; invalid-model statistics are proxies, not certified harmonic errors")
                summaries.append(result)
    return summaries


def harmonic_mask_control(rows):
    row = next(r for r in rows if r["spec"]["role"]=="validation" and
               r["spec"]["type"]=="single" and any(r["hardware_only_eligible"]))
    # Metadata ablations exercise failure handling, not a waveform model.
    failed = json.loads(json.dumps(row))
    failed["models"]["production"]["measurement"]["valid"] = False
    failed["models"]["production"]["measurement"]["rejections"] = ["planted_fit_failure"]
    failed["models"]["production"]["candidate_under_minus45_dbc"] = [True]*len(row["hardware_only_eligible"])
    base = summarize_harmonics([row],["production"])[0]
    bad = summarize_harmonics([failed],["production"])[0]
    if bad["candidate_invalid_on_hardware_valid_windows"] != 1:
        raise AssertionError("Candidate invalid-window flag disappeared")
    for band in base["bands"]:
        a,b = base["bands"][band],bad["bands"][band]
        if a["required_original_only_bins"] != b["required_original_only_bins"] or a["complete_mask_proxy_statistics"] != b["complete_mask_proxy_statistics"]:
            raise AssertionError("Candidate fit/weak flag selected original harmonic mask")
    missing = json.loads(json.dumps(failed))
    del missing["models"]["production"]["ratio_difference_db"]
    absent = summarize_harmonics([missing],["production"])[0]
    for band in absent["bands"].values():
        if band["required_original_only_bins"] and (band["missing_candidate_bins"] != band["required_original_only_bins"] or band["complete_mask_proxy_statistics"] is not None):
            raise AssertionError("Missing model bins silently reduced complete-mask denominator")
    return dict(status="passed",candidate_fit_and_weak_flags_leave_original_masks_unchanged=True,
                missing_model_bins_prevent_complete_mask_summary=True,
                exercised_reference_samples=row["hardware_samples"])


def load_model(folder,expected_sha,baseline_receipt=None):
    folder = Path(folder).resolve()
    wav = folder/"candidate.wav"
    info = artifact(wav,expected_sha)
    receipt_path = folder/"candidate.render.json"
    receipt = json.loads(receipt_path.read_text())
    patch = artifact(folder/"patch.syx")
    midi = artifact(folder/"performance.mid",high.MIDI_HASH)
    if receipt["output"]["sha256"] != info["sha256"] or receipt["inputs"]["midi"]["sha256"] != midi["sha256"] or receipt["inputs"]["sysex"]["sha256"] != patch["sha256"]:
        raise ValueError("Render receipt identity mismatch")
    if baseline_receipt:
        for key in ("settings","replay_events","ignored_events","replay_event_counts"):
            if receipt[key] != baseline_receipt[key]:
                raise ValueError("Candidate changed replay/settings: "+key)
        if patch["sha256"] != baseline_receipt["inputs"]["sysex"]["sha256"]:
            raise ValueError("Candidate changed raw recipe")
    if receipt["output"]["active_voices_at_end"] != 0 or receipt["output"]["latency_samples"] != 93 or receipt["replay_event_counts"] != {"note_on":124,"note_off":124}:
        raise ValueError("Candidate replay contract changed")
    ignored = receipt["ignored_events"]
    if len(ignored)!=1 or ignored[0]["meta_type"]!=32 or ignored[0]["hex"]!="00":
        raise ValueError("Unexpected omitted MIDI")
    sr,audio = wavfile.read(wav)
    if sr != SR or audio.dtype != np.float32 or audio.ndim!=2 or audio.shape[1]!=2 or not np.isfinite(audio).all():
        raise ValueError("Invalid candidate float stereo audio")
    if len(audio)!=receipt["output"]["frames"] or len(audio)<=receipt["midi"]["end_sample"]:
        raise ValueError("Incomplete candidate duration")
    if float(abs(audio[:,0]-audio[:,1]).max()) > np.finfo(np.float32).eps*float(abs(audio).max()):
        raise ValueError("Dry mono routing changed; left-only scoring would hide a channel difference")
    return dict(audio=audio[:,0].astype(float),receipt=receipt,
                provenance=dict(wav=info,receipt=artifact(receipt_path),patch=patch,midi=midi,
                     renderer=artifact(receipt["inputs"]["renderer"]["path"],receipt["inputs"]["renderer"]["sha256"]),
                     exact_patch_hex=(folder/"patch.syx").read_bytes().hex(),
                     peak=float(abs(audio).max()),full_scale_samples=int(np.count_nonzero(abs(audio)>=1)),
                     max_channel_difference=float(abs(audio[:,0]-audio[:,1]).max()),finite=True,ended_voices=0,no_future_midi=True))


def candidate_provenance(root,model,slope):
    root = Path(root).resolve()
    manifest = json.loads((root/"manifest.json").read_text())
    selected = manifest["selection"]
    selection_info = artifact(selected["path"],selected["sha256"])
    selection = json.loads(Path(selection_info["path"]).read_text())
    folder = root/f"lp{slope}"
    receipt_path = folder/"experiment-render.json"
    rendered = json.loads(receipt_path.read_text())
    pins = {key:artifact(rendered[key]["path"],rendered[key]["sha256"])
            for key in ("source_manifest","coefficients","native_config","wav","render_receipt")}
    if pins["wav"]["sha256"]!=model["provenance"]["wav"]["sha256"] or pins["render_receipt"]["sha256"]!=model["provenance"]["receipt"]["sha256"]:
        raise ValueError("Candidate experiment receipt disagrees with measured output")
    build_path = Path(pins["source_manifest"]["path"])
    build = json.loads(build_path.read_text())
    if build["revision"]!=REVISION:
        raise ValueError("Candidate builder used another shipping revision")
    for path,expected in build["source_original_sha256"].items():
        original = subprocess.check_output(["git","show",f"{REVISION}:{path}"],cwd=ROOT)
        if hashlib.sha256(original).hexdigest()!=expected:
            raise ValueError("Candidate original source identity mismatch")
    frozen = {path:artifact(build_path.parent/"source"/path,h)
              for path,h in build["source_frozen_sha256"].items()}
    binary = build["binaries"]["SeptumRenderMidi"]
    if binary["sha256"]!=model["provenance"]["renderer"]["sha256"]:
        raise ValueError("Candidate renderer did not come from this build")
    values = json.loads(Path(pins["coefficients"]["path"]).read_text())
    coeff = [*values["negative"],*values["positive"]]
    if len(coeff)!=32 or not np.isfinite(coeff).all() or values["ramp"]!=1 or values["phase_cycles_training_note91"]!=0 or not values["enabled"]:
        raise ValueError("Candidate changed fixed ramp/canonical phase or W4 family")
    if coeff!=selection["candidate_coefficients"] or selection["canonical_phase_cycles"]!=0:
        raise ValueError("Candidate coefficients do not equal frozen training selection")
    native = [float(v) for v in Path(pins["native_config"]["path"]).read_text().split()]
    if native != [1.,1.,0.,*coeff]:
        raise ValueError("Native renderer config differs from selected JSON")
    return dict(manifest=artifact(root/"manifest.json"),selection=selection_info,
                experiment_receipt=artifact(receipt_path),render_pins=pins,
                verified_frozen_source=frozen,state_diagnostics=rendered["stats"],
                fixed_canonical_phase=True,fixed_unit_ramp=True,selected_coefficients=coeff)


def factory_inventory(output):
    gain_root = ROOT/"build-fidelity/hardware-benchmark/reverb-gain-candidates/run-01"
    production_root = ROOT/"build-fidelity/hardware-benchmark/reverb-return-integration/run-01/renders"
    original_root = ROOT/"build-fidelity/hardware-benchmark/final-production-linear-lfo"
    saved = json.loads((gain_root/"results.json").read_text())
    verification = json.loads((production_root/"results.json").read_text())
    rows = []
    for row in saved["cases"]:
        name = row["id"]
        current = production_root/"legacy"/name
        record = next(r for r in verification["results"] if r["cohort"]=="legacy" and r["id"]==name)
        wav = artifact(current/"shipping.wav",record["wav_sha256"])
        receipt = json.loads((current/"shipping.render.json").read_text())
        sr,c = assess.read_audio(wav["path"])
        hw_path = gain_root/"cases"/name/"hardware-excerpt-raw.wav"
        hardware = artifact(hw_path,row["input_sha256"]["hardware-excerpt-raw.wav"])
        hs,h = assess.read_audio(hw_path)
        if sr!=SR or hs!=sr:
            raise ValueError("Changed factory sample rate")
        lag = row["calibration"]["candidate_lag_samples"]
        a,b = row["calibration_reference_samples"]
        ca,cb = row["calibration_candidate_samples"]
        if [ca,cb]!=[a+lag,b+lag]:
            raise ValueError("Changed factory prefix coverage")
        gain = assess.rms(h[a:b])/assess.rms(c[ca:cb])
        expected = row["models"]["gain-0.5"]["training_gain"]
        if abs(gain-expected)>1e-12 or wav["sha256"]!=row["models"]["gain-0.5"]["raw_sha256"]:
            raise ValueError("Current prefix scalar or output failed identity")
        source_files = {key:artifact(current/key,row["input_sha256"][key])
                        for key in ("original-patch.syx","reconstructed-performance.mid")}
        if any(receipt["inputs"][key]["sha256"]!=source_files[filename]["sha256"]
               for key,filename in (("sysex","original-patch.syx"),("midi","reconstructed-performance.mid"))):
            raise ValueError("Factory receipt input mismatch")
        rows.append(dict(id=name,classic_saw_active=name in FACTORY_SAW,
             byte_identity_control=name in FACTORY_CONTROL,
             current_wav=wav,current_receipt=artifact(current/"shipping.render.json",record["receipt_sha256"]),
             source_files=source_files,hardware=hardware,
             original_comparison=artifact(original_root/name/"comparison.json",row["comparison_sha256"]),
             preserved_settings=receipt["settings"],case=row["case"],uncertainty=row["limitations"],
             lag_samples=lag,calibration_reference_samples=[a,b],calibration_candidate_samples=[ca,cb],
             evaluation_samples=row["evaluation_samples"],fixed_current_production_gain=expected,
             verified_current_prefix_gain=gain,old_pre_return_scalar_sensitivity=row["calibration"]["candidate_gain"]))
    if {r["id"] for r in rows} != FACTORY_SAW|FACTORY_CONTROL:
        raise ValueError("Factory ten-case set changed")
    result = dict(status="inputs_only_no_candidate_factory_scoring",source=artifact(gain_root/"results.json"),
         production_verification=artifact(production_root/"results.json"),cases=rows,
         policy="Saved pre-return-production first-quarter lag and coverage; current-half-return scalar reproduced from exactly that prefix. Baseline and W4 share it. Candidate prefix scalar is sensitivity only.")
    save(output,result)
    return artifact(output)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sources",required=True,type=Path)
    p.add_argument("--baseline-root",type=Path,default=ROOT/"build-fidelity/envelope-hypothesis/dry-v2")
    p.add_argument("--candidate-root",action="append",default=[],help="id=directory; absent means baseline/control only")
    p.add_argument("--output",required=True,type=Path)
    p.add_argument("--skip-factory-inventory",action="store_true",help="For reproductions without the separate cached ten-preset bundle")
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    sources = args.sources.resolve()
    source_hashes = {}
    for name in subprocess.check_output(["git","ls-tree","-r","--name-only",REVISION,"Source/DSP"],cwd=ROOT,text=True).splitlines()+["Tools/RenderMidi.cpp"]:
        data = subprocess.check_output(["git","show",f"{REVISION}:{name}"],cwd=ROOT)
        source_hashes[name] = hashlib.sha256(data).hexdigest()
        if (ROOT/name).read_bytes()!=data:
            raise ValueError("Working shipping source differs from authoritative545b3d3")
    q0 = json.loads(high.RECIPE.read_text())
    train = q0["protocol"]["training_note"]
    isolated = [n for n in q0["protocol"]["isolated_validation_notes"] if n["on"]!=18.75]
    midi_path = sources/"deepsonic_-_filter_demo_-_comparsion_sequence.mid"
    midi_info = artifact(midi_path,high.MIDI_HASH)
    parsed = parse_smf(midi_path.read_bytes())
    held,notes = {},[]
    for event in parsed["events"]:
        if event["kind"]!="midi":
            continue
        m = bytes.fromhex(event["hex"])
        if m[0]==0x90 and m[2]:
            held[m[1]] = event["sample"]/SR
        elif m[0] in (0x80,0x90):
            notes.append(dict(note=m[1],on=held.pop(m[1]),off=event["sample"]/SR))
        else:
            raise ValueError("Original MIDI contains control changes")
    if held or len(notes)!=124:
        raise ValueError("Original sequence changed")
    chord_notes = []
    for on,pitches,target in chords.CHORDS:
        select = [n for n in notes if n["on"]==on and n["note"] in pitches]
        if len(select)!=3 or len({n["off"] for n in select})!=1:
            raise ValueError("Chord events changed")
        chord_notes.append(dict(on=on,off=select[0]["off"],notes=pitches,target=target))
    candidate_roots = {}
    for value in args.candidate_root:
        name,path = value.split("=",1)
        if not name or name=="production" or name in candidate_roots or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-._" for c in name):
            raise ValueError("Invalid/duplicate candidate ID")
        candidate_roots[name] = Path(path).resolve()
    protocol = dict(status="frozen_before_candidate_scoring",source_revision=REVISION,shipping_source_sha256=source_hashes,
         original_midi=midi_info,recipe_source=artifact(high.RECIPE),prior_highnote=artifact(high.W4),
         lag_samples=LAG,lag_formula="round(93+nominal_filter_attack1ms*44100-.035*44100)",
         fixed_primary_gains=GAINS,gain_calibration_reference_samples=list(TRAIN),gain_calibration_candidate_samples=[t+LAG for t in TRAIN],
         gain_policy="Original note36 scalars primary shared baseline/candidate; each complete candidate note36 RMS gain is separately labeled sensitivity only",
         exclusion_reference_samples=list(EXCLUDED),exclusion_seconds=[18.75,19.25],
         exclusion_policy="Remove coefficient-training note from every primary aggregate; restart STFT/RMS inside each support; never concatenate audio across a gap",
         whole_primary=["before-calibration[0,1.45)","post-calibration[2,18.75)+[19.25,common-end)","union_of_those_three"],
         isolated_notes=isolated,chords=chord_notes,stft_windows=list(FFT_WINDOWS),rms_windows=list(RMS_WINDOWS),rms_hop=220,
         spectral_log_policy="Hardware-only activity mask primary at-60dB of aggregate hardware peak; floor-80dB. Pair-union activity sensitivity retains candidate-only artifacts. Counts saved.",
         harmonic_policy="Existing80ms independent quadrature/linear-ramp estimator, up to30harmonics below8kHz. Original residual<=1%, condition<=100 and H2-H16>-45dBc determine masks. Chords additionally>=20dB SNRproxy. Candidate failure/weak flags never remove original bins.",
         harmonic_offsets=list(OFFSETS),chord_offsets=[.46,.54,.62],
         five_highnote_policy="Unchanged W4 fivewindows+originalLP12aliasIDs remain exploratory; overlapping91diagnostic not primary. No waveform phase/frequency/gain optimization.",
         source_status="original124-noteMIDI plus physical recipe reconstruction; capture and originalrawpatch uncertainty retained",
         equivalence_status="not_established")
    save(out/"protocol.json",protocol)
    (out/"experiment-script.py").write_bytes(Path(__file__).read_bytes())
    provenance = dict(script=artifact(__file__),command=[sys.executable,*sys.argv],
         dependencies={n:artifact(ROOT/"Tools"/n) for n in ("assess_hardware_equivalence.py","assess_production_high_note_saw.py","analyze_deepsonic_filter.py","analyze_deepsonic_chord_envelope.py","analyze_deepsonic_saw_aliases.py","fit_high_note_saw_wrap_kernels.py","fit_high_note_saw_models.py","render_midi.py","generate_timbre_capture.py")},
         libraries=dict(numpy=np.__version__,scipy=scipy.__version__),
         production_source=high.source_provenance(args.baseline_root),
         candidate_manifests={name:artifact(path/"manifest.json") for name,path in candidate_roots.items()})
    if not args.skip_factory_inventory:
        provenance["official_preset_inputs"] = factory_inventory(out/"official-preset-inputs.json")
    decoder = Path(shutil.which("ffmpeg")).resolve()
    provenance["decoder"] = dict(**artifact(decoder),version=subprocess.check_output([str(decoder),"-version"],text=True).splitlines()[0])
    previous = json.loads(high.W4.read_text())
    passages = [previous["protocol"]["training"]]+previous["protocol"]["evaluation"]
    poly = next(r for r in previous["baseline_models"] if r["id"]=="polyblep")
    masks = [r["aliases"]["lines"] for r in poly["scores"]]
    acquisition = json.loads(high.CATALOG.read_text())
    results = dict(protocol=protocol,provenance=provenance,slopes=[])
    for slope in (12,24):
        name = f"roland_sh-201_-_filter_demo_-_lpf{slope}_q000.mp3"
        expected = next(x["sha256"] for x in acquisition["assets"] if Path(x["path"]).name==name)
        media = artifact(sources/name,expected)
        wav = out/f"hardware-lp{slope}.wav"
        command = [str(decoder),"-hide_banner","-loglevel","error","-nostdin","-i",media["path"],"-c:a","pcm_f32le",str(wav)]
        subprocess.run(command,check=True)
        sr,hardware = wavfile.read(wav)
        if sr!=SR or hardware.ndim!=1 or hardware.dtype!=np.float32 or not np.isfinite(hardware).all():
            raise ValueError("Unexpected original decode")
        hardware = hardware.astype(float)
        baseline = load_model(args.baseline_root/f"audio/production/lp{slope}",high.WAV_HASH[slope])
        if baseline["provenance"]["patch"]["sha256"] != high.PATCH_HASH[slope]:
            raise ValueError("Pinned dry recipe hash changed")
        models = {"production":baseline}
        for label,path in candidate_roots.items():
            models[label] = load_model(path/f"lp{slope}",None,baseline["receipt"])
            models[label]["provenance"]["experiment"] = candidate_provenance(path,models[label],slope)
        if any(len(m["audio"])!=len(baseline["audio"]) for m in models.values()):
            raise ValueError("Candidate changed full render duration")
        n = min(len(hardware),len(baseline["audio"])-LAG)
        base_segments = paired_support([[0,round(1.45*SR)],[2*SR,n]],len(hardware),len(baseline["audio"]))
        segments = subtract(base_segments)
        supports = dict(primary_all=segments,before_calibration=segments[:1],after_calibration=segments[1:])
        for i,note in enumerate(isolated):
            supports[f"isolated-{i}-{note['note']}"] = paired_support([[round(note["on"]*SR),round(note["off"]*SR)]],len(hardware),len(baseline["audio"]))
        for i,chord in enumerate(chord_notes):
            supports[f"chord-{i}-full"] = [[round(chord["on"]*SR),round(chord["off"]*SR)]]
            supports[f"chord-{i}-late"] = [[round((chord["on"]+.41)*SR),round((chord["on"]+.67)*SR)]]
        if any(a<EXCLUDED[1] and b>EXCLUDED[0] for ss in supports.values() for a,b in ss):
            raise AssertionError("Training interval leaked into primary support")
        scored = {}
        for label,model in models.items():
            model["fixed_gain"] = GAINS[slope]
            model["training_gain"] = assess.rms(hardware[TRAIN[0]:TRAIN[1]])/assess.rms(model["audio"][TRAIN[0]+LAG:TRAIN[1]+LAG])
            if label=="production" and abs(model["training_gain"]-GAINS[slope])>1e-12:
                raise ValueError("Frozen dry baseline training scalar did not reproduce")
            scored[label] = dict(provenance=model["provenance"],note36_gain=model["training_gain"],
                  fixed_primary_gain=GAINS[slope],identical_raw_to_production=model["provenance"]["wav"]["sha256"]==high.WAV_HASH[slope],
                  primary_fixed_gain={key:measure_segments(hardware,model["audio"],value,GAINS[slope]) for key,value in supports.items()},
                  candidate_note36_gain_sensitivity={key:measure_segments(hardware,model["audio"],value,model["training_gain"]) for key,value in supports.items()} if label!="production" else "identical_to_primary")
            print(f"LP{slope} {label}: full audio metrics complete",flush=True)
        specs = [dict(type="single",role="calibration" if note==train else "validation",on=note["on"],note=note["note"],offset=offset,width=.08)
                 for note in [train,*isolated] for offset in OFFSETS]
        specs += [dict(type="chord",role="validation",on=n["on"],notes=n["notes"],target=n["target"],offset=offset,width=.08)
                  for n in chord_notes for offset in (.46,.54,.62)]
        observed = harmonic_rows(hardware,models,specs)
        exploratory = []
        for i,passage in enumerate(passages):
            a,b = passage["start_sample"],passage["end_sample"]
            x = hardware[a:b]
            if slope==12 and hashlib.sha256(x.tobytes()).hexdigest()!=passage["sample_sha256"]:
                raise ValueError("Exploratory original PCM changed")
            hx = high.spectral_observation(x,passage["note"])
            row = dict(passage=passage,hardware=hx,models={})
            for label,model in models.items():
                y = model["audio"][a+LAG:b+LAG]*GAINS[slope]
                hy = high.spectral_observation(y,passage["note"])
                row["models"][label] = dict(harmonics=high.wrap.compare_harmonics(x,y,passage["note"]),
                      aliases=high.fixed_aliases(hx,hy,masks[i]),
                      fixed_phase_error_power=float(np.mean((y-x)**2)/np.mean(x*x)))
            exploratory.append(row)
        control = frame_guard_control(baseline["audio"])
        results["slopes"].append(dict(slope=slope,original=media,decoded=artifact(wav),decode_command=command,
                      supports=supports,models=scored,harmonic_rows=observed,
                      harmonic_summary=summarize_harmonics(observed,models),
                      harmonic_mask_control=harmonic_mask_control(observed),
                      exploratory_five_windows=exploratory,baseline_mask_control=control))
        print(f"LP{slope}: harmonics, exploratory windows and exclusion controls complete",flush=True)
    save(out/"results.json",results)
    print(out/"results.json",flush=True)


if __name__=="__main__":
    main()
