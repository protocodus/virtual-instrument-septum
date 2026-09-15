#!/usr/bin/env python3
"""Measure dry audio-metric sensitivity to four fixed global saw phases.

Same frozen engine/patch/MIDI, no best-phase selection, no production edits.
Requires original deepsonic MIDI/Q000 MP3s, compiler, ffmpeg, NumPy and SciPy.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
from scipy import signal
from scipy.io import wavfile

ROOT = Path(__file__).resolve().parents[1]
REVISION = "b0f6c03"
PHASES = (0., .25, .5, .75)
MIDI_SHA = "21ea21b9ba3ba14cc205931134fb7a320b09e67821bd3a3c70f97fa2e8b5d99a"
MP3_SHA = {12:"28e241247a0efb217eb4cb7154cc3b69713fcebca781639c45b8904b3dc8615b",
           24:"ebb6fa4e12136028bbff614633095aa510c31654fcce840af5e3a85b3a469d90"}
CHORDS = ((22.,(60,64,67)),(22.75,(48,52,55)),(24.,(60,65,69)),
          (24.75,(48,53,57)),(26.75,(50,55,59)),(28.,(60,64,67)),(28.75,(48,52,55)))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+"\n")


def phase_id(phase):
    return "phase-" + str(round(phase*100)).zfill(2)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    frozen=out/"frozen-source"
    names=subprocess.check_output(["git","ls-tree","-r","--name-only",REVISION,"Source/DSP"],cwd=ROOT,text=True).splitlines()
    names += ["Tools/"+name for name in ("RenderMidi.cpp","build_timbre_candidate.py","render_midi.py",
                                        "generate_timbre_capture.py","assess_hardware_equivalence.py","analyze_deepsonic_filter.py")]
    source_hashes={}
    for name in names:
        path=frozen/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(subprocess.check_output(["git","show",f"{REVISION}:{name}"],cwd=ROOT))
        source_hashes[name]=sha(path)
    q0_path=out/"q0-recipe-source.json"
    q0_path.write_bytes(subprocess.check_output(["git","show",f"{REVISION}:Docs/fidelity/source-audits/dry-end-to-end-2026-09-15.json"],cwd=ROOT))
    q0=json.loads(q0_path.read_text())
    (out/"experiment-script.py").write_bytes(Path(__file__).read_bytes())
    save(out/"source-manifest.json",{"revision":REVISION,"input_sha256":source_hashes,"script_sha256":sha(__file__),"q0_recipe_sha256":sha(q0_path)})
    sys.path.insert(0,str(frozen/"Tools"))
    import build_timbre_candidate as builder
    import generate_timbre_capture as capture
    import assess_hardware_equivalence as assessor
    import render_midi
    cache=out/"source-cache";cache.mkdir()
    midi=cache/"deepsonic_-_filter_demo_-_comparsion_sequence.mid"
    source_midi=args.sources/midi.name
    if sha(source_midi)!=MIDI_SHA:raise ValueError("Original MIDI identity changed")
    shutil.copyfile(source_midi,midi)
    held,notes={},[]
    for event in render_midi.parse_smf(midi.read_bytes())["events"]:
        if event["kind"]!="midi":continue
        m=bytes.fromhex(event["hex"])
        if m[0]==0x90 and m[2]:held[m[1]]=event["sample"]/44100
        elif m[0] in (0x80,0x90):notes.append({"note":m[1],"on":held.pop(m[1]),"off":event["sample"]/44100})
        else:raise ValueError("Unexpected channel control in original MIDI")
    if len(notes)!=124 or held:raise ValueError("Original note count or allocation changed")
    decoder=shutil.which("ffmpeg")
    if not decoder:raise ValueError("ffmpeg required")
    decode={"binary":decoder,"binary_sha256":sha(decoder),"version":subprocess.check_output([decoder,"-version"],text=True).splitlines()[0],"files":[]}
    hardware={}
    for slope in (12,24):
        mp3=args.sources/f"roland_sh-201_-_filter_demo_-_lpf{slope}_q000.mp3"
        if sha(mp3)!=MP3_SHA[slope]:raise ValueError("Original MP3 identity changed")
        wav=cache/mp3.with_suffix(".wav").name
        command=[decoder,"-hide_banner","-loglevel","error","-nostdin","-i",str(mp3),"-c:a","pcm_f32le",str(wav)]
        subprocess.run(command,check=True)
        sr,h=wavfile.read(wav)
        if sr!=44100 or h.ndim!=1 or not np.isfinite(h).all():raise ValueError("Unexpected hardware format")
        hardware[slope]=h.astype(float)
        decode["files"].append({"command":command,"source_sha256":sha(mp3),"decoded_sha256":sha(wav)})
    save(cache/"decode-manifest.json",decode)
    profiles=out/"profiles";profiles.mkdir()
    builds={}
    for phase in PHASES:
        name=phase_id(phase);profile={"version":1,"id":name,"evidence":"Experimental fixed four-phase sensitivity control; no phase optimization or production change.","waves":{"phase_cycles":[phase,0.,0.,0.,0.]}}
        path=profiles/(name+".json");save(path,profile)
        builds[phase]=builder.build_candidate(path,out/"builds"/name,source_root=frozen)
        if builds[phase]["source"]["input_sha256"]!=builds[0.]["source"]["input_sha256"]:raise ValueError("Source drift")
        print("Built",name,flush=True)
    init=out/"engine-init.syx"
    subprocess.run([str(out/"builds/phase-00/SeptumRenderMidi"),"--write-init-patch",str(init)],check=True)
    initial=capture.decode_syx(init.read_bytes())
    patches={};recipe_dir=out/"recipes";recipe_dir.mkdir()
    for slope in (12,24):
        recipe=q0["recipes"][f"onset-corrected-trajectory-lp{slope}"]
        blocks=[bytearray(b) for b in initial]
        blocks[0]=bytearray.fromhex(recipe["common_hex"]);blocks[1]=bytearray.fromhex(recipe["upper_tone_hex"]);blocks[2]=bytearray(blocks[1])
        capture.validate_blocks(blocks)
        path=recipe_dir/f"lp{slope}.syx";path.write_bytes(capture.encode_syx(blocks,0x10));patches[slope]=path
        save(path.with_suffix(".json"),{"status":"documented_recipe_reconstruction","common_hex":blocks[0].hex(),"upper_tone_hex":blocks[1].hex(),"patch_sha256":sha(path),"inactive_blocks":"Engine INIT; inactiveLower copiesUpper"})
    train=q0["protocol"]["training_note"];isolated=q0["protocol"]["isolated_validation_notes"]
    chord_intervals=[]
    for on,pitches in CHORDS:
        matching=[n for n in notes if n["on"]==on and n["note"] in pitches]
        if len(matching)!=3 or len({n["off"] for n in matching})!=1:raise ValueError("Chord identity changed")
        chord_intervals.append({"on":on,"off":matching[0]["off"],"notes":pitches})
    protocol={"source_revision":REVISION,"midi_sha256":MIDI_SHA,"phases_cycles":PHASES,
        "training_note":train,"isolated_notes":isolated,"chords":chord_intervals,
        "self_policy":"Eachphase vsphase0; lag0, fixedgain1 and separately oneRMSgain from note36 only; originalMIDI-time intervals with retained common rendererlatency",
        "hardware_policy":"Fixed physical35ms lag round(93+44.1-1543.5)=-1406; oneRMSgain from note36 perphase and baselinephase0 gain sensitivity; no bestphase selection",
        "stft_windows_samples":[512,1024,2048,8192],"legacy_mean_windows_samples":[512,2048,8192],"requested_short_mean_windows_samples":[512,1024,2048],
        "rms_windows_seconds":[.01,.05],"all_other_dsp_and_patch_parameters_unchanged":True,
        "qualification":"Same synthesis parameters apart from waveform origin; phase can change finite-window statistics and actual note/filter transients. This control cannot prove phases are inaudible or establish hardware equivalence.","equivalence_status":"not_established"}
    save(out/"protocol-before-rendering.json",protocol)
    audio={};renders=[]
    for phase in PHASES:
        for slope in (12,24):
            name=phase_id(phase);directory=out/"audio"/name/f"lp{slope}";directory.mkdir(parents=True)
            path=directory/"candidate.wav";renderer=out/"builds"/name/"SeptumRenderMidi"
            command=[sys.executable,"-B",str(frozen/"Tools/render_midi.py"),"--renderer",str(renderer),"--midi",str(midi),"--syx",str(patches[slope]),"--output",str(path),"--tail","2","--master-level","100","--tempo-policy","follow-midi","--allow-unsupported"]
            subprocess.run(command,check=True,stdout=subprocess.DEVNULL)
            receipt=json.loads(path.with_suffix(".render.json").read_text())
            omitted=receipt["ignored_events"]
            if len(omitted)!=1 or omitted[0]["meta_type"]!=32 or omitted[0]["hex"]!="00":raise ValueError("Unexpected omitted MIDI")
            if receipt["replay_event_counts"]!={"note_on":124,"note_off":124} or receipt["output"]["active_voices_at_end"]:raise ValueError("Replay failed")
            sr,stereo=wavfile.read(path);diff=float(np.max(abs(stereo[:,0]-stereo[:,1])))
            if sr!=44100 or not np.isfinite(stereo).all() or diff>np.finfo(np.float32).eps*np.max(abs(stereo)):raise ValueError("Render format failed")
            audio[phase,slope]=stereo[:,0].astype(float)
            r={"phase_cycles":phase,"id":name,"slope":slope,"wav":str(path),"sha256":sha(path),"renderer_sha256":sha(renderer),"patch_sha256":sha(patches[slope]),"midi_sha256":MIDI_SHA,"render_manifest_sha256":sha(path.with_suffix(".render.json")),"peak":receipt["output"]["peak"],"full_scale_samples":int(np.count_nonzero(abs(stereo)>=1)),"finite":True,"active_voices_at_end":0,"maximum_channel_difference":diff}
            if phase==0:
                old=next(r for r in q0["results"] if r["recipe"]=="onset-corrected-trajectory" and r["slope"]==slope and r["family"]=="zero-resonance-k1p2")
                if sha(path)!=old["raw_render_sha256"]:raise ValueError("Phase0 not byte-identical to production dryQ0")
                r["production_identity_guard"]=True
            renders.append(r);print("Rendered",name,slope,flush=True)
    save(out/"renders.json",{"protocol":protocol,"source_manifest_sha256":sha(out/"source-manifest.json"),"renders":renders})

    def measure(a,b):
        # Existing metrics retain comparability; add1024 without altering their legacy mean.
        metrics=assessor.measure(a[:,None],b[:,None],44100)
        n=1024;arrays=[]
        for y in (a,b):
            _,_,z=signal.stft(y,fs=44100,window="hann",nperseg=n,noverlap=3*n//4,boundary=None,padded=False)
            arrays.append(abs(z))
        x,y=arrays;peak=float(x.max());floor=max(peak*10**(assessor.FLOOR_DB/20),1e-30)
        active=np.maximum(x,y)>=max(peak*10**(assessor.ACTIVE_DB/20),1e-30)
        delta=abs(20*np.log10(np.maximum(y,floor)/np.maximum(x,floor)))
        extra={"window_samples":n,"hop_samples":n//4,"frames":x.shape[-1],"frequency_resolution_hz":44100/n,
               "spectral_convergence":float(np.linalg.norm(y-x)/max(np.linalg.norm(x),1e-30)),"log_spectral_error_db_mean":float(np.mean(delta[active])),"log_spectral_error_db_p95":float(np.percentile(delta[active],95)),"active_time_frequency_channel_bins":int(active.sum())}
        metrics["multi_resolution_stft"].append(extra);metrics["multi_resolution_stft"].sort(key=lambda s:s["window_samples"])
        metrics["summary"]["spectral_convergence_short_512_1024_2048_mean"]=float(np.mean([s["spectral_convergence"] for s in metrics["multi_resolution_stft"] if s["window_samples"]!=8192]))
        return metrics

    results=[]
    for phase in PHASES:
        for slope in (12,24):
            c,zero,h=audio[phase,slope],audio[0.,slope],hardware[slope]
            a,b=round(train["on"]*44100),round(train["off"]*44100)
            self_gain=assessor.rms(zero[a:b])/assessor.rms(c[a:b])
            lag=-1406;gain=assessor.rms(h[a:b])/assessor.rms(c[a+lag:b+lag]);baseline_gain=assessor.rms(h[a:b])/assessor.rms(zero[a+lag:b+lag])
            intervals=[{"label":"before_training","start":0.,"end":1.45},{"label":"after_training","start":2.,"end":len(h)/44100}]
            intervals += [{"label":"isolated","note":n,"start":n["on"],"end":n["off"]} for n in isolated]
            for n in chord_intervals:
                intervals += [{"label":"chord_full","chord":n,"start":n["on"],"end":n["off"]},{"label":"chord_late","chord":n,"start":n["on"]+.41,"end":n["on"]+.67}]
            row={"phase_cycles":phase,"slope":slope,"self_training_gain":self_gain,"self_training_gain_db":20*math.log10(self_gain),"hardware_training_gain":gain,"hardware_training_gain_db":20*math.log10(gain),"hardware_baseline_phase0_gain":baseline_gain,"hardware_lag_samples":lag,"intervals":[]}
            for interval in intervals:
                start,end=round(interval["start"]*44100),round(interval["end"]*44100)
                hs,he=max(start,-lag),min(end,len(c)-lag,len(h))
                item={**interval,"self_reference_samples":[start,end],"hardware_reference_samples":[hs,he],
                      "self_fixed_gain1":measure(zero[start:end],c[start:end]),
                      "self_training_gain":measure(zero[start:end],c[start:end]*self_gain),
                      "hardware_training_gain":measure(h[hs:he],c[hs+lag:he+lag]*gain),
                      "hardware_phase0_gain":measure(h[hs:he],c[hs+lag:he+lag]*baseline_gain)}
                row["intervals"].append(item)
            results.append(row)
            post=next(i for i in row["intervals"] if i["label"]=="after_training")
            print(phase,slope,"selfSC",post["self_fixed_gain1"]["summary"]["spectral_convergence_mean"],"hardwareSC",post["hardware_training_gain"]["summary"]["spectral_convergence_mean"],flush=True)
    save(out/"results.json",{"protocol":protocol,"renders_manifest_sha256":sha(out/"renders.json"),"results":results})
    print(out/"results.json")


if __name__=="__main__":
    main()
