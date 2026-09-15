#!/usr/bin/env python3
"""Freeze a hardware-only Class A opening, including its observed pitch bend.

No renderer is called or read. Notes/onsets are source hypotheses; gate variants
preserve uncertainty in SOLO LEGATO articulation. No original MIDI was found.
"""
import argparse
from copy import deepcopy
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

import assess_hardware_equivalence as assess
from compare_hardware import write_midi
from extract_reference_patch import read_bank,parse_bank,encode_syx
from render_midi import parse_smf,replay_events

ROOT=Path(__file__).resolve().parents[1]
MP3_SHA="88dc73e66c854e6ea57d976a96cd884dddb85275d56f73719000806f1609b886"
PATCH_SHA="5ac5ab7f052f6f17c48cc342bf4493ee5919572fc66dabf7daaddd25178b95e9"
# Refined source-only pitch-family inspection. Onset brackets deliberately
# exceed timing precision of short Hann windows; they are not statistical CIs.
# nominal onset, played MIDI, bracket, interior evidence window, confidence
NOTES=[
    (.035,45,(.029,.041),(.060,.110),"high"),
    (.133,52,(.123,.145),(.160,.200),"high"),
    (.223,57,(.213,.237),(.226,.238),"medium-low; very brief"),
    (.252,50,(.240,.264),(.265,.290),"medium; octave supported by low family"),
    (.306,52,(.296,.316),(.322,.348),"high"),
    (.364,55,(.353,.380),(.377,.391),"medium; brief"),
    (.410,45,(.398,.425),(.440,.500),"high"),
    (.532,52,(.521,.544),(.552,.590),"high"),
    (.613,57,(.601,.625),(.616,.625),"medium-low; very brief"),
    (.636,62,(.628,.650),(.656,.689),"medium-high; octave checked against half-frequency family"),
    (.710,64,(.699,.725),(.741,.800),"high"),
    (.834,67,(.822,.848),(.900,1.100),"high"),
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def spectrum(y,sr,lo,hi):
    segment=y[round(lo*sr):round(hi*sr)]
    f,p=signal.periodogram(segment,sr,window="hann",nfft=262144,axis=0)
    return f,p.mean(axis=1)


def bend_evidence(y,sr):
    result=[]
    for centre in np.round(np.arange(1.1,2.101,.1),2):
        f,p=spectrum(y,sr,float(centre-.04),float(centre+.04));frequencies=[]
        for h in (1,2,3):
            indices=np.flatnonzero((f>=388*h)&(f<=445*h));j=indices[np.argmax(p[indices])]
            z=np.log(np.maximum(p[j-1:j+2],1e-30))
            delta=.5*(z[0]-z[2])/(z[0]-2*z[1]+z[2])
            frequencies.append(float((f[j]+delta*(f[1]-f[0]))/h))
        median=float(np.median(frequencies));base=440*2**(-2/12)
        result.append(dict(centre_seconds=float(centre),width_seconds=.08,
            fundamental_from_harmonics_hz=frequencies,median_frequency_hz=median,
            cents_above_nominal_G4=float(1200*np.log2(median/base)),
            harmonic_estimate_spread_cents=float(1200*np.log2(max(frequencies)/min(frequencies)))))
    return result


def source_evidence(y,sr):
    evidence=[]
    flux={}
    for size in (1024,2048):
        f,t,z=signal.stft(y[:sr],sr,nperseg=size,noverlap=size-32,axis=0,boundary="zeros")
        m=np.sqrt(np.mean(abs(z)**2,axis=1));band=(f>=200)&(f<=8000)
        flux[str(size)]=(t[1:],np.sqrt(np.sum(np.maximum(m[band,1:]-m[band,:-1],0)**2,axis=0)))
    for onset,note,bracket,window,confidence in NOTES:
        f,p=spectrum(y,sr,*window);bins=np.flatnonzero((f>=40)&(f<=2000))
        peaks,_=signal.find_peaks(p[bins],prominence=p[bins].max()*.01)
        indexes=sorted(bins[peaks],key=lambda j:p[j],reverse=True)[:16]
        row=dict(onset_seconds=onset,played_midi=note,pitch_confidence=confidence,
            onset_bracket_seconds=list(bracket),spectrum_window_seconds=list(window),
            predicted_osc1_hz=440*2**((note-69)/12),predicted_osc2_hz=440*2**((note-81)/12),
            spectral_peaks=[dict(hz=float(f[j]),relative_db=float(10*np.log10(p[j]/p.max()))) for j in indexes],
            local_flux_maxima={})
        for size,(t,v) in flux.items():
            indices=np.flatnonzero((t>=bracket[0])&(t<=bracket[1]));j=indices[np.argmax(v[indices])]
            row["local_flux_maxima"][size]=dict(seconds=float(t[j]),amplitude=float(v[j]))
        evidence.append(row)
    power=np.mean(y[:sr]**2,axis=1)
    rms=np.sqrt(np.maximum(signal.convolve(power,np.ones(44)/44,mode="same"),0))
    peak=rms[:round(.18*sr)].max()
    thresholds=[dict(relative_db=db,seconds=float(np.flatnonzero(rms>peak*10**(db/20))[0]/sr)) for db in (-60,-50,-40,-30,-20,-10)]
    periodicity=[]
    for centre in np.round(np.arange(.08,.921,.02),2):
        segment=y[round((centre-.03)*sr):round((centre+.03)*sr)]
        autocorrelation=sum(signal.correlate(segment[:,c],segment[:,c],mode="full",method="fft")[len(segment)-1:] for c in range(2))
        cumulative=np.r_[0.,np.cumsum(np.sum(segment*segment,axis=1))]
        lags=np.arange(len(segment));denominator=np.sqrt(cumulative[len(segment)-lags]*(cumulative[-1]-cumulative[lags]))
        normalized=autocorrelation/np.maximum(denominator,1e-30)
        peaks,_=signal.find_peaks(normalized[60:1000]);peaks=peaks+60
        chosen=sorted(peaks,key=lambda j:normalized[j],reverse=True)[:3]
        periodicity.append(dict(centre_seconds=float(centre),width_seconds=.06,
            peaks=[dict(lag_samples=int(j),normalized_correlation=float(normalized[j]),
                        apparent_played_midi_from_half_frequency_assumption=float(69+12*np.log2((2*sr/j)/440))) for j in chosen]))
    return dict(notes=evidence,first_onset_1ms_rms_threshold_sensitivity=thresholds,
        stereo_periodicity=periodicity,
        periodicity_qualification="Top three normalized stereo autocorrelation peaks,60mswindows,lags60–999. Period multiples and old wet notes create octave/subharmonic ambiguities; not an automatic note selector. Source spectra and stored octave relation are also required.",
        onset_method="Inspect changed low and upper harmonic families, retain nominal rounded onset plus conservative source bracket; 1024/2048 Hann positive-flux maxima are sensitivity evidence, not exact note-on estimators. Phase/beating and filter attack can move their maxima.")


def make_plot(y,sr,notes,bends,rows,path):
    fig,ax=plt.subplots(3,1,figsize=(12,9),layout="constrained")
    for i,(lo,hi) in enumerate(((0,.95),(.8,3.))):
        segment=y[round(lo*sr):round(hi*sr)]
        f,t,z=signal.stft(segment,sr,nperseg=2048,noverlap=1920,axis=0,boundary=None,padded=False)
        p=np.mean(abs(z)**2,axis=1)
        ax[i].pcolormesh(t+lo,f,10*np.log10(np.maximum(p,1e-20)),vmin=-70,vmax=-20,cmap="magma",shading="auto")
        for j,n in enumerate(notes):
            if n["off"]<=lo or n["on"]>=hi:continue
            frequency=440*2**((n["note"]-69)/12)
            tline=np.linspace(max(n["on"],lo),min(n["off"],hi),300)
            curve=np.interp(tline,[b["time"] for b in bends],[b["value"] for b in bends])
            pitch=frequency*2**(((curve-8192)/8191*2)/12)
            for scale in (.5,1.): ax[i].plot(tline,pitch*scale,color="cyan",lw=.85)
            if i==0:ax[i].text(n["on"],frequency*2.2,str(j+1),color="white",fontsize=8)
        ax[i].set(yscale="log",ylim=(40,2500),xlim=(lo,hi),ylabel="Hz",xlabel="Original recording time / s")
    ax[0].axvline(.30,color="lime",ls="--",lw=1)
    ax[0].set_title("Class A: source spectrogram and frozen two-oscillator pitch hypothesis; training ends 0.30 s")
    ax[1].set_title("G4 with reconstructed +2-semitone bend; no oscillator/filter parameters fitted")
    for h in range(3):
        ax[2].plot([r["centre_seconds"] for r in rows],
                   [1200*np.log2(r["fundamental_from_harmonics_hz"][h]/(440*2**(-2/12))) for r in rows],
                   "o",ms=4,label="Hardware harmonic "+str(h+1))
    ax[2].plot([b["time"] for b in bends if b["time"]>=1.1],
               [(b["value"]-8192)/8191*200 for b in bends if b["time"]>=1.1],color="#173d67",label="Frozen 14-bit input")
    ax[2].set(xlim=(1.05,2.15),xlabel="Recording time / s",ylabel="Cents above G4")
    ax[2].legend(loc="lower right",fontsize=8)
    fig.savefig(path,dpi=150);plt.close(fig)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sources",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    catalog_path=ROOT/"Docs/fidelity/hardware-reference-catalog.json";catalog=json.loads(catalog_path.read_text())
    ref=next(r for r in catalog["recordings"] if r["id"]=="lead-01")
    bank=next(b for b in catalog["banks"] if b["id"]=="lead")
    mp3=a.sources/ref["local_filename"];archive=a.sources/bank["local_filename"]
    if sha(mp3)!=MP3_SHA or ref["sha256"]!=MP3_SHA or sha(archive)!=bank["sha256"]:
        raise ValueError("Original source identity failed")
    raw,member=read_bank(archive)
    if member!=bank["archive_member"] or hashlib.sha256(raw).hexdigest()!=bank["bank_sha256"]:
        raise ValueError("Original bank member changed")
    name,blocks=parse_bank(raw)[ref["patch_number"]-1]
    patch=out/"original-patch.syx";patch.write_bytes(encode_syx(blocks))
    if name!="Class A" or sha(patch)!=PATCH_SHA: raise ValueError("Exact original patch changed")
    upper=blocks[1]
    if upper[0]!=0 or upper[6]!=0 or upper[2]!=100 or upper[8]!=64 or upper[60]!=63 or upper[21]!=64 or upper[59]!=2:
        raise ValueError("Pitch/coarse/octave/cutoff-velocity/bend assumption changed")
    ffmpeg=shutil.which("ffmpeg");wav=out/"hardware-full.wav"
    command=[ffmpeg,"-hide_banner","-loglevel","error","-nostdin","-i",str(mp3),"-ar","44100","-ac","2","-c:a","pcm_f32le",str(wav)]
    subprocess.run(command,check=True);sr,y=assess.read_audio(wav)
    source=source_evidence(y,sr);bend_rows=bend_evidence(y,sr)
    # Nominal G4 is centered through1.2s; the independently observed A4
    # endpoint is represented by the published +2semitone maximum at2.0s.
    # Interior knots are medians of three hardware harmonic-frequency estimates.
    knots=[(1.2,0.)]+[(r["centre_seconds"],max(0.,min(200.,r["cents_above_nominal_G4"])))
                      for r in bend_rows if 1.2<r["centre_seconds"]<2.]+[(2.,200.)]
    bends=[dict(time=0.,value=8192),dict(time=1.1,value=8192)]
    for tick in range(120,201):
        t=tick/100;v=float(np.interp(t,[q[0] for q in knots],[q[1] for q in knots]))
        bends.append(dict(time=t,value=int(round(8192+8191*v/200))))
    uncertainties=[
        "Original MIDI, velocity, controller state, system tuning/transpose and recorded patch revision are unavailable.",
        "No Septum output, candidate gain score or DSP parameter fit was used to choose performance inputs.",
        "Pitch families are interpreted through exact stored coarse+12/0 and tone octave−1: net OSC1=played, OSC2=played−12. Brief A3 events and some octave assignments have lower confidence.",
        "Onset brackets are conservative source inspection bounds, not confidence intervals. Echoes, phase and finite windows limit exact timing.",
        "Velocity100 is a placeholder. Cutoff velocity sensitivity is0; AMP sensitivity+8 remains. No per-note velocity fit or cutoff-velocity sensitivity render is performed.",
        "SOLO LEGATO makes note overlap affect envelope retriggering; contiguous nominal,10ms gap and20ms overlap variants are all frozen before scoring.",
        "The continuous G4-to-A4 frequency rise is encoded as a reconstructed pitch-bend hypothesis using stored range2semitones, not original controller data. It constrains pitch input from the same source used for later audio evaluation.",
        "Final note-off3.0s is an artificial crop while hardware continues; synthetic output after3.0s is not a matched wet tail. Separate full-recording tail observations cannot establish opening-performance equivalence.",
    ]
    base=dict(schema_version=1,id="class-a-opening",title="Class A — source-derived opening and pitch bend",reference_id="lead-01",
        midi_status="reconstructed_not_original",source_start_seconds=0,duration_seconds=3.,calibration_end_seconds=.30,
        method="Source-only full-recording spectrogram, local harmonic peaks and stereo periodicity distinguish12early events. Both octave-related oscillator families determine played pitch with nominal A440. Conservative spectral-onset brackets are retained. Source H1/H2/H3 frequency medians in80mswindows supply interior bend knots; values are linearly interpolated in cents on a10msgrid and rounded to14bit. No renderer is consulted.",
        uncertainties=uncertainties,pitch_bends=bends,
        benchmark_protocol=dict(status="frozen_before_any_candidate_render_or_score",calibration_interval_seconds=[0,.30],
            evaluation_interval_seconds=[.30,3.],
            diagnostic_regions_seconds={"later_unbent_notes":[.32,.82],"new_G4_plateau":[.90,1.16],"source_derived_bend":[1.28,1.90],"held_maximum_bend":[2.10,3.]},
            source_start_seconds=0,hidden_preroll_seconds=0,render_tempo_policy="preserve-patch",nominal_velocity=100,
            cutoff_velocity_raw=64,cutoff_velocity_signed=0,amp_velocity_raw=72,amp_velocity_signed=8,
            patch_sha256=PATCH_SHA,hardware_mp3_sha256=MP3_SHA,
            no_postcrop_wet_comparison=True,descriptive_full_file_tail_seconds=[18.25,19.25],
            final_tail_qualification="After the complete recording's final excitation, which has not been reconstructed here; descriptive source-only tail, not paired to this opening MIDI."))
    cases={}
    for variant,shift in (("nominal",0.),("gap-10ms",-.010),("overlap-20ms",.020)):
        case=deepcopy(base);case["id"]="class-a-"+variant
        case["gate_hypothesis"]=dict(name=variant,note_off_relative_to_next_onset_seconds=shift,final_off_is_crop=True)
        notes=[]
        for i,(on,note,bracket,window,confidence) in enumerate(NOTES):
            off=round(NOTES[i+1][0]+shift,6) if i+1<len(NOTES) else 3.
            notes.append(dict(on=on,off=off,note=note,velocity=100,pitch_confidence=confidence,
                onset_confidence="medium; source bracket retained",onset_bracket_seconds=list(bracket),
                note_off_confidence="unverified articulation" if i+1<len(NOTES) else "artificial crop",
                evidence_window_seconds=list(window)))
        case["notes"]=notes
        case_path=out/(case["id"]+".json");case_path.write_text(json.dumps(case,indent=2,allow_nan=False)+"\n")
        midi=out/(case["id"]+".mid");write_midi(midi,case)
        parsed=parse_smf(midi.read_bytes());replay,ignored=replay_events(parsed,tempo_policy="preserve-patch")
        if ignored:raise ValueError("Unexpected ignored MIDI events")
        # Check channel bytes independently of meta-event naming.
        channel=[e for e in parsed["events"] if e.get("channel")==1]
        ons=[e for e in channel if int(e["hex"][:2],16)==0x90]
        offs=[e for e in channel if int(e["hex"][:2],16)==0x80]
        bends_parsed=[e for e in channel if int(e["hex"][:2],16)==0xe0]
        if len(ons)!=12 or len(offs)!=12 or len(bends_parsed)!=len(bends):raise ValueError("MIDI event count failed")
        decoded_values=[int(e["hex"][2:4],16)+128*int(e["hex"][4:6],16) for e in bends_parsed]
        if decoded_values!=[b["value"] for b in bends]:raise ValueError("MIDI bend roundtrip failed")
        cases[variant]=dict(case_path=str(case_path),case_sha256=sha(case_path),midi_path=str(midi),midi_sha256=sha(midi),
            note_on_count=len(ons),note_off_count=len(offs),pitch_bend_count=len(bends_parsed),parsed_replay_events=replay)
    receipt=dict(schema_version=1,status="Source-only protocol frozen; no renderer run or candidate score",source_evidence=source,
        bend_frequency_evidence=bend_rows,bend_knots_seconds_cents=knots,
        bend_mapping="Nominal G4, range+2semitones; center8192, positive max16383. Median H1/H2/H3 frequency knots1.3–1.9s; fixed center1.2s and maximum2.0s; linear cents interpolation10ms, nearest14bit.",
        initial_and_endpoint_checks=[r for r in bend_rows if r["centre_seconds"] in (1.1,1.2,2.,2.1)],
        cases=cases,patch_sha256=sha(patch),original_mp3_sha256=sha(mp3),original_bank_sha256=sha(archive),
        decoded_sha256=sha(wav),decode_command=command,decoder_version=subprocess.check_output([ffmpeg,"-version"],text=True).splitlines()[0],decoder_sha256=sha(ffmpeg),
        catalog_sha256=sha(catalog_path),tool_sha256={n:sha(ROOT/"Tools"/n) for n in (Path(__file__).name,"compare_hardware.py","render_midi.py","extract_reference_patch.py","assess_hardware_equivalence.py")})
    (out/"receipt.json").write_text(json.dumps(receipt,indent=2,allow_nan=False)+"\n")
    make_plot(y,sr,json.loads((out/"class-a-nominal.json").read_text())["notes"],bends,bend_rows,out/"source-protocol.png")
    print(out/"receipt.json")


if __name__=="__main__":
    main()
