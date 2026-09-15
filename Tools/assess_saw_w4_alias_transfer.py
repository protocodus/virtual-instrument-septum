#!/usr/bin/env python3
"""Frozen eight-pitch alias transfer check; no source fitting or model selection."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('VECLIB_MAXIMUM_THREADS','1')
import numpy as np
from scipy.io import wavfile
import analyze_deepsonic_saw_aliases as alias

ROOT=Path(__file__).resolve().parents[1]
PRIOR=ROOT/'Docs/fidelity/source-audits/deepsonic-saw-aliases-2026-09-15.json'
SR=44100

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pin(p,h=None):
    p=Path(p).resolve();actual=sha(p)
    if h and actual!=h:raise ValueError('Hash mismatch: '+str(p))
    return {'path':str(p),'sha256':actual}
def save(p,v):Path(p).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def index(m):return {x['parent_harmonic']:x for x in m['tested_alias_lines'] if x['rate_hypothesis_hz']==44100}
def summary(rows):
    result={}
    for name in ('production','w4'):
        delta=np.array([r[name]['relative_h1_db']-r['hardware']['relative_h1_db'] for r in rows])
        result[name]={'mask_lines':len(rows),'resolved_lines':sum(r[name]['passes_line_threshold'] for r in rows),
            'search_maximum_proxy_rms_db':float(np.sqrt(np.mean(delta**2))) if len(rows) else None,
            'search_maximum_proxy_median_signed_db':float(np.median(delta)) if len(rows) else None}
    result['absolute_error_improved_lines']=sum(abs(r['w4']['relative_h1_db']-r['hardware']['relative_h1_db'])<abs(r['production']['relative_h1_db']-r['hardware']['relative_h1_db']) for r in rows)
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-root',type=Path,required=True)
    parser.add_argument('--production-root',type=Path,default=ROOT/'build-fidelity/envelope-hypothesis/dry-v2/audio/production')
    parser.add_argument('--sources',type=Path,default=ROOT/'build-fidelity/deepsonic')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    previous=json.loads(PRIOR.read_text());candidate_manifest=json.loads((args.candidate_root/'manifest.json').read_text())
    pin(alias.__file__,previous['script_sha256'])
    selection=pin(candidate_manifest['selection']['path'],candidate_manifest['selection']['sha256'])
    models={}
    for slope in (12,24):
        models[slope]={name:pin(root/f'lp{slope}/candidate.wav') for name,root in [('production',args.production_root),('w4',args.candidate_root)]}
        prior_result=json.loads((ROOT/f'build-fidelity/saw-w4-engine-assessment/candidate-01/results.json').read_text())
        for name in models[slope]:
            expected=next(s for s in prior_result['slopes'] if s['slope']==slope)['models'][name]['provenance']['wav']['sha256']
            if models[slope][name]['sha256']!=expected:raise ValueError('Frozen measured vector changed')
    source=[pin(args.sources/Path(s['path']).name,s['sha256']) for s in previous['sources']]
    protocol={'stage':'frozen before new alias extraction; no model/phase/gain/frequency fit',
        'prior':pin(PRIOR),'tool':pin(__file__),'measurement_helper':pin(alias.__file__),
        'source_pins':source,'selection':selection,'models':models,
        'notes':previous['notes'],'offsets':previous['window_offsets_seconds'],'width_seconds':.08,
        'mask':'exact per-slope original-hardware-qualified first descending44.1k branch IDs; LP12=200 and LP24=168 line-windows',
        'primary_alignment':'both production and W4: hardware[a:b] versus engine[a-1406:b-1406,0]; fixed prior gains cancel in relativeH1 observations',
        'historical_reproduction':'Old production audit used float32 stereo mean and measure(onset-.035+93/44100,offset), approximately-1450.5 samples. Reproduce separately without silently equating that convention to-1406.',
        'train_status':'MIDI91 excluded from coefficient-transfer aggregates; all eight pitches were viewed before this check; not blind validation',
        'retention':'All original mask bins retained, including below-threshold candidate maxima; aggregate dB errors are search-maximum proxies, not resolved physical-line error when thresholds fail.',
        'summary_groups':['all frozen windows','excluding note91','each frozen note/offset'],
        'forbidden':['coefficient changes','phase/lag/gain selection','new windows','candidate-selected masks']}
    save(out/'protocol-before-measurement.json',protocol)
    result={'protocol':protocol,'slopes':[],'hardware_equivalence':'not_established'}
    decoder=Path(shutil.which('ffmpeg')).resolve();result['decoder']=pin(decoder)
    for slope in (12,24):
        mp3=args.sources/f'roland_sh-201_-_filter_demo_-_lpf{slope}_q000.mp3'
        decoded=out/f'hardware-lp{slope}.wav';command=[str(decoder),'-hide_banner','-loglevel','error','-nostdin','-i',str(mp3),'-c:a','pcm_f32le',str(decoded)]
        subprocess.run(command,check=True)
        sr,h=wavfile.read(decoded);assert sr==SR and h.ndim==1
        ys={};old=None
        for name,p in models[slope].items():
            rate,y=wavfile.read(p['path']);assert rate==SR and y.dtype==np.float32 and y.ndim==2 and np.isfinite(y).all()
            ys[name]=y[:,0]
            if name=='production':old=y.mean(axis=1)
        frozen=next(r for r in previous['engine_comparisons'] if r['id']==f'engine-production-lp{slope}')['measurements']
        assert len(frozen)==(200 if slope==12 else 168)
        all_rows=[];windows=[];max_hardware_error=0.;max_historical_error=0.
        for note in previous['notes']:
            for offset in previous['window_offsets_seconds']:
                a=round((note['on']+offset-.04)*SR);b=round((note['on']+offset+.04)*SR)
                assert b-a==3528
                hw=index(alias.measure(h,note['on'],note['note'],offset))
                history=index(alias.measure(old,note['on']-.035+93/SR,note['note'],offset))
                current={name:index(alias.measure(y[a-1406:b-1406],.04,note['note'],0)) for name,y in ys.items()}
                mask=[r for r in frozen if r['note']==note['note'] and r['offset_seconds']==offset]
                rows=[]
                for saved in mask:
                    k=saved['parent_harmonic'];x=hw[k]
                    max_hardware_error=max(max_hardware_error,abs(x['relative_h1_db']-saved['hardware_db']))
                    max_historical_error=max(max_historical_error,abs(history[k]['relative_h1_db']-saved['model_db']))
                    if not x['passes_line_threshold']:raise ValueError('Original mask eligibility changed')
                    rows.append({'note':note['note'],'offset_seconds':offset,'parent_harmonic':k,'expected_hz':saved['frequency_hz'],
                        'hardware':x,'production':current['production'][k],'w4':current['w4'][k],
                        'historical_production':history[k],'historical_saved':saved})
                all_rows+=rows
                windows.append({'note':note['note'],'offset_seconds':offset,'hardware_samples':[a,b],'engine_samples':[a-1406,b-1406],
                    'hardware_float64_sha256':hashlib.sha256(h[a:b].astype('<f8').tobytes()).hexdigest(),
                    'summary':summary(rows),'lines':rows})
        if max_hardware_error>1e-9 or max_historical_error>1e-9:raise ValueError('Historical source/baseline extraction did not reproduce')
        data={'slope':slope,'hardware_decoded':pin(decoded),'decode_command':command,
            'historical_reproduction_max_hardware_db_difference':max_hardware_error,
            'historical_reproduction_max_model_db_difference':max_historical_error,
            'all_windows':summary(all_rows),'excluding_note91':summary([r for r in all_rows if r['note']!=91]),'windows':windows}
        result['slopes'].append(data);save(out/'results.json',result)
        print(slope,json.dumps(data['excluding_note91']),flush=True)
    print(out/'results.json',flush=True)
if __name__=='__main__':main()
