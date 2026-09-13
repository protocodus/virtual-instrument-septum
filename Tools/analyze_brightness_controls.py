#!/usr/bin/env python3
"""Bounded Cotton/Air control experiment using preserved SH-201 demo comparisons.

This measures spectra; it does not identify original MIDI or optimize DSP values.
All baseline velocities 1..127 are tested with the same reconstructed notes and
original preset. Stereo powers are averaged before ratios. Broad-band energy is
less sensitive to Super Saw beating than single FFT peaks, but still depends on
phase, performance and wet effects. Window variants are sensitivity checks, not
independent observations or confidence intervals.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal
from scipy.io import wavfile

from compare_hardware import write_midi

ROOT = Path(__file__).resolve().parents[1]
LATENCY = 93 / 44100
WINDOWS = {
    'opening_note': [.16, .35],
    'opening_early': [.16, .30],
    'opening_middle': [.18, .32],
    'opening_late': [.20, .34],
    'held_chord': [2.9, 3.3],
    'repeated_bass': [4.16, 4.35],
}
BANDS = {'saw_fundamental': [110,155], 'saw_second': [230,290],
         'saw_third': [350,425], 'mid': [200,700], 'high': [700,3000],
         'high_narrow': [900,2000]}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_audio(path):
    sr, audio = wavfile.read(path)
    if sr != 44100 or audio.ndim != 2 or not np.isfinite(audio).all():
        raise ValueError(f'Expected finite stereo 44.1kHz audio: {path}')
    if np.issubdtype(audio.dtype, np.integer):
        audio = audio.astype(float) / 2 ** (8 * audio.dtype.itemsize - 1)
    return sr, audio.astype(float)


def measure(audio, sr, rendered):
    f, psd = signal.welch(audio[:5*sr], sr, nperseg=8192, axis=0)
    p = psd.mean(axis=1)
    audible = (f >= 20) & (f <= 16000)
    result = {'whole_excerpt_centroid_hz': float(np.dot(f[audible],p[audible])/p[audible].sum()),
              'windows': {}}
    for name, (start, end) in WINDOWS.items():
        offset = LATENCY if rendered else 0
        y = audio[round((start+offset)*sr):round((end+offset)*sr)]
        f, psd = signal.periodogram(y, sr, window='hann', nfft=65536, axis=0)
        p = psd.mean(axis=1)
        powers = {key: float(p[(f>=lo)&(f<hi)].sum()) for key,(lo,hi) in BANDS.items()}
        ratio = lambda a,b: float(10*np.log10(max(powers[a],1e-30)/max(powers[b],1e-30)))
        result['windows'][name] = {
            '700_3000_over_200_700_db':ratio('high','mid'),
            '900_2000_over_110_155_db':ratio('high_narrow','saw_fundamental'),
            'saw_second_over_first_db':ratio('saw_second','saw_fundamental'),
            'saw_third_over_first_db':ratio('saw_third','saw_fundamental')}
    return result


def render(binary, midi, patch, wav):
    command = [sys.executable,str(ROOT/'Tools/render_midi.py'), '--renderer',str(binary),
               '--midi',str(midi),'--syx',str(patch),'--output',str(wav),
               '--tempo-policy','preserve-patch','--tail','2','--master-level','100']
    done = subprocess.run(command,capture_output=True,text=True)
    if done.returncode:
        raise RuntimeError(done.stderr or done.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidates',type=Path,required=True)
    parser.add_argument('--renderers',type=Path,required=True)
    parser.add_argument('--air',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--jobs',type=int,default=4)
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    source = args.candidates/'depth-10/cotton-wool'
    case = json.loads((source/'comparison.json').read_text())['case']
    patch = source/'original-patch.syx'
    hardware = source/'hardware-excerpt-raw.wav'
    paths = [patch,hardware,source/'reconstructed-performance.mid']
    binaries = {depth:(args.renderers/f'depth-{depth}/SeptumRenderMidi').resolve() for depth in (10,12,14)}
    paths += list(binaries.values())
    original_hashes = {str(p):sha(p) for p in paths}
    sr,y = read_audio(hardware)
    measured = {'hardware':measure(y,sr,False)}
    for depth in (10,12,14):
        wav = args.candidates/f'depth-{depth}/cotton-wool/septum-raw.wav'
        paths.append(wav)
        original_hashes[str(wav)] = sha(wav)
        sr,y = read_audio(wav)
        measured[f'depth_{depth}'] = measure(y,sr,True)

    def run_velocity(velocity):
        variant = json.loads(json.dumps(case))
        for event in variant['notes']:
            event['velocity'] = velocity
        with tempfile.TemporaryDirectory(prefix='septum-brightness-') as temp:
            temp = Path(temp)
            midi,wav = temp/'velocity.mid',temp/'velocity.wav'
            write_midi(midi,variant)
            render(binaries[10],midi,patch,wav)
            sr,y = read_audio(wav)
            return {'velocity':velocity,'wav_sha256':sha(wav), **measure(y,sr,True)}

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        velocities = list(pool.map(run_velocity,range(1,128)))
    air_results = {}
    for depth in (10,12):
        wav = args.output/f'air-depth-{depth}.wav'
        midi,syx = args.air/'opening-note-reconstructed.mid',args.air/'original-patch.syx'
        paths.extend([midi,syx])
        original_hashes.update({str(p):sha(p) for p in (midi,syx)})
        render(binaries[depth],midi,syx,wav)
        air_results[str(depth)] = {'wav_sha256':sha(wav),'path':str(wav)}

    for p in paths:
        if sha(p) != original_hashes[str(p)]:
            raise ValueError(f'Input changed during analysis: {p}')
    velocity_ranges = {'whole_excerpt_centroid_hz':{
        'minimum':min(v['whole_excerpt_centroid_hz'] for v in velocities),
        'maximum':max(v['whole_excerpt_centroid_hz'] for v in velocities)}}
    for window in WINDOWS:
        velocity_ranges[window] = {}
        for metric in measured['hardware']['windows'][window]:
            values = [v['windows'][window][metric] for v in velocities]
            velocity_ranges[window][metric] = {'minimum':min(values),'maximum':max(values),
                                              'maximum_velocity':velocities[int(np.argmax(values))]['velocity']}
    result = {'schema_version':1,'experiment':'filter_depth_and_unknown_velocity_sensitivity',
              'tool_sha256':sha(Path(__file__)), 'source_hashes':original_hashes,
              'limitations':__doc__.strip(),'sample_rate':44100,'retained_engine_latency_samples':93,
              'method':{'window':'Hann periodogram','fft_size':65536,'stereo':'mean channel powers',
                        'windows_seconds':WINDOWS,'bands_hz':BANDS,
                        'global_centroid':'Welch nperseg8192, 20..16000Hz, first5s'},
              'cotton_patch':{'filter_cutoff':0,'filter_resonance':0,'filter_depth':39,
                              'filter_velocity_sensitivity':18,'filter_sustain':87,'filter_keyfollow':60,
                              'first_note_midi':48,'first_note_super_saw_hz':130.8128,'sine_about_hz':65.142},
              'mapping_sensitivity_octaves':{
                  'depth_10_to_12_peak':39*2/63,
                  'depth_10_to_12_sustain':39*2/63*87/127,
                  'velocity_100_to_127':18/63*(1-100/127)*8},
              'measured':measured,'baseline_velocity_sweep':velocities,
              'baseline_velocity_ranges':velocity_ranges,
              'baseline_velocity_100_matches_preserved':velocities[99]['wav_sha256']==sha(source/'septum-raw.wav'),
              'air_negative_control':{'depth_10_and_12_byte_identical':air_results['10']['wav_sha256']==air_results['12']['wav_sha256'],
                                      'renders':air_results,'filter_envelope_depth':0,'filter_velocity_sensitivity':0,
                                      'qualification':'Reconstructed opening MIDI, original published SysEx; equality is a DSP negative control, not a claim of hardware agreement.'}}
    (args.output/'brightness-controls.json').write_text(json.dumps(result,indent=2)+'\n')
    fig,axes = plt.subplots(1,3,figsize=(13,4),layout='constrained')
    axes[0].plot(range(1,128),[v['whole_excerpt_centroid_hz'] for v in velocities],label='Depth10, velocity sweep')
    for label,key,colour in [('Hardware','hardware','#222222'),('Depth12, velocity100','depth_12','#cb7030')]:
        axes[0].axhline(measured[key]['whole_excerpt_centroid_hz'],color=colour,ls='--',label=label)
    axes[0].set(xlabel='Uniform note velocity',ylabel='20Hz–16kHz power centroid / Hz',title='Whole five-second reconstruction')
    for ax,name in zip(axes[1:],('opening_note','held_chord')):
        metric='700_3000_over_200_700_db'
        ax.plot(range(1,128),[v['windows'][name][metric] for v in velocities])
        for label,key,colour in [('Hardware','hardware','#222222'),('Depth12','depth_12','#cb7030')]:
            ax.axhline(measured[key]['windows'][name][metric],color=colour,ls='--')
        ax.set(xlabel='Uniform note velocity',ylabel='700–3000Hz /200–700Hz power / dB',title=name.replace('_',' '))
    axes[0].legend(fontsize=8)
    for ax in axes: ax.grid(alpha=.2)
    fig.suptitle('Cotton Wool: fixed published patch and reconstructed MIDI; no quality score')
    fig.savefig(args.output/'brightness-controls.png',dpi=160)
    print(json.dumps({'measured':measured,'velocity_ranges':velocity_ranges,
                      'baseline_reproduced':result['baseline_velocity_100_matches_preserved'],
                      'air_identical':result['air_negative_control']['depth_10_and_12_byte_identical']},indent=2))


if __name__=='__main__':
    main()
