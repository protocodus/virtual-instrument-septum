#!/usr/bin/env python3
"""Freeze a source-only, explicitly estimated Ambient SQR opening performance.

No instrument renderer or candidate scores are read. Frozen note/onset/gate
choices are conservative human interpretations of the original recording.
Gates and velocities are not recovered hardware MIDI.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal
from scipy.io import wavfile
from scipy.ndimage import uniform_filter1d

from compare_hardware import write_midi
from extract_reference_patch import read_bank, parse_bank, encode_syx

ROOT = Path(__file__).resolve().parents[1]
MP3_SHA = "d113bb3d65c34bb6827d29561e29dd9c9d4a6236143d5528685643f84a86e565"
BANK_SHA = "102c47ee393c09115779172b8cbbb2c2f2563e0b4fdb2f57e0c8fca2a23c3b29"
SYX_SHA = "1e420e8a04502d790a1018f4547167377bdfd4470e21bb6602853d09218aff07"
INTERIORS = [(74, .10, .35), (76, .45, .58), (77, .64, .76)]
CASE = {
    "schema_version": 1,
    "id": "ambient-sqr",
    "title": "Ambient SQR — first three notes",
    "reference_id": "lead-07",
    "midi_status": "reconstructed_not_original",
    "source_start_seconds": 0,
    "duration_seconds": .775,
    "calibration_end_seconds": .405,
    "method": "Source-only original MP3 inspection: native stereo spectra, fundamental and odd-harmonic families in three fixed plateaus, short RMS history and time-frequency transitions. Dominant families near 587, 659, 698 Hz support played MIDI 74, 76, 77 under the unchanged published preset's zero coarse/octave and zero pitch-envelope/LFO depths. Nominal key-ups follow envelope roll-off near the observed level maxima, with broad operational uncertainty; they are not recovered release events. No engine or candidate scores were used.",
    "uncertainties": [
        "Original MIDI, velocity, controllers, global transpose/tuning, output latency/capture chain and exact recorded patch revision are unavailable. The MP3 and bank are associated by Roland name/category.",
        "Velocity 100 is nominal. Upper AMP velocity sensitivity is 0, Lower is 8; both cutoff velocity sensitivities are 0. Velocity can alter the layer and wet/dry balance, so a common scalar gain does not remove its uncertainty.",
        "Upper has two Squares, drive 30, Solo Legato and portamento 20; Lower has two Sines, slower AMP attack 76 and Solo without portamento. Old-note energy may be release, delay or reverb; it does not prove held-key overlap.",
        "Onset ranges are operational source-clock reconstruction uncertainties, not certified MIDI time bounds. A later production-only prefix alignment may absorb one common latency; do not tune later notes to candidate errors.",
        "Key-up estimates near envelope maxima are provisional: the amplitude/filter envelopes, two layers, drive, interference and wet tails prevent uniquely recovering key release. Off-time ranges are sensitivity settings, not confidence intervals or observed gates.",
        "The 0.775-second crop excludes the next obvious new pitch group near 0.79 s. The third note's gate is still estimated; later hardware decay is not covered by this short reconstruction.",
        "All three original notes and preceding silence are retained from source time 0 for effect history. Exact published SysEx must remain unchanged. This is a conditional generalization case, not an output-equivalence benchmark."
    ],
    "notes": [
        {"on":.085,"off":.200,"note":74,"velocity":100,
         "on_uncertainty_seconds":[.075,.095],"off_sensitivity_seconds":[.160,.240]},
        {"on":.418,"off":.530,"note":76,"velocity":100,
         "on_uncertainty_seconds":[.408,.428],"off_sensitivity_seconds":[.490,.570]},
        {"on":.618,"off":.730,"note":77,"velocity":100,
         "on_uncertainty_seconds":[.608,.628],"off_sensitivity_seconds":[.700,.760]}
    ],
    "validation_plan": {
        "calibration_seconds":[0,.405],
        "later_evaluation_seconds":[.405,.775],
        "training_note":74,"later_notes":[76,77],
        "frozen_before_candidate_render_or_score_inspection":True,
        "comparison_policy":"One production-only prefix lag and gain; freeze for the later E5/F5 region. Any velocity/gate sensitivity must be predeclared, reported in full and applied equally to all DSP candidates without selecting its best error. Keep original SysEx unchanged.",
        "velocity_sensitivity_suggestion":[80,100,120],
        "gate_sensitivity_suggestion":"Nominal key-ups; then all early endpoints; then all late endpoints from each note's off_sensitivity_seconds. These bracket plausible articulation without recovering it."
    },
    "active_velocity_sensitivity":{
        "upper":{"cutoff":0,"amp":0},"lower":{"cutoff":0,"amp":8}
    },
    "unmodified_sysex_sha256":SYX_SHA,
    "original_mp3_sha256":MP3_SHA
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sources",type=Path,default=ROOT/"build-fidelity/hardware-benchmark/sources")
    ap.add_argument("--out",type=Path,default=ROOT/"build-fidelity/reverb-reference-expansion/ambient-performance-v1")
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    mp3=a.sources/"TOP8_AmbientSQR.mp3";bank=a.sources/"SH-201_Patch_LEAD.zip"
    assert sha(mp3)==MP3_SHA and sha(bank)==BANK_SHA
    data,member=read_bank(bank);name,blocks=parse_bank(data)[6]
    assert name=="Ambient SQR" and member=="SH-201_Patch_LEAD/100_LEAD.shl"
    patch=a.out/"original-patch.syx";patch.write_bytes(encode_syx(blocks))
    assert sha(patch)==SYX_SHA
    # The tracked native inventory supplies decoded raw-control meaning only.
    invpath=ROOT/"Docs/fidelity/source-audits/static-filter-reference-inventory-2026-09-15.json"
    inv=next(r for r in json.loads(invpath.read_text())["references"] if r["id"]=="lead-07")
    assert inv["unmodified_sysex_sha256"]==SYX_SHA
    decoded=inv["decoded"]
    for part in ("upper", "lower"):
        decoded[part].pop("model_base_cutoff_hz_diagnostic", None)
        decoded[part].pop("model_base_cutoff_status", None)
    for part,amp in (("upper",0),("lower",8)):
        assert decoded[part]["cutoffVelocitySens"]==0 and decoded[part]["levelVelocitySens"]==amp
        assert decoded[part]["octaveShift"]==0
        for osc in ("osc1","osc2"):
            assert decoded[part][osc]["coarse"]==0 and decoded[part][osc]["pitchEnvDepth"]==0
    wav=a.out/"hardware-full.wav"
    command=["ffmpeg","-v","error","-i",str(mp3),"-c:a","pcm_f32le","-y",str(wav)]
    subprocess.run(command,check=True)
    fs,audio=wavfile.read(wav)
    assert fs==44100 and audio.ndim==2 and audio.shape[1]==2 and np.isfinite(audio).all()
    measures=[]
    for note,start,end in INTERIORS:
        y=audio[round(start*fs):round(end*fs)].astype(float);n=len(y)
        z=np.fft.rfft(y*np.hanning(n)[:,None],n=8*n,axis=0)
        power=np.mean(abs(z)**2,axis=1);f=np.fft.rfftfreq(8*n,1/fs)
        f0=440*2**((note-69)/12);harm=[]
        for h in (1,3,5):
            select=np.flatnonzero((f>f0*h*.96)&(f<f0*h*1.04));i=select[np.argmax(power[select])]
            harm.append({"harmonic_hypothesis":h,"frequency_hz":float(f[i]),
                         "frequency_divided_by_h_hz":float(f[i]/h),
                         "relative_spectrum_peak_db":float(10*np.log10(power[i]/power.max()))})
        measures.append({"played_note_hypothesis":note,"interior_seconds":[start,end],
                         "native_bin_hz":fs/n,"harmonic_peak_hypotheses":harm})
    x=audio[:round(1.05*fs)].astype(float)
    rms20=np.sqrt(uniform_filter1d(np.mean(x*x,axis=1),round(.020*fs),mode="constant"))
    maxima=[]
    for note,start,end in INTERIORS:
        ix=np.arange(round(start*fs),round(end*fs));i=ix[np.argmax(rms20[ix])]
        maxima.append({"note":note,"time_seconds":i/fs,"rms":float(rms20[i]),
                       "meaning":"20 ms centered RMS maximum; not a detected key release"})
    fig,ax=plt.subplots(3,1,figsize=(12,9),layout="constrained")
    f,t,z=signal.stft(x,fs,window="hann",nperseg=1024,noverlap=980,nfft=4096,axis=0,boundary=None,padded=False)
    power=np.mean(abs(z)**2,axis=1)
    for axis,band,vmin,vmax in ((ax[0],(450,850),-65,-12),(ax[1],(1450,2500),-75,-30)):
        mask=(f>=band[0])&(f<=band[1]);axis.pcolormesh(t,f[mask],10*np.log10(np.maximum(power[mask],1e-20)),vmin=vmin,vmax=vmax,cmap="magma",shading="auto")
        axis.set(ylabel="Hz",ylim=band)
    ax[2].plot(np.arange(len(x))/fs,20*np.log10(np.maximum(rms20,1e-15)))
    ax[2].set(ylabel="20 ms centered RMS / dBFS",xlabel="Source seconds",ylim=(-65,-3))
    for axis in ax:
        axis.axvline(.405,color="cyan",ls="--",label="Calibration ends")
        axis.axvline(.775,color="lime",ls="--",label="Excerpt ends")
        for note in CASE["notes"]:axis.axvline(note["on"],color="white" if axis!=ax[2] else "gray",lw=.6,alpha=.7)
        axis.set(xlim=(0,1.05));axis.grid(alpha=.15)
    ax[0].legend(fontsize=8)
    fig.suptitle("Ambient SQR: original audio only; provisional D5 / E5 / F5 performance\nContext includes the following pitch group outside the frozen 0.775 s excerpt")
    plot=a.out/"performance-source.png";fig.savefig(plot,dpi=150);plt.close(fig)
    case=a.out/"ambient-sqr.json";case.write_text(json.dumps(CASE,indent=2,allow_nan=False)+"\n")
    midi=a.out/"reconstructed-performance.mid";write_midi(midi,CASE)
    ffmpeg=Path(shutil.which("ffmpeg"))
    receipt={"schema_version":1,"claim":"Source-only frozen reconstruction, not original MIDI or exact gate/velocity recovery.",
             "candidate_scores_or_engine_audio_consulted":False,
             "source":{"url":"https://www.rolandus.com/go/sh-201_patches/mp3/LEAD/TOP8_AmbientSQR.mp3","path":str(mp3),"sha256":sha(mp3)},
             "bank":{"path":str(bank),"sha256":sha(bank),"member":member,"member_sha256":hashlib.sha256(data).hexdigest()},
             "patch":{"path":str(patch),"sha256":sha(patch)},
             "decoded_parameters":{"source_inventory":str(invpath),"sha256":sha(invpath),"active_parts":inv["active_parts"],"decoded":decoded},
             "decoder":{"command":command,"sample_rate":fs,"channels":2,"no_resampling_or_downmix":True,"binary_sha256":sha(ffmpeg),"version":subprocess.check_output([str(ffmpeg),"-version"],text=True).splitlines()[0],"wav":str(wav),"wav_sha256":sha(wav)},
             "tools":{n:sha(ROOT/"Tools"/n) for n in (Path(__file__).name,"compare_hardware.py","extract_reference_patch.py")},
             "pitch_evidence":measures,"envelope_maxima":maxima,
             "case":{"path":str(case),"sha256":sha(case)},"midi":{"path":str(midi),"sha256":sha(midi)},
             "plot":{"path":str(plot),"sha256":sha(plot)},"case_definition":CASE}
    (a.out/"results.json").write_text(json.dumps(receipt,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"pitch_evidence":measures,"envelope_maxima":maxima,"case":receipt["case"],"midi":receipt["midi"]},indent=2))


if __name__=="__main__":
    main()
