#!/usr/bin/env python3
"""Check Juicy Fat separability and Sequence Bs source consistency.

Uses freshly decoded, hash-verified originals from the inventory tool. No
cutoff is fitted. Juicy Fat's conditioning test is deliberately optimistic:
Upper contributes only odd pulse harmonics, and fine tune is assumed exact.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import numpy as np
from scipy.io import wavfile
from scipy.optimize import minimize_scalar
from scipy.signal import stft
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def window(y,sr,center,width):
    start,end=round((center-width/2)*sr),round((center+width/2)*sr)
    if start<0 or end>len(y):
        raise ValueError('Window outside recording')
    return y[start:end]


def conditioning(sr,width,frequency,ramp,offsets=(-4,5)):
    t=(np.arange(round(width*sr))-(round(width*sr)-1)/2)/sr
    u=t/(width/2)
    families=[('upper',frequency,h) for h in range(1,12,2)]
    families += [('lower_saw1',frequency*2**(offsets[0]/1200),h) for h in range(1,13)]
    families += [('lower_saw2',frequency*2*2**(offsets[1]/1200),h) for h in range(1,7)]
    columns=[np.ones(len(t)),u]
    for name,f,h in families:
        co,si=np.cos(2*np.pi*f*h*t),np.sin(2*np.pi*f*h*t)
        columns.extend((co,si))
        if ramp=='all' or (ramp=='lower_only' and name!='upper'):
            columns.extend((u*co,u*si))
    matrix=np.column_stack(columns)
    singular=np.linalg.svd(matrix,compute_uv=False)
    return dict(width_seconds=width,independent_linear_complex_ramps=ramp,
                lower_fine_offsets_cents=list(offsets),
                samples=len(t),columns=matrix.shape[1],
                condition_number=float(singular[0]/singular[-1]),
                below_predeclared_condition_limit_100=bool(singular[0]/singular[-1]<100))


def band_energy(y,sr,center,width):
    x=window(y,sr,center,width)
    spectrum=abs(np.fft.rfft((x-x.mean())*np.hanning(len(x)),262144))**2
    f=np.fft.rfftfreq(262144,1/sr)
    def energy(lo,hi):
        return float(spectrum[(f>=lo)&(f<hi)].sum()/max(spectrum.sum(),1e-30))
    return dict(center_seconds=center,width_seconds=width,
                rms=float(np.sqrt(np.mean(x*x))),peak_frequency_hz=float(f[np.argmax(spectrum)]),
                power_below_1khz=energy(0,1000),power_1_to_8khz=energy(1000,8000),
                power_8_to_16khz=energy(8000,16000),power_above_16khz=energy(16000,sr/2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True,help='new directory')
    args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    inventory=json.loads(args.inventory.read_text())
    sources=[];audio={}
    for item in inventory['decoded_audio']:
        if sha(item['path'])!=item['sha256']:
            raise ValueError('Decoded audio identity changed')
        sr,y=wavfile.read(item['path'])
        if sr!=44100 or y.dtype.kind!='f' or y.shape[1]!=2:
            raise ValueError('Expected floating 44.1 kHz stereo')
        mono=y.astype(float).mean(axis=1)
        audio[item['id']]=(sr,mono)
        sources.append(item)
    sr,y=audio['bass-07']
    c,w=.23,.12
    x=window(y,sr,c,w);t=np.arange(len(x))/sr;hann=np.hanning(len(x))
    fit=minimize_scalar(lambda f:-abs(np.dot(x*hann,np.exp(-2j*np.pi*f*t))),
                        bounds=(62,68),method='bounded')
    f0=float(fit.x)
    condition=[conditioning(sr,w,f0,ramp) for w in (.08,.12,.20)
               for ramp in ('none','lower_only','all')]
    juicy=dict(opening_window_center_seconds=c,opening_window_width_seconds=w,
        dominant_fundamental_peak_hz=f0,
        physical_note_interpretation='Approximately C2 sounding, conditional on tuning; Upper coarse -12 implies played C3. Original MIDI is unavailable.',
        assumed_family_offsets_cents=[0,-4,1205],
        upper_harmonics_assumed=list(range(1,12,2)),lower_saw1_harmonics=list(range(1,13)),
        lower_saw2_harmonics=list(range(1,7)),
        nearest_upper_lower_saw1_separation_hz=[dict(harmonic=h,hz=float(h*f0*(1-2**(-4/1200)))) for h in (1,3,5)],
        conditioning=condition,
        separated_frequency_matrix_controls=[conditioning(sr,w,f0,'lower_only',(-50,50))
                                              for w in (.08,.12,.20)],
        verdict='Reject independent time-local layer amplitudes: even holding Upper amplitude/phase constant, all moving-Lower models exceed condition 100. Constant-amplitude models for every layer do not allow the moving Lower filter.',
        cutoff_estimate_hz=None)
    sr,y=audio['bass-08']
    sequence=dict(windows=[band_energy(y,sr,c,w) for c,w in ((.16,.08),(.25,.08),(.40,.08),
                              (1.,.08),(2.,.08),(3.,.08),(4.,.08),(6.,.08),(10.,.08))],
        verdict='Reject the opening as a static bank-patch filter measurement: energy distribution is inconsistent with an ordinary unmodulated sine-plus-square LP12 at maximum cutoff. Unknown controllers, system effects or patch revision can explain the discrepancy; no cause is identified.',
        cutoff_estimate_hz=None)
    figure,axes=plt.subplots(2,1,figsize=(12,7),layout='constrained')
    for ax,(identifier,title,maxfreq) in zip(axes,(('bass-07','Juicy Fat: first 0.6 s',2000),
                                                ('bass-08','Sequence Bs: first 6 s',18000))):
        sr,y=audio[identifier]
        duration=.6 if identifier=='bass-07' else 6
        # Keep context past the displayed endpoint; truncating there invents
        # a broadband edge in the last displayed FFT windows.
        f,t,z=stft(y[:round((duration+.1)*sr)],sr,nperseg=4096,noverlap=3840)
        ax.pcolormesh(t,f,20*np.log10(abs(z)+1e-10),vmin=-85,vmax=-15,cmap='magma',shading='auto')
        ax.set(xlim=(0,duration),ylim=(0,maxfreq),xlabel='Seconds in original recording',ylabel='Hz',title=title)
    figure.savefig(out/'openings.png',dpi=150);plt.close(figure)
    result=dict(schema_version=1,status='source feasibility audit; no DSP changes',
        tool_sha256=sha(__file__),inventory_sha256=sha(args.inventory),sources=sources,
        method='Hann-window peak/energy diagnostics; unweighted full-sample joint quadrature condition number with optional independent linear complex-amplitude ramps. No layer amplitudes or cutoff fit retained after conditioning failure.',
        juicy_fat=juicy,sequence_bass=sequence,
        limits=['No original performance MIDI/controllers/system settings or exact recording patch revision.',
                'MP3, output path and processing may color spectra.',
                'Nominal fine tune cents and symmetric pulse are optimistic assumptions, not isolated hardware measurements.',
                'Conditioning is necessary, not sufficient for separation; low condition alone does not authenticate any source model.'])
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(juicy_fat=juicy,sequence_bass=sequence),indent=2))


if __name__=='__main__':
    main()
