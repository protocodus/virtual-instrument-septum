#!/usr/bin/env python3
"""Bound nominal-f0 / capture-clock bias in frozen Saw alias measurements.

No oscillator coefficients, model phase/gain, raw patch or DSP is fitted. Local
frequency measurements are source-only diagnostics. Synthetic tones keep exact
known amplitudes while independently changing oscillator pitch or capture clock.
"""
import argparse
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np
from scipy.io import wavfile
from scipy.optimize import minimize_scalar
import analyze_deepsonic_saw_aliases as aliases
import fit_high_note_saw_asymmetric_kernels as kernels

ROOT = Path(__file__).resolve().parents[1]
SR, SIZE = aliases.SR, 3528
PPM = (-100., -50., 0., 50., 100.)
PHASES = (.137, .713)
BASELINE = ROOT/"Docs/fidelity/source-audits/deepsonic-saw-asymmetric-kernels-2026-09-15.json"
INVARIANCE = ROOT/"Docs/fidelity/source-audits/deepsonic-high-note-invariance-2026-09-15.json"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(x):
    return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()


@lru_cache(maxsize=64)
def basis(base):
    t=(np.arange(SIZE)-(SIZE-1)/2)/SR
    u=t/(aliases.WIDTH/2)
    columns=[np.ones(SIZE),u,u*u]
    for h in range(1,int(20000/base)+1):
        co,si=np.cos(2*np.pi*h*base*t),np.sin(2*np.pi*h*base*t)
        columns.extend((co,si,u*co,u*si,u*u*co,u*u*si))
    matrix=np.column_stack(columns)
    left,singular,right=np.linalg.svd(matrix,full_matrices=False)
    return matrix,(right.T/singular)@left.T,float(singular[0]/singular[-1])


def local_peak(x, expected, half_width):
    t=(np.arange(len(x))-(len(x)-1)/2)/SR
    hann=np.hanning(len(x))
    def amplitude(f):
        return 2*abs(np.dot(x*hann,np.exp(-2j*np.pi*f*t)))/hann.sum()
    fit=minimize_scalar(lambda f:-amplitude(f),bounds=(expected-half_width,expected+half_width),
                        method='bounded',options={'xatol':1e-8})
    return dict(hz=float(fit.x),offset_hz=float(fit.x-expected),amplitude=float(amplitude(fit.x)),
                nominal_amplitude=float(amplitude(expected)),at_boundary=bool(abs(fit.x-expected)>half_width*.99))


def measure(x,note,frequencies,base=None,refine=False):
    nominal=aliases.f0(note)
    matrix,inverse,condition=basis(nominal if base is None else base)
    coefficient=inverse@x
    residual=x-matrix@coefficient
    h1=float(np.hypot(coefficient[3],coefficient[4]))
    hann=np.hanning(SIZE)
    spectrum=2*abs(np.fft.rfft(residual*hann,aliases.NFFT))/hann.sum()
    grid=np.fft.rfftfreq(aliases.NFFT,1/SR)
    mask=aliases.distance_to_harmonic(grid,nominal)>aliases.GUARD
    rows=[]
    for h,expected in frequencies:
        indices=np.flatnonzero((abs(grid-expected)<=6)&mask)
        k=indices[np.argmax(spectrum[indices])]
        line=dict(parent_harmonic=h,expected_hz=expected,peak_hz=float(grid[k]),peak_offset_hz=float(grid[k]-expected),
                  relative_h1_db=float(20*np.log10(max(spectrum[k],1e-20)/h1)),
                  interior_peak=bool(k>indices[0] and k<indices[-1] and spectrum[k]>=spectrum[k-1] and spectrum[k]>=spectrum[k+1]))
        if refine:
            local=local_peak(residual,expected,6.)
            local['relative_h1_db']=float(20*np.log10(max(local['amplitude'],1e-20)/h1))
            local['peak_over_nominal_frequency_db']=float(20*np.log10(max(local['amplitude'],1e-20)/max(local['nominal_amplitude'],1e-20)))
            line['continuous_peak_diagnostic']=local
        rows.append(line)
    return dict(fitted_h1_amplitude=h1,harmonic_basis_hz=nominal if base is None else base,
                harmonic_basis_condition=condition,lines=rows),coefficient


def planted(note,coefficients,frequencies,truth,ppm,kind,phase,positive):
    t=(np.arange(SIZE)-(SIZE-1)/2)/SR
    alpha=1+ppm/1e6
    base=aliases.f0(note)
    h1=np.hypot(coefficients[3],coefficients[4])
    y=np.zeros(SIZE)
    count=(len(coefficients)-3)//6
    # Stationary harmonic magnitudes are measured from the original LP12 window.
    # Two fixed phase patterns stress leakage without choosing a favorable phase.
    for h in range(1,count+1):
        amplitude=np.hypot(coefficients[3+6*(h-1)],coefficients[4+6*(h-1)])
        y+=amplitude*np.cos(2*np.pi*(h*base*alpha*t+phase*h)+.17*h)
    if positive:
        for (h,expected),dbc in zip(frequencies,truth):
            f=(44100-h*base*alpha) if kind=='oscillator_pitch' else expected*alpha
            y+=h1*10**(dbc/20)*np.cos(2*np.pi*(f*t+phase*h)+.31*h)
    return y


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sources',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    previous=json.loads(BASELINE.read_text())
    if previous['script_sha256']!=sha(kernels.__file__):
        raise ValueError('Frozen kernel fitter changed')
    for name,expected in previous['dependency_sha256'].items():
        if sha(ROOT/'Tools'/name)!=expected:raise ValueError('Frozen helper changed: '+name)
    catalog_path=ROOT/'Docs/fidelity/source-audits/deepsonic-acquisition-2026-09-15.json'
    catalog=json.loads(catalog_path.read_text())
    if sha(catalog_path)!=previous['catalog_sha256']:raise ValueError('Source catalog changed')
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:raise ValueError('ffmpeg required')
    sources=[];audio={}
    for slope in (12,24):
        name=f'roland_sh-201_-_filter_demo_-_lpf{slope}_q000.mp3'
        asset=next(v for v in catalog['assets'] if Path(v['path']).name==name)
        source=a.sources/name
        if sha(source)!=asset['sha256']:raise ValueError('Original recording changed')
        wav=out/f'hardware-lp{slope}.wav'
        command=[ffmpeg,'-hide_banner','-loglevel','error','-nostdin','-i',str(source.resolve()),'-c:a','pcm_f32le',str(wav)]
        subprocess.run(command,check=True)
        rate,y=wavfile.read(wav)
        if rate!=SR or y.ndim!=1 or not np.isfinite(y).all():raise ValueError('Unexpected source decode')
        audio[slope]=y
        sources.append(dict(original=asset,decode_command=command,decoded_sha256=sha(wav)))
    midi=a.sources/Path(previous['original_midi']['path']).name
    if sha(midi)!=previous['original_midi']['sha256']:raise ValueError('Original MIDI changed')
    model=next(m for m in previous['models'] if m['id']=='asymmetric-W4')
    result=dict(schema_version=1,status='Bounded estimator-frequency diagnostic; no candidate refit or DSP change.',
        baseline_sha256=sha(BASELINE),invariance_sha256=sha(INVARIANCE),catalog_sha256=sha(catalog_path),
        tool_sha256=sha(__file__),alias_detector_sha256=sha(aliases.__file__),
        sources=sources,original_midi=previous['original_midi'],
        decoder=dict(path=ffmpeg,sha256=sha(ffmpeg),version=subprocess.check_output([ffmpeg,'-version'],text=True).splitlines()[0]),
        protocol=dict(passages=[s['passage'] for s in model['scores']],source_frequency_measurement='Independent H1/H2/H3 Hann peaks within +/-3Hz; descriptive local phase/frequency, not hardware oscillator tuning or capture-clock estimation.',
            source_sensitivity='Same LP12 hardware-only eligible line mask, expected aliases and +/-6Hz local peak search; only harmonic subtraction carrier changes from nominal to local H1 peak. LP24 uses the same LP12 mask.',
            control_ppm=list(PPM),control_phases_cycles=list(PHASES),
            control_amplitudes='Original-window H1 and harmonic magnitudes plus all LP12-qualified descending alias levels; fixed throughout every pitch/clock control. Stationary amplitudes, no MP3 roundtrip.',
            control_frequencies='Pitch-only: harmonics h*f0*alpha, aliases44100-h*f0*alpha. Capture-clock-only: every harmonic and alias frequency multiplied by alpha. Both measured by unchanged nominal detector.',
            controls='Positive planted aliases and alias-free negative controls at all pitch/clock/phase combinations; compare detector output with known planted dB/H1; no kernel/gain/phase fit.',
            limits='Source Hann peaks include moving-filter phase. Finite-window/source-derived synthetic controls bound this nominal-frequency estimator confound, not unknown analog/digital capture filtering, original codec history or all possible nonstationarity.'),
        original_windows=[],controls=[])
    for score in model['scores']:
        passage=score['passage'];note=passage['note']
        frequencies=[(r['parent_harmonic'],r['expected_hz']) for r in score['aliases']['lines']]
        truth=[r['hardware_dbc'] for r in score['aliases']['lines']]
        nominal=aliases.f0(note)
        for slope in (12,24):
            x=audio[slope][passage['start_sample']:passage['end_sample']].astype(float)
            if len(x)!=SIZE:raise ValueError('Source coverage changed')
            if slope==12 and digest(x)!=passage['sample_sha256']:raise ValueError('Frozen source samples changed')
            peaks=[dict(harmonic=h,**local_peak(x,h*nominal,3.)) for h in (1,2,3)]
            reference,coefficients=measure(x,note,frequencies,refine=True)
            refined,_=measure(x,note,frequencies,base=peaks[0]['hz'],refine=True)
            if slope==12:
                prior=np.array(truth)
                current=np.array([r['relative_h1_db'] for r in reference['lines']])
                if np.max(abs(prior-current))>1e-8:raise ValueError('Nominal detector reproduction differs')
                original_coefficients=coefficients
            changes=[b['relative_h1_db']-a0['relative_h1_db'] for a0,b in zip(reference['lines'],refined['lines'])]
            result['original_windows'].append(dict(slope=slope,passage=passage,sample_sha256=digest(x),
                local_harmonic_peaks=peaks,local_h1_shift_cents=float(1200*np.log2(peaks[0]['hz']/nominal)),
                local_h1_shift_ppm=float((peaks[0]['hz']/nominal-1)*1e6),nominal=reference,local_h1_basis=refined,
                basis_change_db=changes,basis_change_max_absolute_db=float(np.max(abs(np.array(changes))))))
        for kind in ('oscillator_pitch','capture_clock'):
            for ppm in PPM:
                for phase in PHASES:
                    row=dict(passage=passage,kind=kind,ppm=ppm,phase_cycles=phase,lines=[])
                    positive=planted(note,original_coefficients,frequencies,truth,ppm,kind,phase,True)
                    negative=planted(note,original_coefficients,frequencies,truth,ppm,kind,phase,False)
                    plus,_=measure(positive,note,frequencies)
                    minus,_=measure(negative,note,frequencies)
                    for expected,pp,nn in zip(truth,plus['lines'],minus['lines']):
                        h=pp['parent_harmonic'];f=pp['expected_hz']
                        planted_hz=44100-h*nominal*(1+ppm/1e6) if kind=='oscillator_pitch' else f*(1+ppm/1e6)
                        row['lines'].append(dict(parent_harmonic=h,nominal_hz=f,planted_hz=planted_hz,planted_dbc=expected,
                            recovered_dbc=pp['relative_h1_db'],error_db=pp['relative_h1_db']-expected,
                            peak_hz=pp['peak_hz'],interior_peak=pp['interior_peak'],negative_residual_dbc=nn['relative_h1_db'],
                            negative_minus_planted_db=nn['relative_h1_db']-expected))
                    result['controls'].append(row)
        print(note,passage['offset_seconds'],'source/controls complete',flush=True)
    (out/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(out/'results.json')


if __name__=='__main__':main()
