#!/usr/bin/env python3
"""Measure how unknown velocity affects the reconstructed hardware comparisons.

Sweep a uniform note-on velocity across 1..127 with fixed notes, gates, patch
bytes and engine settings. This is a model sensitivity experiment, not recovery
of the hardware performance, and cannot bound arbitrary per-note velocities,
controllers, alternative voicings or recording processing.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
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


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def measure(audio, rate):
    frequencies, psd = signal.welch(audio, rate, nperseg=8192, axis=0)
    power = psd.mean(axis=1)
    audible = (frequencies >= 20) & (frequencies <= 16000)
    sub = (frequencies >= 20) & (frequencies < 40)
    above_sub = (frequencies >= 40) & (frequencies <= 16000)
    low = (frequencies >= 20) & (frequencies < 200)
    high = (frequencies >= 200) & (frequencies <= 16000)
    ratio_db = lambda a,b: float(10*np.log10(max(power[a].sum(), 1e-30)/max(power[b].sum(), 1e-30)))
    return {'centroid_20_16000_hz': float((frequencies[audible]*power[audible]).sum()/power[audible].sum()),
            'sub_to_above_sub_db': ratio_db(sub, above_sub),
            'above_200_to_below_200_db': ratio_db(high, low),
            'rms_dbfs': float(20*np.log10(max(np.sqrt(np.mean(audio.astype(float)**2)),1e-30)))}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--comparison', type=Path, required=True, help='existing compare_hardware.py output')
    p.add_argument('--renderer', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True, help='new output directory')
    p.add_argument('--jobs', type=int, default=4)
    args = p.parse_args()
    if not 1 <= args.jobs <= 16:
        p.error('--jobs must be 1..16')
    args.output.mkdir(parents=True, exist_ok=False)
    binary = args.renderer.resolve()
    binary_hash = sha(binary)
    references = []
    for manifest_path in sorted(args.comparison.glob('*/comparison.json')):
        original = json.loads(manifest_path.read_text())
        directory = manifest_path.parent
        patch = directory/'original-patch.syx'
        hardware = directory/'hardware-excerpt-raw.wav'
        for source in (patch, hardware):
            if sha(source) != original['files'][source.name]:
                raise ValueError(f'Comparison source has changed: {source}')
        rate, audio = wavfile.read(hardware)
        if rate != 44100 or not np.isfinite(audio).all():
            raise ValueError('Expected finite 44.1 kHz comparison audio')
        references.append({'id':original['case']['id'], 'case': original['case'],
                           'patch': patch, 'patch_sha256':sha(patch),
                           'comparison_manifest_sha256':sha(manifest_path),
                           'hardware':measure(audio, rate),
                           'baseline_raw_render_sha256':original['files']['septum-raw.wav']})
    if not references:
        p.error('No comparison cases found')

    def run(job):
        reference, velocity = job
        case = json.loads(json.dumps(reference['case']))
        for note in case['notes']:
            note['velocity'] = velocity
        with tempfile.TemporaryDirectory(prefix='septum-velocity-') as temporary:
            directory = Path(temporary)
            midi, wav = directory/'performance.mid', directory/'take.wav'
            write_midi(midi,case)
            command = [sys.executable, str(ROOT/'Tools/render_midi.py'), '--renderer',str(binary),
                       '--midi',str(midi), '--syx',str(reference['patch']), '--output',str(wav),
                       '--tempo-policy','preserve-patch','--tail','2','--master-level','100']
            result = subprocess.run(command,capture_output=True,text=True)
            if result.returncode:
                raise RuntimeError(result.stderr)
            rate, audio = wavfile.read(wav)
            if not np.isfinite(audio).all():
                raise ValueError('Non-finite sensitivity render')
            values = measure(audio[:round(case['duration_seconds']*rate)], rate)
            return {'case':reference['id'], 'velocity':velocity, **values,
                    'midi_sha256':sha(midi), 'raw_render_sha256':sha(wav)}

    jobs = [(reference, velocity) for reference in references for velocity in range(1,128)]
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        rows = list(pool.map(run,jobs))
    if sha(binary) != binary_hash:
        raise ValueError('Renderer changed during the experiment; reject the run')
    for reference in references:
        if sha(reference['patch']) != reference['patch_sha256']:
            raise ValueError('Patch changed during the experiment')
    summaries = []
    fig, axes = plt.subplots(len(references),2,figsize=(11,3*len(references)),layout='constrained',squeeze=False)
    for index, reference in enumerate(references):
        selected=[row for row in rows if row['case']==reference['id']]
        summary={k:v for k,v in reference.items() if k not in ('patch','case')}
        summary['velocity_100_matches_prior_render'] = selected[99]['raw_render_sha256']==reference['baseline_raw_render_sha256']
        summary['uniform_velocity_ranges'] = {metric:{'minimum':min(row[metric] for row in selected),
                                                     'maximum':max(row[metric] for row in selected)}
                                              for metric in ('centroid_20_16000_hz','sub_to_above_sub_db','above_200_to_below_200_db')}
        summaries.append(summary)
        for ax, metric, label in zip(axes[index],('centroid_20_16000_hz','sub_to_above_sub_db'),
                                    ('Power centroid 20 Hz–16 kHz / Hz','20–40 Hz / 40 Hz–16 kHz / dB')):
            ax.plot([row['velocity'] for row in selected],[row[metric] for row in selected],color='#386a98',label='Septum: uniform velocity sweep')
            ax.axhline(reference['hardware'][metric],color='#222222',linestyle='--',label='Hardware excerpt')
            ax.set(title=reference['id'],xlabel='Uniform note-on velocity',ylabel=label,xlim=(1,127))
            ax.grid(alpha=.2)
        axes[index,0].legend(frameon=False,fontsize=8)
    fig.suptitle('Velocity sensitivity — fixed reconstructed notes and unchanged presets',fontsize=13)
    fig.savefig(args.output/'velocity-sensitivity.png',dpi=150)
    plt.close(fig)
    with (args.output/'velocity-sensitivity.csv').open('w',newline='') as output:
        writer=csv.DictWriter(output,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    manifest={'schema_version':1,'experiment':'uniform_velocity_sweep_1_to_127',
              'limitations':__doc__.strip(), 'renderer_sha256':binary_hash,
              'tool_sha256':sha(Path(__file__)), 'comparison_tool_sha256':sha(ROOT/'Tools/compare_hardware.py'),
              'midi_renderer_tool_sha256':sha(ROOT/'Tools/render_midi.py'),
              'settings':{'sample_rate':44100,'master_level':100,'tempo_policy':'preserve-patch','tail_seconds':2},
              'render_count':len(rows),'summaries':summaries}
    (args.output/'velocity-sensitivity.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))


if __name__=='__main__':
    main()
