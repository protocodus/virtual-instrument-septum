#!/usr/bin/env python3
"""Audit whether moving Q50 recordings identify a stationary filter response.

The owner's 50% label does not establish raw resonance 63 or 64. Fits here
are diagnostics, not accepted control calibration. Invalid harmonic windows
are retained with rejection reasons, never silently admitted as evidence.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
import numpy as np
from scipy.io import wavfile
from scipy.optimize import least_squares

from analyze_deepsonic_filter import (CATALOG, NOTES, OFFSETS, digest, measure,
                                     errors, mask, fit_cutoff, rms, self_test)
from render_midi import parse_smf

EXTRA_TIMES = (.14, .22, .30, .38)
WIDTHS = (.04, .06, .08, .10)


def current_dampings(raw):
    generic = 2 - 2.04*np.sqrt(raw/127)
    first = (1.2 + (.5591507918157866-1.2)*raw/40 if raw < 40 else
             2*(generic/2)**1.5 if generic > 0 else generic)
    return [float(first), float(np.clip(first, .5, 1.2))]


def selected_dampings(parameters, slope, topology):
    if topology == 'shared_all':
        return [parameters[0]]*(slope//12)
    if topology == 'separate_slopes':
        return [parameters[0]] if slope == 12 else [parameters[1]]*2
    if topology == 'linked_first_stage':
        return [parameters[0]] if slope == 12 else list(parameters[:2])
    if topology == 'independent_slopes':
        return [parameters[0]] if slope == 12 else list(parameters[1:3])
    if topology == 'fixed':
        return list(parameters[:slope//12])
    raise ValueError(topology)


def fit_dampings(rows, topology):
    count = {'shared_all': 1, 'separate_slopes': 2,
             'linked_first_stage': 2, 'independent_slopes': 3}[topology]
    low = np.log([.02]*count + [r['fundamental_hz']*.5 for r in rows])
    high = np.log([3.]*count + [r['fundamental_hz']*20 for r in rows])
    def residual(p):
        k, fc = np.exp(p[:count]), np.exp(p[count:])
        return np.concatenate([errors(r, f, selected_dampings(k, r['slope'], topology))[mask(r)]
                               for r, f in zip(rows, fc)])
    solutions = []
    for start in (.08, .3, .6, 1.2):
        ks = [start]*count
        fcs = [fit_cutoff(r, selected_dampings(ks, r['slope'], topology))['cutoff_hz'] for r in rows]
        fit = least_squares(residual, np.log(ks+fcs), bounds=(low, high),
                            xtol=1e-10, ftol=1e-10, gtol=1e-10, max_nfev=2000)
        solutions.append((float(np.mean(fit.fun**2)), fit))
    _, best = min(solutions, key=lambda item: item[0])
    return dict(topology=topology, parameters=np.exp(best.x[:count]).tolist(),
                training_windows=len(rows), training_rmse_db=rms(best.fun.tolist()),
                starts=[dict(rmse_db=float(np.sqrt(cost)),
                             parameters=np.exp(fit.x[:count]).tolist()) for cost, fit in solutions])


def evaluate(rows, parameters, topology):
    observations = []
    for row in rows:
        if row.get('conditioning_rejected'):
            continue
        ks = selected_dampings(parameters, row['slope'], topology)
        fitted = fit_cutoff(row, ks)
        observations.append({k: row[k] for k in ('slope', 'on', 'note', 'offset', 'width', 'role', 'valid')}
                            | dict(dampings=ks, **fitted))
    summaries = {}
    for slope in (12, 24):
        for width in WIDTHS:
            for role in ('training', 'time_holdout', 'note_holdout', 'note_and_time_holdout'):
                group = [r for r in observations if r['slope'] == slope and r['width'] == width
                         and r['role'] == role and r['valid']]
                summaries[f'lp{slope}_{width:g}_{role}'] = dict(windows=len(group),
                    lower_harmonic_rmse_db=rms([r['fit_h2_h8_rmse_db'] for r in group]),
                    withheld_upper_harmonic_count=sum(len(r['withheld_h9_h16_error_db']) for r in group),
                    withheld_upper_harmonic_rmse_db=rms([v for r in group for v in r['withheld_h9_h16_error_db']]))
    return dict(parameters=parameters, topology=topology, summary=summaries, windows=observations)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    self_test()
    args.output.mkdir(parents=True, exist_ok=False)
    catalog = json.loads(CATALOG.read_text())['assets']
    sources = []
    def verify(filename):
        item = next(a for a in catalog if Path(a['path']).name == filename)
        path = args.sources/filename
        if digest(path) != item['sha256']:
            raise ValueError(f'Changed reference: {filename}')
        sources.append(dict(filename=filename, sha256=item['sha256'], url=item['url']))
        return path
    midi = verify('deepsonic_-_filter_demo_-_comparsion_sequence.mid')
    performance = parse_smf(midi.read_bytes())
    starts = {(round(e['sample']/44100, 5), bytes.fromhex(e['hex'])[1])
              for e in performance['events'] if e['kind'] == 'midi'
              and bytes.fromhex(e['hex'])[0] == 0x90 and bytes.fromhex(e['hex'])[2] > 0}
    if not all(note in starts for note in NOTES):
        raise ValueError('Selected notes do not match original MIDI')
    rows = []
    for slope in (12, 24):
        mp3 = verify(f'roland_sh-201_-_filter_demo_-_lpf{slope}_q050.mp3')
        wav = args.output/f'lp{slope}-hardware.wav'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
                        '-i', str(mp3), '-c:a', 'pcm_f32le', str(wav)], check=True)
        sr, y = wavfile.read(wav)
        if sr != 44100 or y.ndim != 1 or not np.isfinite(y).all():
            raise ValueError('Unexpected hardware decode')
        for on, note in NOTES:
            for offset in sorted(OFFSETS+EXTRA_TIMES):
                role = ('training' if on == 1.5 else 'note_holdout') if offset in OFFSETS else (
                    'time_holdout' if on == 1.5 else 'note_and_time_holdout')
                for width in WIDTHS:
                    f0 = 440*2**((note-69)/12)
                    row = dict(slope=slope, on=on, note=note, offset=offset, width=width,
                               role=role, fundamental_hz=f0)
                    try:
                        row.update(measure(y, sr, on+offset, width, f0))
                        row['valid'] = row['fit_residual_power'] <= .01
                        row['rejection'] = None if row['valid'] else 'over_1_percent_unexplained_power'
                    except ValueError as error:
                        row.update(valid=False, conditioning_rejected=True, rejection=str(error))
                    rows.append(row)
    models = {name: evaluate(rows, ks, 'fixed') for name, ks in (
        ('known_q0', [1.2, 1.2]), ('current_raw63', current_dampings(63)),
        ('current_raw64', current_dampings(64)))}
    fits = {}
    # Forty milliseconds is the only tested width for which most training
    # windows pass. This post-inspection choice is explicit and is tested at
    # different times/notes. It cannot rescue rejected windows.
    train = [r for r in rows if r['role'] == 'training' and r['width'] == .04 and r['valid']]
    for topology in ('shared_all', 'separate_slopes', 'linked_first_stage', 'independent_slopes'):
        fits[topology] = fit_dampings(train, topology)
        models[topology] = evaluate(rows, fits[topology]['parameters'], topology)
    quality = {}
    for slope in (12, 24):
        for width in WIDTHS:
            group = [r for r in rows if r['slope'] == slope and r['width'] == width]
            measured = [r for r in group if not r.get('conditioning_rejected')]
            quality[f'lp{slope}_{width:g}'] = dict(windows=len(group), valid=sum(r['valid'] for r in group),
                conditioning_rejected=len(group)-len(measured),
                median_unexplained_power=float(np.median([r['fit_residual_power'] for r in measured])),
                max_unexplained_power=max(r['fit_residual_power'] for r in measured))
    result = dict(schema_version=1, sources=sources, tool_sha256=digest(__file__),
                  estimator_sha256=digest(Path(__file__).with_name('analyze_deepsonic_filter.py')),
                  patch_status='documented_recipe_not_sysex',
                  midi_status='original_performance',
                  acceptance_status='diagnostic_only_nonstationary_and_upper_harmonic_failure',
                  training_rule='note 36 at 1.5 s, offsets .10 .18 .26 .34, width .04, valid windows only',
                  validation_rule='new .14 .22 .30 .38 times, five other notes, H9-H16, width sensitivity',
                  quality=quality, fits=fits, models=models, observations=rows,
                  limits=['50 percent label does not establish raw resonance 63 or 64.',
                          'A fit to local amplitudes is conditional on approximately stationary filtering.',
                          'Moving narrow resonance can bias stationary transfer even with low harmonic residual.',
                          'Forty ms windows were selected after observing the failure of eighty ms windows.',
                          'No raw patch, isolated bypass waveform, recording chain or cross-unit replication.'])
    (args.output/'results.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(quality=quality, fits=fits), indent=2))


if __name__ == '__main__':
    main()
