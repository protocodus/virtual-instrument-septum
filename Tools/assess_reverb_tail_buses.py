#!/usr/bin/env python3
"""Validate frozen bus decomposition, then measure predeclared tail supports.

No performance, source, gain, delay or DSP fitting. Run after
decompose_reverb_tail_buses.py. All synthetic controls are defined before any
component or hardware interval is scored; original media and model hashes stay
strict. Component powers are descriptive and are never added as probabilities.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.io import wavfile
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from decompose_reverb_tail_buses import ROOT, SR, sha, save, replay, difference
from render_midi import parse_smf

MODES = ('dry', 'delay', 'direct_reverb', 'delay_reverb')


def read_raw(path):
    x = np.fromfile(path, dtype='<f4').reshape(-1, 6)
    if not np.isfinite(x).all():
        raise ValueError('Nonfinite raw output')
    return x


def db_rms(x):
    p = float(np.mean(np.asarray(x, float)**2))
    return 10*np.log10(p) if p > 0 else None


def stereo_levels(x):
    x = np.asarray(x,float)
    return dict(stereo=db_rms(x),mid=db_rms(.5*(x[:,0]+x[:,1])),side=db_rms(.5*(x[:,0]-x[:,1])))


def first_changed(x, y):
    hits = np.flatnonzero(np.any(x != y, axis=1))
    return int(hits[0]) if len(hits) else None


def check_prefix(x, y, minimum):
    hit = first_changed(x, y)
    if hit is not None and hit < minimum:
        raise ValueError(f'Halt changed earlier samples: {hit} < {minimum}')
    return dict(identical_before_minimum=True, minimum_frame=minimum,
                first_changed_frame=hit, identical_complete=hit is None)


def levels(x, stems, halts, begin, end):
    y = x[begin:end, 4:]
    if len(y) != end-begin or not len(y):
        raise ValueError('Incomplete declared interval')
    norm = np.linalg.norm(y)
    result = dict(samples=[begin, end], full_rms_dbfs=db_rms(y),
                  full_stereo_levels_dbfs=stereo_levels(y),
                  component_rms_dbfs={k:db_rms(v[begin:end, 4:]) for k,v in stems.items()},
                  component_stereo_levels_dbfs={k:stereo_levels(v[begin:end,4:]) for k,v in stems.items()},
                  before_output_component_rms_dbfs={k:db_rms(v[begin:end, :2]) for k,v in stems.items()},
                  halt_difference={})
    for key, value in halts.items():
        h = value[begin:end, 4:]
        result['halt_difference'][key] = dict(
            removed_signal_rms_dbfs=db_rms(y-h),
            removed_signal_stereo_levels_dbfs=stereo_levels(y-h),
            side_relative_waveform_rms=float(np.linalg.norm((y-h)[:,0]-(y-h)[:,1])/max(np.linalg.norm(y[:,0]-y[:,1]),1e-300)),
            relative_waveform_rms=float(np.linalg.norm(y-h)/max(norm, 1e-300)),
            rms_level_delta_db=(db_rms(h)-db_rms(y)) if db_rms(h) is not None else None)
    powers = [float(np.mean(v[begin:end, 4:].astype(float)**2)) for v in stems.values()]
    total = float(np.mean(y.astype(float)**2))
    result['sum_component_power_over_full_power'] = sum(powers)/max(total, 1e-300)
    result['coherent_cross_term_fraction'] = (total-sum(powers))/max(total, 1e-300)
    return result


def synthetic_controls(run, out):
    """Known post-voice input, independently tests effects and output chain."""
    binary = run/'builds/diagnostic/EffectsReplay'
    syx = run/'ambient-sqr-nominal-v100/original-patch.syx'
    dst = out/'synthetic'; dst.mkdir()
    frames = 2*SR
    bus = np.zeros((frames, 26), dtype='<f8')
    bus[:,20] = 100/127; bus[:,21:23] = 1
    bus[7::8,25] = 1; bus[-1,25] = 1
    n = round(.2*SR); t = np.arange(n)/SR
    rng = np.random.default_rng(20260915)
    upper = .03*(np.sin(2*np.pi*173*t)+.2*rng.standard_normal(n))
    lower = .025*(np.sin(2*np.pi*277*t+.8)+.2*rng.standard_normal(n))
    for c in range(2):
        bus[:n,6+c] = upper*(1 if c==0 else .8)
        bus[:n,8+c] = lower*(.7 if c==0 else 1)
        for base, factor in [(10,40/127), (14,43/127)]:
            bus[:n,base+c] = bus[:n,6+c]*factor
        bus[:n,12+c] = bus[:n,8+c]*(40/127)
        bus[:n,16+c] = bus[:n,8+c]*(112/127)
        bus[:,c] = bus[:,6+c]+bus[:,8+c]
        bus[:,2+c] = bus[:,10+c]+bus[:,12+c]
        bus[:,4+c] = bus[:,14+c]+bus[:,16+c]
    path = dst/'known-input.raw'; bus.tofile(path)
    records = []
    for scale in (1., 100.):
        tag = 'quiet' if scale==1 else 'overloaded'
        full, meta = replay(binary, syx, path, dst/(tag+'-full.raw'), -1, 'full', scale=scale)
        stems = {}; receipts = {}
        for part in (0,1):
            for mode in MODES:
                key = str(part)+'-'+mode
                stems[key], receipts[key] = replay(binary,syx,path,dst/(tag+'-'+key+'.raw'),part,mode,scale=scale)
        summed = sum(v.astype(float) for v in stems.values())
        differences = {key:difference(summed[:,a:b], full[:,a:b]) for key,a,b in
                       [('before_output',0,2),('before_limiter',2,4),('after_limiter',4,6)]}
        if differences['before_limiter']['relative_rms'] > 2e-6:
            raise ValueError('Known linear control failed')
        if scale==1 and (meta['limited_samples'] or differences['after_limiter']['maximum_absolute']>2e-6):
            raise ValueError('Known quiet control failed')
        if scale==100 and (not meta['limited_samples'] or differences['after_limiter']['relative_rms']<.01):
            raise ValueError('Overload failed to distinguish output nonlinearity')
        records.append(dict(name=tag,scale=scale,full=meta,stems=receipts,recombination=differences))
    # Direct impulse reveals strict causal onset, distinct from group delay.
    impulse = np.zeros((SR,26),dtype='<f8'); impulse[:,20]=100/127; impulse[:,21:23]=1
    impulse[7::8,25]=1; impulse[-1,25]=1
    impulse[0,:6]=.05
    ip = dst/'impulse.raw'; impulse.tofile(ip)
    onsets = {}
    for name in ('club-bass','ambient-sqr-nominal-v100','cotton-wool'):
        onsets[name] = {}
        for mode in ('dry','direct_reverb'):
            y, meta = replay(binary,run/name/'original-patch.syx',ip,dst/(name+'-'+mode+'-impulse.raw'),-1,mode)
            onsets[name][mode] = dict(before_output=first_changed(y[:,:2], np.zeros_like(y[:,:2])),
                before_limiter=first_changed(y[:,2:4],np.zeros_like(y[:,2:4])),receipt=meta)
    return dict(known_input_sha256=sha(path), impulse_sha256=sha(ip), levels=records, strict_impulse_onsets=onsets)


def hardware_input(name):
    new = name == 'ambient-sqr-nominal-v100'
    run = ROOT/'build-fidelity/hardware-benchmark'/('reverb-new-preset-validation' if new else 'reverb-gain-candidates')/'run-01'
    result = json.loads((run/'results.json').read_text())
    row = next(r for r in result['cases'] if r['id']==name)
    corpus = run/'baseline-corpus' if new else ROOT/'build-fidelity/hardware-benchmark/final-production-linear-lfo'
    folder = corpus/name
    meta = json.loads((folder/'comparison.json').read_text())
    if sha(folder/'comparison.json') != row['comparison_sha256']:
        raise ValueError('Prior comparison changed')
    wav = folder/'hardware-excerpt-raw.wav'
    expected = meta['files'][wav.name] if new else row['input_sha256'][wav.name]
    if sha(wav)!=expected:
        raise ValueError('Hardware excerpt changed')
    mp3 = ROOT/'build-fidelity/hardware-benchmark/sources'/meta['reference']['local_filename']
    if sha(mp3)!=meta['reference']['sha256']:
        raise ValueError('Original MP3 changed')
    sr, y = wavfile.read(wav)
    if sr != SR or y.dtype != np.float32 or not np.isfinite(y).all():
        raise ValueError('Unexpected reference representation')
    return y, row['calibration'], dict(result_path=str(run/'results.json'), result_sha256=sha(run/'results.json'),
        comparison_sha256=sha(folder/'comparison.json'), reference=meta['reference'],
        original_mp3_sha256=sha(mp3), excerpt_sha256=sha(wav))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    a = p.parse_args(); run = a.run.resolve(); out = a.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    receipt = json.loads((run/'results.json').read_text())
    for f, expected in receipt['build']['files_sha256'].items():
        if sha(run/'builds'/f)!=expected: raise ValueError('Frozen source or executable changed: '+f)
    protocol = dict(status='Diagnostic decomposition and causality validation; no coefficient fitting or DSP selection.',
        decomposition_result_sha256=sha(run/'results.json'), decomposition_protocol_sha256=sha(run/'protocol-before-build.json'),
        tool_sha256=sha(__file__), builder_sha256=sha(Path(__file__).with_name('decompose_reverb_tail_buses.py')),
        known_control='Ambient exact FX,200ms deterministic two-source stereo burst; scale1 and100, two-second output. All eight stems; quiet output sum and overloaded pre-limiter sum must pass. Overloaded post-limiter sum must fail.',
        identity_guard='Native/diagnostic/prior WAV identity; strict per-stage halt prefix equality through measured impulse onset. Group delay is not the strict causal onset: do not add93 samples to the captured post-voice effects buses.',
        measurements='Full/stem RMS, coherent cross terms, waveform norm removed by each halt and RMS change. Same frozen gain/lag only for predeclared hardware opening supports; no refitting, no parameter choice.',
        public_support=receipt['protocol']['supports'], hardware_support_policy='Clip declared supports only to the already frozen common evaluation coverage; record requested and actual intervals. Retain source/MIDI uncertainty. Controlled tail ages are model-clock only and never matched to final hardware performance.')
    save(out/'protocol-before-measurement.json',protocol)
    controls = synthetic_controls(run,out)
    save(out/'controls.json',controls)
    records = []
    for case in receipt['cases']:
        name = case['id']; folder=run/name
        original = next(c['receipt'] for c in receipt['protocol']['cases'] if c['id']==name)
        parsed = parse_smf((folder/'reconstructed-performance.mid').read_bytes(), SR)
        if (original['output']['active_voices_at_end'] != 0 or original['output']['patch_arpeggio_on']
                or parsed['end_sample'] >= case['original_frames']
                or max(e['sample'] for e in original['replay_events']) >= case['original_frames']):
            raise ValueError('Zero active voices alone cannot establish safe extension')
        extension_guard = dict(all_midi_tracks_ended_before_extension=True,
            independently_parsed_smf_end_sample=parsed['end_sample'],
            last_replayed_event_sample=max(e['sample'] for e in original['replay_events']),
            active_voices_at_original_render_end=0,arpeggio_enabled=False,
            original_render_samples=[0,case['original_frames']],
            controlled_extension_samples=[case['original_frames'],case['extended_frames']],
            qualification='Zero active voices is insufficient alone. All SMF tracks ended, every replay event precedes original render end, and the stored arpeggiator is off; no future performance event is queued.')
        full=read_raw(folder/'full.raw')
        if sha(folder/'full.raw')!=case['full']['raw_sha256']:raise ValueError('Full render changed')
        stems={}; halts={}; guards={}
        for key,meta in case['stems'].items():
            if sha(folder/(key+'.raw'))!=meta['raw_sha256']:raise ValueError('Stem changed')
            stems[key]=read_raw(folder/(key+'.raw'))
        if case['full']['limited_samples'] or any(m['limited_samples']for m in case['stems'].values()):
            raise ValueError('Actual stems require nonlinear qualification')
        for key,meta in case['halts'].items():
            if sha(folder/(key+'.raw'))!=meta['raw_sha256']:raise ValueError('Halt changed')
            h=halts[key]=read_raw(folder/(key+'.raw'))
            frame=case['last_note_off_sample']+(round(.25*SR) if key.endswith('plus250ms') else 0)
            mode='dry' if key.startswith('source') else 'direct_reverb'
            onset=controls['strict_impulse_onsets'][name][mode]
            guards[key]={label:check_prefix(h[:,a:b],full[:,a:b],frame+onset[onsetkey]) for label,a,b,onsetkey in
                         [('before_output',0,2,'before_output'),('before_limiter',2,4,'before_limiter'),('after_limiter',4,6,'before_limiter')]}
        ages=receipt['protocol']['supports']['synthetic_tail_ages_after_final_gate']
        tails=[dict(ages_seconds=[a,b],**levels(full,stems,halts,case['last_note_off_sample']+round(a*SR),case['last_note_off_sample']+round(b*SR)))for a,b in ages]
        hardware,cal,provenance=hardware_input(name)
        key={'club-bass':'club','ambient-sqr-nominal-v100':'ambient','cotton-wool':'cotton'}[name]
        supports=receipt['protocol']['supports'][key+'_matched_source_seconds']
        lag=cal['candidate_lag_samples']; gain=cal['candidate_gain']; public=[]
        for a,b in supports:
            begin=max(round(a*SR),max(0,-lag)); end=min(round(b*SR),len(hardware),len(hardware)-lag,len(full)-lag)
            if begin>=end:raise ValueError('No public support')
            measures=levels(full,stems,halts,begin+lag,end+lag)
            measures['requested_hardware_seconds']=[a,b]; measures['hardware_samples']=[begin,end]
            measures['hardware_rms_dbfs']=db_rms(hardware[begin:end])
            measures['hardware_stereo_levels_dbfs']=stereo_levels(hardware[begin:end])
            model_levels=stereo_levels(full[begin+lag:end+lag,4:]*gain)
            measures['model_minus_hardware_stereo_levels_db']={k:model_levels[k]-v if model_levels[k] is not None and v is not None else None for k,v in measures['hardware_stereo_levels_dbfs'].items()}
            measures['model_minus_hardware_rms_db']=db_rms(full[begin+lag:end+lag,4:]*gain)-db_rms(hardware[begin:end])
            public.append(measures)
        bus=np.fromfile(folder/'replay-buses.raw',dtype='<f8').reshape(-1,26)
        def last_nonzero(cols):
            hits=np.flatnonzero(np.any(bus[:,cols]!=0,axis=1));return int(hits[-1])if len(hits)else None
        records.append(dict(id=name,original_input_sha256=case['original_input_sha256'],native_sha256=case['native_sha256'],
            verified_native_identity=case['native_diagnostic_original_byte_identity'],recombination=case['recombination'],
            extension_guard=extension_guard,
            last_reconstructed_gate_sample=case['last_note_off_sample'],
            last_exact_nonzero_bus_sample={k:last_nonzero(cols) for k,cols in
                [('dry',[0,1]),('delay_send',[2,3]),('direct_reverb_send',[4,5]),('upper',[6,7]),('lower',[8,9])]},
            halt_causality=guards,controlled_tail_ages=tails,public_support=public,
            frozen_calibration=cal,hardware_provenance=provenance))
        print(name,'causality passed; first tail source/removal',[round(t['halt_difference']['source_gate']['relative_waveform_rms'],5)for t in tails],flush=True)
    fig, axes = plt.subplots(1,3,figsize=(13,4),layout='constrained')
    for ax,case in zip(axes,receipt['cases']):
        folder=run/case['id']; gate=case['last_note_off_sample']
        signals={'full':read_raw(folder/'full.raw')[:,4:].astype(float)}
        for mode in MODES:
            signals[mode]=sum(read_raw(folder/(part+'_'+mode+'.raw'))[:,4:].astype(float) for part in ('upper','lower'))
        starts=np.arange(gate+round(.09*SR),gate+round(5.50*SR),round(.05*SR))
        for color,(key,value) in enumerate(signals.items()):
            if not np.any(value):continue
            ys=[db_rms(value[s:s+round(.05*SR)]) for s in starts]
            ax.plot((starts-gate)/SR+.025,ys,label=key.replace('_',' '),color='C'+str(color))
        ax.set(title=case['id'].replace('-nominal-v100',''),xlabel='Age after reconstructed gate / s',ylabel='50 ms stereo RMS / dBFS',ylim=(-125,-30))
        ax.grid(alpha=.25)
    axes[1].legend(fontsize=8)
    fig.suptitle('Controlled current-engine tails; not the unknown final hardware performance')
    plot=out/'model-tail-components.png';fig.savefig(plot,dpi=160);plt.close(fig)
    result=dict(protocol=protocol,decomposition_receipt=receipt,controls=controls,cases=records,
        plot=dict(path=str(plot),sha256=sha(plot),policy='Descriptive fixed50ms component trajectory; no new intervals used to choose a model or parameter.'),
        limitation='These are actual current-engine pathways. Hardware stems and true release/effect state are unobserved. Cotton/Ambient long hardware tails have no matched input reconstruction; model extensions are controls only. No DSP coefficient is identified by decomposition alone.')
    save(out/'results.json',result)


if __name__=='__main__':main()
