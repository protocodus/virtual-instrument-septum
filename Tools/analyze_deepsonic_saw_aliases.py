#!/usr/bin/env python3
"""Bounded first-fold alias-line audit of original-MIDI dry single-Saw notes.

No internal sample rate is inferred from the 44.1 kHz capture format. The
three hypotheses predict nonharmonic line positions; missing lines cannot
exclude a rate when the source oscillator could already be bandlimited.
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
from scipy.signal import find_peaks
from render_midi import parse_smf

ROOT=Path(__file__).resolve().parents[1]
CATALOG=ROOT/'Docs/fidelity/source-audits/deepsonic-acquisition-2026-09-15.json'
SELECTION=((8.5,69),(12.5,76),(13.25,81),(18.25,93),(18.75,91),
           (19.25,86),(19.75,88),(20.25,84))
RATES=(32000,44100,48000)
OFFSETS=(.10,.16)
WIDTH=.08
SR=44100
NFFT=262144
GUARD=3/WIDTH


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def f0(note):
    return 440*2**((note-69)/12)


def distance_to_harmonic(f,base):
    return np.abs(f-np.round(np.asarray(f)/base)*base)


def candidates(note,rate):
    base=f0(note)
    return [dict(parent_harmonic=h,frequency_hz=float(rate-h*base))
            for h in range(int(rate/(2*base))+1,int(rate/base)+1)
            if 300<rate-h*base<15000 and distance_to_harmonic(rate-h*base,base)>GUARD]


@lru_cache(maxsize=20)
def harmonic_model(note,size):
    t=(np.arange(size)-(size-1)/2)/SR
    u=t/(WIDTH/2)
    columns=[np.ones(size),u,u*u]
    hs=np.arange(1,int(20000/f0(note))+1)
    for h in hs:
        co,si=np.cos(2*np.pi*h*f0(note)*t),np.sin(2*np.pi*h*f0(note)*t)
        columns.extend((co,si,u*co,u*si,u*u*co,u*u*si))
    matrix=np.column_stack(columns)
    left,singular,right=np.linalg.svd(matrix,full_matrices=False)
    return matrix,(right.T/singular)@left.T,float(singular[0]/singular[-1])


def measure(y,on,note,offset):
    center=on+offset
    a,b=round((center-WIDTH/2)*SR),round((center+WIDTH/2)*SR)
    x=y[a:b].astype(float)
    matrix,inverse,condition=harmonic_model(note,len(x))
    coefficient=inverse@x
    residual=x-matrix@coefficient
    reference=float(np.hypot(coefficient[3],coefficient[4]))
    hann=np.hanning(len(x))
    spectrum=2*abs(np.fft.rfft(residual*hann,NFFT))/hann.sum()
    frequency=np.fft.rfftfreq(NFFT,1/SR)
    true_harmonic_mask=distance_to_harmonic(frequency,f0(note))>GUARD
    def line(expected):
        search=(abs(frequency-expected)<=6)&true_harmonic_mask
        if not np.any(search):return None
        indices=np.flatnonzero(search)
        k=indices[np.argmax(spectrum[indices])]
        background=(abs(frequency-expected)<250)&(abs(frequency-expected)>GUARD)&true_harmonic_mask
        background &= (frequency>300)&(frequency<15000)
        floor=float(np.median(spectrum[background])) if background.sum()>50 else float('inf')
        rel=float(20*np.log10(max(spectrum[k],1e-20)/max(reference,1e-20)))
        prominence=float(20*np.log10(max(spectrum[k],1e-20)/max(floor,1e-20)))
        # A rising flank at the edge is not an observed line at the expected
        # frequency. This check applies identically to all rates and controls.
        interior_peak=bool(k>indices[0] and k<indices[-1]
                           and spectrum[k]>=spectrum[k-1] and spectrum[k]>=spectrum[k+1])
        # This is a spectral-background proxy, not a calibrated probability.
        return dict(expected_hz=float(expected),peak_hz=float(frequency[k]),
                    peak_error_hz=float(frequency[k]-expected),relative_h1_db=rel,
                    local_median_relative_h1_db=float(20*np.log10(max(floor,1e-20)/max(reference,1e-20))),
                    local_prominence_db=prominence,
                    genuine_interior_local_peak=interior_peak,
                    passes_line_threshold=bool(interior_peak and prominence>=12 and rel>=-75))
    tested=[]
    for rate in RATES:
        for c in candidates(note,rate):
            measured=line(c['frequency_hz'])
            if measured is not None:
                tested.append(dict(rate_hypothesis_hz=rate,parent_harmonic=c['parent_harmonic'],**measured))
    nulls=[]
    for expected in np.arange(350,15000,137.):
        if distance_to_harmonic(expected,f0(note))<=GUARD:continue
        measured=line(expected)
        if measured is not None:nulls.append(measured)
    peaks=find_peaks(spectrum)[0]
    peaks=peaks[(frequency[peaks]>300)&(frequency[peaks]<15000)&true_harmonic_mask[peaks]]
    peaks=peaks[np.argsort(spectrum[peaks])[-12:]][::-1]
    return dict(on_seconds=on,note=note,nominal_fundamental_hz=f0(note),offset_seconds=offset,
                center_seconds=center,width_seconds=WIDTH,
                harmonic_model_condition=condition,
                residual_power_fraction=float(np.mean(residual**2)/max(np.var(x),1e-30)),
                fitted_h1_amplitude=reference,
                diagnostic_nonharmonic_peaks=[dict(frequency_hz=float(frequency[k]),
                     relative_h1_db=float(20*np.log10(max(spectrum[k],1e-20)/max(reference,1e-20)))) for k in peaks],
                tested_alias_lines=tested,
                frequency_grid_null=dict(tested=len(nulls),passing=sum(r['passes_line_threshold'] for r in nulls)),
                null_lines_passing=[r for r in nulls if r['passes_line_threshold']])


def summary(rows):
    result={}
    for rate in RATES:
        rates=[r for row in rows for r in row['tested_alias_lines'] if r['rate_hypothesis_hz']==rate]
        repeated=[]
        for note in sorted(set(r['note'] for r in rows)):
            select=[r for r in rows if r['note']==note]
            groups={}
            for row in select:
                for line in row['tested_alias_lines']:
                    if line['rate_hypothesis_hz']==rate:
                        groups.setdefault(line['parent_harmonic'],[]).append(line)
            for h,lines in groups.items():
                if len(lines)==len(OFFSETS) and all(r['passes_line_threshold'] for r in lines):
                    repeated.append(dict(note=note,parent_harmonic=h,
                                         expected_hz=lines[0]['expected_hz'],
                                         peak_hz=[r['peak_hz'] for r in lines],
                                         relative_h1_db=[r['relative_h1_db'] for r in lines],
                                         prominence_db=[r['local_prominence_db'] for r in lines]))
        result[str(rate)]=dict(line_windows=len(rates),passing_line_windows=sum(r['passes_line_threshold'] for r in rates),
                               repeated_lines=repeated,notes_with_repeated_line=sorted(set(r['note'] for r in repeated)))
    result['frequency_grid_null']=dict(tested=sum(r['frequency_grid_null']['tested'] for r in rows),
                                      passing=sum(r['frequency_grid_null']['passing'] for r in rows))
    return result


def synthesize(notes,positive):
    y=np.zeros(round((notes[-1]['on']+.8)*SR))
    injections=[]
    for row in notes:
        note,on,off=row['note'],row['on'],row['off']
        start=round((on+.035)*SR)
        length=round((off-on+.08)*SR)
        elapsed=np.arange(length)/SR
        gate=off-on
        amp=np.minimum(1,elapsed/.002)*np.exp(-np.maximum(elapsed-gate,0)/.008)
        base=f0(note)
        # Frozen effective Hz curve expressed in original MIDI time. It is
        # an alias-free moving-amplitude/phase stress signal, not a DSP clone.
        cutoff=np.minimum(20000,base*(.9318832715+8.4984344071*np.exp(-(elapsed+.035)/.2140763348)))
        signal=np.zeros(length)
        h1=None
        for h in range(1,int(20000/base)+1):
            ratio=np.tan(np.pi*h*base/SR)/np.tan(np.pi*cutoff/SR)
            transfer=1/(1-ratio*ratio+1.2j*ratio)
            if h==1:h1=.1*np.abs(transfer)
            signal += .1/h*np.real(transfer*np.exp(2j*np.pi*h*base*elapsed+.17j*h))
        if positive:
            selected=candidates(note,44100)[:2]
            for c in selected:
                signal += h1*10**(-60/20)*np.sin(2*np.pi*c['frequency_hz']*elapsed+.31)
                injections.append(dict(note=note,frequency_hz=c['frequency_hz'],parent_harmonic=c['parent_harmonic'],
                                       relative_h1_db=-60,rate_hypothesis_hz=44100))
        y[start:start+length]+=amp*signal
    return y.astype(np.float32),injections


def codec_roundtrip(wav,out):
    mp3=out.with_suffix('.mp3')
    encode=['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-i',str(wav),
            '-c:a','libmp3lame','-b:a','320k',str(mp3)]
    decode=['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-i',str(mp3),'-c:a','pcm_f32le',str(out)]
    subprocess.run(encode,check=True);subprocess.run(decode,check=True)
    sr,y=wavfile.read(out)
    if sr!=SR:raise ValueError('Changed control sample rate')
    return y,dict(encode=encode,decode=decode,original_wav_sha256=sha(wav),mp3_sha256=sha(mp3),decoded_wav_sha256=sha(out))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True,help='new directory')
    parser.add_argument('--engine-root',type=Path,help='Optional frozen dry-v2 experiment directory, containing audio/{production,dry-hz-35ms}/lp{12,24}/candidate.wav and sidecars')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    catalog=json.loads(CATALOG.read_text());sources=[]
    def verify(name):
        item=next(a for a in catalog['assets'] if Path(a['path']).name==name)
        path=args.sources/name
        if sha(path)!=item['sha256']:raise ValueError('Original source hash mismatch')
        sources.append(item);return path
    midi=verify('deepsonic_-_filter_demo_-_comparsion_sequence.mid')
    events=parse_smf(midi.read_bytes())['events'];active={};notes=[]
    for e in events:
        if e['kind']!='midi':continue
        b=bytes.fromhex(e['hex']);status=b[0]&240;key=(b[0]&15,b[1])
        if status==144 and b[2]>0:active[key]=(e['sample']/SR,b[2])
        elif status==128 or (status==144 and b[2]==0):
            on,velocity=active.pop(key)
            if (on,b[1]) in SELECTION:notes.append(dict(on=on,off=e['sample']/SR,note=b[1],velocity=velocity))
    notes.sort(key=lambda r:r['on'])
    if len(notes)!=len(SELECTION) or any(n['velocity']!=127 for n in notes):
        raise ValueError('MIDI note selection changed')
    groups=[]
    for slope in (12,24):
        mp3=verify(f'roland_sh-201_-_filter_demo_-_lpf{slope}_q000.mp3')
        wav=out/f'hardware-lp{slope}.wav'
        command=['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-i',str(mp3),'-c:a','pcm_f32le',str(wav)]
        subprocess.run(command,check=True)
        sr,y=wavfile.read(wav)
        if sr!=SR or y.ndim!=1 or y.dtype.kind!='f':raise ValueError('Unexpected source decode')
        rows=[measure(y,n['on'],n['note'],offset) for n in notes for offset in OFFSETS]
        groups.append(dict(id=f'hardware-lp{slope}',decode_command=command,wav_sha256=sha(wav),
                           summary=summary(rows),windows=rows))
    for positive in (False,True):
        name='injected-44100-positive' if positive else 'bandlimited-negative'
        y,injections=synthesize(notes,positive)
        wav=out/(name+'.wav');wavfile.write(wav,SR,y)
        for codec in (False,True):
            if codec:y,metadata=codec_roundtrip(wav,out/(name+'-roundtrip.wav'))
            else:metadata=dict(wav_sha256=sha(wav))
            rows=[measure(y,n['on'],n['note'],offset) for n in notes for offset in OFFSETS]
            groups.append(dict(id=name+('-mp3' if codec else '-pcm'),injections=injections,
                               provenance=metadata,summary=summary(rows),windows=rows))
    if args.engine_root:
        checkpoint=args.engine_root/'checkpoint.json'
        checkpoint_provenance=dict(path=str(checkpoint.resolve()),sha256=sha(checkpoint),
                                   contents=json.loads(checkpoint.read_text()))
        for candidate in ('production','dry-hz-35ms'):
            for slope in (12,24):
                wav=args.engine_root/'audio'/candidate/f'lp{slope}'/'candidate.wav'
                sidecar=wav.with_suffix('.render.json')
                meta=json.loads(sidecar.read_text())
                if sha(wav)!=meta['output']['sha256'] or meta['inputs']['midi']['sha256']!=sha(midi):
                    raise ValueError('Frozen renderer source/output identity mismatch')
                for kind in ('sysex','renderer'):
                    identity=meta['inputs'][kind]
                    if sha(identity['path'])!=identity['sha256']:
                        raise ValueError('Frozen renderer/patch identity mismatch')
                if meta['output']['latency_samples']!=93 or meta['output']['latency_compensated']:
                    raise ValueError('Unexpected frozen renderer latency convention')
                sr,y=wavfile.read(wav)
                if sr!=SR or y.dtype.kind!='f':raise ValueError('Unexpected engine WAV')
                if y.ndim==2:y=y.mean(axis=1)
                shift=-.035+93/SR
                rows=[measure(y,n['on']+shift,n['note'],offset) for n in notes for offset in OFFSETS]
                groups.append(dict(id=f'engine-{candidate}-lp{slope}',
                    provenance=dict(wav_sha256=sha(wav),sidecar_sha256=sha(sidecar),
                                    renderer_sha256=meta['inputs']['renderer']['sha256'],
                                    patch_sha256=meta['inputs']['sysex']['sha256'],checkpoint=checkpoint_provenance),
                    alignment='Engine centers = original MIDI onset + offset -35ms hardware onset convention +93/44100s renderer latency. Applied once.',
                    summary=summary(rows),windows=rows))
    result=dict(schema_version=1,status='diagnostic alias-line feasibility; no DSP change or sample-rate fit',
        script_sha256=sha(__file__),catalog_sha256=sha(CATALOG),sources=sources,
        recipe='Owner-described dry single classic Saw, no FX/modulation/velocity sensitivity, full key tracking. Raw patch controls and SysEx unavailable.',
        notes=notes,window_offsets_seconds=list(OFFSETS),width_seconds=WIDTH,
        method=dict(capture_sample_rate_hz=SR,internal_rate_hypotheses_hz=list(RATES),
                    prediction='First fold only: Fs - h*f0, with Fs/2 < h*f0 <= Fs; 300..15000 Hz retained.',
                    harmonic_guard_hz=GUARD,frequency_search_half_width_hz=6,
                    harmonic_nuisance='Full 44.1 kHz sample grid; known MIDI f0, every harmonic below20kHz, independent quadratic complex-amplitude variation.',
                    threshold='Genuine interior local maximum within +/-6Hz, at least12dB above local median residual-amplitude background and at least -75dB relativeH1; repeat in both windows.',
                    negative_control='Alias-free additive bandlimited saw with frozen moving complex filter response, PCM and mono320kbps libmp3lame roundtrip.',
                    positive_control='Two predicted44.1k first-fold tones per eligible note injected at -60dB relative to H1 after filtering; PCM and MP3.'),
        groups=groups,
        analysis_revision='v2: v1 was exploratory; add the necessary interior-local-maximum check after finding alternate-rate candidate windows landed on unrelated rising flanks. Same rule applied to every hypothesis and synthetic/codec control. Add optional hash-verified frozen-engine comparison.',
        limits=['A source that is bandlimited or oversampled can hide aliases at any internal rate.',
                'The recorded PCM rate does not identify an oscillator or DSP rate.',
                'Classic Saw only; no conclusion about SuperSaw.',
                'Original MP3 encoder, capture clock accuracy and any undocumented processing are unknown.',
                'Residual peaks can include moving-filter sidebands, oscillator modulation, preceding-note tails and codec artifacts.',
                'Background prominence is a diagnostic threshold, not a statistical confidence interval.'])
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({g['id']:g['summary'] for g in groups},indent=2))


if __name__=='__main__':main()
