#!/usr/bin/env python3
"""Conditional filter-shape audit of the official SupaJuce 1 recording.

Fits harmonic shape, not a full synthesizer or original MIDI. Upper square
harmonics H2,H6,... do not overlap the lower square in a linear two-oscillator
model. All signal-chain assumptions and nuisance cutoff fits are recorded.
No media, preset or production source is changed or downloaded.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import scipy
from scipy.io import wavfile
from scipy.optimize import least_squares, minimize_scalar

H = np.arange(2, 31, 4)
MODELS = ('lp12', 'lp24_fixed_1.2', 'lp24_fixed_sqrt2', 'lp24_equal', 'ladder24')
SR = 44100


def identity(path):
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def read_audio(path):
    sr, audio = wavfile.read(path)
    if sr != SR or audio.dtype.kind != 'f' or audio.ndim != 2 or not np.isfinite(audio).all():
        raise ValueError('Expected finite 44.1 kHz stereo float PCM')
    return audio


def harmonics(signal, center, width, frequency):
    first, last = round((center-width/2)*SR), round((center+width/2)*SR)
    if first < 0 or last > len(signal):
        raise ValueError('Window outside input')
    y = signal[first:last].astype(float)
    t = np.arange(first, last)/SR-center
    # Full sample rate avoids folding high partials into the modeled band.
    count = min(64, int(.45*SR/frequency))
    columns = [np.ones(len(t)), t/width]
    for n in range(1, count+1):
        angle = 2*np.pi*n*frequency*t
        columns.extend((np.cos(angle), np.sin(angle)))
    matrix = np.column_stack(columns)
    c, _, _, singular = np.linalg.lstsq(matrix, y, rcond=None)
    a = np.hypot(c[2::2], c[3::2])
    measured = 20*np.log10(np.maximum(a[H-1], 1e-30)/max(a[1], 1e-30))
    return dict(amplitude=a.tolist(), harmonic_ratio_db=measured[1:].tolist(),
        square_removed_response_db=(measured+20*np.log10(H/2)).tolist(),
        residual_power=float(np.mean((y-matrix@c)**2)/max(np.var(y), 1e-30)),
        condition=float(singular[0]/singular[-1]))


def observations(path, notes, delay=0, width=.03, channel='mean'):
    audio = read_audio(path)
    y = audio.mean(axis=1) if channel == 'mean' else audio[:, int(channel)]
    rows = []
    for index, note in enumerate(notes):
        nominal = 440*2**((note['note']-12-69)/12)
        midpoint = note['on']+.0675+delay
        f0 = minimize_scalar(lambda f: harmonics(y, midpoint, .04, f)['residual_power'],
            bounds=(nominal*.985, nominal*1.015), method='bounded').x
        times = (.040, .055, .070, .085, .100)
        if index == 4:
            times += (.150, .250, .350, .450)
        for elapsed in times:
            if elapsed+width/2 > note['off']-note['on']-.004:
                continue
            row = dict(note=index, played_note=note['note'], elapsed=elapsed,
                       center=note['on']+elapsed+delay, width=width, frequency=float(f0),
                       channel=channel)
            rows.append(row | harmonics(y, row['center'], width, f0))
    return rows


def response(frequency, cutoff, damping, model, warp=True):
    x = np.tan(np.pi*frequency/SR)/np.tan(np.pi*cutoff/SR) if warp else frequency/cutoff
    if model == 'ladder24':
        return -20*np.log10(np.abs((1+1j*x)**4+damping))
    value = -10*np.log10((1-x*x)**2+(damping*x)**2)
    if model != 'lp12':
        k2 = damping if model == 'lp24_equal' else np.sqrt(2) if model == 'lp24_fixed_sqrt2' else 1.2
        value -= 10*np.log10((1-x*x)**2+(k2*x)**2)
    return value


def predict(row, cutoff, damping, model, source='ideal', highpass=0, warp=True, indices=None):
    indices = H if indices is None else indices
    frequency = row['frequency']*indices
    gain = response(frequency, cutoff, damping, model, warp)
    if source == 'polyblep':
        gain += 40*np.log10(np.maximum(np.sinc(frequency/SR), 1e-15))
    if highpass:
        gain += 20*np.log10(frequency/np.sqrt(frequency**2+highpass**2))
    return (gain-gain[0]-20*np.log10(indices/2))[1:]


def fit_window(row, model, fixed_damping=None, source='ideal', highpass=0, warp=True):
    target = np.array(row['harmonic_ratio_db'])
    peak_index = int(np.argmax(row['square_removed_response_db']))
    peak = np.clip(row['frequency']*H[peak_index], 400, 14000)
    def objective(v):
        cutoff = np.exp(v[0])
        damping = np.exp(v[1]) if fixed_damping is None else fixed_damping
        return predict(row, cutoff, damping, model, source, highpass, warp)-target
    upper = 3.99 if model == 'ladder24' else 2.5
    lower_bounds = np.log([300, .03] if fixed_damping is None else [300])
    upper_bounds = np.log([15000, upper] if fixed_damping is None else [15000])
    starts = [np.log([np.clip(peak*s, 301, 14999), k] if fixed_damping is None
                     else [np.clip(peak*s, 301, 14999)])
              for s in (.8, 1., 1.2) for k in ((.2, .6, 1.5) if fixed_damping is None else (1,))]
    fits = [least_squares(objective, start, bounds=(lower_bounds, upper_bounds),
                         max_nfev=300) for start in starts]
    best = min(fits, key=lambda fit: np.sum(fit.fun**2))
    return dict(cutoff_hz=float(np.exp(best.x[0])),
        damping=float(np.exp(best.x[1])) if fixed_damping is None else float(fixed_damping),
        rms_db=float(np.sqrt(np.mean(best.fun**2))), ratio_errors_db=best.fun.tolist())


def fit_common_damping(rows, model):
    training = [r for r in rows if r['note'] == 0]
    initial = [fit_window(row, model) for row in training]
    start = np.log([np.median([p['damping'] for p in initial])]
                   +[p['cutoff_hz'] for p in initial])
    def residual(v):
        damping = np.exp(v[0])
        return np.concatenate([predict(row, np.exp(cutoff), damping, model)
            -np.array(row['harmonic_ratio_db']) for row, cutoff in zip(training, v[1:])])
    bounds = (np.log([.03]+[300]*len(training)),
              np.log([3.99 if model == 'ladder24' else 2.5]+[15000]*len(training)))
    fit = least_squares(residual, start, bounds=bounds, max_nfev=1000)
    damping = float(np.exp(fit.x[0]))
    # Held-out windows fit one nuisance cutoff only. Their damping and topology
    # remain frozen; this tests spectral shape, not predictive envelope timing.
    fixed = [dict(note=r['note'], elapsed=r['elapsed'],
                  **fit_window(r, model, fixed_damping=damping)) for r in rows]
    free = [dict(note=r['note'], elapsed=r['elapsed'], **fit_window(r, model)) for r in rows]
    by_note = {str(n): float(np.sqrt(np.mean([np.array(p['ratio_errors_db'])**2
                for p in fixed if p['note'] == n]))) for n in range(6)}
    early = {str(n): float(np.sqrt(np.mean([np.array(p['ratio_errors_db'])**2
                for p in fixed if p['note'] == n and p['elapsed'] <= .100]))) for n in range(6)}
    extra = []
    for row, parameters in zip(rows, fixed):
        if row['elapsed'] > .100:
            continue
        high = np.arange(34, min(len(row['amplitude']), int(10000/row['frequency']))+1, 4)
        if len(high) == 0:
            continue
        a = np.array(row['amplitude'])
        observed = 20*np.log10(np.maximum(a[high-1], 1e-30)/max(a[1], 1e-30))
        predicted = predict(row, parameters['cutoff_hz'], damping, model, indices=np.r_[2, high])
        extra.append(dict(note=row['note'], elapsed=row['elapsed'], harmonic_indices=high.tolist(),
            errors_db=(predicted-observed).tolist(), rms_db=float(np.sqrt(np.mean((predicted-observed)**2)))))
    return dict(model=model, first_note_common_damping=damping,
        damping_definition='global ladder feedback, stability boundary4' if model == 'ladder24'
                            else 'second-order pole damping k=1/Q',
        fixed_damping_fits=fixed, free_per_window_fits=free,
        fixed_damping_rms_db_by_note=by_note, early_fixed_damping_rms_db_by_note=early,
        withheld_higher_harmonics=extra,
        validation='Only note0 estimates damping. Every held-out frame refits cutoff, but not damping or spectral offsets.')


def plot_report(result, destination):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8), sharex=True, sharey=True)
    for ax, elapsed in zip(axes, (.04, .07, .10)):
        row = next(r for r in result['observations'] if r['note'] == 0 and r['elapsed'] == elapsed)
        current = next(r for r in result['production_observations'] if r['note'] == 0 and r['elapsed'] == elapsed)
        frequencies = np.geomspace(row['frequency']*2, 12000, 500)
        ax.scatter(row['frequency']*H, row['square_removed_response_db'], c='black', s=24,
                   label='Hardware' if elapsed == .04 else None, zorder=5)
        ax.scatter(current['frequency']*H, current['square_removed_response_db'], marker='x', s=22,
                   color='C2', label='Production audio' if elapsed == .04 else None)
        for model, color, label in (('lp24_fixed_1.2', 'C0', 'One resonant pole pair'),
                                    ('lp24_equal', 'C1', 'Both pole pairs resonant')):
            fit = next(m for m in result['models'] if m['model'] == model)
            parameters = next(p for p in fit['fixed_damping_fits'] if p['note'] == 0 and p['elapsed'] == elapsed)
            response_db = response(frequencies, parameters['cutoff_hz'], parameters['damping'], model)
            anchor_db = response(np.array([row['frequency']*2]), parameters['cutoff_hz'], parameters['damping'], model)[0]
            ax.plot(frequencies, response_db-anchor_db, color=color, label=label if elapsed == .04 else None)
        ax.set_xscale('log')
        ax.set_ylim(-40, 16)
        ax.set_xlim(400, 12000)
        ax.set_title(f'{round(elapsed*1000)} ms after first onset')
        ax.set_xlabel('Frequency (Hz)')
        ax.grid(alpha=.2)
    axes[0].set_ylabel('Square-slope-removed gain relative to H2 (dB)')
    axes[0].legend(fontsize=8, loc='lower left')
    fig.suptitle('SupaJuce 1: a higher, stronger moving filter peak\n'
                 'Conditional fits; no recording EQ or per-harmonic offsets')
    fig.tight_layout()
    fig.savefig(destination, dpi=170)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comparison', required=True, type=Path,
                        help='WIDE-correct after/supa-juce-1 comparison directory')
    parser.add_argument('--trace', type=Path, help='optional independently instrumented production CSV')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    comparison = json.loads((args.comparison/'comparison.json').read_text())
    notes = comparison['case']['notes']
    hardware_path = args.comparison/'hardware-decoded-full.wav'
    render_path = args.comparison/'septum-raw.wav'
    rows = observations(hardware_path, notes)
    production = observations(render_path, notes, 93/SR)
    models = [fit_common_damping(rows, model) for model in MODELS]
    # These are fixed alternatives, not extra nuisance parameters fitted away.
    representative = next(r for r in rows if r['note'] == 0 and r['elapsed'] == .070)
    sensitivity = []
    for source, hp, warp in (('ideal', 0, True), ('polyblep', 0, True),
                            ('ideal', 100, True), ('ideal', 0, False)):
        for model in ('lp24_fixed_1.2', 'lp24_equal'):
            sensitivity.append(dict(model=model, source=source, highpass_hz=hp,
                exact_tpt_warp=warp, **fit_window(representative, model,
                                                source=source, highpass=hp, warp=warp)))
    window_checks = []
    for width, channel in ((.02, 'mean'), (.04, 'mean'), (.03, '0'), (.03, '1')):
        alternate = observations(hardware_path, notes[:1], width=width, channel=channel)
        for row in alternate:
            for model in ('lp24_fixed_1.2', 'lp24_equal'):
                window_checks.append(dict(width=width, channel=channel, elapsed=row['elapsed'],
                                          model=model, **fit_window(row, model)))
    result = dict(schema_version=1, status='conditional resonance shape analysis; no production calibration',
        reference=comparison['reference'], bank=comparison['bank'],
        comparison=identity(args.comparison/'comparison.json'),
        inputs=dict(hardware=identity(hardware_path), production=identity(render_path)),
        patch=dict(resonance=40, cutoff=27, keyfollow=50, slope_db=24,
                   filter_attack=3, decay=61, sustain=74, release=63, depth=31,
                   low_frequency='flat', overdrive=False, delay=True, reverb=True),
        harmonic_indices=H.tolist(), denominator=2, source_law='ideal square amplitude1/n',
        observations=rows, production_observations=production, models=models,
        representative_assumption_sensitivity=sensitivity, window_channel_sensitivity=window_checks,
        production_first_note_fits=[dict(elapsed=r['elapsed'],
            **fit_window(r, 'lp24_fixed_1.2', source='polyblep')) for r in production if r['note'] == 0],
        qualifications=['Original MIDI, velocities, gate overlap, controllers, system state, recorded patch revision and capture processing are unknown.',
            'Within-upper ratios cancel scalar oscillator balance and recording gain, not frequency-dependent capture response.',
            'Ideal square source and linear filtering are assumptions; polyBLEP source and100Hz high-pass alternatives are reported.',
            'Later windows contain enabled delay/reverb and prior-note tails. Their least-squares residuals are retained.',
            'Per-window cutoff+damping fits diagnose shape. Held-out fits freeze first-note damping but refit cutoff; they do not validate a cutoff/envelope control law.',
            'Overlapping windows are correlated; fitted ranges are sensitivity results, not statistical confidence intervals.',
            'LP12 contradicts the selected24dB setting but is included as a diagnostic shape comparator; ladder feedback and pole damping are different parameter definitions.'],
        runtime=dict(numpy=np.__version__, scipy=scipy.__version__), script_sha256=identity(Path(__file__))['sha256'])
    if args.trace:
        with args.trace.open() as stream:
            trace = list(csv.DictReader(stream))
        elapsed = np.cumsum([int(r['samples']) for r in trace])/SR
        result['production_trace'] = dict(input=identity(args.trace), nearest_rows={str(t):
            dict(trace[int(np.argmin(abs(elapsed-t)))], elapsed_seconds=float(elapsed[np.argmin(abs(elapsed-t))]))
            for t in (.040, .055, .070, .085, .100)})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    plot_report(result, args.output.with_suffix('.png'))
    for model in models:
        print(model['model'], 'damping', round(model['first_note_common_damping'], 5),
              'early fixed-damping RMS by note', model['early_fixed_damping_rms_db_by_note'])
    print('production recovery', result['production_first_note_fits'])


if __name__ == '__main__':
    main()
