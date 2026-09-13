#!/usr/bin/env python3
"""Separate Cotton note-off sensitivity from pre-release spectral movement.

Uses original preset and unchanged reconstructed MIDI as the control, then three
first-note gate interventions, one longer-chord gate intervention, and a clearly
labeled FX-off preset diagnostic. No original MIDI or dry hardware stem is known.
Complex sine fits describe a component of the wet output, not an isolated AMP
envelope. Overlapping analysis windows are sensitivity probes, not independent
samples or confidence intervals.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal

from analyze_brightness_controls import read_audio, render
from compare_hardware import write_midi

ROOT = Path(__file__).resolve().parents[1]
LATENCY = 93 / 44100


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def effects_off(data):
    """Change only documented common Delay/Reverb SW bytes and DT1 checksum."""
    result = bytearray()
    edits = []
    for item in data.split(b'\xf7'):
        if not item:
            continue
        frame = bytearray(item + b'\xf7')
        assert frame[:7] == bytes([0xf0,0x41,0x10,0,0,0x16,0x12])
        assert sum(frame[7:-1]) % 128 == 0
        if frame[7:11] == bytes([0x10,0,0,0]):
            for offset in (0x1c,0x1d):
                edits.append({'common_offset':offset,'before':frame[11+offset],'after':0})
                frame[11+offset] = 0
            frame[-2] = (-sum(frame[7:-2])) & 127
        result.extend(frame)
    assert len(edits) == 2
    return bytes(result), edits


def complex_components(audio, sr, centre, width, frequencies, nuisance, offset):
    begin,end = round((centre-width/2+offset)*sr),round((centre+width/2+offset)*sr)
    t = np.arange(begin,end)/sr-offset
    y = audio[begin:end]
    columns = [np.ones(len(t)), t-centre]
    for f in frequencies+nuisance:
        columns += [np.cos(2*np.pi*f*t),np.sin(2*np.pi*f*t)]
    a = np.array(columns).T
    weight = np.sqrt(np.hanning(len(t)))[:,None]
    coefficients = np.linalg.lstsq(a*weight,y*weight,rcond=None)[0]
    return [coefficients[2+2*i]-1j*coefficients[3+2*i] for i in range(len(frequencies))]


def band_ratio(audio,sr,centre,width,offset):
    y = audio[round((centre-width/2+offset)*sr):round((centre+width/2+offset)*sr)]
    f,p = signal.periodogram(y,sr,window='hann',nfft=32768,axis=0)
    p = p.mean(axis=1)
    lo,hi = p[(f>=200)&(f<700)].sum(),p[(f>=700)&(f<3000)].sum()
    return float(10*np.log10(max(hi,1e-30)/max(lo,1e-30)))


def traces(audio,sr,rendered):
    offset = LATENCY if rendered else 0
    result = {}
    configurations = [('opening',np.arange(.10,.501,.01),[65.15],[130.8128*h for h in range(1,10)],.07),
                      ('chord',np.arange(2.60,4.011,.02),
                       [f*2**(-7/1200) for f in (155.5635,174.6141,220)],
                       [f*h for f in (311.127,349.2282,440) for h in (1,2,3)],.12)]
    for name,times,frequencies,nuisance,width in configurations:
        rows = []
        for t in times:
            fitted = complex_components(audio,sr,float(t),width,frequencies,nuisance,offset)
            rows.append({'seconds':float(t),'700_3000_over_200_700_db':band_ratio(audio,sr,float(t),width,offset),
                         'components':[{'frequency_hz':f,'complex_left':[float(c[0].real),float(c[0].imag)],
                                        'complex_right':[float(c[1].real),float(c[1].imag)],
                                        'amplitude_db':float(10*np.log10(max(np.mean(abs(c)**2),1e-30))),
                                        'right_over_left_db':float(20*np.log10(max(abs(c[1]),1e-30)/max(abs(c[0]),1e-30))),
                                        'right_minus_left_phase_degrees':float(np.angle(c[1]/c[0])*180/np.pi)}
                                       for f,c in zip(frequencies,fitted)]})
        for i in range(len(frequencies)):
            interval = (.20,.33) if name=='opening' else (2.95,3.15)
            plateau = float(np.median([r['components'][i]['amplitude_db'] for r in rows if interval[0]<=r['seconds']<=interval[1]]))
            for row in rows:
                row['components'][i]['relative_to_plateau_db'] = row['components'][i]['amplitude_db']-plateau
        result[name] = {'window_seconds':width,'rows':rows}
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--comparison',type=Path,required=True)
    p.add_argument('--renderer',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    control = args.comparison
    manifest = json.loads((control/'comparison.json').read_text())
    case = manifest['case']
    original_patch = control/'original-patch.syx'
    original_midi = control/'reconstructed-performance.mid'
    binary = args.output/'SeptumRenderMidi-frozen'
    shutil.copy2(args.renderer,binary)
    binary = binary.resolve()
    inputs = {str(path):sha(path) for path in (original_patch,original_midi,args.renderer,control/'septum-raw.wav',control/'hardware-excerpt-raw.wav')}
    dry_patch = args.output/'effects-off-diagnostic.syx'
    data,edits = effects_off(original_patch.read_bytes())
    dry_patch.write_bytes(data)
    variants = [('control',{},original_patch),
                ('gate_0400',{0:.400},original_patch),
                ('gate_0440',{0:.440},original_patch),
                ('gate_0480',{0:.480},original_patch),
                ('chord_gates_plus_0200',{16:3.825,17:3.825,18:3.950},original_patch),
                ('effects_off_diagnostic',{},dry_patch)]
    results = {}
    for name,gates,patch in variants:
        copied = json.loads(json.dumps(case))
        changes = []
        for index,off in gates.items():
            changes.append({'note_index':index,'original_off':copied['notes'][index]['off'],'diagnostic_off':off})
            copied['notes'][index]['off'] = off
        midi,wav = args.output/f'{name}.mid',args.output/f'{name}.wav'
        write_midi(midi,copied)
        render(binary,midi,patch,wav)
        sr,audio = read_audio(wav)
        results[name] = {'midi_sha256':sha(midi),'sysex_sha256':sha(patch),'wav_sha256':sha(wav),
                         'note_off_interventions':changes,'preset_interventions':edits if name=='effects_off_diagnostic' else [],
                         'traces':traces(audio,sr,True)}
        if name=='control':
            baseline_audio = audio
        elif gates:
            earliest = min(change['original_off'] for change in changes)
            samples = round(earliest*sr)
            results[name]['identical_before_first_changed_note_off'] = bool(np.array_equal(audio[:samples],baseline_audio[:samples]))
    # The last variant is the FX-off diagnostic. Compare it against the exact
    # production control without estimating a hardware wet stem.
    difference = np.max(abs(baseline_audio-audio),axis=1)
    effects_arrival = []
    for threshold in (0,1e-8,1e-6,1e-5,1e-4):
        indices = np.flatnonzero(difference>threshold)
        first = int(indices[0]) if len(indices) else None
        effects_arrival.append({'absolute_sample_difference_threshold':threshold,
                                'first_sample':first,
                                'latency_adjusted_seconds':None if first is None else (first-93)/sr})
    sr,hardware = read_audio(control/'hardware-excerpt-raw.wav')
    results['hardware'] = {'traces':traces(hardware,sr,False)}
    sensitivity = []
    for width in (.05,.07,.09):
        for t in (.22,.30,.36,.40,.42,.44,.46,.48):
            c = complex_components(hardware,sr,t,width,[65.15],[130.8128*h for h in range(1,10)],0)[0]
            sensitivity.append({'centre_seconds':t,'width_seconds':width,
                                'amplitude_db':float(10*np.log10(np.mean(abs(c)**2))),
                                'right_over_left_db':float(20*np.log10(abs(c[1])/abs(c[0]))),
                                'right_minus_left_phase_degrees':float(np.angle(c[1]/c[0])*180/np.pi)})
    coherent = {}
    for lo,hi in ((.20,.35),(.40,.48)):
        rows = [r['components'][0] for r in results['hardware']['traces']['opening']['rows'] if lo<=r['seconds']<=hi]
        left = np.array([complex(*r['complex_left']) for r in rows])
        right = np.array([complex(*r['complex_right']) for r in rows])
        coherent[f'{lo}_{hi}'] = float(abs(np.vdot(left,right))**2/(np.vdot(left,left).real*np.vdot(right,right).real))
    result = {'schema_version':1,'tool_sha256':sha(Path(__file__)),'source_hashes':inputs,
              'renderer_frozen_sha256':sha(binary),'limitations':__doc__.strip(),
              'method':{'sine':'Weighted real least squares, Hann weights; constant/linear trend and Super Saw harmonics included as nuisance sinusoids',
                        'amplitude':'mean squared complex channel amplitudes, referenced to each signal/component own plateau',
                        'phase':'complex right/left ratio; absolute sine phase is not treated as original oscillator phase',
                        'bands':'Hann periodogram, FFT32768, stereo mean power,700..3000Hz /200..700Hz',
                        'latency_samples':93,'sample_rate':44100},
              'modeled_parameters':{'filter_A10_seconds':.001*5000**(10/127),
                                    'filter_D58_seconds':.002+11.998*(58/127)**(np.log((.4189852819747085-.002)/11.998)/np.log(49/127)),
                                    'filter_S87':87/127,'filter_R105_60db_seconds':.002*6000**(105/127),
                                    'amp_A0_seconds':.001,'amp_D0_60db_seconds':.002,'amp_S127':1,
                                    'amp_R39_60db_seconds':.002*6000**(39/127)},
              'baseline_reproduced':results['control']['wav_sha256']==sha(control/'septum-raw.wav'),
              'modeled_effects_first_output_difference':effects_arrival,
              'hardware_sine_fit_window_sensitivity':sensitivity,
              'hardware_temporal_complex_channel_consistency':{
                  'description':'Normalized squared complex inner product across overlapping fitted time windows; descriptive, not an independent statistical coherence estimate',
                  'values':coherent},'results':results}
    for path,digest in inputs.items():
        if sha(Path(path)) != digest:
            raise RuntimeError(f'Input changed: {path}')
    assert result['baseline_reproduced']
    (args.output/'cotton-envelope.json').write_text(json.dumps(result,indent=2)+'\n')
    fig,axes = plt.subplots(2,2,figsize=(12,8),layout='constrained')
    chosen = [('hardware','Hardware','#222222'),('control','Current / off 0.370','#477caa'),
              ('gate_0400','Gate-only off 0.400','#c17a2b'),('gate_0440','Gate-only off 0.440','#8c61a0'),
              ('gate_0480','Gate-only off 0.480','#52917b')]
    for key,label,colour in chosen:
        rows = results[key]['traces']['opening']['rows']
        times = [r['seconds'] for r in rows]
        axes[0,0].plot(times,[r['components'][0]['relative_to_plateau_db'] for r in rows],label=label,color=colour)
        if key in ('hardware','control'):
            axes[0,1].plot(times,[r['700_3000_over_200_700_db'] for r in rows],label=label,color=colour)
            axes[1,0].plot(times,[r['components'][0]['right_minus_left_phase_degrees'] for r in rows],label=label,color=colour)
    for key,label,colour in [('hardware','Hardware','#222222'),('control','Current','#477caa'),
                             ('chord_gates_plus_0200','Chord gates +200ms','#c17a2b')]:
        rows = results[key]['traces']['chord']['rows']
        axes[1,1].plot([r['seconds'] for r in rows],[r['components'][2]['relative_to_plateau_db'] for r in rows],label=label,color=colour)
    # The next reconstructed note starts at .500s. A70ms centered window at
    # .465s is the last whose support ends before that note; show only these
    # uncontaminated windows. Earlier/later rows remain explicitly in the JSON.
    axes[0,0].set(title='Opening 65Hz component; each plateau 0dB',ylabel='Relative fitted component / dB',ylim=(-30,3),xlim=(.13,.465))
    axes[0,1].set(title='Brightness before note-off (window ends before 0.370s)',ylabel='700–3000Hz /200–700Hz power / dB',ylim=(-12,0),xlim=(.16,.335))
    axes[1,0].set(title='Opening component: stereo phase diverges in tail',ylabel='Right minus left phase / degrees',ylim=(-175,40),xlim=(.20,.465))
    axes[1,1].set(title='Held chord: 219Hz component',ylabel='Relative fitted component / dB',ylim=(-30,3),xlim=(2.65,4.0))
    for ax in axes.flat:
        ax.set_xlabel('Seconds from source start');ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Cotton Wool temporal diagnostics — original MIDI unknown; gate variants are interventions')
    fig.savefig(args.output/'cotton-envelope.png',dpi=150)
    print(json.dumps({'baseline_reproduced':result['baseline_reproduced'],'modeled_parameters':result['modeled_parameters'],
                      'hardware_channel_consistency':coherent,'variants':list(results)},indent=2))


if __name__=='__main__':
    main()
