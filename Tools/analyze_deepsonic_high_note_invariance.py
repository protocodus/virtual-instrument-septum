#!/usr/bin/env python3
"""Measure high-note harmonic invariance, not an oscillator/filter candidate.

Original-MIDI Q0 sources are freshly decoded after catalog hash checks. A
frequency refinement is frozen on LP12's first 80ms window for each note;
other times and LP24 do not select it. No source or raw cutoff law is fitted.
"""
import argparse
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import subprocess
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import numpy as np
from scipy.io import wavfile
from scipy.optimize import minimize_scalar
from scipy.signal import correlate
from render_midi import parse_smf

ROOT=Path(__file__).resolve().parents[1]
CATALOG=ROOT/'Docs/fidelity/source-audits/deepsonic-acquisition-2026-09-15.json'
SELECT=((8.5,69),(18.25,93),(18.75,91),(19.25,86),(19.75,88),(20.25,84))
SR=44100
FROZEN=(.9318832715,8.4984344071,.2140763348)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def fundamental(note):return 440*2**((note-69)/12)


def extract(y,center,width):
    first,last=round((center-width/2)*SR),round((center+width/2)*SR)
    if first<0 or last>len(y):raise ValueError('Window outside source')
    return y[first:last].astype(float)


@lru_cache(maxsize=16)
def basis(size,base,width,nominal):
    t=(np.arange(size)-(size-1)/2)/SR;u=t/(width/2)
    hs=np.arange(1,int(20000/base)+1)
    columns=[np.ones(size),u,u*u]
    for h in hs:
        co,si=np.cos(2*np.pi*h*base*t),np.sin(2*np.pi*h*base*t)
        columns.extend((co,si,u*co,u*si,u*u*co,u*u*si))
    # The prior independent alias audit identifies both first44.1k branches.
    # Include them as nuisance tones so their deterministic residual does
    # not masquerade as uncertain main-harmonic amplitude. Their predicted
    # positions stay at original MIDI tuning: the H1 peak refinement can
    # contain local moving-filter phase, not a true oscillator tuning change.
    alias_frequencies=sorted(set(abs(44100-h*nominal) for h in range(1,int(64100/nominal)+1)
                                 if 100<=abs(44100-h*nominal)<20000))
    for frequency in alias_frequencies:
        co,si=np.cos(2*np.pi*frequency*t),np.sin(2*np.pi*frequency*t)
        columns.extend((co,si,u*co,u*si))
    matrix=np.column_stack(columns)
    left,singular,right=np.linalg.svd(matrix,full_matrices=False)
    inverse=(right.T/singular)@left.T
    return matrix,inverse,float(singular[0]/singular[-1]),len(hs)


def estimate_frequency(y,on,note):
    x=extract(y,on+.10,.08);t=(np.arange(len(x))-(len(x)-1)/2)/SR;hann=np.hanning(len(x))
    base=fundamental(note)
    fit=minimize_scalar(lambda f:-abs(np.dot(x*hann,np.exp(-2j*np.pi*f*t))),
                        bounds=(base*.997,base*1.003),method='bounded')
    return float(fit.x)


def measure(y,on,offset,width,base,nominal):
    x=extract(y,on+offset,width)
    matrix,inverse,condition,harmonics=basis(len(x),base,width,nominal)
    if condition>100:raise ValueError(f'Ill-conditioned harmonic/alias model: {condition}')
    coeff=inverse@x;residual=x-matrix@coeff
    stop=3+6*harmonics
    amplitude=np.hypot(coeff[3:stop:6],coeff[4:stop:6]);h=np.arange(1,len(amplitude)+1)
    variance=np.dot(residual,residual)/(len(x)-len(coeff))
    diagonal=np.sum(inverse*inverse,axis=1)
    noise=np.sqrt(variance*(diagonal[3:stop:6]+diagonal[4:stop:6]))
    relative=20*np.log10(np.maximum(amplitude,1e-30)/amplitude[0])
    return dict(offset_seconds=offset,width_seconds=width,frequency_hz=base,
        condition_number=condition,residual_power_fraction=float(np.mean(residual**2)/max(np.var(x),1e-30)),
        h1_amplitude=float(amplitude[0]),harmonics=h.tolist(),harmonic_amplitudes=amplitude.tolist(),
        relative_h1_db=relative.tolist(),saw_slope_removed_db=(relative+20*np.log10(h)).tolist(),
        coefficient_snr_proxy_db=(20*np.log10(np.maximum(amplitude,1e-30)/np.maximum(noise,1e-30))).tolist())


def stats(values):
    x=np.asarray(values)
    return dict(rms_db=float(np.sqrt(np.mean(x*x))),max_abs_db=float(np.max(abs(x))))


def assess(audio,notes):
    rows=[];refinements=[];summaries=[]
    for n in notes:
        note,on=n['note'],n['on'];nominal=fundamental(note)
        refined=estimate_frequency(audio[12],on,note)
        refinements.append(dict(note=note,nominal_hz=nominal,refined_hz=refined,
                                shift_cents=float(1200*np.log2(refined/nominal))))
        for policy,base in (('nominal',nominal),('frozen_refined',refined)):
            for slope in (12,24):
                for width in (.06,.08,.10):
                    for offset in (.10,.16):
                        rows.append(dict(note=note,on=on,slope=slope,frequency_policy=policy,
                                         purpose='invariance',**measure(audio[slope],on,offset,width,base,nominal)))
                offsets=(.08,.12,.16,.20)+((.24,.28,.32,.36,.40) if n['off']-on>.4 else ())
                for offset in offsets:
                    rows.append(dict(note=note,on=on,slope=slope,frequency_policy=policy,
                        purpose='cutoff_divergence',frozen_low_note_cutoff_extrapolation_hz=float(nominal*(FROZEN[0]+FROZEN[1]*np.exp(-offset/FROZEN[2]))),
                        **measure(audio[slope],on,offset,.04,base,nominal)))
        select=[r for r in rows if r['note']==note and r['purpose']=='invariance']
        # Common source-only eligibility across both slopes, times, widths
        # and frequency conventions; no synthetic/candidate-derived mask.
        eligible=[h for h in range(2,9) if all(r['relative_h1_db'][h-1]>-55 and r['coefficient_snr_proxy_db'][h-1]>=20 for r in select)]
        if not eligible:raise ValueError('No qualified invariant harmonics')
        methods=[]
        for policy in ('nominal','frozen_refined'):
            for width in (.06,.08,.10):
                primary=[r for r in select if r['frequency_policy']==policy and r['width_seconds']==width]
                def values(slope,offset):
                    r=next(r for r in primary if r['slope']==slope and r['offset_seconds']==offset)
                    return np.array(r['relative_h1_db'])[np.array(eligible)-1]
                time=np.concatenate([values(s,.16)-values(s,.10) for s in (12,24)])
                slopes=np.concatenate([values(24,t)-values(12,t) for t in (.10,.16)])
                methods.append(dict(frequency_policy=policy,width_seconds=width,
                                    time_difference=stats(time),slope_difference=stats(slopes)))
        sweep=[]
        for policy in ('nominal','frozen_refined'):
            offsets=sorted(set(r['offset_seconds'] for r in rows if r['note']==note and r['purpose']=='cutoff_divergence'))
            for offset in offsets:
                pair=[r for r in rows if r['note']==note and r['purpose']=='cutoff_divergence'
                      and r['frequency_policy']==policy and r['offset_seconds']==offset]
                low=next(r for r in pair if r['slope']==12);high=next(r for r in pair if r['slope']==24)
                # Keep H2..H8 exactly as in the main invariance test; report
                # whether the same mask remains eligible as the filter closes.
                valid=all(r['relative_h1_db'][h-1]>-55 and r['coefficient_snr_proxy_db'][h-1]>=20 for r in pair for h in eligible)
                delta=np.array(high['relative_h1_db'])[:8]-np.array(low['relative_h1_db'])[:8]
                sweep.append(dict(frequency_policy=policy,offset_seconds=offset,
                    frozen_low_note_cutoff_extrapolation_hz=low['frozen_low_note_cutoff_extrapolation_hz'],
                    common_harmonics_still_eligible=valid,lp24_minus_lp12_h2_h8_db=delta[1:].tolist(),
                    fixed_h2_h4_still_eligible=all(r['relative_h1_db'][h-1]>-55 and r['coefficient_snr_proxy_db'][h-1]>=20 for r in pair for h in (2,3,4)),
                    fixed_h2_h4=stats(delta[1:4]),
                    **stats(delta[np.array(eligible)-1])))
        summaries.append(dict(note=note,common_eligible_harmonics=eligible,methods=methods,slope_divergence=sweep))
    return dict(frequency_refinements=refinements,note_summaries=summaries,windows=rows)


def synthesize(notes,slope,moving):
    y=np.zeros(round((notes[-1]['on']+1)*SR));known=[]
    profile=np.array([0,-1,-3,-6,-17,-23,-13,-16])
    for n in notes:
        start=round((n['on']+.035)*SR);length=round((n['off']-n['on']+.08)*SR)
        t=np.arange(length)/SR;base=fundamental(n['note'])*2**(3/1200)
        amp=np.minimum(1,t/.002)*np.exp(-np.maximum(t-(n['off']-n['on']),0)/.008)
        cutoff=np.minimum(20000,fundamental(n['note'])*(FROZEN[0]+FROZEN[1]*np.exp(-(t+.035)/FROZEN[2])))
        signal=np.zeros(length)
        capture_gain=1.0 if slope==12 else .83
        oscillator_phase=0.0 if slope==12 else .31
        for h in range(1,int(20000/base)+1):
            if moving:
                ratio=np.tan(np.pi*h*base/SR)/np.tan(np.pi*cutoff/SR)
                gain=1/(1-ratio*ratio+1.2j*ratio)**(slope//12)
            else:gain=10**((profile[h-1] if h<=8 else -30)/20)
            signal+=.1/h*np.real(gain*np.exp(2j*np.pi*h*base*t+1j*(.173+oscillator_phase)*h))
        y[start:start+length]+=capture_gain*signal*amp
        known.append(dict(note=n['note'],actual_carrier_hz=base,detune_cents=3,
                          capture_gain=capture_gain,oscillator_phase_radians=oscillator_phase,
                          h1_h8_saw_removed_profile_db=None if moving else profile.tolist()))
    return y.astype(np.float32),known


def duplicate_check(low,high,on):
    # Preserve the full waveform: no periodic/alias subtraction and no EQ.
    # Allow one lag and one scalar gain, then test the other time window.
    width=.08;start=round((on+.10-width/2)*SR);size=round(width*SR);radius=round(.002*SR)
    x=low[start:start+size].astype(float)
    candidates=[]
    for lag in range(-radius,radius+1):
        z=high[start+lag:start+lag+size].astype(float)
        gain=float(np.dot(x,z)/np.dot(z,z));error=float(np.mean((x-gain*z)**2)/np.mean(x*x))
        candidates.append((error,lag,gain))
    error,lag,gain=min(candidates)
    start=round((on+.16-width/2)*SR);x=low[start:start+size].astype(float);z=high[start+lag:start+lag+size].astype(float)
    return dict(training_offset_seconds=.10,validation_offset_seconds=.16,
                allowed_lag_samples=radius,selected_lag_samples=lag,selected_gain=gain,
                training_relative_waveform_rms_error=float(np.sqrt(error)),
                frozen_validation_relative_waveform_rms_error=float(np.sqrt(np.mean((x-gain*z)**2)/np.mean(x*x))))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True,help='new directory')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    catalog=json.loads(CATALOG.read_text());sources=[]
    def verify(name):
        item=next(a for a in catalog['assets'] if Path(a['path']).name==name)
        path=args.sources/name
        if sha(path)!=item['sha256']:raise ValueError('Changed original')
        sources.append(item);return path
    midi=verify('deepsonic_-_filter_demo_-_comparsion_sequence.mid');active={};notes=[]
    for event in parse_smf(midi.read_bytes())['events']:
        if event['kind']!='midi':continue
        b=bytes.fromhex(event['hex']);kind=b[0]&240;key=(b[0]&15,b[1])
        if kind==144 and b[2]>0:active[key]=(event['sample']/SR,b[2])
        elif kind==128 or (kind==144 and b[2]==0):
            on,velocity=active.pop(key)
            if (on,b[1]) in SELECT:notes.append(dict(on=on,off=event['sample']/SR,note=b[1],velocity=velocity))
    notes.sort(key=lambda n:n['on'])
    if len(notes)!=len(SELECT):raise ValueError('Original MIDI selection changed')
    audio={};decodes=[]
    for slope in (12,24):
        mp3=verify(f'roland_sh-201_-_filter_demo_-_lpf{slope}_q000.mp3');wav=out/f'hardware-lp{slope}.wav'
        command=['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-i',str(mp3),'-c:a','pcm_f32le',str(wav)]
        subprocess.run(command,check=True);sr,y=wavfile.read(wav)
        if sr!=SR or y.ndim!=1:raise ValueError('Unexpected original decode')
        audio[slope]=y;decodes.append(dict(command=command,wav_sha256=sha(wav)))
    hardware=assess(audio,notes)
    duplicates=[dict(note=n['note'],**duplicate_check(audio[12],audio[24],n['on'])) for n in notes]
    controls=[]
    for moving in (False,True):
        name='moving-filter' if moving else 'invariant-notched-source'
        pcm={};mp3_audio={};provenance=[]
        for slope in (12,24):
            y,known=synthesize(notes,slope,moving);pcm[slope]=y
            wav=out/f'{name}-lp{slope}.wav';mp3=wav.with_suffix('.mp3');decoded=out/f'{name}-lp{slope}-decoded.wav'
            wavfile.write(wav,SR,y)
            encode=['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-i',str(wav),'-c:a','libmp3lame','-b:a','320k',str(mp3)]
            decode=['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-i',str(mp3),'-c:a','pcm_f32le',str(decoded)]
            subprocess.run(encode,check=True);subprocess.run(decode,check=True)
            sr,mp3_audio[slope]=wavfile.read(decoded)
            provenance.append(dict(slope=slope,known=known,wav_sha256=sha(wav),mp3_sha256=sha(mp3),
                                   decoded_sha256=sha(decoded),encode_command=encode,decode_command=decode))
        controls.extend([dict(id=name+'-pcm',provenance=provenance,**assess(pcm,notes)),
                         dict(id=name+'-mp3',provenance=provenance,**assess(mp3_audio,notes))])
    result=dict(schema_version=1,status='independent invariance audit; no candidate or raw-control fit',
        tool_sha256=sha(__file__),catalog_sha256=sha(CATALOG),sources=sources,decodes=decodes,notes=notes,
        method='Joint full-sample quadratures to20kHz with independent quadratic complex ramps for true harmonics and linear complex ramps for both independently established44.1k alias branches; H2..H8/H1. Nominal MIDI frequency and per-note LP12+.10s/H1 refinement frozen for every other window and slope. Common hardware mask≥−55dB/H1 and coefficient-SNRproxy≥20dB across both frequency policies and60/80/100ms widths.40ms cutoff-divergence sweep also reports fixedH2..H4 eligibility separately.',
        analysis_revision='v2 adds the previously independently established alias branches as nuisance columns; v1 treated these as residual and inflated harmonic uncertainty. v3 changes synthetic LP24 phase and capture gain independently so the invariant control is not two identical input files. Hardware measurement code/numerics unchanged fromv2. No frequency or alias level is fitted across notes.',
        frozen_cutoff_extrapolation=dict(formula='f0 * (A + B*exp(-original_MIDI_elapsed_seconds/tau))',
                                        A=FROZEN[0],B=FROZEN[1],tau=FROZEN[2],
                                        status='Frozen low-note effective trajectory extrapolated to high notes; not actual cutoff measurement or raw law.'),
        hardware=hardware,waveform_duplicate_checks=duplicates,controls=controls,
        limitations=['One stored dry-Saw recipe, no original SysEx or raw control values.',
                     'Normalized magnitudes cannot separate a common oscillator transfer from capture EQ or a common fixed filter.',
                     'Equality of LP12/24 ratios may be compatible with bypass, clamping, hidden controls or source/capture processing; it does not identify the mechanism.',
                     'Local coefficient noise is a proxy because residuals include deterministic aliases and modulation.',
                     'The320kbps control uses a known encoder, not the unknown original encoding history.'])
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(refinements=hardware['frequency_refinements'],summary=hardware['note_summaries'],duplicates=duplicates),indent=2))


if __name__=='__main__':main()
