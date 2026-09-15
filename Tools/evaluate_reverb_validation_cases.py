#!/usr/bin/env python3
"""Evaluate frozen reverb-gain builds on independently transcribed new cases.

Case JSONs must fix their calibration boundary before candidate rendering.
Half return gain is the primary hypothesis; quarter gain is a sensitivity.
No MIDI, preset, gate, gain law or DSP parameter is optimized here.
"""
import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from types import SimpleNamespace

os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
import numpy as np
from scipy.io import wavfile
import compare_hardware as comparison
import assess_hardware_equivalence as assess

ROOT = Path(__file__).resolve().parents[1]
MODELS = ('gain-1', 'gain-0.5', 'gain-0.25')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=Path, action='append', required=True)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--models', type=Path, required=True,
                        help='Completed reverb-gain-candidates run directory')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--exploratory', action='store_true',
                        help='Label follow-up inputs chosen after earlier candidate results')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    catalog_path = ROOT/'Docs/fidelity/hardware-reference-catalog.json'
    catalog = json.loads(catalog_path.read_text())
    model_result = json.loads((args.models/'results.json').read_text())
    if model_result['protocol']['mode'] != 'gain' or model_result['protocol']['source_revision'] != 'b0f6c03':
        raise ValueError('Expected frozen b0f6c03 gain family')
    builds = {}
    for name in MODELS:
        directory = args.models/'builds'/name
        manifest_path = directory/'manifest.json'
        if sha(manifest_path) != model_result['build_manifest_sha256'][name]:
            raise ValueError('Model build manifest changed')
        manifest = json.loads(manifest_path.read_text())
        expected = {c['models'][name]['renderer_sha256'] for c in model_result['cases']}
        if len(expected) != 1 or sha(directory/'SeptumRenderMidi') not in expected:
            raise ValueError('Renderer identity changed')
        for filename, expected_hash in manifest['frozen_sha256'].items():
            if sha(directory/filename) != expected_hash:
                raise ValueError('Frozen build input changed: '+filename)
        builds[name] = dict(directory=str(directory.resolve()), renderer_sha256=sha(directory/'SeptumRenderMidi'),
                            manifest_sha256=sha(manifest_path))
    specs = []
    seen = set()
    for path in args.case:
        case = json.loads(path.read_text())
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', case['id']):
            raise ValueError('Invalid case identity')
        if case['id'] in seen:
            raise ValueError('Duplicate case identity')
        seen.add(case['id'])
        if case.get('midi_status') != 'reconstructed_not_original' or case.get('source_start_seconds', 0) != 0:
            raise ValueError('Expected original-clock reconstruction with all preceding events')
        cal = case['calibration_end_seconds']
        if not .1 <= cal < case['duration_seconds']-.2:
            raise ValueError('Invalid predeclared calibration boundary')
        target = out/(case['id']+'-frozen-reconstruction.json')
        shutil.copyfile(path, target)
        midi = target.with_suffix('.mid')
        comparison.write_midi(midi, case)
        if path.with_suffix('.mid').exists() and sha(midi) != sha(path.with_suffix('.mid')):
            raise ValueError('Reconstruction differs from the independently frozen MIDI')
        ref = next(r for r in catalog['recordings'] if r['id'] == case['reference_id'])
        bank = next(b for b in catalog['banks'] if b['id'] == ref['bank_id'])
        for asset in (ref, bank):
            if sha(args.sources/asset['local_filename']) != asset['sha256']:
                raise ValueError('Original source identity changed')
        data, member = comparison.read_bank(args.sources/bank['local_filename'])
        if member != bank['archive_member'] or hashlib.sha256(data).hexdigest() != bank['bank_sha256']:
            raise ValueError('Original bank identity changed')
        patch_name, blocks = comparison.parse_bank(data)[ref['patch_number']-1]
        patch_hash = hashlib.sha256(comparison.encode_syx(blocks)).hexdigest()
        extra = case.get('benchmark_protocol', {})
        if (patch_name != ref['patch_name']
                or patch_hash != case.get('unmodified_sysex_sha256', extra.get('patch_sha256'))
                or ref['sha256'] != case.get('original_mp3_sha256', extra.get('hardware_mp3_sha256'))):
            raise ValueError('Case identity differs from source-only reconstruction evidence')
        specs.append(dict(path=str(path.resolve()), frozen_path=str(target), sha256=sha(path),
                          midi_sha256=sha(midi), sysex_sha256=patch_hash, case=case))
    scope = ('Exploratory follow-up after earlier candidate outcomes. New inputs are fixed before their own scores; this is not independent confirmation or a replacement for the earlier cases.'
        if args.exploratory else 'Case selections and reconstructions fixed before these candidate scores. No new-case selection or parameter fitting.')
    protocol = dict(status=('exploratory_articulation_followup' if args.exploratory
                            else 'prospective_candidate_checks_with_reconstructed_inputs'),
        primary_hypothesis='gain-0.5', secondary_sensitivity='gain-0.25', baseline='gain-1',
        models=builds, cases=specs, model_result_sha256=sha(args.models/'results.json'),
        catalog_sha256=sha(catalog_path),
        transformation='Primary: one production-only prefix lag bounded50ms and gain, frozen across models. Candidate-prefix RMS gains are a separately reported sensitivity. Same evaluation supports for all models.',
        scope=scope+' Original performance MIDI, gates, velocity and recorded patch revision remain unauthenticated.',
        tools={name: sha(ROOT/'Tools'/name) for name in ('evaluate_reverb_validation_cases.py',
               'compare_hardware.py', 'assess_hardware_equivalence.py', 'render_midi.py', 'extract_reference_patch.py')})
    save(out/'protocol-before-rendering.json', protocol)
    shutil.copyfile(__file__, out/Path(__file__).name)
    corpus = out/'baseline-corpus'
    corpus.mkdir()
    records, sections = [], []
    for item in specs:
        case = item['case']
        meta = comparison.render_case(Path(item['frozen_path']),
            SimpleNamespace(renderer=args.models/'builds/gain-1/SeptumRenderMidi',
                            sources=args.sources, output=corpus), catalog)
        source = corpus/case['id']
        if (sha(source/'original-patch.syx') != item['sysex_sha256']
                or sha(source/'reconstructed-performance.mid') != item['midi_sha256']):
            raise ValueError('Rendered inputs differ from pre-render protocol')
        directory = out/'cases'/case['id']
        directory.mkdir(parents=True)
        sr, hardware = assess.read_audio(source/'hardware-excerpt-raw.wav')
        rate, base_full = assess.read_audio(source/'septum-raw.wav')
        n = meta['comparison_frames']
        if sr != 44100 or rate != sr or len(hardware) != n or len(base_full) < n:
            raise ValueError('Invalid baseline coverage')
        cal = round(case['calibration_end_seconds']*sr)
        transform = assess.fit_transform(hardware, base_full[:n], sr, cal, .05)
        lag = transform['candidate_lag_samples']
        ca, cb = max(0, -lag), min(cal, cal-lag)
        start, end = max(cal, cal-lag), min(n, n-lag)
        record = dict(id=case['id'], reconstruction_sha256=item['sha256'],
            comparison_sha256=sha(source/'comparison.json'), comparison=meta,
            calibration=transform, calibration_reference_samples=[ca, cb],
            calibration_candidate_samples=[ca+lag, cb+lag], evaluation_samples=[start, end], models={})
        listening = {'hardware': hardware[start:end]}
        for name in MODELS:
            wav = directory/(name+'.wav')
            if name == 'gain-1':
                shutil.copyfile(source/'septum-raw.wav', wav)
                shutil.copyfile(source/'septum-raw.render.json', wav.with_suffix('.render.json'))
                command = None
            else:
                command = [sys.executable, str(ROOT/'Tools/render_midi.py'),
                    '--renderer', str((args.models/'builds'/name/'SeptumRenderMidi').resolve()),
                    '--midi', str(source/'reconstructed-performance.mid'),
                    '--syx', str(source/'original-patch.syx'), '--output', str(wav),
                    '--tail', '2', '--tempo-policy', 'preserve-patch', '--master-level', '100']
                subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
            rate, c = assess.read_audio(wav)
            receipt = json.loads(wav.with_suffix('.render.json').read_text())
            if (rate != sr or c.shape != base_full.shape or not np.isfinite(c).all()
                    or receipt['ignored_events'] or receipt['output']['active_voices_at_end']
                    or receipt['inputs']['renderer']['sha256'] != builds[name]['renderer_sha256']
                    or receipt['inputs']['midi']['sha256'] != item['midi_sha256']
                    or receipt['inputs']['sysex']['sha256'] != item['sysex_sha256']
                    or receipt['output']['sha256'] != sha(wav)):
                raise ValueError('Candidate render guard failed')
            gain = assess.rms(hardware[ca:cb])/assess.rms(c[ca+lag:cb+lag])
            fixed = c[start+lag:end+lag]*transform['candidate_gain']
            fitted = c[start+lag:end+lag]*gain
            record['models'][name] = dict(wav_sha256=sha(wav), receipt_sha256=sha(wav.with_suffix('.render.json')),
                command=command, fitted_prefix_gain=gain, peak=float(abs(c).max()), finite=True,
                samples_at_or_above_full_scale=int(np.count_nonzero(abs(c)>=1)), active_voices_at_end=0,
                measurements=assess.measure(hardware[start:end], fixed, sr),
                candidate_prefix_gain_sensitivity=assess.measure(hardware[start:end], fitted, sr))
            diagnostics = {}
            for region, bounds in case.get('benchmark_protocol', {}).get('diagnostic_regions_seconds', {}).items():
                a, b = max(start, round(bounds[0]*sr)), min(end, round(bounds[1]*sr))
                if b-a < sr/4:
                    raise ValueError('Predeclared diagnostic region too short after alignment')
                diagnostics[region] = dict(reference_samples=[a, b], candidate_samples=[a+lag, b+lag],
                    measurements=assess.measure(hardware[a:b], c[a+lag:b+lag]*transform['candidate_gain'], sr))
            record['models'][name]['predeclared_diagnostics'] = diagnostics
            listening[name] = fixed
        scale = min(.1/assess.rms(listening['hardware']),
                    .98/max(float(abs(y).max()) for y in listening.values()))
        for name, y in listening.items():
            wavfile.write(directory/(name+'-listen.wav'), sr, (y*scale).astype(np.float32))
        record['listening_common_gain'] = scale
        save(directory/'result.json', record)
        records.append(record)
        players = ''.join(f'<p>{html.escape(name)}<br><audio controls preload="none" src="cases/{case["id"]}/{name}-listen.wav"></audio></p>' for name in listening)
        sections.append(f'<section><h2>{html.escape(case["title"])}</h2>{players}</section>')
        print(case['id'], ' '.join(f'{name}={row["measurements"]["summary"]["spectral_convergence_mean"]:.5f}'
              for name, row in record['models'].items()), flush=True)
    save(out/'results.json', dict(protocol=protocol, cases=records))
    (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>New reverb-gain checks</title>'
        '<style>body{font:16px system-ui;max-width:900px;margin:40px auto;padding:20px}section{border-top:1px solid #bbb;margin-top:32px}audio{width:100%}</style>'
        '<h1>Reverb return level: '+('exploratory follow-up' if args.exploratory else 'new preset checks')+'</h1><p>'+html.escape(scope)+' '
        'Gain1 is the previous return, gain.5 is half return, gain.25 a sensitivity. '
        'Listening contains later evaluation only, using the same production-prefix timing and gain for every model. '
        'Original performance and exact recorded patch revision remain unverified.</p>'+''.join(sections))
    print(out/'results.json')


if __name__ == '__main__':
    main()
