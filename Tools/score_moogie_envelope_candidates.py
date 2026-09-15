#!/usr/bin/env python3
"""Select Moogie envelope candidates on one note; score frozen holdouts.

Inputs are existing WAVs. This tool never renders audio, changes a patch,
fits EQ, or changes performance MIDI. Candidate audio is advanced by the
known renderer delay through sample-window selection, exactly once.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
import numpy as np
from scipy.io import wavfile
from scipy.optimize import minimize_scalar

from render_midi import parse_smf

NOTES = ((.029, .400, 39), (.939, 1.315, 39), (1.901, 2.245, 39))
CENTERS = (.10, .18, .26)
SHIFTS = (-.02, 0., .02)
WIDTH = .08
EXPECTED_SYSEX = '33d39a6b1cbf47abd830ecf879e1ef6774b50eb6a4eb4db6997749f4f7cffabc'
EXPECTED_MIDI = '354540c1ac357a80473d0d71e62a20ff2af79e125fcdf82166d20ec12cf71104'
KNOWN_HARDWARE = {
    '46fa72b890e918f1d62b2a467cb6dc11aade820167879ba6a19b2930c71e1502': 'full official-demo decode',
    'b68b102973532d6e904cdceee31aebd89a304c43059d2ebcf2b22e57d83ba377': 'unmodified first-3.7-second excerpt',
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rms(values):
    return float(np.sqrt(np.mean(np.square(values)))) if len(values) else None


def read_audio(path):
    sr, audio = wavfile.read(path)
    if sr != 44100 or audio.dtype.kind != 'f' or audio.ndim not in (1,2):
        raise ValueError(f'Expected 44.1 kHz floating mono/stereo PCM: {path}')
    if audio.ndim == 2 and audio.shape[1] != 2:
        raise ValueError(f'Unexpected channel count: {path}')
    if not np.isfinite(audio).all():
        raise ValueError(f'Nonfinite audio: {path}')
    mono = audio.astype(float).mean(axis=1) if audio.ndim == 2 else audio.astype(float)
    return sr, mono, dict(path=str(Path(path).resolve()), sha256=digest(path),
                         sample_rate=sr, frames=len(audio), channels=1 if audio.ndim==1 else 2,
                         peak=float(np.max(np.abs(audio))),
                         samples_at_or_above_full_scale=int(np.count_nonzero(np.abs(audio)>=1)))


@lru_cache(maxsize=24)
def basis(sr, size, frequency, harmonics):
    # Centering on the actual sample window keeps the design reusable across
    # different absolute times; a sub-sample phase origin cannot affect gain.
    t = (np.arange(size)-(size-1)/2)/sr
    u = t/max((size-1)/(2*sr),1/sr)
    columns = [np.ones(size),u]
    for h in range(1,harmonics+1):
        co, si = np.cos(2*np.pi*h*frequency*t), np.sin(2*np.pi*h*frequency*t)
        columns.extend((co,si,u*co,u*si))
    matrix = np.column_stack(columns)
    left, singular, right = np.linalg.svd(matrix,full_matrices=False)
    condition = float(singular[0]/singular[-1])
    if condition > 100:
        raise ValueError(f'Ill-conditioned harmonic fit: {condition}')
    inverse = (right.T/singular)@left.T
    # Coefficient variance proxy under a white-residual model. Deterministic
    # leakage also receives a global residual-power check and synthetic test.
    diagonal = np.sum(inverse*inverse,axis=1)
    return matrix, inverse, diagonal, condition


def measure(y,sr,center,frequency,harmonics=96):
    first,last = round((center-WIDTH/2)*sr),round((center+WIDTH/2)*sr)
    if first < 0 or last > len(y):
        raise ValueError('Harmonic window outside audio')
    x = y[first:last]
    if np.var(x) < 1e-16:
        raise ValueError('Cannot score a silent harmonic window')
    matrix,inverse,diagonal,condition = basis(sr,len(x),frequency,harmonics)
    coefficient = inverse@x
    amplitude = np.hypot(coefficient[2::4],coefficient[3::4])
    residual = x-matrix@coefficient
    residual_fraction = float(np.mean(residual**2)/np.var(x))
    variance = float(np.sum(residual**2)/(len(x)-len(coefficient)))
    uncertainty = np.sqrt(variance*(diagonal[2::4]+diagonal[3::4]))
    h1 = max(amplitude[0],1e-15)
    return dict(amplitude=amplitude.tolist(),
                relative_h1_db=(20*np.log10(np.maximum(amplitude,1e-15)/h1)).tolist(),
                snr_proxy_db=(20*np.log10(np.maximum(amplitude,1e-15)/np.maximum(uncertainty,1e-30))).tolist(),
                residual_power_fraction=residual_fraction,condition_number=condition,
                window_start_sample=first,window_end_sample=last)


def estimate_frequency(y,sr,on,nominal,latency):
    # Frequency is a hardware/production nuisance measured once, before any
    # candidate is scored. Small 16-harmonic fits keep this bounded search
    # separate from the 96-harmonic amplitude measurement.
    def objective(frequency):
        total = []
        for offset in CENTERS:
            first,last = round((on+offset+latency-WIDTH/2)*sr),round((on+offset+latency+WIDTH/2)*sr)
            x = y[first:last]
            t = (np.arange(len(x))-(len(x)-1)/2)/sr
            u = t/(WIDTH/2)
            columns = [np.ones(len(x)),u]
            for h in range(1,17):
                co,si=np.cos(2*np.pi*h*frequency*t),np.sin(2*np.pi*h*frequency*t)
                columns.extend((co,si,u*co,u*si))
            matrix=np.column_stack(columns)
            coeff=np.linalg.lstsq(matrix,x,rcond=None)[0]
            total.append(np.mean((x-matrix@coeff)**2)/max(np.var(x),1e-30))
        return float(np.mean(total))
    found=minimize_scalar(objective,bounds=(nominal*.97,nominal*1.03),method='bounded',
                          options={'xatol':1e-7})
    return float(found.x)


def hardware_eligibility(row):
    # Only hardware controls the common mask; a missing candidate harmonic
    # must increase error, never remove the observation from its score.
    qualified = row['residual_power_fraction'] <= .01
    usable = [qualified and ratio > -45 and snr >= 20 for ratio,snr in
              zip(row['relative_h1_db'],row['snr_proxy_db'])]
    groups = {'full':(0,(1,2,3,4,5,6,7)), 'odd':(0,(2,4,6)), 'even':(1,(3,5,7))}
    return {name:[i+1 for i in indices if usable[reference] and usable[i]]
            for name,(reference,indices) in groups.items()}


def difference(actual,reference,eligible):
    a,b = np.asarray(actual['relative_h1_db']),np.asarray(reference['relative_h1_db'])
    result={}
    for group,hs in eligible.items():
        normalizer=1 if group=='even' else 0
        result[group]=[float((a[h-1]-a[normalizer])-(b[h-1]-b[normalizer])) for h in hs]
    return result


def summarize(rows):
    result={}
    for shift in SHIFTS:
        for role in ('training','holdout'):
            group=[r for r in rows if r['shift_seconds']==shift and r['role']==role]
            result[f'{role}_shift_{shift:+.2f}']={name:dict(
                observations=sum(len(r['error_db'][name]) for r in group),
                rmse_db=rms([v for r in group for v in r['error_db'][name]])) for name in ('full','odd','even')}
    return result


def choose(models):
    qualified=[(m['summary']['training_shift_+0.00']['even']['rmse_db'],name)
               for name,m in models.items() if name!='production'
               and m['selection_eligible']]
    if not qualified:
        raise ValueError('No candidate has valid training measurements')
    score,name=min(qualified)
    return dict(candidate_id=name,training_even_rmse_db=score,
                rule='minimum first-note H4/H2,H6/H2,H8/H2 RMSE at zero shift; candidate-id breaks exact ties')


def self_test():
    sr,f=44100,38.89
    t=np.arange(sr)/sr
    gains=np.array([.4,.15,.11,.07,.045,.03,.025,.015]+[.003/h for h in range(9,97)])
    y=.01+.004*t
    for h,g in enumerate(gains,1):
        y+=g*(1+.3*h/96*(t-.4))*np.cos(2*np.pi*h*f*t+.117*h*h)
    observed=measure(y,sr,.4,f)
    maximum=float(np.max(np.abs(np.array(observed['amplitude'])-gains)))
    # The actual sample-grid center differs from requested center by half a
    # sample. Include that deterministic linear-ramp displacement explicitly.
    midpoint=(observed['window_start_sample']+observed['window_end_sample']-1)/(2*sr)
    expected=gains*(1+.3*np.arange(1,97)/96*(midpoint-.4))
    error=float(np.max(np.abs(np.array(observed['amplitude'])-expected)))
    if error>1e-10:
        raise ValueError(f'Synthetic amplitude recovery failed: {error}')
    delayed=np.concatenate((np.zeros(93),y))
    moved=measure(delayed,sr,.4+93/sr,f)
    delay_error=float(np.max(np.abs(np.array(moved['relative_h1_db'])-
                                   observed['relative_h1_db'])))
    if delay_error>1e-10:
        raise ValueError('Renderer-delay compensation failed')
    eligible=hardware_eligibility(observed)
    missing=dict(observed,relative_h1_db=list(observed['relative_h1_db']))
    missing['relative_h1_db'][3]=-150
    e=difference(missing,observed,eligible)['even']
    if len(e)!=3 or max(abs(v) for v in e)<100:
        raise ValueError('Candidate-dependent eligibility regression')
    fixture={name:dict(selection_eligible=True,summary={'training_shift_+0.00':
             {'even':{'rmse_db':score}}}) for name,score in (('train-winner',1),('holdout-winner',2))}
    if choose(fixture)['candidate_id']!='train-winner':
        raise ValueError('First-note selection regression')
    return dict(amplitude_max_error=error,uncorrected_center_error=maximum,
                delay_compensation_max_error_db=delay_error,hardware_only_mask=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path)
    parser.add_argument('--hardware',type=Path)
    parser.add_argument('--production',type=Path)
    parser.add_argument('--candidate',action='append',default=[],metavar='ID=WAV')
    parser.add_argument('--sysex',type=Path)
    parser.add_argument('--midi',type=Path)
    parser.add_argument('--renderer-latency-samples',type=int,default=93)
    parser.add_argument('--frequency-policy',choices=('estimated','nominal'),default='estimated',
                        help='nominal is an explicit sensitivity check, not a new primary selection')
    parser.add_argument('--frozen-candidate',help='score an already selected candidate without reselecting it')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    sanity=self_test()
    if args.self_test:
        print(json.dumps(sanity,indent=2));return
    if not args.output:
        parser.error('--output is required')
    if args.manifest:
        if any((args.hardware,args.production,args.candidate,args.sysex,args.midi)):
            parser.error('Use either --manifest or direct audio/input options')
        config=json.loads(args.manifest.read_text())
        base=args.manifest.resolve().parent
    else:
        if not all((args.hardware,args.production,args.candidate,args.sysex,args.midi)):
            parser.error('Direct mode requires --hardware --production --candidate --sysex --midi')
        candidates=[]
        for entry in args.candidate:
            if '=' not in entry:parser.error('--candidate must be ID=WAV')
            name,path=entry.split('=',1);candidates.append(dict(id=name,wav=path))
        config=dict(hardware_wav=str(args.hardware),production_wav=str(args.production),
                    sysex=str(args.sysex),midi=str(args.midi),candidates=candidates,
                    renderer_latency_samples=args.renderer_latency_samples)
        base=Path.cwd()
    def resolve(value):
        path=Path(value);return path if path.is_absolute() else base/path
    if config.get('hardware_origin_seconds',0)!=0:
        raise ValueError('Hardware must retain the original timeline origin (zero)')
    delay=config.get('renderer_latency_samples',93)
    if not isinstance(delay,int) or delay!=93:
        raise ValueError('This protocol requires the verified 93-sample 44.1 kHz renderer delay')
    candidates=config['candidates']
    names=[c['id'] for c in candidates]
    if len(set(names))!=len(names) or 'production' in names or any(not n for n in names):
        raise ValueError('Candidate ids must be nonempty, unique and not production')
    if not candidates:raise ValueError('No candidates supplied')
    sysex,midi=resolve(config['sysex']),resolve(config['midi'])
    if digest(sysex)!=EXPECTED_SYSEX or digest(midi)!=EXPECTED_MIDI:
        raise ValueError('Moogie original patch or frozen reconstructed MIDI changed')
    events=parse_smf(midi.read_bytes())['events']
    for on,off,note in NOTES:
        if not any(e['kind']=='midi' and abs(e['sample']/44100-on)<1/44100 and
                   bytes.fromhex(e['hex'])==bytes((0x90,note,100)) for e in events):
            raise ValueError('Selected long note does not match reconstructed MIDI')
    sr,hardware,hardware_info=read_audio(resolve(config['hardware_wav']))
    _,production,production_info=read_audio(resolve(config['production_wav']))
    latency=delay/sr
    frequencies={}
    reference=[]
    for index,(on,off,note) in enumerate(NOTES):
        nominal=440*2**((note-12-69)/12)
        hf=estimate_frequency(hardware,sr,on,nominal,0) if args.frequency_policy=='estimated' else nominal
        pf=estimate_frequency(production,sr,on,nominal,latency) if args.frequency_policy=='estimated' else nominal
        frequencies[index]=dict(nominal_hz=nominal,hardware_hz=hf,production_hz=pf)
        for offset in CENTERS:
            for shift in SHIFTS:
                center=on+offset+shift
                observed=measure(hardware,sr,center,hf)
                eligible=hardware_eligibility(observed)
                reference.append(dict(note_index=index,played_midi_note=note,on_seconds=on,
                    offset_seconds=offset,shift_seconds=shift,center_seconds=center,
                    role='training' if index==0 else 'holdout',eligible=eligible,**observed))
    train=[r for r in reference if r['note_index']==0 and r['shift_seconds']==0]
    if any(len(r['eligible']['even'])<2 for r in train):
        raise ValueError('Hardware does not qualify at least two even ratios in every training window')
    models={}
    provenance={'hardware':hardware_info,'production':production_info,'candidates':{}}
    for item in [dict(id='production',wav=config['production_wav'])]+candidates:
        name=item['id']
        if name=='production':y,info=production,production_info
        else:_,y,info=read_audio(resolve(item['wav']))
        info['declared_metadata']={k:v for k,v in item.items() if k not in ('id','wav')}
        # Verify a render sidecar when supplied, otherwise retain an explicit
        # provenance limit rather than claiming the WAV proves patch use.
        metadata_path=item.get('render_metadata')
        info['render_input_provenance']='declared inputs; WAV alone cannot prove their use'
        automatic_sidecar=resolve(item['wav']).with_suffix('.render.json')
        if metadata_path is None and automatic_sidecar.is_file():
            metadata_path=str(automatic_sidecar.resolve())
        if metadata_path:
            meta_path=resolve(metadata_path);meta=json.loads(meta_path.read_text())
            if (meta['inputs']['sysex']['sha256']!=EXPECTED_SYSEX or
                meta['inputs']['midi']['sha256']!=EXPECTED_MIDI or
                meta['output']['sha256']!=info['sha256'] or meta['output']['latency_samples']!=delay):
                raise ValueError(f'Render sidecar does not match candidate: {name}')
            info['render_input_provenance']='verified matching render sidecar'
            info['render_metadata_sha256']=digest(meta_path)
            info['renderer_sha256']=meta['inputs']['renderer']['sha256']
        if name!='production':provenance['candidates'][name]=info
        rows=[]
        cached={}
        for ref in reference:
            key=(ref['note_index'],ref['offset_seconds'])
            if key not in cached:
                cached[key]=measure(y,sr,ref['on_seconds']+ref['offset_seconds']+latency,
                                    frequencies[ref['note_index']]['production_hz'])
            observed=cached[key]
            rows.append(dict(note_index=ref['note_index'],role=ref['role'],
                offset_seconds=ref['offset_seconds'],shift_seconds=ref['shift_seconds'],
                hardware_center_seconds=ref['center_seconds'],
                render_center_seconds=ref['on_seconds']+ref['offset_seconds']+latency,
                eligible_harmonics=ref['eligible'],error_db=difference(observed,ref,ref['eligible']),
                hardware_residual_power=ref['residual_power_fraction'],
                render_residual_power=observed['residual_power_fraction']))
        summary=summarize(rows)
        primary=[r for r in rows if r['role']=='training' and r['shift_seconds']==0]
        selectable=all(r['render_residual_power']<=.01 for r in primary)
        models[name]=dict(selection_eligible=selectable,summary=summary,windows=rows,
                          render_measurements=[dict(note_index=k[0],offset_seconds=k[1],**r)
                                               for k,r in cached.items()])
    if args.frozen_candidate:
        if args.frozen_candidate not in names:
            raise ValueError('Frozen candidate id not present in the manifest')
        selection=dict(candidate_id=args.frozen_candidate,
            training_even_rmse_db=models[args.frozen_candidate]['summary']['training_shift_+0.00']['even']['rmse_db'],
            rule='externally frozen candidate; no selection or offset optimization in this sensitivity run')
    else:
        if args.frequency_policy!='estimated':
            raise ValueError('Nominal-frequency sensitivity requires --frozen-candidate')
        selection=choose(models)
    winner=selection['candidate_id']
    result=dict(schema_version=1,status='conditional same-patch reconstructed-performance candidate scoring',
        tool_sha256=digest(__file__),manifest_sha256=digest(args.manifest) if args.manifest else None,
        manifest_metadata={k:v for k,v in config.items() if k not in ('hardware_wav','production_wav','sysex','midi','candidates')},
        self_test=sanity,inputs=dict(sysex_sha256=digest(sysex),midi_sha256=digest(midi),**provenance),
        hardware_association=KNOWN_HARDWARE.get(hardware_info['sha256'],'unrecognized WAV hash; source association is caller-declared'),
        source_url='https://www.rolandus.com/go/sh-201_patches/mp3/BASS/TOP8_Moogie1.mp3',
        frequency_estimates=frequencies,hardware_measurements=reference,models=models,selection=selection,
        selected_holdouts=models[winner]['summary'],
        protocol=dict(notes=[dict(on=a,off=b,played_midi_note=n) for a,b,n in NOTES],
            centers_after_onset_seconds=list(CENTERS),width_seconds=WIDTH,hardware_shifts_seconds=list(SHIFTS),
            renderer_latency_samples=delay,renderer_compensation='measure render at on+offset+93/sr; measure hardware at on+offset+shift',
            source_fundamental_offset_semitones=-12,measurement_harmonics=96,
            reference_only_eligibility='power residual <=1%, amplitude >-45 dB relative H1, coefficient SNR proxy >=20 dB',
            normalization=dict(full='H2-H8/H1',odd='H3,H5,H7/H1',even='H4,H6,H8/H2'),
            fitted_gain_eq_or_ratio_offsets=False,
            candidate_frequencies=('frozen production estimate per note' if args.frequency_policy=='estimated'
                                   else 'nominal physical MIDI family for all signals'),
            frequency_policy=args.frequency_policy,
            selected_timing_shift=False,selection_note=0,selection_shift_seconds=0),
        limits=['Original performance MIDI is unavailable; the frozen reconstruction is an estimate.',
                'Even-harmonic isolation assumes symmetric lower square/triangle and sufficiently linear processing.',
                'Frequency nuisance estimates are independent for hardware/production; candidates inherit production.',
                'A moving filter can bias effective harmonic-frequency estimates; they are not calibrated oscillator tuning.',
                'SNR uses a white-residual proxy; deterministic waveform changes and capture processing remain.',
                'Timing sensitivity freezes the primary winner; it does not select the best offset.',
                'Holdout notes and other presets must not be used to retune the selected anchor.',
                'WAV and input hashes alone do not prove rendering provenance without a verified sidecar.',
                'These harmonic errors do not establish complete audio equivalence.'])
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(selection=selection,summary={k:v['summary'] for k,v in models.items()}),indent=2))


if __name__=='__main__':main()
