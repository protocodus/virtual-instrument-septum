#!/usr/bin/env python3
"""Compare effective cutoff trajectories and independent Q100 spectral ridges.

Train only the formal Q0 estimator's four time points on MIDI note 36; new
time points and all other notes are holdouts. Unknown patch/controller curves
mean this does not identify a raw envelope table or justify a DSP change.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
import numpy as np
from scipy.fft import rfft, rfftfreq
from scipy.io import wavfile
from scipy.optimize import least_squares
from scipy.signal import find_peaks

from analyze_deepsonic_filter import CATALOG, measure, fit_cutoff

MODELS = {
    'linear_log_cutoff': (lambda p,t: p[0]+p[1]*t,
                         [2.1,-3.5], [-5,-30], [5,0]),
    'exponential_log_cutoff': (lambda p,t: p[0]+p[1]*np.exp(-t/p[2]),
                             [0,2.5,.4], [-5,0,.02], [2,12,10]),
    'exponential_hz_with_floor': (lambda p,t: np.log(p[0]+p[1]*np.exp(-t/p[2])),
                                [1,8,.2], [.001,.001,.02], [10,100,10]),
    'linear_hz': (lambda p,t: np.log(np.maximum(p[0]+p[1]*t,.001)),
                  [8,-17], [.1,-50], [30,0]),
}
EXTRA_TIMES = (.14,.22,.30,.38)


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ridge(y,sr,center,width,f0):
    a,b=round((center-width/2)*sr),round((center+width/2)*sr)
    x=y[a:b].astype(float)
    x=(x-x.mean())*np.hanning(len(x))
    fft_size=32768
    spectrum=np.abs(rfft(x,fft_size))
    frequencies=rfftfreq(fft_size,1/sr)
    peaks=find_peaks(spectrum)[0]
    peaks=peaks[(frequencies[peaks]>1.3*f0)&(frequencies[peaks]<10*f0)]
    if len(peaks)==0:raise ValueError('No resonance-region spectral peak')
    ordered=sorted(peaks,key=lambda p:spectrum[p],reverse=True)
    peak=ordered[0]
    logs=np.log(np.maximum(spectrum[peak-1:peak+2],1e-30))
    adjustment=.5*(logs[0]-logs[2])/(logs[0]-2*logs[1]+logs[2])
    frequency=(peak+np.clip(adjustment,-.5,.5))*sr/fft_size
    dominance=None if len(ordered)<2 else float(20*np.log10(spectrum[peak]/spectrum[ordered[1]]))
    return dict(frequency_hz=float(frequency),frequency_over_f0=float(frequency/f0),
                competing_peak_margin_db=dominance,
                isolated_peak=dominance is None or dominance>=6,
                # This is a spectral ridge. A driven nonlinear resonator can
                # lock to source harmonics, so it is not an exact cutoff.
                nearest_source_harmonic=int(round(frequency/f0)))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources',type=Path,required=True)
    parser.add_argument('--filter-results',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    # Independent chirp with known instantaneous frequency at the center.
    time=np.arange(44100)/44100-.5
    signal=np.sin(2*np.pi*(400*time-500*time*time))
    sanity=ridge(signal,44100,.5,.04,65.40639132514966)
    if abs(sanity['frequency_hz']-400)>1:
        raise ValueError('Synthetic spectral-ridge control failed')
    args.output.mkdir(parents=True,exist_ok=False)
    formal=json.loads(args.filter_results.read_text())
    nominal=[r for r in formal['models']['rounded_candidate']['windows']
             if r['shift']==0 and r['width']==.08]
    notes=sorted({(r['on'],r['note']) for r in nominal})
    rows=[]
    sources={}
    source_records=[]
    catalog=json.loads(CATALOG.read_text())['assets']
    def decode(slope,resonance):
        filename=f'roland_sh-201_-_filter_demo_-_lpf{slope}_q{resonance:03d}.mp3'
        record=next(a for a in catalog if Path(a['path']).name==filename)
        original=args.sources/filename
        if sha(original)!=record['sha256']:
            raise ValueError(f'Changed original reference: {filename}')
        wav=args.output/filename.replace('.mp3','.wav')
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin',
                        '-i',str(original),'-c:a','pcm_f32le',str(wav)],check=True)
        source_records.append(dict(filename=filename,url=record['url'],sha256=record['sha256'],
                                   decoded_filename=wav.name,decoded_sha256=sha(wav)))
        return wav
    for r in nominal:
        f0=440*2**((r['note']-69)/12)
        rows.append(dict(**r,fundamental_hz=f0,cutoff_over_f0=r['cutoff_hz']/f0,
                         role='training' if r['training'] else 'note_holdout'))
    ridges=[]
    for slope in (12,24):
        q0_path=decode(slope,0)
        q100_path=decode(slope,100)
        sr,q0=wavfile.read(q0_path)
        sr100,q100=wavfile.read(q100_path)
        if sr!=44100 or sr100!=44100 or q0.ndim!=1 or q100.ndim!=1:
            raise ValueError('Expected 44.1 kHz mono hardware decodes')
        for path in (q0_path,q100_path):sources[path.name]=sha(path)
        for on,note in notes:
            f0=440*2**((note-69)/12)
            for offset in EXTRA_TIMES:
                measured=measure(q0,sr,on+offset,.08,f0)
                if measured['fit_residual_power']>.01:
                    raise ValueError('New Q0 window is not sufficiently explained by harmonics')
                measured['fundamental_hz']=f0
                fitted=fit_cutoff(measured,[1.2]*(slope//12))
                rows.append(dict(slope=slope,on=on,note=note,offset=offset,width=.08,shift=0,
                    fundamental_hz=f0,cutoff_over_f0=fitted['cutoff_hz']/f0,
                    role='time_holdout' if on==1.5 else 'note_and_time_holdout',
                    harmonic_fit_residual_power=measured['fit_residual_power'],**fitted))
            for offset in sorted({r['offset'] for r in nominal}|set(EXTRA_TIMES)):
                for width in (.03,.04,.05):
                    ridges.append(dict(slope=slope,on=on,note=note,offset=offset,width=width,
                        **ridge(q100,sr,on+offset,width,f0)))
    train=[r for r in rows if r['role']=='training']
    t=np.array([r['offset'] for r in train]); y=np.log([r['cutoff_over_f0'] for r in train])
    candidates={}
    for name,(function,p0,low,high) in MODELS.items():
        fitted=least_squares(lambda p:function(p,t)-y,p0,bounds=(low,high),
                            xtol=1e-12,ftol=1e-12,gtol=1e-12,max_nfev=10000)
        error=lambda a,b:float(1200/np.log(2)*(a-b))
        comparisons=[dict(slope=r['slope'],on=r['on'],note=r['note'],offset=r['offset'],role=r['role'],
            predicted_cutoff_over_f0=float(np.exp(function(fitted.x,r['offset']))),
            error_cents=error(function(fitted.x,r['offset']),np.log(r['cutoff_over_f0']))) for r in rows]
        groups={}
        for role in sorted({r['role'] for r in comparisons}):
            e=[r['error_cents'] for r in comparisons if r['role']==role]
            groups[role]={'count':len(e),'rmse_cents':float(np.sqrt(np.mean(np.square(e)))),
                          'bias_cents':float(np.mean(e))}
        candidates[name]=dict(parameters=fitted.x.tolist(),summary=groups,observations=comparisons)
    for ridge_row in ridges:
        paired=next(r for r in rows if r['slope']==ridge_row['slope'] and r['on']==ridge_row['on']
                    and abs(r['offset']-ridge_row['offset'])<1e-6)
        ridge_row['q0_cutoff_over_f0']=paired['cutoff_over_f0']
        ridge_row['q100_ridge_vs_q0_cents']=float(1200*np.log2(
            ridge_row['frequency_over_f0']/paired['cutoff_over_f0']))
    slopes=[]
    for source in ('q0','q100'):
        for slope in (12,24):
            for width in ((.08,) if source=='q0' else (.03,.04,.05)):
                selected=[r for r in (rows if source=='q0' else ridges)
                          if r['slope']==slope and r['note']!=57 and r['width']==width]
                notes_summary=[]
                for on in sorted({r['on'] for r in selected}):
                    rates=[]
                    for early in (True,False):
                        part=[r for r in selected if r['on']==on and
                              (r['offset']<=.22 if early else r['offset']>=.26)]
                        values=np.log([r['cutoff_over_f0'] if source=='q0' else
                                       r['frequency_over_f0'] for r in part])
                        rates.append(float(np.polyfit([r['offset'] for r in part],values,1)[0]))
                    notes_summary.append(dict(on=on,early_log_rate=rates[0],late_log_rate=rates[1]))
                slopes.append(dict(source=source,slope=slope,width=width,notes=notes_summary,
                    median_early_log_rate=float(np.median([r['early_log_rate'] for r in notes_summary])),
                    median_late_log_rate=float(np.median([r['late_log_rate'] for r in notes_summary])),
                    every_note_flattens=all(r['late_log_rate']>r['early_log_rate'] for r in notes_summary)))
    result=dict(schema_version=1,status='effective trajectory experiment; no DSP changes',
        spectral_ridge_synthetic_control=sanity,local_log_rate_comparison=slopes,
        filter_results_sha256=sha(args.filter_results),analysis_sha256=sha(__file__),
        filter_estimator_sha256=sha(Path(__file__).with_name('analyze_deepsonic_filter.py')),
        source_sha256=sources,original_sources=source_records,
        training='MIDI 36 at 1.5s; Q0 at 100,180,260,340ms only',
        cutoff_observations=rows,models=candidates,q100_ridges=ridges,
        limits=['Raw patch controls and system state are unavailable; local cutoff is a nuisance estimate.',
                'Envelope control shape cannot be separated from its mapping into cutoff in this dataset.',
                'Single-note gates are under 0.44s; an inferred asymptote is extrapolation.',
                'Q100 is a driven nonlinear resonance recording; spectral maxima need not equal the natural cutoff.',
                'The effective shape comparison is conditional on the adopted zero-resonance transfer model.'])
    (args.output/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({name:{'parameters':v['parameters'],'summary':v['summary']} for name,v in candidates.items()},indent=2))


if __name__=='__main__':main()
