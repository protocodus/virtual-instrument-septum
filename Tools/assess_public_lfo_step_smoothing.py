#!/usr/bin/env python3
"""Bounded forward-model feasibility of pitch-step smoothing in public audio.

These are synthetic sinusoidal carrier/neighbor models, not Engine renders.
Source-derived plateau values stay identical across all hypotheses. No patch,
raw modulation depth, polarity, rate or shipping DSP parameter is changed.
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
from scipy import optimize, signal
from scipy.io import wavfile

ROOT = Path(__file__).resolve().parents[1]
TAUS_MS = (0., .1, .5, 1., 2., 3., 5.)
SR = 48000
TRACKS = ((1320.,150.), (1047.5,150.))
OFFSETS = np.arange(-.012,.016,.001)
SOURCE_SHA = "6ed77a823dde937f4bf87bf9cf803a7293dd21a97056f36694704355b8b15f4c"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+"\n")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-webm",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args = p.parse_args()
    if sha(args.source_webm)!=SOURCE_SHA:
        raise ValueError("Original Opus source identity failed")
    out = args.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    copied = out/"tools"
    copied.mkdir()
    for name in ("analyze_public_lfo_clock.py","assess_public_lfo_step_smoothing.py"):
        shutil.copyfile(ROOT/"Tools"/name,copied/name)
    sys.path.insert(0,str(copied))
    import analyze_public_lfo_clock as clock
    clock_path = ROOT/"Docs/fidelity/source-audits/public-lfo-clock-2026-09-15.json"
    # The independently retained primary clock is the 1320 Hz record.
    recorded_clock = next(r for r in json.loads(clock_path.read_text())["tracks"] if r["center_hz"]==1320)
    period = 1/recorded_clock["training_frequency_hz"]
    origin = recorded_clock["training_grid_origin_seconds"]
    decoder = shutil.which("ffmpeg")
    if not decoder:
        raise ValueError("ffmpeg required")
    commands=[]
    def execute(command):
        commands.append(command)
        subprocess.run(command,check=True)
    source_wav = out/"source-first-50s.wav"
    execute([decoder,"-hide_banner","-loglevel","error","-nostdin","-i",str(args.source_webm.resolve()),
             "-t","50","-c:a","pcm_f32le",str(source_wav)])
    sr,stereo=wavfile.read(source_wav)
    if sr!=SR or stereo.shape!=(2400000,2) or not np.isfinite(stereo).all():
        raise ValueError("Unexpected source format")
    source=stereo[:7*sr].mean(axis=1).astype(float)
    t=np.arange(len(source))/sr
    feature_t=np.arange(7000)/1000
    source_features=np.array([clock.pitch_track(source,c,w) for c,w in TRACKS])
    static_offsets=np.median(source_features[:,1800:2800],axis=1)
    source_features-=static_offsets[:,None]
    # These observed plateau levels are fixed inputs, not optimized separately
    # for each tau or inferred from candidate residuals.
    grid=origin+np.arange(int(7/period)+1)*period
    levels=[]
    for g in grid:
        if g<3.0:level=0.
        elif g>5.5:level=levels[-1]
        else:level=float(np.median(source_features[0,(feature_t>=g+.015)&(feature_t<g+.027)]))
        levels.append(level)
    levels=np.asarray(levels)
    target=levels[np.clip(np.searchsorted(grid,t,side="right")-1,0,len(levels)-1)]
    edges=[]
    for k,g in enumerate(grid):
        if k and 3.35<=g<5.35 and abs(levels[k]-levels[k-1])>=60:
            edges.append(dict(index=k,time_seconds=float(g),before_cents=float(levels[k-1]),
                after_cents=float(levels[k]),step_cents=float(levels[k]-levels[k-1]),
                role="training" if len(edges)<4 else "later_check"))
    if len(edges)<12:
        raise ValueError("Too few source-defined large isolated steps")
    # Static one-second fit determines the fixed sinusoidal carrier mixture.
    # Bases use third-partial phase tracks to avoid low-band beating.
    bases=np.array([TRACKS[1][0]/3*2**(static_offsets[1]/1200),
                    TRACKS[0][0]/3*2**(static_offsets[0]/1200)])
    frequencies=np.concatenate([f*np.arange(1,1+int(8000/f)) for f in bases])
    families=np.concatenate([np.full(int(8000/f),i) for i,f in enumerate(bases)])
    harmonics=np.concatenate([np.arange(1,1+int(8000/f)) for f in bases])
    static=(t>=1.8)&(t<2.8)
    st=t[static]
    matrix=np.column_stack([np.cos(2*np.pi*f*st) for f in frequencies]+[np.sin(2*np.pi*f*st) for f in frequencies])
    coefficients=np.linalg.lstsq(matrix,source[static],rcond=None)[0]
    amps=np.hypot(coefficients[:len(frequencies)],coefficients[len(frequencies):])
    phases=np.arctan2(-coefficients[len(frequencies):],coefficients[:len(frequencies)])
    static_residual=float(np.mean((source[static]-matrix@coefficients)**2)/np.var(source[static]))
    train=np.array([e["role"]=="training" for e in edges])
    def windows(features,shift=0):
        return np.array([[(np.interp(e["time_seconds"]+OFFSETS+shift,feature_t,f)-e["before_cents"])/e["step_cents"]
                          for f in features] for e in edges])
    reference=windows(source_features)
    def compare(candidate,ref):
        def loss(shift):
            return float(np.mean((windows(candidate,shift)[train]-ref[train])**2))
        fit=optimize.minimize_scalar(loss,bounds=(-.006,.006),method="bounded",options={"xatol":1e-8})
        predicted=windows(candidate,float(fit.x))
        error=predicted-ref
        return dict(training_shift_ms=float(fit.x*1000),
            shift_hit_bound=bool(abs(fit.x)>.00595),
            training_normalized_rmse=float(np.sqrt(np.mean(error[train]**2))),
            later_normalized_rmse=float(np.sqrt(np.mean(error[~train]**2))),
            later_rmse_by_partial=[float(np.sqrt(np.mean(error[~train,i]**2))) for i in range(len(TRACKS))],
            per_edge_rmse=np.sqrt(np.mean(error**2,axis=(1,2))).tolist(),
            predicted_windows=predicted.tolist())
    variants={}
    audio_dir=out/"audio"
    audio_dir.mkdir()
    audio_records=[]
    conditions=("neighbors-clean","neighbors-opus128","neighbors-phase-quarter")
    for tau in TAUS_MS:
        ticks=target[::8]
        if tau:
            pole=np.exp(-8/(sr*tau/1000))
            ticks=signal.lfilter([1-pole],[1,-pole],ticks)
        smoothed=np.repeat(ticks,8)[:len(t)]
        cycles=np.cumsum(2**(smoothed/1200))/sr
        for condition in conditions:
            name=f"tau-{tau:g}-{condition}"
            # Each neighbor phase is moved with its own harmonic number;
            # amplitudes and the common source-derived pitch steps stay fixed.
            shifted=phases+(harmonics*np.pi/2 if condition.endswith("quarter") else 0)
            y=np.zeros(len(t))
            for amplitude,f,phase in zip(amps,frequencies,shifted):
                y+=amplitude*np.cos(2*np.pi*f*cycles+phase)
            wav=audio_dir/(name+".wav")
            wavfile.write(wav,sr,np.column_stack([y,y]).astype(np.float32))
            if condition=="neighbors-opus128":
                encoded=audio_dir/(name+".opus")
                decoded=audio_dir/(name+"-decoded.wav")
                execute([decoder,"-hide_banner","-loglevel","error","-nostdin","-i",str(wav),
                    "-c:a","libopus","-b:a","128k","-vbr","on","-application","audio",
                    "-frame_duration","20",str(encoded)])
                execute([decoder,"-hide_banner","-loglevel","error","-nostdin","-i",str(encoded),
                    "-c:a","pcm_f32le",str(decoded)])
                ds,d=wavfile.read(decoded)
                if ds!=sr or d.shape!=(len(t),2):
                    raise ValueError("Synthetic codec roundtrip changed duration/rate")
                y=d.mean(axis=1).astype(float)
            features=np.array([clock.pitch_track(y,c,w) for c,w in TRACKS])
            features-=np.median(features[:,1800:2800],axis=1)[:,None]
            variants[name]=features
            audio_records.append(dict(id=name,tau_ms=tau,condition=condition,
                wav_sha256=sha(wav),feature_sha256=hashlib.sha256(features.tobytes()).hexdigest(),
                decoded_sha256=sha(decoded) if condition=="neighbors-opus128" else None,
                peak=float(np.max(abs(y))),finite=bool(np.isfinite(y).all())))
        print("Forward modeled tau",tau,"ms",flush=True)
    hardware=[]
    for row in audio_records:
        hardware.append(dict(id=row["id"],tau_ms=row["tau_ms"],condition=row["condition"],
                             **compare(variants[row["id"]],reference)))
    controls=[]
    # Known planted tau under codec/phase changes is compared against the same
    # clean library. Every tau score remains; no threshold claims separability.
    for true_tau in TAUS_MS:
        for condition in ("neighbors-opus128","neighbors-phase-quarter"):
            ref=windows(variants[f"tau-{true_tau:g}-{condition}"])
            rows=[]
            for fit_tau in TAUS_MS:
                rows.append(dict(tau_ms=fit_tau,**compare(variants[f"tau-{fit_tau:g}-neighbors-clean"],ref)))
            controls.append(dict(planted_tau_ms=true_tau,condition=condition,scores=rows))
    result=dict(status="conditional_forward_model_feasibility_no_dsp_selection",
        source=dict(url=clock.SOURCE_URL,source_sha256=SOURCE_SHA,decoded_sha256=sha(source_wav),
            clock_result_sha256=sha(clock_path),source_engine_sha256={name:sha(ROOT/name) for name in
                ("Source/DSP/SeptumEngine.cpp","Source/DSP/SeptumEngine.h")}),
        tools_sha256={p.name:sha(p) for p in copied.glob("*.py")},
        decoder=dict(binary=decoder,binary_sha256=sha(decoder),
                     version=subprocess.check_output([decoder,"-version"],text=True).splitlines()[0]),
        protocol=dict(taus_ms=TAUS_MS,shipping_pitch_tau_ms=0,filter_parameter_tau_ms=2.5,
            pitch_source_finding="S&H returns heldValue; oscillator phase increments update directly at 8-sample control ticks. Filter parameter smoothing is separate and cannot be inferred from pitch.",
            rate_hz=1/period,grid_origin_seconds=origin,source_plateau_window_after_grid_seconds=[.015,.027],
            source_static_fit_seconds=[1.8,2.8],large_edge_minimum_cents=60,
            passage_seconds=[3.35,5.35],training="First four qualifying edges; later checks are every remaining qualifying edge",
            normalized_profile_offsets_seconds=OFFSETS.tolist(),
            nuisance_fit="One shared candidate time shift bounded +/-6ms on four training edges only, across both partials; no per-edge shifts, level/gain/depth/sign fitting or EQ",
            input_reconstruction="Hardware plateau values, including later values, reconstruct unknown random input and are frozen across taus; later checks test transition shape, not prediction of new random values",
            filters="Identical frozen clock pitch extractor, centers 1320/1047.5 Hz, half-width 150 Hz; shared noncausal seven-second feature extraction",
            codec="One offered-format sensitivity: libopus stereo 128k VBR, 20 ms frames. Original target bitrate/encoder and prior capture processing are unknown.",
            hypothesis_domain="One-pole smoothing in cents at 8-sample ticks, before frequency conversion; this synthetic library is not a complete Engine or hardware model"),
        steps=dict(grid_seconds=grid.tolist(),levels_cents=levels.tolist(),edges=edges),
        static_spectrum=dict(base_frequencies_hz=bases.tolist(),frequencies_hz=frequencies.tolist(),
            families=families.tolist(),harmonics=harmonics.tolist(),amplitudes=amps.tolist(),phases=phases.tolist(),
            residual_power_fraction=static_residual),
        hardware_windows=reference.tolist(),hardware_comparisons=hardware,
        planted_controls=controls,audio=audio_records,commands=commands,
        limitations=["Passband ringing, weak neighboring partials, codec and phase can alter measured step shape.",
            "Fixed spectral amplitudes/phases do not model unknown filter/capture response during a pitch transition.",
            "Plateau estimates may retain settling from a slow transition; their unobserved unsmoothed targets are not known.",
            "Exploratory passage and large-edge selection, no independent raw patch or performance MIDI.",
            "A best synthetic tau is an effective model descriptor, not an identified internal LFO smoothing constant.",
            "No perceptual equivalence or calibrated statistical separability threshold is supplied."])
    save(out/"results.json",result)
    print(out/"results.json")


if __name__=="__main__":
    main()
