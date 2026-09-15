#!/usr/bin/env python3
"""Source-only SINGLE/damped and DUAL/neutral opening feasibility.

Selection follows observed prior results: explicitly a confound investigation,
not blind validation. No renderer/candidate audio is called or read. One short
201vsJP8000 pitch hypothesis and two gate assumptions are frozen; Soundtrack's
opening remains untranscribed because keyboard-note attribution is ambiguous.
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
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import assess_hardware_equivalence as assess
from compare_hardware import write_midi
from extract_reference_patch import read_bank,parse_bank,encode_syx
from render_midi import parse_smf

ROOT=Path(__file__).resolve().parents[1]
CATALOG=ROOT/'Docs/fidelity/hardware-reference-catalog.json'
INVENTORY=ROOT/'Docs/fidelity/source-audits/reverb-reference-openings-2026-09-15.json'
BANK_SHA='d00b19491c2cec27ee640147e0dfb6d1b8a47bcb70831a93a819a70d21a2a222'
CONFIG={
    'pad-06':dict(mp3_sha256='0681718b242a89b23d350237e3f2aad2085e877ee5818256a004eca921d49e2c',
                  sysex_sha256='70e44e7665a3e6b46faabf733588fda615dcf2161a85dea693e70c319a3f1501',
                  windows=[(.315,.405),(.415,.565),(.575,.725),(.725,.875)]),
    'pad-02':dict(mp3_sha256='b0352755c05b15b1c52248800330baeb4674df6cae2d8726ad9d9fbb699d21ae',
                  sysex_sha256='dc8844cda1f6ed4ee913945ecba9b485ff199a1c9e8a8b0b847d17112f075cbf',
                  windows=[(.20,.60),(.65,1.25),(1.25,1.45)])}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path,obj):path.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')


def spectrum(y,sr,bounds):
    a,b=[round(t*sr)for t in bounds];x=y[a:b];hann=np.hanning(len(x))
    f=np.fft.rfftfreq(131072,1/sr)
    p=np.mean(abs(np.fft.rfft(x*hann[:,None],131072,axis=0))**2,axis=1)
    peaks=signal.find_peaks(p,distance=max(1,round(3/(sr/131072))))[0]
    peaks=peaks[(f[peaks]>=40)&(f[peaks]<=850)]
    indices=peaks[np.argsort(p[peaks])[-24:]][::-1]
    return dict(seconds=bounds,samples=[a,b],width_seconds=len(x)/sr,
        method='Stereo power averaged before peak extraction; Hann/zero-padding aids visualization but does not supply independent sub-Hz resolution or unique note identities.',
        peaks=[dict(hz=float(f[k]),relative_to_window_peak_db=float(10*np.log10(p[k]/p.max())))for k in indices])


def make_case(ref,held):
    identity='201-vs-jp8000-held-opening' if held else '201-vs-jp8000-c3-release-opening'
    return dict(schema_version=1,id=identity,title='201vsJP8000 — two opening octave notes'+(' (held gates)' if held else ' (C3 release sensitivity)'),
        reference_id='pad-06',midi_status='reconstructed_not_original',source_start_seconds=0.,duration_seconds=.710,calibration_end_seconds=.400,
        method='Original-only stereo spectra and 5ms RMS/40ms and93ms spectrograms. Initial130.8Hz family at~.320s, then new65.4/196.2Hz family at~.425s support played C3/MIDI48 and C2/MIDI36 under unchanged zero-coarse, zero-octave original preset. Stop at.710s before a new233Hz family near.735s. Note-offs are explicit censoring/articulation assumptions, not recovered gates. No renderer or candidate score was used.',
        selection_status='post_result_keyboard_mode_vs_damping_confound_investigation_not_blind_validation',
        uncertainties=[
            'Original performance MIDI, velocity/controllers, global transpose/tuning, recording chain and exact recorded patch revision are unavailable; official MP3/bank association is by name.',
            'After C2 starts, its even harmonics overlap the earlier C3 family. The earlier C3 note may still be held or already releasing; the source does not uniquely distinguish these cases.',
            'Both Super Saws, AMP release61, delay/reverb and active filter LFO34 leave key-up uncertain. Held-through-crop is a censored input hypothesis, not evidence of held keys; the first-C3 early-release variant is an alternative, not a confidence bound.',
            'Second-note release is not recovered. It remains censored at the crop in both variants. No matched post-off tail or independent reverb decay is claimed.',
            'Onsets have operational source brackets, not certified MIDI bounds; MP3 pre-echo, the direct onset and filtered band onset can differ. A later fixed production-prefix lag may absorb one global delay only.',
            'Velocity100 is nominal. Active Upper cutoff velocity0, AMP velocity+8; lower is inactive. Both variants preserve velocity and all exact stored controls.',
            'This is an explicit post-result confound investigation. Report both gate assumptions with the same comparison policy; do not select a favorable reconstruction from DSP errors.',
            'The crop is deliberately short and dominated by held/overlapping sound. A later result cannot independently establish a reverb damping model or whole-instrument equivalence.'],
        notes=[dict(on=.320,off=.710 if held else .390,note=48,velocity=100,
                    pitch_confidence='high',onset_confidence='medium-high',on_uncertainty_seconds=[.315,.325],
                    off_status='censored_at_crop_not_recovered' if held else 'early_release_sensitivity_not_recovered',
                    evidence='130.8Hz fundamental plus approximate261.6/392.4/523.2Hz multiples before the lower octave enters; no stored transposition.'),
               dict(on=.425,off=.710,note=36,velocity=100,pitch_confidence='high',onset_confidence='medium',
                    on_uncertainty_seconds=[.405,.435],off_status='censored_at_crop_not_recovered',
                    evidence='New65.4Hz family and its odd196.2Hz multiple appear around.425s; persists to selected crop with unknown gate/release.')],
        benchmark_protocol=dict(calibration_seconds=[0.,.400],later_evaluation_seconds=[.400,.710],
            calibration_end_seconds=.400,training_note=48,later_note=36,maximum_proposed_common_alignment_seconds=.050,
            minimum_common_later_support_seconds=.260,
            comparison_policy='One lag and gain from before/production prefix only, frozen for all models; same samples for all models; retain gate sensitivity without selecting its best error.',
            gate_hypotheses={'held_opening':'Both notes censored at.710s crop.','c3_release_opening':'First C3 note-off.390s is an explicit sensitivity suggested by early upper-harmonic diminution; first C3 release remains inseparable from filter/phase/overlap. C2 still censored.'},
            final_tail_status='No source-matched tail after recovered final key-up.',
            all_preceding_events_retained=True,source_only_frozen_before_rendering=True),
        active_velocity_sensitivity={'upper':{'cutoff':0,'amp':8}},
        velocity_sensitivity_review=dict(uniform_velocity_cases_omitted=True,
            current_model_formula='g(v)=1-(8/63)*(1-v/127); post-filter common voice amplitude',
            uniform_80_and_120_vs_100_db=[-.180375377706313,.176705692785186],
            full_velocity_1_to_127_span_db=1.169614843385989,
            reason='SINGLE Upper with cutoff velocity0 and overdrive off; uniform velocity changes largely reduce to global amplitude absorbed by a per-case production-prefix gain. No layer rebalance. Relative note velocity remains unknown and can affect small later-level differences; this formula is the current model, not a measured hardware velocity law.'),
        unmodified_sysex_sha256=CONFIG['pad-06']['sysex_sha256'],original_mp3_sha256=CONFIG['pad-06']['mp3_sha256'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sources',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    catalog=json.loads(CATALOG.read_text());inventory=json.loads(INVENTORY.read_text())
    bank=next(b for b in catalog['banks']if b['id']=='pad');archive=a.sources/bank['local_filename']
    if sha(archive)!=BANK_SHA or bank['sha256']!=BANK_SHA:raise ValueError('Original bank ZIP changed')
    data,member=read_bank(archive)
    if member!=bank['archive_member']or hashlib.sha256(data).hexdigest()!=bank['bank_sha256']:raise ValueError('Original bank member changed')
    patches=parse_bank(data);ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:raise ValueError('ffmpeg required')
    result=dict(schema_version=1,status='201vsJP8000 conditional two-pitch input with explicit gate ambiguity; Soundtrack not transcribed.',
        selection='Explicit post-result confound investigation: SINGLE+HF-damped201vsJP8000 versus DUAL+neutral Soundtrack. No candidate audio or scores used for these source choices.',
        tool_sha256=sha(__file__),catalog_sha256=sha(CATALOG),inventory_sha256=sha(INVENTORY),
        helpers={n:sha(ROOT/'Tools'/n)for n in ['compare_hardware.py','extract_reference_patch.py','render_midi.py','assess_hardware_equivalence.py']},
        decoder=dict(path=ffmpeg,sha256=sha(ffmpeg),version=subprocess.check_output([ffmpeg,'-version'],text=True).splitlines()[0]),
        bank=bank,velocity_mapping_source_sha256=sha(ROOT/'Source/DSP/SeptumEngine.cpp'),cases={},frozen_inputs=[])
    sounds={}
    for identity,c in CONFIG.items():
        ref=next(r for r in catalog['recordings']if r['id']==identity)
        inv=next(r for r in inventory['references']if r['id']==identity)
        mp3=a.sources/ref['local_filename']
        if sha(mp3)!=c['mp3_sha256'] or ref['sha256']!=c['mp3_sha256']:raise ValueError('Original MP3 changed')
        name,blocks=patches[ref['patch_number']-1];syx=encode_syx(blocks)
        if name!=ref['patch_name'] or hashlib.sha256(syx).hexdigest()!=c['sysex_sha256'] or inv['patch_sha256']!=c['sysex_sha256']:raise ValueError('Exact patch changed')
        directory=out/identity;directory.mkdir();(directory/'original-patch.syx').write_bytes(syx)
        wav=directory/'hardware-full.wav';command=[ffmpeg,'-hide_banner','-loglevel','error','-nostdin','-i',str(mp3.resolve()),'-ar','44100','-ac','2','-c:a','pcm_f32le',str(wav)]
        subprocess.run(command,check=True);sr,y=assess.read_audio(wav)
        if sr!=44100 or y.shape[1]!=2 or not np.isfinite(y).all():raise ValueError('Unexpected decode')
        sounds[identity]=y
        raw=blocks[4]
        rec=dict(reference=ref,source_mp3_path=str(mp3.resolve()),decoded_sha256=sha(wav),decode_command=command,
            sysex_sha256=c['sysex_sha256'],active_parts=inv['active_parts'],decoded=deepcopy(inv['decoded']),
            raw_common=list(blocks[0]),raw_upper=list(blocks[1]),raw_lower=list(blocks[2]),raw_delay=list(blocks[3]),raw_reverb=list(raw),
            reverb_summary=dict(time_raw=raw[0],predelay_raw=raw[1],size_raw=raw[2],high_cut_raw=raw[3],
                lf_gain_db=raw[7]-36,hf_gain_db=raw[9]-36),spectral_windows=[spectrum(y,sr,t)for t in c['windows']])
        for part in ('upper','lower'):
            rec['decoded'][part].pop('model_base_cutoff_hz_diagnostic',None);rec['decoded'][part].pop('model_base_cutoff_status',None)
        if identity=='pad-06':
            n=round(.005*sr);x=y[:sr];x=x[:len(x)//n*n].reshape(-1,n,2)
            rec['first_second_5ms_rms']=dict(width_samples=n,centers_seconds=((np.arange(len(x))+.5)*n/sr).tolist(),
                rms_dbfs=(10*np.log10(np.maximum(np.mean(x*x,axis=(1,2)),1e-30))).tolist())
            rec['feasibility']='Conditional short two-pitch benchmark; gate ambiguity remains and must not be selected from model scores.'
            rec['next_unmodeled_pitch_family']=dict(approximate_onset_bracket_seconds=[.725,.750],frequency_hz=233.1,note_hypothesis=58,excluded_from_crop=True)
        else:
            rec['feasibility']='No defensible short note/gate reconstruction frozen.'
            rec['failure_reasons']=[
                'Opening combines several sustained line families around65/98/131/196/233/294/311/392Hz, with overlapping harmonics and SuperSaw side components. They do not uniquely determine played-key count/octaves.',
                'Upper uses only oscillator2 SuperSaw at decoded+8semitones plus pitch-envelope depth−19 and decay24. Lower uses two untransposed SuperSaws. This layered transposition/pitch motion obscures attribution of additional families.',
                'Slow AMP attacks52/48 and releases79/79, filter envelopes and Upper cutoff LFO16 blur individual note-on/key-up and continue excitation through subsequent chord changes.',
                'No simple isolated opening plateau with a uniquely attributable gate supports the requested independent later-note check. Retain source spectra instead of inventing a MIDI chord.',
                'Neutral LF/HF damping is verified, but HIGH CUT index12=2500Hz introduces an additional spectral difference; this is not a clean mode-only counterpart even if MIDI were known.']
        result['cases'][identity]=rec
    for held in (True,False):
        case=make_case(result['cases']['pad-06']['reference'],held)
        path=out/(case['id']+'.json');save(path,case);midi=path.with_suffix('.mid');write_midi(midi,case)
        parsed=parse_smf(midi.read_bytes());events=[]
        for e in parsed['events']:
            if e['kind']!='midi':continue
            b=bytes.fromhex(e['hex']);events.append(dict(sample=e['sample'],bytes=list(b)))
        ons=[e for e in events if e['bytes'][0]&240==144 and e['bytes'][2]>0]
        offs=[e for e in events if e['bytes'][0]&240==128 or(e['bytes'][0]&240==144 and e['bytes'][2]==0)]
        if len(ons)!=2 or len(offs)!=2:raise ValueError('Canonical MIDI event counts changed')
        for n in case['notes']:
            if not any(e['bytes'][1]==n['note']and abs(e['sample']/sr-n['on'])<=1/sr for e in ons):raise ValueError('MIDI onset roundtrip failed')
            if not any(e['bytes'][1]==n['note']and abs(e['sample']/sr-n['off'])<=1/sr for e in offs):raise ValueError('MIDI release roundtrip failed')
        result['frozen_inputs'].append(dict(id=case['id'],json_sha256=sha(path),midi_sha256=sha(midi),parsed_note_events=events))
    fig,axs=plt.subplots(2,2,figsize=(13,8.5),layout='constrained')
    for row,identity in enumerate(CONFIG):
        y=sounds[identity];end=1. if identity=='pad-06' else 4.
        for col,size in enumerate((4096,2048)):
            f,t,z=signal.stft(y[:round(end*sr)],sr,nperseg=size,noverlap=size-128,axis=0,boundary=None,padded=False)
            power=np.mean(abs(z)**2,axis=1);axs[row,col].pcolormesh(t,f,10*np.log10(np.maximum(power,1e-20)),vmin=-70,vmax=-15,cmap='magma',shading='auto')
            axs[row,col].set(yscale='log',ylim=(40,1000)if col==0 else(200,6000),xlim=(0,end),xlabel='Original source time / s',ylabel='Hz',title=result['cases'][identity]['reference']['title'])
            if identity=='pad-06':
                axs[row,col].axvline(.4,color='lime',ls='--',lw=1,label='Calibration end.400s');axs[row,col].axvline(.710,color='cyan',lw=1,label='Crop.710s')
        if identity=='pad-06':axs[row,0].legend(fontsize=8,loc='upper right')
    fig.suptitle('Post-result mode/damping confound investigation: source only, no candidate audio',fontsize=13)
    fig.savefig(out/'source-openings.png',dpi=150);plt.close(fig)
    save(out/'results.json',result);print(out/'results.json')


if __name__=='__main__':main()
