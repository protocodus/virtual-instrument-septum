#!/usr/bin/env python3
"""Exploratory 22.05 kHz image-family diagnostic; never changes the parent audit.

Uses a hash-verified copy of its harmonic nuisance helper, original MIDI,
both Q0 recordings and all four existing PCM/MP3 controls. Ordinary harmonics
and both 44.1 kHz image branches are excluded before measuring any new line.
"""
import argparse
from functools import lru_cache
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
import numpy as np
from scipy.io import wavfile

ROOT = Path(__file__).resolve().parents[1]
HELPER_SHA = '99e07f49b6804d605df6376dacd957add4d7bbda49d9b1b7136d3885824dc1c0'
SELECTION = ((8.5,69),(12.5,76),(13.25,81),(18.25,93),(18.75,91),
             (19.25,86),(19.75,88),(20.25,84))
SR, RATE, NFFT = 44100, 22050, 262144
OFFSETS, WIDTH, GUARD = (.10,.16), .08, 37.5


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def f0(note):
    return 440*2**((note-69)/12)


def harmonic_distance(f, base):
    return np.abs(f-np.round(np.asarray(f)/base)*base)


def independent_distance(f, base):
    """Distance to true harmonics and either +/-44.1k image branch."""
    return np.minimum(harmonic_distance(f,base),
                      np.minimum(harmonic_distance(44100-np.asarray(f),base),
                                 harmonic_distance(44100+np.asarray(f),base)))


def candidates(note):
    rows=[]
    for h in range(1,int((RATE+15000)/f0(note))+1):
        signed=RATE-h*f0(note)
        expected=abs(signed)
        if not 300 < expected < 15000:
            continue
        distance=float(independent_distance(expected,f0(note)))
        rows.append(dict(parent_harmonic=h,branch='22050-minus-hf0' if signed>0 else 'hf0-minus-22050',
                         expected_hz=expected,nearest_excluded_family_hz=distance,
                         eligible=distance>GUARD))
    return rows


@lru_cache(maxsize=8)
def spectral_grid(note):
    frequency=np.fft.rfftfreq(NFFT,1/SR)
    mask=independent_distance(frequency,f0(note))>GUARD
    return frequency,mask


def measure(y,note,on,offset,helper):
    a,b=round((on+offset-WIDTH/2)*SR),round((on+offset+WIDTH/2)*SR)
    x=y[a:b].astype(float)
    if len(x)!=round(WIDTH*SR) or not np.isfinite(x).all() or np.var(x)<1e-16:
        raise ValueError('Invalid diagnostic window')
    matrix,inverse,condition=helper.harmonic_model(note,len(x))
    coeff=inverse@x
    residual=x-matrix@coeff
    h1=float(np.hypot(coeff[3],coeff[4]))
    if h1<1e-8 or condition>100:
        raise ValueError('Invalid harmonic reference or nuisance basis')
    hann=np.hanning(len(x))
    spectrum=2*abs(np.fft.rfft(residual*hann,NFFT))/hann.sum()
    frequency,mask=spectral_grid(note)
    lines=[]
    for candidate in candidates(note):
        if not candidate['eligible']:
            continue
        expected=candidate['expected_hz']
        indices=np.flatnonzero((abs(frequency-expected)<=6)&mask)
        if not len(indices):
            raise ValueError('Eligible candidate lost all search bins')
        k=indices[np.argmax(spectrum[indices])]
        background=(abs(frequency-expected)<250)&(abs(frequency-expected)>GUARD)&mask
        background &= (frequency>300)&(frequency<15000)
        floor=float(np.median(spectrum[background])) if background.sum()>50 else float('inf')
        rel=float(20*np.log10(max(spectrum[k],1e-20)/h1))
        prominence=float(20*np.log10(max(spectrum[k],1e-20)/max(floor,1e-20)))
        interior=bool(k>indices[0] and k<indices[-1] and
                      spectrum[k]>=spectrum[k-1] and spectrum[k]>=spectrum[k+1])
        lines.append(dict(**candidate,peak_hz=float(frequency[k]),relative_h1_db=rel,
                          local_prominence_db=prominence,interior_peak=interior,
                          passes_line_threshold=bool(interior and prominence>=12 and rel>=-75)))
    return dict(note=note,on_seconds=on,offset_seconds=offset,start_sample=a,end_sample=b,
                h1_amplitude=h1,harmonic_condition=condition,
                residual_power_fraction=float(np.mean(residual**2)/np.var(x)),lines=lines)


def summarize(rows):
    repeated=[]
    for note in sorted({r['note'] for r in rows}):
        note_rows=[r for r in rows if r['note']==note]
        for c in candidates(note):
            if not c['eligible']:
                continue
            lines=[v for r in note_rows for v in r['lines'] if v['parent_harmonic']==c['parent_harmonic']]
            if len(lines)==2 and all(v['passes_line_threshold'] for v in lines):
                repeated.append(dict(note=note,**c,relative_h1_db=[v['relative_h1_db'] for v in lines],
                                     peak_hz=[v['peak_hz'] for v in lines],
                                     local_prominence_db=[v['local_prominence_db'] for v in lines]))
    lines=[v for r in rows for v in r['lines']]
    return dict(tested_line_windows=len(lines),passing_line_windows=sum(v['passes_line_threshold'] for v in lines),
                repeated_lines=repeated,notes_with_repeated_lines=sorted({v['note'] for v in repeated}))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    original_helper=ROOT/'Tools/analyze_deepsonic_saw_aliases.py'
    if sha(original_helper)!=HELPER_SHA:
        raise ValueError('Original helper changed; review before running')
    copied=out/'original_alias_helper.py';shutil.copyfile(original_helper,copied)
    spec=importlib.util.spec_from_file_location('frozen_original_alias_helper',copied)
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    original=args.experiment_dir/'results.json';prior=json.loads(original.read_text())
    if prior['script_sha256']!=HELPER_SHA or sorted((n['on'],n['note']) for n in prior['notes'])!=sorted(SELECTION):
        raise ValueError('Parent audit/helper or selection changed')
    for source in prior['sources']:
        if sha(ROOT/source['path'])!=source['sha256']:
            raise ValueError('Original MP3/MIDI changed')
    midi=next(s for s in prior['sources'] if s['path'].endswith('.mid'))
    events=helper.parse_smf((ROOT/midi['path']).read_bytes())['events']
    starts={(e['sample']/SR,bytes.fromhex(e['hex'])[1]) for e in events if e['kind']=='midi'
            and bytes.fromhex(e['hex'])[0]&240==144 and bytes.fromhex(e['hex'])[2]==127}
    if not set(SELECTION)<=starts:
        raise ValueError('Original MIDI no longer supplies selected notes')
    protocol=dict(status='exploratory_half_rate_image_family_not_internal_rate_measurement',
                  parent_result_sha256=sha(original),copied_helper_sha256=sha(copied),
                  capture_sample_rate=SR,tested_family=RATE,frequency_range_hz=[300,15000],
                  prediction='abs(22050-h*f0), h>=1; both branches, including images above11025Hz',
                  selection=SELECTION,offset_seconds=OFFSETS,width_seconds=WIDTH,
                  exclusion='Bins and candidate centers must be >37.5Hz from true harmonics and either abs(44100-h*f0) branch.',
                  threshold='Interior local peak within +/-6Hz, >=12dB local residual median prominence and >=-75dB/H1; repeat in both windows.',
                  candidates={str(note):candidates(note) for _,note in SELECTION},
                  interpretation='No 22.05k DSP conclusion. Remaining lines may be unrelated sidebands. Two windows overlap by20ms. Positive controls test sensitivity, not hardware architecture.')
    (out/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    mapping={'hardware-lp12':'hardware-lp12.wav','hardware-lp24':'hardware-lp24.wav',
             'bandlimited-negative-pcm':'bandlimited-negative.wav','bandlimited-negative-mp3':'bandlimited-negative-roundtrip.wav',
             'injected-44100-positive-pcm':'injected-44100-positive.wav','injected-44100-positive-mp3':'injected-44100-positive-roundtrip.wav'}
    groups=[];negative=None
    for group_id,filename in mapping.items():
        entry=next(g for g in prior['groups'] if g['id']==group_id)
        expected=entry.get('wav_sha256') or entry['provenance'].get('wav_sha256') or entry['provenance']['decoded_wav_sha256']
        path=args.experiment_dir/filename
        if sha(path)!=expected:
            raise ValueError('Existing WAV identity changed')
        sr,y=wavfile.read(path)
        if sr!=SR or y.ndim!=1 or y.dtype.kind!='f' or not np.isfinite(y).all():
            raise ValueError('Unexpected WAV format')
        if group_id=='bandlimited-negative-pcm':negative=y.copy()
        rows=[measure(y,note,on,offset,helper) for on,note in SELECTION for offset in OFFSETS]
        groups.append(dict(id=group_id,wav_sha256=sha(path),summary=summarize(rows),windows=rows))
        print(group_id,groups[-1]['summary']['passing_line_windows'],len(groups[-1]['summary']['repeated_lines']),flush=True)
    # Fixed sensitivity control: first two eligible h on each branch/note,
    # injected at absolute0.0001 peak (approximately -60dBc in the existing
    # additive Saw) with a 2ms attack and 8ms post-gate decay.
    y=negative.astype(float);injections=[]
    for n in prior['notes']:
        note,on,off=n['note'],n['on'],n['off']
        start=round((on+.035)*SR);size=round((off-on+.08)*SR);t=np.arange(size)/SR
        gate=np.minimum(1,t/.002)*np.exp(-np.maximum(t-(off-on),0)/.008)
        for branch in ('22050-minus-hf0','hf0-minus-22050'):
            for c in [c for c in candidates(note) if c['eligible'] and c['branch']==branch][:2]:
                y[start:start+size] += .0001*gate*np.sin(2*np.pi*c['expected_hz']*t+.31)
                injections.append(dict(note=note,absolute_peak_amplitude=.0001,**c))
    wav=out/'injected-22050-positive.wav';wavfile.write(wav,SR,y.astype(np.float32))
    for codec in (False,True):
        if codec:
            mp3=out/'injected-22050-positive.mp3';decoded=out/'injected-22050-positive-roundtrip.wav'
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-i',str(wav),'-c:a','libmp3lame','-b:a','320k',str(mp3)],check=True)
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-i',str(mp3),'-c:a','pcm_f32le',str(decoded)],check=True)
        path=decoded if codec else wav
        sr,y=wavfile.read(path)
        if sr!=SR or y.ndim!=1 or not np.isfinite(y).all():raise ValueError('Changed positive control format')
        rows=[measure(y,note,on,offset,helper) for on,note in SELECTION for offset in OFFSETS]
        summary=summarize(rows)
        expected={(r['note'],r['parent_harmonic']) for r in injections}
        recovered={(r['note'],r['parent_harmonic']) for r in summary['repeated_lines']}
        groups.append(dict(id='injected-22050-positive-'+('mp3' if codec else 'pcm'),wav_sha256=sha(path),
                           injections=injections,injected_lines=len(expected),recovered_injected_lines=len(expected&recovered),
                           summary=summary,windows=rows))
        print(groups[-1]['id'],len(expected&recovered),'/',len(expected),flush=True)
    assert sha(original_helper)==HELPER_SHA and helper.RATES==(32000,44100,48000)
    result=dict(protocol=protocol,script_sha256=sha(__file__),parent_result=str(original.resolve()),
                render_midi_helper_sha256=sha(ROOT/'Tools/render_midi.py'),groups=groups,
                conclusion='Diagnostic only; assess repeat and control results before interpreting any family.')
    (out/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':
    main()
