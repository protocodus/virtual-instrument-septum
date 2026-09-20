#!/usr/bin/env python3
"""Compare two frozen-model runs against the same reconstructed hardware cases.

This reports broad spectral residuals, not a perceptual or exact-input fidelity
score. No alignment, EQ, preset edits or performance fitting is performed.
"""
import argparse
import hashlib
import html
import json
from pathlib import Path
import re
import shutil

import numpy as np
from scipy import signal
from scipy.io import wavfile

from compare_hardware import validate_audio


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def band_shape(audio, sample_rate):
    """Stereo power in 32 fixed bands, normalized within 25–12500 Hz."""
    validate_audio(audio)
    f, power = signal.welch(audio.astype(np.float64), sample_rate,
                            nperseg=min(8192, len(audio)), axis=0)
    power = power.mean(axis=1)
    edges = np.geomspace(25, 12500, 33)
    bands = np.array([power[(f >= lo) & (f < hi)].sum()
                      for lo, hi in zip(edges[:-1], edges[1:])])
    if not np.isfinite(bands).all() or bands.sum() <= 0:
        raise ValueError('No usable energy in analysis bands')
    return bands / bands.sum()


def spectral_residual(hardware, rendered):
    # Admit bands based on the reference alone. Exclude hardware bands below
    # -50 dB relative to its strongest band: MP3 noise is not a timbre target.
    included = hardware >= hardware.max() * 1e-5
    difference = 10 * np.log10(np.maximum(rendered, 1e-12)
                               / np.maximum(hardware, 1e-12))
    return {'band_shape_rmse_db': float(np.sqrt(np.mean(difference[included] ** 2))),
            'included_band_count': int(included.sum()),
            'included_bands': included.tolist(), 'difference_db': difference.tolist()}


def load_run(directory):
    rows = json.loads((directory / 'summary.json').read_text())
    result = {}
    run_identity = None
    for row in rows:
        key = row['case']['id']
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', key):
            raise ValueError('Invalid comparison case id')
        if key in result:
            raise ValueError('Duplicate case: ' + key)
        if json.loads((directory / key / 'comparison.json').read_text()) != row:
            raise ValueError('Summary disagrees with comparison provenance: ' + key)
        if row['case'].get('midi_status') != 'reconstructed_not_original':
            raise ValueError('Expected explicitly reconstructed MIDI: ' + key)
        provenance = row.get('renderer_provenance', {})
        if not provenance.get('build_sources_verified'):
            raise ValueError('Use frozen, manifest-verified candidate renderers: ' + key)
        build = provenance.get('build_manifest', {})
        if (build.get('status') != 'complete' or build.get('experimental') is not True
                or build.get('hardware_match_claim') is not False
                or build.get('frozen_inputs_verified') is not True
                or build.get('renderer', {}).get('sha256') != provenance.get('sha256')):
            raise ValueError('Invalid frozen renderer provenance: ' + key)
        identity = (provenance['sha256'], provenance.get('build_manifest_sha256'))
        if run_identity is not None and identity != run_identity:
            raise ValueError('A comparison run must use one frozen renderer')
        run_identity = identity
        for name, expected in row['files'].items():
            if Path(name).name != name or name in ('.', '..'):
                raise ValueError('Invalid comparison artifact filename')
            # File identities in compare_hardware are SHA-256 strings.
            if sha(directory / key / name) != expected:
                raise ValueError('Comparison artifact hash mismatch: ' + name)
        required = ('original-patch.syx', 'reconstructed-performance.mid',
                    'hardware-excerpt-raw.wav', 'septum-raw.wav', 'septum-raw.render.json')
        if any(name not in row['files'] for name in required):
            raise ValueError('Missing required comparison artifact: ' + key)
        render = json.loads((directory / key / 'septum-raw.render.json').read_text())
        if (render['inputs']['renderer']['sha256'] != provenance['sha256']
                or render['inputs']['midi']['sha256'] != row['files']['reconstructed-performance.mid']
                or render['inputs']['sysex']['sha256'] != row['files']['original-patch.syx']
                or render['output']['sha256'] != row['files']['septum-raw.wav']
                or render.get('degraded_replay') is not False
                or render['output']['latency_samples'] != row['retained_engine_latency_samples']):
            raise ValueError('Render identity or replay qualification mismatch: ' + key)
        result[key] = row
    return result


def evaluate(baseline, candidate, output):
    before, after = load_run(baseline), load_run(candidate)
    if before.keys() != after.keys() or not before:
        raise ValueError('Both runs must contain exactly the same nonempty case set')
    if output.exists() or output.is_symlink():
        raise ValueError('Output exists; choose a new directory')
    results = []
    for key, base in before.items():
        trial = after[key]
        for field in ('case', 'reference', 'bank', 'hardware_start_sample',
                      'comparison_frames', 'retained_engine_latency_samples'):
            if base[field] != trial[field]:
                raise ValueError('Comparison input mismatch: ' + key + '/' + field)
        for name in ('original-patch.syx', 'reconstructed-performance.mid',
                     'hardware-excerpt-raw.wav'):
            if base['files'][name] != trial['files'][name]:
                raise ValueError('Paired artifact mismatch: ' + key + '/' + name)
        renders = [json.loads((root / key / 'septum-raw.render.json').read_text())
                   for root in (baseline, candidate)]
        if renders[0]['settings'] != renders[1]['settings']:
            raise ValueError('Paired render settings differ: ' + key)
        paths = [baseline / key / 'hardware-excerpt-raw.wav',
                 baseline / key / 'septum-raw.wav', candidate / key / 'septum-raw.wav']
        arrays, rates = [], []
        for path in paths:
            rate, data = wavfile.read(path)
            data = data[:base['comparison_frames']]
            if len(data) != base['comparison_frames']:
                raise ValueError('Truncated audio: ' + str(path))
            validate_audio(data)
            arrays.append(data)
            rates.append(rate)
        if len(set(rates)) != 1:
            raise ValueError('Sample rates differ')
        if any(render['settings']['sample_rate'] != rates[0] for render in renders):
            raise ValueError('Audio sample rate disagrees with render settings: ' + key)
        shapes = [band_shape(data, rates[0]) for data in arrays]
        result = {'id': key, 'title': base['case']['title'],
                  'qualification': base['qualification'],
                  'source_page': base['reference']['source_page_url'],
                  'before': spectral_residual(shapes[0], shapes[1]),
                  'candidate': spectral_residual(shapes[0], shapes[2]),
                  'raw_render_identical': base['files']['septum-raw.wav'] == trial['files']['septum-raw.wav'],
                  'comparison_sha256': {'baseline': sha(baseline / key / 'comparison.json'),
                                        'candidate': sha(candidate / key / 'comparison.json')}}
        result['delta_rmse_db'] = result['candidate']['band_shape_rmse_db'] - result['before']['band_shape_rmse_db']
        results.append((result, arrays, rates[0]))
    # Recheck after analysis: a changed artifact must not be silently assigned
    # the identity that was verified before its PCM was read.
    if load_run(baseline) != before or load_run(candidate) != after:
        raise ValueError('Comparison run changed during matrix analysis')
    output.mkdir(parents=True)
    for result, arrays, rate in results:
        target = output / result['id']
        target.mkdir()
        # Constant RMS gain per track, with common three-way peak headroom.
        gains = [.1 / np.sqrt(np.mean(data.astype(np.float64) ** 2)) for data in arrays]
        common = min(1., .95 / max(np.max(np.abs(data)) * gain for data, gain in zip(arrays, gains)))
        result['listening_gains'] = dict(zip(('hardware', 'baseline', 'candidate'),
                                             [float(g * common) for g in gains]))
        for name, data, gain in zip(('hardware', 'baseline', 'candidate'), arrays, gains):
            wavfile.write(target / (name + '.wav'), rate, (data * gain * common).astype(np.float32))
        for name in ('original-patch.syx', 'reconstructed-performance.mid'):
            shutil.copyfile(baseline / result['id'] / name, target / name)
        result['listening_sha256'] = {p.name: sha(p) for p in target.glob('*.wav')}
    report = {'schema_version': 1, 'experimental': True, 'hardware_match_claim': False,
              'method': 'Whole-excerpt stereo Welch power; 32 geometric bands, 25–12500 Hz; normalize band sums; floor normalized powers at 1e-12; unweighted dB RMSE on reference bands within 50 dB of peak.',
              'limitations': 'Reconstructed MIDI, unknown velocities/controllers and recording processing. Broad spectral residual only; this is not a perceptual score, a null test or proof of a globally correct model.',
              'baseline_summary_sha256': sha(baseline / 'summary.json'),
              'candidate_summary_sha256': sha(candidate / 'summary.json'),
              'models': {'baseline': next(iter(before.values()))['renderer_provenance'],
                         'candidate': next(iter(after.values()))['renderer_provenance']},
              'cases': [r for r, _, _ in results]}
    (output / 'matrix.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    write_page(report, output)
    return report


def write_page(report, output):
    cards = []
    for row in report['cases']:
        key = row['id']
        before = row['before']['band_shape_rmse_db']
        after = row['candidate']['band_shape_rmse_db']
        state = 'Identical render' if row['raw_render_identical'] else f'Spectral residual: {before:.2f} → {after:.2f} dB'
        buttons = ''.join(f'<button data-track="{track}">{label}</button>' for track, label in
                          [('hardware', 'Roland hardware'), ('baseline', 'Current Septum'), ('candidate', 'Experimental model')])
        cards.append(f'''<section data-case="{key}"><h2>{html.escape(row['title'])}</h2>
<p>{state}</p><div>{buttons}<button data-stop>Stop</button></div>
<audio controls preload="metadata" src="{key}/hardware.wav"></audio><p role="status"></p>
<p><a href="{key}/reconstructed-performance.mid">Estimated MIDI</a> ·
<a href="{key}/original-patch.syx">Published preset</a> ·
<a href="{html.escape(row['source_page'], quote=True)}">Reference source</a></p></section>''')
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SH-201 model comparison</title><style>
body{max-width:1020px;margin:40px auto;padding:0 24px;background:#f6f4ee;color:#202c2b;font:17px/1.5 system-ui}
h1{font-size:38px;line-height:1.15}h2{font-size:23px}a{color:#24665e}section{border-top:1px solid #bdc8c2;margin-top:30px;padding-top:18px}
button{padding:9px 14px;margin:4px;border:1px solid #617971;border-radius:6px;background:white;font:inherit;cursor:pointer}
button[aria-pressed=true]{background:#245f57;color:white}audio{width:100%;margin-top:14px}.notice{padding:16px;background:#e3eae3;border-radius:8px}
</style><h1>SH-201 model comparison</h1><p class="notice"><strong>Experimental model. All MIDI is estimated; no original performance MIDI.</strong>
Each recording is associated with a named published preset; the exact recorded revision is unverified.
Unknown performance controls and recording processing remain possible causes of differences.</p>
<p>Switch between hardware, current Septum and the candidate at the same playback position. Each clip uses scalar RMS matching only.
Lower spectral residual means closer broad band balance for this excerpt. It does not measure overall authenticity.</p>
<p><a href="matrix.json">Measurements and provenance</a></p>''' + ''.join(cards) + '''
<script>let generation=0;document.querySelectorAll('section').forEach(section=>{
const audio=section.querySelector('audio'),status=section.querySelector('[role=status]');
const clear=()=>section.querySelectorAll('[data-track]').forEach(b=>b.setAttribute('aria-pressed','false'));
audio.addEventListener('play',()=>document.querySelectorAll('audio').forEach(a=>{if(a!==audio)a.pause()}));
audio.addEventListener('ended',clear);
section.querySelectorAll('[data-track]').forEach(button=>button.onclick=()=>{
const position=audio.ended?0:audio.currentTime, request=++generation;
document.querySelectorAll('audio').forEach(a=>{a.pause();a.onloadedmetadata=null});
document.querySelectorAll('[data-track]').forEach(b=>b.setAttribute('aria-pressed','false'));
button.setAttribute('aria-pressed','true');status.textContent='';
audio.onloadedmetadata=()=>{if(request!==generation)return;audio.currentTime=Math.min(position,audio.duration||0);
audio.play().catch(e=>{if(request===generation)status.textContent=e.message})};
audio.onerror=()=>{status.textContent='Audio could not be decoded.'};
audio.src=section.dataset.case+'/'+button.dataset.track+'.wav'});
section.querySelector('[data-stop]').onclick=()=>{++generation;audio.onloadedmetadata=null;audio.pause();audio.currentTime=0;clear()};
});</script></html>'''
    (output / 'index.html').write_text(page)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = evaluate(args.baseline, args.candidate, args.output)
    for row in report['cases']:
        print(f"{row['id']}: {row['before']['band_shape_rmse_db']:.3f} -> {row['candidate']['band_shape_rmse_db']:.3f} dB; identical={row['raw_render_identical']}")
    print(args.output / 'index.html')


if __name__ == '__main__':
    main()
