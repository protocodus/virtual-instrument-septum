#!/usr/bin/env python3
"""Audit frozen triangle-wave candidates on Dist and Moogie harmonic families.

Uses the unchanged named-preset recordings and reconstructed MIDI. Frequencies
are nuisance measurements, not MIDI edits. No time alignment, EQ or amplitude
fit is allowed. The result does not establish hardware oscillator phase.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
import numpy as np
from scipy.io import wavfile
from scipy.optimize import minimize_scalar

from analyze_moogie_oscillator_shape import fit_harmonics, NOTES
from compare_hardware import renderer_provenance, validate_audio
from evaluate_timbre_matrix import load_run

GROUPS = {'H2-H8/H1': (range(2, 9), 1),
          'odd_H3_H5_H7/H1': ((3, 5, 7), 1),
          'even_H4_H6_H8/H2': ((4, 6, 8), 2)}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def measure(path, case, latency):
    input_sha = sha(path)
    sr, audio = wavfile.read(path)
    validate_audio(audio)
    if sr != 44100:
        raise ValueError('This audit expects 44.1 kHz')
    mid = audio.mean(axis=1)
    rows = []
    if case['id'] == 'moogie-1':
        if any(not any(n['note'] == 39 and n['on'] == on and n['off'] == off
                       for n in case['notes']) for on, off in NOTES):
            raise ValueError('Moogie diagnostic intervals disagree with case events')
        notes = [(on, off, 38.5) for on, off in NOTES]
    else:
        # Correct physical WIDE-off coarse range: raw -36 = -12 semitones.
        notes = [(n['on'], n['off'], 440 * 2 ** ((n['note'] - 12 - 69) / 12))
                 for n in case['notes']]
    for index, (on, off, nominal) in enumerate(notes):
        fit = minimize_scalar(lambda f: fit_harmonics(mid, sr,
            (on + off + .01) / 2 + latency, off - on - .07, f)['fit_residual'],
            bounds=(nominal * .97, nominal * 1.03), method='bounded')
        centers = ([on + t for t in np.arange(.06, .291, .01)]
                   if case['id'] == 'moogie-1' else [on + .075, off - .065])
        width = .06 if case['id'] == 'moogie-1' else .08
        for shift in (-.01, 0, .01):
            for center in centers:
                for channel, signal in [('mid', mid), ('left', audio[:, 0]),
                                        ('right', audio[:, 1])]:
                    observation = fit_harmonics(signal, sr, center + latency + shift,
                                                width, float(fit.x))
                    rows.append(dict(note=index, center_seconds=float(center),
                        shift_seconds=shift, channel=channel, frequency_hz=float(fit.x),
                        **observation))
    if sha(path) != input_sha:
        raise ValueError('Audio changed during measurement')
    return {'path': str(path), 'sha256': input_sha, 'rows': rows}


def compare(hardware, rendered):
    if len(hardware['rows']) != len(rendered['rows']):
        raise ValueError('Unmatched observations')
    errors = []
    for a, b in zip(hardware['rows'], rendered['rows']):
        keys = ('note', 'center_seconds', 'shift_seconds', 'channel')
        if any(a[k] != b[k] for k in keys):
            raise ValueError('Observation window mismatch')
        row = {k: a[k] for k in keys}
        for name, (harmonics, denominator) in GROUPS.items():
            h = np.array(list(harmonics)) - 1
            x, y = np.maximum(a['amplitude'], 1e-15), np.maximum(b['amplitude'], 1e-15)
            error = 20 * np.log10(y[h] / y[denominator - 1]) - 20 * np.log10(x[h] / x[denominator - 1])
            row[name] = float(np.mean(error ** 2))
        errors.append(row)
    result = []
    for note in sorted({r['note'] for r in errors}):
        for shift in (-.01, 0, .01):
            for channel in ('mid', 'left', 'right'):
                group = [r for r in errors if r['note'] == note and
                         r['shift_seconds'] == shift and r['channel'] == channel]
                result.append(dict(note=note, shift_seconds=shift, channel=channel,
                    **{k: float(np.sqrt(np.mean([r[k] for r in group]))) for k in GROUPS}))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-comparison', required=True, type=Path)
    parser.add_argument('--sweep', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    cases = load_run(args.baseline_comparison)
    sweep = json.loads((args.sweep / 'results.json').read_text())
    result = {'schema_version': 1, 'script_sha256': sha(Path(__file__)),
              'harmonic_estimator_sha256': sha(Path(__file__).with_name('analyze_moogie_oscillator_shape.py')),
              'status': 'experimental; no hardware match or production recommendation',
              'sweep_sha256': sha(args.sweep / 'results.json'), 'cases': {}}
    for key in ('dist-bs-1', 'moogie-1'):
        original = cases[key]
        directory = args.baseline_comparison / key
        baseline_metadata = json.loads((directory / 'septum-raw.render.json').read_text())
        latency = original['retained_engine_latency_samples'] / 44100
        hardware = measure(directory / 'hardware-excerpt-raw.wav', original['case'], 0)
        baseline = measure(directory / 'septum-raw.wav', original['case'], latency)
        item = {'hardware': hardware, 'models': {
            'baseline': {'measurements': baseline, 'errors': compare(hardware, baseline)}}}
        for candidate in sweep:
            trial = candidate['trial']
            if Path(trial).name != trial:
                raise ValueError('Invalid trial name')
            folder = args.sweep / trial
            provenance = renderer_provenance(folder / 'SeptumRenderMidi')
            if provenance != candidate['renderer']:
                raise ValueError('Renderer identity changed')
            path = folder / 'renders' / (key + '.wav')
            recorded = next(r for r in candidate['cases'] if r['id'] == key)
            manifest_path = path.with_suffix('.render.json')
            manifest_sha = sha(manifest_path)
            metadata = json.loads(manifest_path.read_text())
            if (sha(path) != recorded['render_sha256'] or
                    recorded['original_comparison_sha256'] != sha(directory / 'comparison.json')):
                raise ValueError('Rendered audio changed')
            if (metadata['inputs']['renderer']['sha256'] != provenance['sha256'] or
                    metadata['inputs']['midi']['sha256'] != original['files']['reconstructed-performance.mid'] or
                    metadata['inputs']['sysex']['sha256'] != original['files']['original-patch.syx'] or
                    metadata['output']['sha256'] != recorded['render_sha256'] or
                    metadata['settings'] != baseline_metadata['settings'] or
                    metadata['output']['latency_samples'] != original['retained_engine_latency_samples'] or
                    metadata['replay_events'] != baseline_metadata['replay_events'] or
                    metadata['degraded_replay']):
                raise ValueError('Candidate replay differs from original comparison inputs')
            measurement = measure(path, original['case'], latency)
            if sha(manifest_path) != manifest_sha or renderer_provenance(folder / 'SeptumRenderMidi') != provenance:
                raise ValueError('Candidate provenance changed during analysis')
            item['models'][trial] = {'measurements': measurement,
                                      'render_manifest_sha256': manifest_sha,
                                      'errors': compare(hardware, measurement)}
        result['cases'][key] = item
        print(key, flush=True)
        for name, model in item['models'].items():
            nominal = [r for r in model['errors'] if r['channel'] == 'mid' and r['shift_seconds'] == 0]
            print(name, {k: [round(r[k], 3) for r in nominal] for k in GROUPS}, flush=True)
    load_run(args.baseline_comparison)
    if result['sweep_sha256'] != sha(args.sweep / 'results.json'):
        raise ValueError('Sweep changed during analysis')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
