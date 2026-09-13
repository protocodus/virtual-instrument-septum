#!/usr/bin/env python3
"""Isolate filter contributions to the reconstructed SH-201 comparisons.

Every changed preset is a labeled diagnostic intervention, not the published
preset. Notes, gates, velocity and all other patch bytes stay fixed. This does
not infer hardware parameters from a whole-excerpt brightness score.
"""
import argparse
import csv
import hashlib
import html
import json
from pathlib import Path
import subprocess
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal
from scipy.io import wavfile

from compare_hardware import audio_stats, listening_copy

ROOT = Path(__file__).resolve().parents[1]
VARIANTS = ('unchanged', 'filter-bypass', 'cutoff-plus-12', 'cutoff-plus-24',
            'cutoff-plus-36', 'slope-12', 'envelope-disabled', 'envelope-held-at-peak')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def modify_patch(source, variant):
    result = bytearray()
    changes = []
    for message in source.split(b'\xf7'):
        if not message:
            continue
        frame = bytearray(message + b'\xf7')
        if frame[:2] != b'\xf0A' or frame[9] > 21 or frame[10] != 0:
            raise ValueError('Expected complete native temporary patch blocks')
        if frame[9] in (1, 2):
            field, offset, value = None, 0, 0
            if variant == 'filter-bypass':
                field, offset, value = 'filter_type', 0x11, 0
            elif variant.startswith('cutoff-plus-'):
                field, offset = 'cutoff', 0x13
                value = min(127, frame[11+offset] + int(variant.rsplit('-', 1)[1]))
            elif variant == 'slope-12':
                field, offset, value = 'filter_slope', 0x12, 0
            elif variant == 'envelope-disabled':
                field, offset, value = 'filter_envelope_depth_raw', 0x1b, 64
            elif variant == 'envelope-held-at-peak':
                field, offset, value = 'filter_envelope_sustain', 0x19, 127
            elif variant != 'unchanged':
                raise ValueError('Unknown intervention')
            if field is not None:
                changes.append({'tone': 'upper' if frame[9] == 1 else 'lower',
                                'field': field, 'before': frame[11+offset], 'after': value})
                frame[11+offset] = value
                frame[-2] = (-sum(frame[7:-2])) & 127
        result.extend(frame)
    return bytes(result), changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comparison', required=True, type=Path)
    parser.add_argument('--renderer', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--variant', action='append', choices=VARIANTS)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    binary = args.renderer.resolve()
    binary_hash = sha(binary)
    rows, cases, sections = [], [], []
    for case_id in ('moogie-1-octave-revision', 'dist-bs-1', 'cotton-wool'):
        source = args.comparison/case_id
        original = json.loads((source/'comparison.json').read_text())
        for name in ('original-patch.syx', 'reconstructed-performance.mid', 'hardware-excerpt-raw.wav'):
            if sha(source/name) != original['files'][name]:
                raise ValueError(f'Changed comparison input: {source/name}')
        out = args.output/case_id
        out.mkdir()
        rate, hardware = wavfile.read(source/'hardware-excerpt-raw.wav')
        length = round(original['case']['duration_seconds'] * rate)
        hardware_listen, _ = listening_copy(hardware)
        wavfile.write(out/'hardware-listen.wav', rate, hardware_listen.astype(np.float32))
        fig, ax = plt.subplots(figsize=(11, 5), layout='constrained')
        spectra = []
        def spectrum(y, label):
            f, power = signal.welch(y, rate, nperseg=8192, axis=0)
            power = power.mean(axis=1)
            ax.semilogx(f[1:], 10*np.log10(np.maximum(power[1:], 1e-30)), label=label)
            spectra.extend({'series':label, 'frequency_hz':float(x), 'power_density':float(p)}
                           for x,p in zip(f,power))
        spectrum(hardware_listen, 'Hardware reference')
        variants = []
        player = [f'<h2>{html.escape(original["case"]["title"])}</h2>',
                  '<p>Hardware reference</p><audio controls src="'+case_id+'/hardware-listen.wav"></audio>']
        for variant in args.variant or VARIANTS:
            patch, changes = modify_patch((source/'original-patch.syx').read_bytes(), variant)
            syx, wav = out/(variant+'.syx'), out/(variant+'.wav')
            syx.write_bytes(patch)
            command = [sys.executable, str(ROOT/'Tools/render_midi.py'), '--renderer', str(binary),
                       '--midi', str(source/'reconstructed-performance.mid'), '--syx', str(syx),
                       '--output', str(wav), '--tempo-policy', 'preserve-patch', '--strict']
            subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
            sr, full = wavfile.read(wav)
            if sr != rate or not np.isfinite(full).all() or len(full) < length:
                raise ValueError('Invalid diagnostic render')
            y = full[:length]
            matched, gain = listening_copy(y)
            if np.max(np.abs(matched)) >= 1:
                raise ValueError('RMS-matched diagnostic exceeds full scale')
            wavfile.write(out/(variant+'-listen.wav'), rate, matched.astype(np.float32))
            stats = audio_stats(y, rate)
            rows.append({'case':case_id, 'variant':variant, **stats})
            variants.append({'variant':variant, 'changes':changes, 'statistics':stats,
                             'patch_sha256':sha(syx), 'raw_render_sha256':sha(wav),
                             'listening_gain':gain, 'command':command})
            if variant in ('unchanged', 'filter-bypass', 'cutoff-plus-24', 'envelope-held-at-peak'):
                spectrum(matched, variant)
            player.append('<p>'+html.escape(variant)+'</p><audio controls src="'+case_id+'/'+variant+'-listen.wav"></audio>')
        ax.set(xlim=(20, 16000), ylim=(-110,-20), xlabel='Frequency / Hz', ylabel='Power density / dBFS/Hz',
               title=case_id+' — diagnostic preset changes, fixed reconstructed MIDI')
        ax.legend(frameon=False,fontsize=9); ax.grid(alpha=.2)
        fig.savefig(out/'filter-interventions.png',dpi=150); plt.close(fig)
        with (out/'spectrum.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(spectra[0])); w.writeheader();w.writerows(spectra)
        cases.append({'id':case_id, 'baseline_manifest_sha256':sha(source/'comparison.json'),
                      'hardware_statistics':audio_stats(hardware,rate), 'variants':variants})
        player.append('<img alt="Diagnostic spectra" src="'+case_id+'/filter-interventions.png">')
        sections.append('<section>'+''.join(player)+'</section>')
    if sha(binary) != binary_hash:
        raise ValueError('Renderer changed during the experiment')
    report={'schema_version':1,'claim':__doc__.strip(),'renderer_sha256':binary_hash,
            'tool_sha256':sha(Path(__file__)), 'cases':cases,
            'listening_method':'Per-excerpt scalar RMS matching to -20dBFS; no EQ, time alignment or fades.'}
    (args.output/'filter-interventions.json').write_text(json.dumps(report,indent=2)+'\n')
    with (args.output/'filter-interventions.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (args.output/'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Filter isolation</title>'
        '<style>body{font:17px/1.5 system-ui;max-width:1050px;margin:40px auto;padding:20px}audio{width:100%}img{width:100%}section{border-top:1px solid #bbb;margin-top:40px}</style>'
        '<h1>Filter isolation experiments</h1><p>Diagnostic preset changes are labeled below. These are not same-preset hardware comparisons; the reconstructed performance MIDI is held fixed. Listening levels use scalar RMS matching only.</p>'
        + ''.join(sections)+'</html>')
    print(args.output/'filter-interventions.json')


if __name__ == '__main__':
    main()
