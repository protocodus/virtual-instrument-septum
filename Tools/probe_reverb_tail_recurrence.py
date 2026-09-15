#!/usr/bin/env python3
"""Test common tail recurrence on known controls before fitting public audio.

Reuses exact-engine controls with hash-pinned source/fixtures/audio. No new
renderer, hardware pole fit, parameter candidate or production edit occurs.
"""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal
from scipy.io import wavfile

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path,obj):path.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')


def fit(inputs,order):
    rows=[];targets=[]
    for y in inputs:
        for ch in range(y.shape[1]):
            x=y[:,ch]/np.sqrt(np.mean(y[:,ch]**2))
            history=np.lib.stride_tricks.sliding_window_view(x,order+1)
            rows.append(history[:,:order][:,::-1]);targets.append(history[:,order])
    a=np.concatenate(rows);b=np.concatenate(targets)
    coefficients,_,rank,singular=np.linalg.lstsq(a,b,rcond=1e-10)
    return coefficients,dict(rank=int(rank),singular_values=singular.tolist(),
        one_step_training_relative_rms=float(np.linalg.norm(a@coefficients-b)/np.linalg.norm(b)),
        coefficients=coefficients.tolist(),largest_pole_radius=float(max(abs(np.roots(np.r_[1.,-coefficients])))))


def predict(coefficients,training,n):
    p=len(coefficients);out=np.empty((p+n,training.shape[1]));out[:p]=training[-p:]
    for i in range(p,p+n):out[i]=coefficients@out[i-p:i][::-1]
    return out[p:]


def measure(reference,predicted,rate):
    result=dict(finite=bool(np.isfinite(predicted).all()),
        waveform_relative_rms=float(np.linalg.norm(reference-predicted)/np.linalg.norm(reference)),channels={})
    for ch,label in [(0,'left'),(1,'right')]:
        groups=[]
        for milliseconds in (50,100):
            size=round(rate*milliseconds/1000);hop=round(rate*.025)
            starts=np.arange(0,len(reference)-size+1,hop)
            a=np.array([np.mean(reference[s:s+size,ch]**2)for s in starts])
            b=np.array([np.mean(predicted[s:s+size,ch]**2)for s in starts])
            errors=10*np.log10(np.maximum(b,1e-300)/np.maximum(a,1e-300))
            groups.append(dict(window_ms=milliseconds,starts=starts.tolist(),
                reference_db=(10*np.log10(np.maximum(a,1e-300))).tolist(),
                prediction_db=(10*np.log10(np.maximum(b,1e-300))).tolist(),
                prediction_minus_reference_db=errors.tolist(),
                maximum_absolute_error_db=float(max(abs(errors))),
                rms_error_db=float(np.sqrt(np.mean(errors**2)))))
        result['channels'][label]=groups
    result['all_envelope_errors_below_0p5_db']=all(g['maximum_absolute_error_db']<=.5 for groups in result['channels'].values()for g in groups)
    return result


def controls(rate):
    # Exactly eight pairs of poles: no instrumental parameter or source fit.
    t=np.arange(round(.7*rate))/rate
    frequencies=np.array([103.3,151.7,212.1,269.9,334.7,412.3,499.1,603.7])
    times=np.linspace(1.2,4.1,8)
    states=[]
    for state in range(3):
        channels=[]
        for ch in range(2):
            waves=[np.exp(-np.log(1000)*t/tau)*np.sin(2*np.pi*f*t+.31*(h+1)**2+.79*state+.43*ch)/(h+1)
                   for h,(f,tau)in enumerate(zip(frequencies,times))]
            channels.append(np.sum(waves,axis=0))
        states.append(np.column_stack(channels))
    contaminated=states[2].copy();u=np.maximum(0,t-.35)
    chirp=.4*(1-np.exp(-u/.015))*np.sin(2*np.pi*(181*u+127*u*u))
    contaminated+=np.column_stack([chirp,-.7*chirp])
    return states,contaminated,dict(frequencies_hz=frequencies.tolist(),rt60_seconds=times.tolist(),
        interpretation='The identical damped sinusoids can be reverb modes after an impulse or deliberately released oscillators. Output recurrence alone cannot distinguish those causes.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--protocol',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();protocol=json.loads(a.protocol.read_text())
    if sha(a.protocol)!='e8ea594299b6d63273afb00d2c385671d2850523430627e44247ed84a4096410':
        raise ValueError('Frozen protocol changed')
    a.output.mkdir(parents=True,exist_ok=False)
    save(a.output/'protocol-before-controls.json',protocol)
    original=ROOT/protocol['prior_control_receipt']['path']
    if sha(original)!=protocol['prior_control_receipt']['sha256']:raise ValueError('Prior receipt changed')
    prior=json.loads(original.read_text())['fdn_control_receipt'];directory=ROOT/protocol['controls_directory']
    for name,expected in protocol['source_sha256'].items():
        if sha(ROOT/name)!=expected or sha(directory/'frozen-source'/name)!=expected:
            raise ValueError('Current or control DSP source changed: '+name)
    for name,key in [('club-fdn-burst.cpp','fixture_sha256'),('club-fdn-burst','binary_sha256')]:
        if sha(directory/name)!=prior[key]:raise ValueError('Control build changed')
    rate=2100;kernel=signal.firwin(2205,[80,640],pass_zero=False,window='hamming',fs=44100)
    extra_delay=(93+1102)/44100
    supports=[round((t+extra_delay)*rate)for t in(.29,.64,.99)]
    source={};identity=[]
    for row in protocol['control_audio']:
        path=directory/(row['id']+'.wav')
        if sha(path)!=row['wav_sha256']:raise ValueError('Control audio changed')
        sr,y=wavfile.read(path)
        if sr!=44100 or y.shape!=(sr*4,2)or not np.isfinite(y).all():raise ValueError('Invalid control')
        filtered=np.column_stack([signal.fftconvolve(y[:,ch].astype(float),kernel,mode='full')[:len(y)][::21]for ch in(0,1)])
        source[row['id']]=filtered
        identity.append(dict(id=row['id'],wav_sha256=sha(path),filtered_float64_sha256=hashlib.sha256(filtered.tobytes()).hexdigest()))
    states,contaminated,planted=controls(rate);split=round(.35*rate)
    results=[];predictions={}
    for order in protocol['algorithm']['orders']:
        toy_coefficient,toy_fit=fit([v[:split]for v in states[:2]],order)
        toy=[measure(v[split:],predict(toy_coefficient,v[:split],len(v)-split),rate)for v in states]
        negative=measure(contaminated[split:],predict(toy_coefficient,contaminated[:split],len(contaminated)-split),rate)
        trains=[source[name][supports[0]:supports[1]]for name in protocol['algorithm']['train_inputs']]
        coefficient,fdn_fit=fit(trains,order);rows={}
        for name in protocol['algorithm']['check_inputs']:
            training=source[name][supports[0]:supports[1]];check=source[name][supports[1]:supports[2]]
            prediction=predict(coefficient,training,len(check));rows[name]=measure(check,prediction,rate)
            if order==64:predictions[name]=(check,prediction)
        results.append(dict(order=order,role='primary'if order==64 else'fixed_order_sensitivity',
            planted_fit=toy_fit,planted_states=toy,continuing_input_negative=negative,
            fdn_fit=fdn_fit,fdn_check=rows,
            known_mode_positive_pass=all(v['waveform_relative_rms']<1e-3 for v in toy),
            actual_fdn_guard_pass=all(v['all_envelope_errors_below_0p5_db']for v in rows.values())))
    fig,axes=plt.subplots(2,2,figsize=(12,7),layout='constrained')
    for ax,(name,(actual,predicted))in zip(axes.flat,predictions.items()):
        m=measure(actual,predicted,rate)['channels']['left'][0]
        t=(np.array(m['starts'])+rate*.025)/rate
        ax.plot(t,m['reference_db'],label='Exact engine');ax.plot(t,m['prediction_db'],label='Free prediction')
        ax.set(title=name,xlabel='Time after calibration / s',ylabel='50ms left RMS / dB');ax.grid(alpha=.3)
    axes.flat[0].legend();fig.suptitle('Primary order64 recurrence: known fixed Club FDN, no new input')
    fig.savefig(a.output/'control-prediction.png',dpi=140);plt.close(fig)
    result=dict(schema_version=1,protocol=protocol,protocol_sha256=sha(a.protocol),tool_sha256=sha(__file__),
        control_identity=identity,analysis_filter_coefficients=kernel.tolist(),analysis_sample_supports=supports,
        causal_filter_convention='Full causal FIR convolution truncated to original length, then decimate21. No lookahead or check-sample input to prediction; linear-phase group delay included once.',
        planted=planted,results=results,hardware_fit_performed=False,candidate_parameter_selected=False,
        primary_fdn_guard_pass=next(v['actual_fdn_guard_pass']for v in results if v['order']==64),
        any_fixed_order_fdn_guard_pass=any(v['actual_fdn_guard_pass']for v in results),
        plot_sha256=sha(a.output/'control-prediction.png'))
    save(a.output/'results.json',result)
    for r in results:
        print('order',r['order'],'positive',r['known_mode_positive_pass'],'FDN guard',r['actual_fdn_guard_pass'],
              'max envelopes',[round(max(g['maximum_absolute_error_db']for groups in v['channels'].values()for g in groups),3)for v in r['fdn_check'].values()])


if __name__=='__main__':main()
