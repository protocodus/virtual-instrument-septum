#!/usr/bin/env python3
"""Frozen-bus HF-unity diagnostic; no patch, performance or output-gain fit.

Only the HF feedback shelf gain argument changes. Its filter coefficient and
state updates remain. Original replay and neutral Cotton byte identity must
pass before any hardware comparison. No production source is edited.
"""
import argparse
import difflib
import json
import os
from pathlib import Path
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from decompose_reverb_tail_buses import ROOT, SR, sha, save, replace_once, difference
from assess_reverb_tail_buses import hardware_input, stereo_levels, read_raw
from analyze_club_reverb_decay import window as old_window

EDGES=(80,160,320,640)


def measure_window(x):
    x=np.asarray(x,float); n=len(x); hann=np.hanning(n); result={}
    for name,z in dict(stereo=x,mid=np.mean(x,axis=1)[:,None],side=((x[:,0]-x[:,1])/2)[:,None]).items():
        ft=np.fft.rfft(z*hann[:,None],axis=0)
        power=np.mean(abs(ft)**2,axis=1)/(n*np.sum(hann*hann))
        power[1:-1 if n%2==0 else None]*=2
        freq=np.fft.rfftfreq(n,1/SR)
        bands=np.array([power[(freq>=a)&(freq<b)].sum() for a,b in zip(EDGES[:-1],EDGES[1:])])
        result[name]=dict(broadband_dbfs=float(10*np.log10(max(np.mean(z*z),1e-30))),
            band_dbfs=(10*np.log10(np.maximum(bands,1e-30))).tolist(),
            band_power_fractions=(bands/max(power.sum(),1e-30)).tolist(),
            band_level_guard=(bands>=1e-12).tolist(),band_fraction_guard=(bands>=power.sum()*.001).tolist())
    return result


def summarize(rows):
    result={}
    for channel in ('stereo','mid','side'):
        result[channel]={}
        for label,index in [('broadband',None),('80-160',0),('160-320',1),('320-640',2)]:
            def val(r,model):
                q=r[model][channel];return q['broadband_dbfs'] if index is None else q['band_dbfs'][index]
            values={m:np.array([val(r,m)for r in rows])for m in ('hardware','original','hf_unity')}
            ref=values['hardware'];models={}
            for m in ('original','hf_unity'):
                error=values[m]-ref
                models[m]=dict(mean_error_db=float(error.mean()),rms_error_db=float(np.sqrt(np.mean(error**2))),
                    maximum_absolute_error_db=float(max(abs(error))),errors_db=error.tolist())
            eligible=[True if index is None else r['hardware'][channel]['band_level_guard'][index] and r['hardware'][channel]['band_fraction_guard'][index]for r in rows]
            result[channel][label]=dict(windows=len(rows),hardware_eligible_windows=sum(eligible),
                all_hardware_eligible=all(eligible),eligibility=eligible,models=models,
                hf_unity_minus_original_mean_db=float((values['hf_unity']-values['original']).mean()),
                hf_unity_minus_original_error_rmse_db=models['hf_unity']['rms_error_db']-models['original']['rms_error_db'])
    return result


def render(binary,syx,bus,dst,unity):
    command=[str(binary),str(syx),str(bus),str(dst),'-1','full','none','-1','1.0']
    env=os.environ.copy();env.pop('SEPTUM_AUDIT_CAPTURE',None);env['SEPTUM_AUDIT_HF_UNITY']='1' if unity else '0'
    p=subprocess.run(command,check=True,capture_output=True,text=True,env=env)
    m=json.loads(p.stdout);y=read_raw(dst)
    if len(y)!=m['frames']:raise ValueError('Bad render coverage')
    return y,dict(command=command,environment_override=env['SEPTUM_AUDIT_HF_UNITY'],raw_sha256=sha(dst),**m)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--decomposition-run',type=Path,required=True);p.add_argument('--assessment',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run=a.decomposition_run.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    assessed=json.loads(a.assessment.read_text());original=json.loads((run/'results.json').read_text())
    if assessed['protocol']['decomposition_result_sha256']!=sha(run/'results.json') or assessed['decomposition_receipt']!=original:
        raise ValueError('Decomposition identity changed')
    prior_path=ROOT/'Docs/fidelity/source-audits/club-reverb-decay-protocol-2026-09-15.json'
    prior=json.loads(prior_path.read_text())
    if sha(prior_path)!='ccf98d8bb77949c76906da94ecb134d4da032c6b6d83c08276d475148524a2b4':raise ValueError('Old window protocol changed')
    for f,h in original['build']['files_sha256'].items():
        if sha(run/'builds'/f)!=h:raise ValueError('Frozen build changed: '+f)
    protocol=dict(status='Post-result mechanism ablation; not prospective blind validation or a shipping candidate.',
        original_decomposition_sha256=sha(run/'results.json'),assessment_sha256=sha(a.assessment),
        source_revision=original['build']['revision'],source_sha256=original['build']['original_source_sha256'],
        tool_sha256=sha(__file__),band_estimator_source_sha256=sha(ROOT/'Tools/analyze_club_reverb_decay.py'),
        hypothesis='Set only the HF feedback shelf gain argument to1; retain corner/coefficient and state updates, LF shelf, line feedback, geometry, input/output routing, limiter, native preset and bus history.',
        required_identity='Original replay equals all prior raw6-float outputs byte-for-byte. HF-unity Cotton equals original byte-for-byte because its exact preset already has neutral HF damping.',
        evidence_scope='Club first gap is the main conditional network check; Ambient is a short opening with a frozen alignment boundary, Cotton opening a neutral identity control. No full late hardware performance reconstruction.',
        gain_time_policy='Use existing frozen production-prefix gain and integer lag for both models. No candidate gain, fit, equalization, time multiplier, pole fit or phase selection.',
        supports={r['id']:[dict(hardware_samples=s['hardware_samples'],model_samples=s['samples'],requested_seconds=s['requested_hardware_seconds'])for s in r['public_support']]for r in assessed['cases']},
        windows=prior['window_specs'],bands_hz=list(EDGES),measurement='Same complete symmetric-Hann100/150/200ms windows with25ms hop wholly inside inherited supports. Unweighted broadband RMS; Hann one-sided band power. Add Mid to inherited Stereo/Side estimator; verify old channels match exactly. All rows retained; guards use only hardware >=−120dBFS and >=0.1% of its Hann power.',
        limitations='Feedback shelf unity changes phase/modal distribution as well as loss. It is not a monotonic bound on intermediate settings or a uniquely identified hardware gain. Existing patch/performance/capture uncertainty remains. Overlapping windows are not independent trials.')
    save(out/'protocol-before-build.json',protocol)
    build=out/'build';shutil.copytree(run/'builds/diagnostic',build)
    header=build/'Source/DSP/AuditBus.h';header.write_text(replace_once(header.read_text(),' std::int64_t frame=0,haltFrame=-1;',
        ' bool hfUnity=[](){const char*p=std::getenv("SEPTUM_AUDIT_HF_UNITY");return p && std::string(p)=="1";}();\n std::int64_t frame=0,haltFrame=-1;'))
    engine=build/'Source/DSP/SeptumEngine.cpp';old=engine.read_text()
    new=replace_once(old,'detail::reverbHighShelf (value, c.hfGain, c.hfCoeff, high)',
        'detail::reverbHighShelf (value, septum_audit::config().hfUnity ? 1.0 : c.hfGain, c.hfCoeff, high)')
    engine.write_text(new);(build/'hf-unity.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True))))
    binary=build/'EffectsReplay'
    command=['c++','-std=c++20','-O2','-fno-fast-math','-I'+str(build/'Source'),str(build/'EffectsReplay.cpp'),
        *[str(build/'Source/DSP'/n)for n in ('SeptumEngine.cpp','SeptumPresets.cpp','SeptumSysEx.cpp')],'-o',str(binary)]
    subprocess.run(command,check=True)
    manifest=dict(compile_command=command,files_sha256={str(p.relative_to(build)):sha(p)for p in build.rglob('*')if p.is_file()})
    save(out/'build-manifest.json',manifest)
    audio={};render_receipts={}
    for case in assessed['cases']:
        name=case['id'];folder=run/name;dst=out/name;dst.mkdir()
        base=next(c for c in original['cases']if c['id']==name)
        if sha(folder/'replay-buses.raw')!=base['replay_bus_sha256']or sha(folder/'original-patch.syx')!=base['original_input_sha256']['original-patch.syx']:raise ValueError('Input changed')
        audio[name]={};render_receipts[name]={}
        for key,unity in [('original',False),('hf_unity',True)]:
            y,meta=render(binary,folder/'original-patch.syx',folder/'replay-buses.raw',dst/(key+'.raw'),unity)
            if (not unity or name=='cotton-wool') and meta['raw_sha256']!=base['full']['raw_sha256']:raise ValueError('Required byte identity failed: '+name+'/'+key)
            audio[name][key]=y;render_receipts[name][key]=meta;wavfile.write(dst/(key+'.wav'),SR,y[:,4:])
        print(name,'identity controls passed',flush=True)
    save(out/'render-receipts-before-scoring.json',render_receipts)
    records=[]
    for case in assessed['cases']:
        name=case['id'];hardware,cal,prov=hardware_input(name)
        if cal!=case['frozen_calibration'] or prov!=case['hardware_provenance']:raise ValueError('Prior reference changed')
        lag=cal['candidate_lag_samples'];gain=cal['candidate_gain'];supports=[]
        for support in case['public_support']:
            begin,end=support['hardware_samples'];lo,hi=support['samples']
            if [lo,hi]!=[begin+lag,end+lag]:raise ValueError('Coverage changed')
            signals={k:v[lo:hi,4:].astype(float)*gain for k,v in audio[name].items()}
            wh=hardware[begin:end].astype(float)
            hlevels=stereo_levels(wh);mlevels={k:stereo_levels(y)for k,y in signals.items()}
            delta=signals['hf_unity']-signals['original']
            windows=[]
            for spec in prior['window_specs']:
                length=round(spec['duration_seconds']*SR);hop=spec['hop_seconds'];rows=[]
                # Inherit source-clock start scheduling (round each fractional-hop timestamp).
                count=int(np.floor(((end-begin)/SR-spec['duration_seconds']+1e-9)/hop))+1
                for i in range(count):
                    start_seconds=begin/SR+i*hop
                    s=round(start_seconds*SR);e=round((start_seconds+spec['duration_seconds'])*SR)
                    if not begin<=s<e<=end:raise ValueError('Window crossed inherited support')
                    row=dict(hardware_samples=[s,e],model_samples=[s+lag,e+lag],center_seconds=(s+e)/(2*SR),
                        hardware=measure_window(hardware[s:e]),
                        **{k:measure_window(v[s+lag:e+lag,4:].astype(float)*gain)for k,v in audio[name].items()})
                    check=old_window(hardware.astype(float),start_seconds,spec['duration_seconds'])
                    for ch in ('stereo','side'):
                        if row['hardware'][ch]!=check['channels'][ch]:raise ValueError('Inherited estimator changed')
                    rows.append(row)
                if not rows:raise ValueError('Window has no coverage')
                windows.append(dict(spec=spec,rows=rows,summary=summarize(rows)))
            supports.append(dict(hardware_samples=[begin,end],model_samples=[lo,hi],requested_seconds=support['requested_hardware_seconds'],
                hardware_stereo_levels_dbfs=hlevels,model_stereo_levels_dbfs=mlevels,
                model_minus_hardware_db={k:{ch:v-hlevels[ch]for ch,v in levels.items()}for k,levels in mlevels.items()},
                removed_waveform_stereo_levels_dbfs=stereo_levels(delta),
                removed_waveform=difference(signals['hf_unity'],signals['original']),
                removed_side_relative_rms=float(np.linalg.norm(delta[:,0]-delta[:,1])/max(np.linalg.norm(signals['original'][:,0]-signals['original'][:,1]),1e-300)),windows=windows))
        records.append(dict(id=name,hardware_provenance=prov,frozen_calibration=cal,renders=render_receipts[name],supports=supports))
    fig,axes=plt.subplots(2,4,figsize=(14,6),layout='constrained')
    club=next(c for c in records if c['id']=='club-bass')
    for row,ch in enumerate(('stereo','side')):
        for col,label in enumerate(('broadband','80-160','160-320','320-640')):
            ax=axes[row,col]
            for key,color in [('hardware','C0'),('original','C1'),('hf_unity','C2')]:
                rows=[r for support in club['supports'] for r in support['windows'][0]['rows']]
                x=[r['center_seconds']for r in rows]
                y=[r[key][ch]['broadband_dbfs'] if col==0 else r[key][ch]['band_dbfs'][col-1]for r in rows]
                ax.plot(x,y,'.-',label=key.replace('_',' '),color=color)
            ax.axvline(2.65,color='gray',ls=':');ax.axvline(3.,color='gray',ls=':')
            ax.set(title=ch+' '+label,xlabel='Original source time / s',ylabel='dBFS');ax.grid(alpha=.2)
    axes[0,0].legend(fontsize=8);fig.suptitle('Club HF-unity diagnostic — fixed inputs and gain; no coefficient selection')
    plot=out/'club-hf-unity.png';fig.savefig(plot,dpi=160);plt.close(fig)
    save(out/'results.json',dict(protocol=protocol,build=manifest,cases=records,plot=dict(path=str(plot),sha256=sha(plot)),
        numerical_guard='Original and Cotton unity raw identities passed; every inherited hardware Stereo/Side window reproduces the prior estimator exactly.',
        decision='Mechanism diagnostic only. No fitted coefficient, monotonic bound or hardware equivalence claim.'))


if __name__=='__main__':main()
