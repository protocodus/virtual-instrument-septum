#!/usr/bin/env python3
"""Identify zero-resonance filter shape in the owner's dry SH-201 recordings.

Original performance MIDI is supplied, but the hardware patch is a documented
recipe rather than a SysEx dump. Each analysis window has one nuisance cutoff;
its value is NOT an estimate of Roland's raw cutoff/envelope control table.
Only the note at 1.5 s selects damping. Other notes and upper harmonics test it.
No audio EQ, per-harmonic gain or nonlinear time alignment is fitted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from scipy.io import wavfile
from scipy.optimize import least_squares, minimize_scalar

from render_midi import parse_smf

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'Docs/fidelity/source-audits/deepsonic-acquisition-2026-09-15.json'
NOTES = ((.75, 24), (1.5, 36), (2., 29), (4.75, 24), (6., 31), (17.25, 57))
# Keep every sensitivity window >=50 ms after MIDI onset and <=390 ms.
# Earlier windows included the recording's attack transient; this exclusion
# is common to both recordings and does not assert an exact capture latency.
OFFSETS = (.10, .18, .26, .34)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def measure(y, sr, center, width, f0):
    """Joint quadrature amplitudes with an independent local linear ramp.

    Use the known MIDI fundamental. The ramp also approximates small phase
    rotation from the moving filter without mistaking it for oscillator tune.
    Fit the original sample grid with no spectral/phase preprocessing; include
    harmonics only below 8 kHz, well below the capture Nyquist of 22.05 kHz.
    """
    a, b = round((center - width / 2) * sr), round((center + width / 2) * sr)
    if a < 0 or b > len(y):
        raise ValueError('Analysis window outside the capture')
    x = y[a:b].astype(float)
    t = np.arange(a, b) / sr - center
    u = t / (width / 2)
    hs = np.arange(1, min(30, int(8000 / f0)) + 1)
    columns = [np.ones(len(t)), u]
    for h in hs:
        c, s = np.cos(2*np.pi*h*f0*t), np.sin(2*np.pi*h*f0*t)
        columns.extend((c, s, u*c, u*s))
    matrix = np.column_stack(columns)
    coeff, _, _, singular = np.linalg.lstsq(matrix, x, rcond=None)
    condition = float(singular[0] / singular[-1])
    if condition > 100:
        raise ValueError(f'Ill-conditioned harmonic fit: {condition}')
    amplitude = np.hypot(coeff[2::4], coeff[3::4])
    ratio = 20*np.log10(np.maximum(amplitude, 1e-15) / amplitude[0])
    residual = float(np.mean((x-matrix@coeff)**2) / max(np.var(x), 1e-30))
    return dict(harmonics=hs.tolist(), amplitude=amplitude.tolist(),
                harmonic_ratio_db=ratio.tolist(),
                saw_slope_removed_db=(ratio + 20*np.log10(hs)).tolist(),
                fit_residual_power=residual, condition_number=condition)


def response(hz, cutoff, dampings, sr=44100):
    z = np.tan(np.pi*np.asarray(hz)/sr) / np.tan(np.pi*cutoff/sr)
    return sum(-10*np.log10((1-z*z)**2+(k*z)**2) for k in dampings)


def mask(row, upper=False):
    h = np.asarray(row['harmonics'])
    return ((h >= 9) & (h <= 16) if upper else (h >= 2) & (h <= 8)) & (
        np.asarray(row['harmonic_ratio_db']) > -45)


def errors(row, cutoff, dampings):
    f = np.asarray(row['harmonics']) * row['fundamental_hz']
    prediction = response(f, cutoff, dampings)
    return prediction-prediction[0]-np.asarray(row['saw_slope_removed_db'])


def fit_cutoff(row, dampings):
    select = mask(row)
    f0 = row['fundamental_hz']
    def objective(log_cutoff):
        e = errors(row, np.exp(log_cutoff), dampings)[select]
        return np.mean(e*e)
    # The modest two-dimensional physical model still needs a grid to avoid
    # selecting the wrong side of a resonance peak with a local solver.
    grid = np.linspace(np.log(f0*.5), np.log(f0*20), 81)
    i = int(np.argmin([objective(x) for x in grid]))
    optimum = minimize_scalar(objective, bounds=(grid[max(0, i-1)],
                                                 grid[min(len(grid)-1, i+1)]),
                              method='bounded')
    cutoff = float(np.exp(optimum.x))
    residual = errors(row, cutoff, dampings)
    return dict(cutoff_hz=cutoff, fit_h2_h8_rmse_db=float(np.sqrt(
        np.mean(residual[select]**2))),
        withheld_h9_h16_error_db=residual[mask(row, True)].tolist(),
        residual_db=residual.tolist())


def rms(values):
    return float(np.sqrt(np.mean(np.square(values)))) if values else None


def model_summary(rows, dampings):
    measured = []
    for row in rows:
        k = dampings[:1] if row['slope'] == 12 else dampings
        result = fit_cutoff(row, k)
        measured.append(dict(slope=row['slope'], note=row['note'], on=row['on'],
                             offset=row['offset'], shift=row['shift'], width=row['width'],
                             training=row['training'], **result))
    summaries = {}
    for slope in (12, 24):
        for train in (True, False):
            select = [r for r in measured if r['slope'] == slope and r['training'] == train
                      and r['shift'] == 0 and r['width'] == .08]
            summaries[f'lp{slope}_' + ('training' if train else 'validation')] = dict(
                windows=len(select), lower_harmonic_rmse_db=rms(
                    [r['fit_h2_h8_rmse_db'] for r in select]),
                withheld_upper_harmonic_windows=sum(
                    bool(r['withheld_h9_h16_error_db']) for r in select),
                withheld_upper_harmonic_observations=sum(
                    len(r['withheld_h9_h16_error_db']) for r in select),
                withheld_upper_harmonic_rmse_db=rms(
                    [v for r in select for v in r['withheld_h9_h16_error_db']]))
    return dict(dampings=dampings, summary=summaries, windows=measured)


def self_test():
    sr, f0, center, width = 44100, 65.40639132514966, .5, .08
    t = np.arange(sr)/sr
    hs = np.arange(1, 31)
    gains = 10**(response(hs*f0, 300, [1.2])/20)/hs
    y = sum(g*(1+.1*(t-center))*np.sin(2*np.pi*h*f0*t+.31*h)
            for h, g in zip(hs, gains))
    row = measure(y, sr, center, width, f0)
    np.testing.assert_allclose(row['amplitude'], gains, rtol=1e-8, atol=1e-12)
    row['fundamental_hz'] = f0
    fit = fit_cutoff(row, [1.2])
    assert abs(fit['cutoff_hz']-300) < .01
    assert fit['fit_h2_h8_rmse_db'] < 1e-4
    assert fit_cutoff(row, [2.0])['fit_h2_h8_rmse_db'] > .5


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    self_test()
    if args.self_test:
        print('Harmonic estimator and independent response recovery passed')
        return
    if not args.sources or not args.output:
        parser.error('--sources and --output are required')
    args.output.mkdir(parents=True, exist_ok=False)
    catalog = json.loads(CATALOG.read_text())
    assets = catalog['assets']
    sources = []
    def verify(filename):
        record = next(a for a in assets if Path(a.get('path', a.get('local_filename', ''))).name == filename)
        path = args.sources/filename
        if digest(path) != record['sha256']:
            raise ValueError(f'Changed reference: {filename}')
        sources.append(dict(filename=filename, sha256=record['sha256'], url=record.get('url')))
        return path
    midi = verify('deepsonic_-_filter_demo_-_comparsion_sequence.mid')
    parsed = parse_smf(midi.read_bytes())
    starts = {(round(e['sample']/44100, 5), bytes.fromhex(e['hex'])[1])
              for e in parsed['events'] if e['kind'] == 'midi'
              and bytes.fromhex(e['hex'])[0] == 0x90 and bytes.fromhex(e['hex'])[2] > 0}
    if not all(item in starts for item in NOTES):
        raise ValueError('Analysis note selection no longer matches original MIDI')
    rows = []
    for slope in (12, 24):
        mp3 = verify(f'roland_sh-201_-_filter_demo_-_lpf{slope}_q000.mp3')
        wav = args.output/f'lp{slope}-hardware.wav'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
                        '-i', str(mp3), '-c:a', 'pcm_f32le', str(wav)], check=True)
        sr, y = wavfile.read(wav)
        if sr != 44100 or y.ndim != 1 or not np.isfinite(y).all():
            raise ValueError('Unexpected hardware decode')
        for on, note in NOTES:
            for offset in OFFSETS:
                # Primary analysis + independent time/window sensitivity.
                for shift, width in ((0, .08), (-.01, .08), (.01, .08), (0, .10)):
                    f0 = 440*2**((note-69)/12)
                    row = measure(y, sr, on+offset+shift, width, f0)
                    if row['fit_residual_power'] > .01:
                        raise ValueError(f'Harmonic model fails to explain a selected dry window: '
                                         f'LP{slope} on={on} offset={offset} shift={shift} '
                                         f'width={width} residual={row["fit_residual_power"]}')
                    rows.append(dict(slope=slope, on=on, note=note, offset=offset,
                                     shift=shift, width=width, fundamental_hz=f0,
                                     training=on == 1.5, **row))
    train = [r for r in rows if r['training'] and r['shift'] == 0 and r['width'] == .08]
    def objective(p):
        k = np.exp(p[0])
        return np.concatenate([errors(r, np.exp(fc), [k]*(r['slope']//12))[mask(r)]
                               for r, fc in zip(train, p[1:])])
    low = np.log([.3]+[r['fundamental_hz']*.5 for r in train])
    high = np.log([3.]+[r['fundamental_hz']*20 for r in train])
    fit = least_squares(objective, np.log([1.2]+[r['fundamental_hz']*4 for r in train]),
                        bounds=(low, high), xtol=1e-12, ftol=1e-12, gtol=1e-12)
    k = float(np.exp(fit.x[0]))
    result = dict(schema_version=1, sources=sources, tool_sha256=digest(__file__),
                  midi_status='original_performance', patch_status='documented_recipe_not_sysex',
                  fit_status='conditional_filter_shape_identification_not_full_output_equivalence',
                  analysis=dict(training_note=36, training_on_seconds=1.5,
                                train_harmonics='H2-H8 above -45 dB relative to H1',
                                withheld_harmonics='H9-H16 with the same hardware-only floor',
                                max_residual_power=max(r['fit_residual_power'] for r in rows),
                                max_condition=max(r['condition_number'] for r in rows),
                                nominal_equal_tempered_pitch=True, local_amplitude_ramps=True,
                                per_window_cutoff_is_nuisance_not_control_calibration=True),
                  fitted_shared_damping=k,
                  models={name:model_summary(rows, ks) for name, ks in
                          [('production', [2., 1.2]), ('rounded_candidate', [1.2, 1.2]),
                           ('fitted', [k, k])]}, observations=rows,
                  limits=['Hardware SysEx and recording-chain calibration are absent.',
                          'The source recipe describes a saw; isolated bypass spectrum is unavailable.',
                          'Local response assumes approximately stationary filtering within each window.',
                          'One owner and device, two recordings; no replication across hardware units.',
                          'This analysis identifies resonance-zero shape, not the full resonance curve.',
                          'An acoustic match here cannot establish whole-instrument or market superiority.'])
    (args.output/'results.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(fitted_shared_damping=k, models={n:m['summary']
                                                         for n,m in result['models'].items()}), indent=2))


if __name__ == '__main__':
    main()
