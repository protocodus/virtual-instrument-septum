#!/usr/bin/env python3
"""Fixed-control Air/Cotton stereo and detuned-line measurement feasibility.

No DSP parameters are fitted. Requires the pinned E10 identity renderer from
compare_cutoff_taper_candidates.py and the original final-production corpus.
Effects/oscillator mutes are causal controls, not reconstructed hardware stems.
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
import numpy as np
from scipy import signal

import assess_hardware_equivalence as assess
import generate_timbre_capture as capture

ROOT = Path(__file__).resolve().parents[1]
REVISION = "b0f6c03"
LATENCY = 93
PINS = {
    "air-lead-1": ("e7e911d9be986fcc4987c41d79836034ef60ea5f9c70308a7d5f57348f4c091e",
                   "43bca32341c215f6ccfe58291f787a7c286602f8772061e26d59566921c591e3"),
    "cotton-wool": ("e7f23e39445895f2158482037b37a19dfe413e536869c0e6f78352de6e49fbef",
                    "54b7512438fb6a743292f314354cf5c37d68ba4f74a39e9474f03f9854e219a5"),
}
# Declared before rendering. Times refer to excerpt / reconstructed MIDI clock;
# renderer compensation is exactly its known 93 samples, no hardware lag fit.
REGIONS = {
    "air-lead-1": [("opening_training", .065, .115),
                   ("second_note_check", .155, .215),
                   ("held_note_check", .50, 1.05),
                   ("later_held_note_check", 2.15, 2.50)],
    "cotton-wool": [("pre_predelay_training", .155, .210),
                    ("first_note_late_check", .260, .350),
                    ("first_tail_check", .410, .485),
                    ("second_note_check", .535, .610),
                    ("held_chord_check", 2.85, 3.30),
                    ("repeated_bass_check", 4.155, 4.210)],
}
OFFSETS = np.array([-.11002313, -.06288439, -.01952356, 0,
                    .01991221, .06216538, .10745242])
POLY = [10028.7312891634, -50818.8652045924, 111363.4808729368,
        -138150.6761080548, 106649.6679158292, -53046.9642751875,
        17019.9518580080, -3425.0836591318, 404.2703938388,
        -24.1878824391, .6717417634, .0030115596]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def db(ratio):
    return float(10*np.log10(max(float(ratio), 1e-30)))


def cut(audio, sr, lo, hi, rendered=False):
    start, end = round(lo*sr), round(hi*sr)
    if rendered:
        start += LATENCY
        end += LATENCY
    if start < 0 or end > len(audio):
        raise ValueError("Region outside audio")
    return audio[start:end]


def stereo(y, fixed_gain):
    l, r = y.T
    pl, pr = np.dot(l,l), np.dot(r,r)
    mid, side = (l+r)/2, (l-r)/2
    return dict(rms=float(np.sqrt(np.mean(y*y))), right_over_left_db=db(pr/max(pl,1e-30)),
                side_over_mid_db=db(np.dot(side,side)/max(np.dot(mid,mid),1e-30)),
                cosine_similarity=float(np.dot(l,r)/max(np.sqrt(pl*pr),1e-30)),
                fixed_training_channel_gain=float(fixed_gain),
                fixed_channel_prediction_relative_error=float(np.linalg.norm(r-fixed_gain*l)/max(np.linalg.norm(r),1e-15)),
                max_abs_channel_difference=float(np.max(abs(l-r))))


def arrival(a, b, sr):
    diff=np.max(abs(a-b),axis=1)
    result=[]
    for threshold in (0, 1e-8, 1e-6, 1e-5, 1e-4):
        ix=np.flatnonzero(diff>threshold)
        result.append(dict(threshold=threshold, sample=int(ix[0]) if len(ix) else None,
                           midi_clock_seconds=float((ix[0]-LATENCY)/sr) if len(ix) else None))
    return result


def line_probe(audio, sr, lo, hi, f0, harmonic, rendered):
    y=cut(audio,sr,lo,hi,rendered)
    frequencies=f0*harmonic*(1+OFFSETS*np.polyval(POLY,41/127))
    t=np.arange(len(y))/sr
    # Design only: no coefficient fit to hardware and no detune search. Hann
    # weighting reproduces finite-window information loss independent of phase.
    design=np.column_stack([fun(2*np.pi*f*t) for f in frequencies for fun in (np.cos,np.sin)])
    sv=np.linalg.svd(design*np.sqrt(np.hanning(len(y)))[:,None],compute_uv=False)
    fft_size=1 << int(np.ceil(np.log2(max(262144,len(y)))))
    f,p=signal.periodogram(y,sr,window="hann",nfft=fft_size,axis=0,scaling="spectrum")
    power=p.mean(axis=1)
    lo_f,hi_f=frequencies[0]-2/(hi-lo),frequencies[-1]+2/(hi-lo)
    mask=(f>=lo_f)&(f<=hi_f)
    indexes=np.flatnonzero(mask)
    peaks,_=signal.find_peaks(power[mask],prominence=max(power[mask].max()*0.01,1e-30))
    peak_bins=indexes[peaks]
    main=(f>=f0*.96)&(f<=f0*1.04)
    return dict(region_seconds=[lo,hi], fundamental_hz=f0,harmonic=harmonic,
                predicted_frequencies_hz=frequencies.tolist(),
                minimum_predicted_spacing_hz=float(np.diff(frequencies).min()),
                reciprocal_window_hz=1/(hi-lo),hann_first_zero_half_width_hz=2/(hi-lo),
                design_condition_number=float(sv[0]/sv[-1]),
                conditioning_scope="Optimistic single seven-line family, constant amplitudes, no overlapping-note/FX nuisance columns; good conditioning alone does not identify hardware lines.",
                cluster_peak_over_fundamental_peak_db=db(power[mask].max()/max(power[main].max(),1e-30)),
                local_peaks_hz=f[peak_bins].tolist(),
                local_peak_levels_relative_cluster_db=[db(v/max(power[mask].max(),1e-30)) for v in power[peak_bins]],
                qualification="Candidate-predicted frequency region; local maxima are not identified oscillator lines. Window resolution is unchanged by FFT zero padding.")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--corpus",type=Path,required=True)
    p.add_argument("--renderer-build",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    source=a.renderer_build.resolve()
    build=json.loads((source/"manifest.json").read_text())
    if build["id"]!="cutoff-e10" or build["profile"]["provided_fields"]!={"filter":["cutoff_hz"]}:
        raise ValueError("Expected controlled E10 build")
    if sha(source/"SeptumRenderMidi")!=build["renderer"]["sha256"]:
        raise ValueError("Renderer changed since recorded build")
    for name,h in build["frozen_sha256"].items():
        if sha(source/name)!=h:
            raise ValueError("Frozen build input changed: "+name)
    verified={}
    for name,h in build["source"]["input_sha256"].items():
        raw=subprocess.check_output(["git","show",REVISION+":"+name],cwd=ROOT)
        if hashlib.sha256(raw).hexdigest()!=h:
            raise ValueError("Frozen source is not b0f6c03: "+name)
        verified[name]=h
    for name in ("SeptumRenderMidi","manifest.json","profile.json","CandidateProfile.h"):
        shutil.copy2(source/name,out/name)
    renderer=out/"SeptumRenderMidi"
    result=dict(schema_version=1,claim="Conditional stereo and line-resolution feasibility; no hardware DSP estimate or equivalence claim.",
        frozen_revision=REVISION,source_sha256=verified,renderer_sha256=sha(renderer),
        build_manifest=build,profile=json.loads((source/"profile.json").read_text()),
        tool_sha256={n:sha(ROOT/"Tools"/n) for n in
            (Path(__file__).name,"render_midi.py","generate_timbre_capture.py","assess_hardware_equivalence.py")},
        policy=dict(regions=REGIONS,render_latency_samples=LATENCY,hardware_delay_fit=False,
            global_audio_gain_fit=False,channel_gain="One least-squares scalar R=aL from first named training region independently for each signal; freeze on later regions. Also report raw stereo metrics.",
            phase="No phase fit or random phase selection. Centered single-tone mono dry routing holds for every internal oscillator phase/spread. Same deterministic renderer seed and MIDI in every control.",
            stereo_score="Descriptive channel relation, not auditory mismatch, confidence interval, or proof of an original routing topology.",
            line_probe="No hardware sinusoid amplitude or frequency fit. Known nominal candidate grid, spectral local peaks and design conditioning only."), cases={})
    for case,(patch_pin,audio_pin) in PINS.items():
        inp=a.corpus/case;directory=out/case;directory.mkdir()
        for name in ("original-patch.syx","reconstructed-performance.mid","comparison.json"):
            shutil.copy2(inp/name,directory/name)
        if sha(directory/"original-patch.syx")!=patch_pin or sha(inp/"septum-raw.wav")!=audio_pin:
            raise ValueError("Pinned patch/production identity failed")
        blocks=capture.decode_syx((directory/"original-patch.syx").read_bytes())
        if capture.encode_syx(blocks)!=(directory/"original-patch.syx").read_bytes():
            raise ValueError("SysEx round trip failed")
        meta=json.loads((inp/"comparison.json").read_text())
        sr,hardware=assess.read_audio(inp/"hardware-excerpt-raw.wav")
        sounds={"hardware":hardware};record=dict(input_sha256={n:sha(inp/n) for n in
            ("original-patch.syx","reconstructed-performance.mid","hardware-excerpt-raw.wav","septum-raw.wav","comparison.json")},
            original_blocks_hex=[bytes(b).hex() for b in blocks],notes=meta["case"]["notes"],
            comparison_limits=meta["comparison_limits"],
            region_samples={name:dict(hardware=[round(lo*sr),round(hi*sr)],
                                     rendered=[round(lo*sr)+LATENCY,round(hi*sr)+LATENCY])
                            for name,lo,hi in REGIONS[case]},controls={})
        for model in ("original","effects_off","delay_only","reverb_only","osc1_dry","osc2_dry"):
            b=[bytearray(v) for v in blocks];edits=[]
            changes=[]
            if model in ("effects_off","osc1_dry","osc2_dry"):
                changes += [(0,28,0),(0,29,0)]
            elif model=="delay_only": changes += [(0,29,0)]
            elif model=="reverb_only": changes += [(0,28,0)]
            if model=="osc1_dry": changes += [(1,15,1)]
            if model=="osc2_dry": changes += [(1,15,127)]
            for block,offset,value in changes:
                edits.append(dict(block=block,offset=offset,before=b[block][offset],after=value))
                b[block][offset]=value
            patch=directory/(model+".syx");patch.write_bytes(capture.encode_syx(b))
            wav=directory/(model+".wav")
            command=[sys.executable,str(ROOT/"Tools/render_midi.py"),"--renderer",str(renderer),
                     "--midi",str(directory/"reconstructed-performance.mid"),"--syx",str(patch),
                     "--output",str(wav),"--tempo-policy","preserve-patch"]
            subprocess.run(command,check=True,stdout=subprocess.DEVNULL)
            cs,y=assess.read_audio(wav);receipt=json.loads(wav.with_suffix(".render.json").read_text())
            if cs!=sr or sr!=44100 or not np.isfinite(y).all() or receipt["ignored_events"] or receipt["output"]["active_voices_at_end"]:
                raise ValueError("Render format/MIDI/voice/finiteness guard failed")
            if model=="original" and sha(wav)!=audio_pin:
                raise ValueError("Original render byte identity failed")
            sounds[model]=y
            record["controls"][model]=dict(edits=edits,patch_sha256=sha(patch),wav_sha256=sha(wav),
                receipt_sha256=sha(wav.with_suffix(".render.json")),peak=float(abs(y).max()),
                active_voices_at_end=receipt["output"]["active_voices_at_end"],command=command)
        record["effects_arrival"]={m:arrival(sounds[m],sounds["effects_off"],sr)
                                   for m in ("original","delay_only","reverb_only")}
        record["stereo"]={}
        for model,y in sounds.items():
            _,lo,hi=REGIONS[case][0]
            train=cut(y,sr,lo,hi,model!="hardware")
            gain=float(np.dot(train[:,0],train[:,1])/max(np.dot(train[:,0],train[:,0]),1e-30))
            record["stereo"][model]={name:stereo(cut(y,sr,lo,hi,model!="hardware"),gain)
                                     for name,lo,hi in REGIONS[case]}
        record["mono_routing_control"]=dict(max_abs_dry_L_minus_R=float(abs(sounds["effects_off"][:,0]-sounds["effects_off"][:,1]).max()),
            dry_minus_sum_of_oscillator_controls_max_abs=float(abs(sounds["effects_off"]-sounds["osc1_dry"]-sounds["osc2_dry"]).max()),
            sum_qualification="These controls sum within the recorded float residual for these two patches; they are model interventions and do not extract hardware stems.")
        if case=="cotton-wool":
            record["delay_send_zero_identity"]={"original_equals_reverb_only":bool(np.array_equal(sounds["original"],sounds["reverb_only"])),
                "delay_only_equals_effects_off":bool(np.array_equal(sounds["delay_only"],sounds["effects_off"]))}
            record["line_resolution"]={}
            for model in ("hardware","original","osc1_dry"):
                record["line_resolution"][model]=[
                    line_probe(sounds[model],sr,lo,hi,440*2**((note-69)/12),h,model!="hardware")
                    for lo,hi,note in ((.155,.210,48),(.155,.350,48),(2.85,3.30,63),(2.85,3.30,65),(2.85,3.30,69),(4.155,4.350,48))
                    for h in (1,5,10,20,30)]
        result["cases"][case]=record
        print(case,"complete",flush=True)
    (out/"results.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(out/"results.json")


if __name__=="__main__":
    main()
