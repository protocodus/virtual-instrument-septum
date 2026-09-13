#!/usr/bin/env python3
"""Audit the residual even-harmonic shape of the named Moogie 1 demo.

This is a conditional falsification of simple waveform/filter explanations,
not a calibration of the SH-201 or recovery of its original performance MIDI.
No input, production source or patch is modified. No media is downloaded.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform

import numpy as np
from scipy.io import wavfile
from scipy import signal
from scipy.optimize import differential_evolution, minimize_scalar

NOTES = ((.029, .400), (.939, 1.315), (1.901, 2.245))
HARMONICS = np.array((2, 4, 6, 8))
BASE_HZ = 20 * 2 ** (30 * 10 / 127)
PEAK_HZ = BASE_HZ * 2 ** (22 * 10 / 63)
PRODUCTION_DECAY = .4189852819747085
PRODUCTION_DUTY = .5 + .45 * 57 / 127
LATENCY_SECONDS = 93 / 44100


def identity(path):
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def read_audio(path):
    sr, audio = wavfile.read(path)
    if sr != 44100:
        raise ValueError('This fixed-timeline audit expects 44.1 kHz reference renders')
    if audio.dtype.kind not in 'f':
        raise ValueError('Use decoded float PCM WAV inputs')
    if audio.ndim == 1:
        audio = audio[:, None]
    if not np.isfinite(audio).all() or len(audio) / sr < NOTES[-1][1] + .02:
        raise ValueError('Nonfinite or short input audio')
    return sr, audio


def fit_harmonics(y, sr, center, width, frequency, harmonics=12, ramp=False):
    """Joint complex amplitudes evaluated at the window center.

    A constant and trend absorb coupling tails. Optional linear variation of
    each sinusoid tests bias from envelope movement. Reject short, ill-
    conditioned ramp designs instead of treating their unstable coefficients
    as harmonic measurements.
    """
    first, last = round((center - width / 2) * sr), round((center + width / 2) * sr)
    if first < 0 or last > len(y):
        raise ValueError('Analysis window outside input')
    x = y[first:last:4].astype(float)
    t = np.arange(first, last, 4) / sr - center
    u = t / (width / 2)
    columns = [np.ones(len(t)), u]
    for n in range(1, harmonics + 1):
        angle = 2 * np.pi * n * frequency * t
        columns.extend((np.cos(angle), np.sin(angle)))
        if ramp:
            columns.extend((u * np.cos(angle), u * np.sin(angle)))
    matrix = np.column_stack(columns)
    coefficients, _, _, singular = np.linalg.lstsq(matrix, x, rcond=None)
    condition = float(singular[0] / singular[-1])
    if condition > 100:
        raise ValueError(f'Ill-conditioned harmonic design: {condition:g}')
    stride = 4 if ramp else 2
    amplitude = np.hypot(coefficients[2::stride], coefficients[3::stride])
    ratio = amplitude[HARMONICS[1:] - 1] / max(amplitude[1], 1e-30)
    bound = max(1 / 3, ratio[0])
    return dict(amplitude=amplitude.tolist(), ratio_db=(20 * np.log10(ratio)).tolist(),
                pulse_bound_excess_db=float(20 * np.log10(ratio[1] / bound)),
                even_to_odd_power_db=float(10 * np.log10(
                    max(np.sum(amplitude[1::2] ** 2), 1e-30)
                    / max(np.sum(amplitude[::2] ** 2), 1e-30))),
                fit_residual=float(np.mean((x - matrix @ coefficients) ** 2)
                                   / max(np.var(x), 1e-30)), condition_number=condition)


def note_frequencies(y, sr, delay):
    return [float(minimize_scalar(lambda f: fit_harmonics(
        y, sr, (on + .04 + off - .03) / 2 + delay,
        off - .03 - on - .04, f)['fit_residual'],
        bounds=(38, 39), method='bounded').x) for on, off in NOTES]


def observations(path, delay=0):
    sr, audio = read_audio(path)
    y = audio.mean(axis=1)
    frequencies = note_frequencies(y, sr, delay)
    rows = []
    for note, ((on, _), frequency) in enumerate(zip(NOTES, frequencies)):
        for time in np.arange(.06, .291, .01):
            rows.append(dict(note=note, time=float(time), frequency=frequency,
                             **fit_harmonics(y, sr, on + time + delay, .06, frequency)))
    # Independently inspect channels, window widths, harmonic counts and
    # linear in-window amplitude change. All fit designs must be well posed.
    robustness = []
    for note, ((on, _), frequency) in enumerate(zip(NOTES, frequencies)):
        for channel, signal in [('mean', y)] + [(str(i), audio[:, i])
                                               for i in range(audio.shape[1])]:
            for width in (.04, .06, .08):
                for count in (12, 24, 40):
                    for ramp in (False, True):
                        if ramp and width < .06:
                            continue
                        robustness.append(dict(note=note, channel=channel,
                            width=width, harmonic_count=count, amplitude_ramp=ramp,
                            **fit_harmonics(signal, sr, on + .15 + delay, width,
                                            frequency, count, ramp)))
    return dict(input=identity(path), sample_rate=sr, delay_seconds=delay,
                frequencies_hz=frequencies, rows=rows, robustness_at_150ms=robustness)


def filter_prediction(rows, duty, scale, k1, k2):
    """Static local response under the unchanged production decay trajectory.

    Pole damping, cutoff scale and duty can be diagnostic candidates; no
    free per-harmonic offsets or fitted EQ hide the waveform mismatch.
    """
    time = np.array([row['time'] for row in rows])
    frequency = np.array([row['frequency'] for row in rows])[:, None] * HARMONICS
    cutoff = BASE_HZ * (PEAK_HZ / BASE_HZ) ** np.maximum(1 - time / PRODUCTION_DECAY, 0)
    x = frequency / (scale * cutoff[:, None])
    response = (-10 * np.log10((1 - x * x) ** 2 + (k1 * x) ** 2)
                - 10 * np.log10((1 - x * x) ** 2 + (k2 * x) ** 2))
    # Current BOOST's continuous-time one-pole equivalent, not hardware EQ.
    shelf = 20 * np.log10(np.abs(1 + (10 ** (.4) - 1) / (1 + 1j * frequency / 200)))
    pulse = 20 * np.log10(np.maximum(np.abs(np.sin(np.pi * HARMONICS * duty)
                                               / HARMONICS), 1e-15))
    total = response + shelf + pulse
    return total[:, 1:] - total[:, :1]


def candidate_models(rows):
    observed = np.array([r['ratio_db'] for r in rows])
    train = np.array([r['note'] == 0 for r in rows])
    cases = (
        ('production', (), ()),
        ('duty_only', ('duty',), ((.5001, .9999),)),
        ('duty_cutoff', ('duty', 'cutoff_scale'), ((.5001, .9999), (.1, 3))),
        ('resonance_cutoff', ('cutoff_scale', 'k1'), ((.1, 3), (.02, 2))),
        ('duty_resonance_cutoff', ('duty', 'cutoff_scale', 'k1'),
            ((.5001, .9999), (.1, 3), (.02, 2))),
        ('duty_two_poles_cutoff', ('duty', 'cutoff_scale', 'k1', 'k2'),
            ((.5001, .9999), (.1, 3), (.02, 2), (.02, 2))),
    )
    result = []
    for name, keys, bounds in cases:
        def parameters(values):
            return dict(duty=PRODUCTION_DUTY, cutoff_scale=1.0, k1=2.0, k2=1.2) | dict(zip(keys, values))
        def predicted(values):
            p = parameters(values)
            return filter_prediction(rows, p['duty'], p['cutoff_scale'], p['k1'], p['k2'])
        # Nested models retain earlier candidates, so optimizer branch choices
        # cannot make a more flexible family worse than its contained model.
        objective = lambda v: np.mean((predicted(v)[train] - observed[train]) ** 2)
        initial = min(([p['parameters'][key] for key in keys] for p in result),
                      key=objective) if keys else ()
        optima = [differential_evolution(objective, bounds, seed=seed,
                    x0=initial, popsize=20, maxiter=600, tol=1e-9)
                  for seed in (7, 73, 763)] if bounds else []
        optimum = min(optima, key=lambda fit: fit.fun) if optima else None
        values = optimum.x if optimum is not None else ()
        residual = predicted(values) - observed
        result.append(dict(name=name, training_note=0, parameters=parameters(values),
            bounds=dict(zip(keys, bounds)), optimizer_success=None if optimum is None
                else bool(optimum.success), rms_db_by_note={str(n): float(np.sqrt(np.mean(
                    residual[np.array([r['note'] == n for r in rows])] ** 2))) for n in range(3)}))
    return result


def free_cutoff_models(rows, fixed_models):
    """Test resonant plausibility without identifying a base/decay law.

    Before sustain, linear envelope control gives cutoff=P*exp(-beta*t).
    Base cutoff and full decay duration are exactly confounded here. Pole
    families are one variable damping plus fixed stage2, or equal dampings.
    Even harmonics identify duty only up to d versus1.5-d; use d<=.75 to
    remove this exact amplitude degeneracy, not to claim a narrower knob law.
    """
    times = np.array([r['time'] for r in rows])
    frequency = np.array([r['frequency'] for r in rows])[:, None]
    amplitude = np.array([r['amplitude'] for r in rows])
    train = np.array([r['note'] == 0 for r in rows])
    all_harmonics = np.arange(2, 13, 2)
    observed = 20 * np.log10(amplitude[:, all_harmonics[1:] - 1] / amplitude[:, 1:2])
    beta = np.log(PEAK_HZ / BASE_HZ) / PRODUCTION_DECAY
    seeds = [dict(duty=p['parameters']['duty'], peak_hz=PEAK_HZ * p['parameters']['cutoff_scale'],
                  beta_per_second=beta, k=p['parameters']['k1']) for p in fixed_models]
    result = []
    for count in (3, 5):
        for model in ('one_variable_pole', 'equal_variable_poles'):
            def unpack(v):
                return dict(duty=v[0], peak_hz=float(np.exp(v[1])),
                            beta_per_second=float(np.exp(v[2])), k=v[3])
            def predicted(v):
                p = unpack(v)
                cutoff = p['peak_hz'] * np.exp(-p['beta_per_second'] * times)
                x = frequency * all_harmonics / cutoff[:, None]
                k1, k2 = p['k'], (1.2 if model == 'one_variable_pole' else p['k'])
                response = (-10 * np.log10((1 - x*x)**2 + (k1*x)**2)
                            -10 * np.log10((1 - x*x)**2 + (k2*x)**2))
                shelf = 20 * np.log10(np.abs(1 + (10**.4-1)
                                        / (1+1j*frequency*all_harmonics/200)))
                source = 20 * np.log10(np.maximum(np.abs(np.sin(
                    np.pi*all_harmonics*p['duty'])/all_harmonics), 1e-15))
                total = response + shelf + source
                return total[:, 1:] - total[:, :1]
            objective = lambda v: np.mean((predicted(v)[train, :count]
                                          - observed[train, :count])**2)
            starts = [[p['duty'] if p['duty'] <= .75 else 1.5-p['duty'],
                       np.log(p['peak_hz']), np.log(p['beta_per_second']), p['k']]
                      for p in seeds]
            initial = min(starts, key=objective)
            bounds = ((.5001, .7499), (np.log(100), np.log(3000)),
                      (np.log(.1), np.log(25)), (.03, 2))
            optima = [differential_evolution(objective, bounds, x0=initial,
                        seed=seed, popsize=25, maxiter=600, tol=1e-9)
                      for seed in (7, 73, 763)]
            optimum = min(optima, key=lambda fit: fit.fun)
            parameters = unpack(optimum.x)
            seeds.append(parameters)
            residual = predicted(optimum.x) - observed
            item = dict(model=model, fitted_harmonics=all_harmonics[1:count+1].tolist(),
                denominator_harmonic=2, training_note=0, parameters=parameters,
                cutoff_law='peak_hz * exp(-beta_per_second * elapsed_seconds); no sustain floor reached',
                fixed_second_damping=1.2 if model == 'one_variable_pole' else None,
                optimizer_success=bool(optimum.success),
                cutoffs_hz={str(t): float(parameters['peak_hz']*np.exp(
                    -parameters['beta_per_second']*t)) for t in (0, .06, .15, .29)},
                equivalent_full_decay_seconds_by_assumed_base_hz={str(base):
                    float(np.log(parameters['peak_hz']/base)/parameters['beta_per_second'])
                    for base in (20, 50, 100)},
                rms_fitted_ratios_db_by_note={}, rms_all_ratios_db_by_note={},
                rms_by_ratio_db_by_note={}, mean_error_by_ratio_db_by_note={})
            for n in range(3):
                error = residual[np.array([r['note'] == n for r in rows])]
                item['rms_fitted_ratios_db_by_note'][str(n)] = float(np.sqrt(np.mean(error[:, :count]**2)))
                item['rms_all_ratios_db_by_note'][str(n)] = float(np.sqrt(np.mean(error**2)))
                item['rms_by_ratio_db_by_note'][str(n)] = np.sqrt(np.mean(error**2, axis=0)).tolist()
                item['mean_error_by_ratio_db_by_note'][str(n)] = np.mean(error, axis=0).tolist()
            result.append(item)
    return result


def shape_errors(hardware, candidate):
    """Framewise ratios: no gain, time, frequency-response or phase fit."""
    result = {}
    groups = {'H2-H8/H1': ((2, 3, 4, 5, 6, 7, 8), 1),
              'odd_H3_H5_H7/H1': ((3, 5, 7), 1),
              'even_H4_H6_H8/H2': ((4, 6, 8), 2)}
    for name, (harmonics, denominator) in groups.items():
        by_note = {}
        for note in range(3):
            ratio = []
            for take in (hardware, candidate):
                amplitude = np.array([r['amplitude'] for r in take['rows'] if r['note'] == note])
                ratio.append(20 * np.log10(amplitude[:, np.array(harmonics) - 1]
                                          / amplitude[:, denominator - 1:denominator]))
            by_note[str(note)] = float(np.sqrt(np.mean((ratio[0] - ratio[1]) ** 2)))
        result[name] = by_note
    return result


def excerpt_spectrum(path):
    sr, audio = read_audio(path)
    y = audio[:round(3.7 * sr)]
    frequency, power = signal.welch(y, sr, nperseg=8192, axis=0)
    power = power.mean(axis=1)
    band = (frequency >= 20) & (frequency <= 16000)
    total = np.sum(power[band])
    return dict(input=identity(path), start_seconds=0, end_seconds=3.7,
        centroid_20_16000_hz=float(np.sum(frequency[band] * power[band]) / total),
        rms_dbfs=float(20 * np.log10(np.sqrt(np.mean(y.astype(float) ** 2)))),
        peak=float(np.max(np.abs(y))),
        relative_band_power_db={f'{lo}-{hi}': float(10 * np.log10(max(np.sum(
            power[(frequency >= lo) & (frequency < hi)]), 1e-30) / total))
            for lo, hi in ((20, 40), (40, 80), (80, 160), (160, 320), (320, 640),
                           (640, 1280), (1280, 2560), (2560, 5120), (5120, 16000))})


def plot_report(hardware, render, destination):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    figure, axes = plt.subplots(1, 3, figsize=(12, 3.8), sharex=True, sharey=True)
    for note, ax in enumerate(axes):
        for result, style in ((hardware, '-'), (render, '--')):
            rows = [r for r in result['rows'] if r['note'] == note]
            for i, harmonic in enumerate((4, 6, 8)):
                ax.plot([r['time'] * 1000 for r in rows],
                        [r['ratio_db'][i] for r in rows], style,
                        color=f'C{i}', label=f'H{harmonic}/H2' if result is hardware else None)
        ax.set_title(f'Low note {note + 1}')
        ax.set_xlabel('Milliseconds after reconstructed onset')
        ax.grid(alpha=.2)
    axes[0].set_ylabel('Harmonic amplitude ratio (dB)')
    axes[0].legend()
    figure.suptitle('Moogie 1: hardware (solid), Septum production (dashed)\n'
                    'Published preset; reconstructed MIDI; no spectral matching')
    figure.tight_layout()
    figure.savefig(destination, dpi=170)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comparison', required=True, type=Path,
                        help='folder containing hardware-decoded-full.wav and septum-raw.wav')
    parser.add_argument('--diagnostics', type=Path,
                        help='optional existing quiet/isolated diagnostic WAV folder')
    parser.add_argument('--output', required=True, type=Path, help='JSON destination; adjacent PNG is generated')
    parser.add_argument('--triangle-render', type=Path, help='optional isolated inverted-triangle render')
    args = parser.parse_args()
    hardware = observations(args.comparison / 'hardware-decoded-full.wav')
    render = observations(args.comparison / 'septum-raw.wav', LATENCY_SECONDS)
    report = dict(schema_version=1, status='conditional oscillator-shape audit; no production calibration',
        source_page='https://www.rolandus.com/go/sh-201_patches/patch_bass.html',
        audio_url='https://www.rolandus.com/go/sh-201_patches/mp3/BASS/TOP8_Moogie1.mp3',
        bank_url='https://www.rolandus.com/go/sh-201_patches/shl/SH-201_Patch_BASS.zip',
        original_midi_available=False, notes=NOTES,
        analysis=dict(ratios=['H4/H2', 'H6/H2', 'H8/H2'], main_width_seconds=.06,
                      main_harmonic_count=12, bound='R6 <= max(1/3, R4)',
                      window_assumption='locally stationary; robustness also fits linear amplitude variation'),
        production_mapping=dict(raw_pw=57, duty=PRODUCTION_DUTY, raw_decay=49,
            decay_seconds=PRODUCTION_DECAY, raw_cutoff=30, base_hz=BASE_HZ,
            raw_depth=22, peak_hz=PEAK_HZ), hardware=hardware, production=render,
        conditional_models=candidate_models(hardware['rows']), diagnostics=[],
        limitations=['Named audio/bank association does not authenticate exact recorded patch revision.',
            'Original MIDI, oscillator isolation, master state and recording processing are unknown.',
            'The pulse bound assumes a rectangular pulse and monotone linear response; resonance, '
            'additional even-harmonic sources, time variation or nonlinear processing may violate it.',
            'Candidate fits use no spectral offsets, but retain provisional cutoff/BOOST/envelope models. '
            'They are model comparisons, not measurements of hardware control laws.',
            'Only note0 fits candidate parameters; notes1/2 reuse them. The production decay had already '
            'been selected using note0 and evaluated on notes1/2; these are replication notes, not a fresh dataset.'],
        runtime=dict(python=platform.python_version(), numpy=np.__version__),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    if args.diagnostics:
        for name in ('dual_quiet', 'upper_only', 'lower_only', 'upper_flat_bypass'):
            path = args.diagnostics / f'{name}.wav'
            if path.exists():
                sr, a = read_audio(path)
                y = a.mean(axis=1)
                frequencies = note_frequencies(y, sr, LATENCY_SECONDS)
                report['diagnostics'].append(dict(name=name, input=identity(path),
                    manifest=identity(path.with_suffix('.render.json')),
                    measurements=[dict(note=n, **fit_harmonics(y, sr,
                        on + .15 + LATENCY_SECONDS, .06, f)) for n, ((on, _), f)
                        in enumerate(zip(NOTES, frequencies))]))
    report['free_cutoff_models'] = free_cutoff_models(hardware['rows'], report['conditional_models'])
    report['production_shape_errors_db'] = shape_errors(hardware, render)
    report['excerpt_spectrum'] = {
        'hardware': excerpt_spectrum(args.comparison / 'hardware-decoded-full.wav'),
        'production': excerpt_spectrum(args.comparison / 'septum-raw.wav')}
    if args.triangle_render:
        original_manifest = json.loads((args.comparison / 'septum-raw.render.json').read_text())
        candidate_manifest = json.loads(args.triangle_render.with_suffix('.render.json').read_text())
        if original_manifest['settings'] != candidate_manifest['settings'] or any(
                original_manifest['inputs'][key]['sha256'] != candidate_manifest['inputs'][key]['sha256']
                for key in ('midi', 'sysex')):
            raise ValueError('Triangle comparison must preserve MIDI, SysEx and all replay settings')
        if candidate_manifest['output']['sha256'] != identity(args.triangle_render)['sha256']:
            raise ValueError('Triangle audio does not match its render manifest')
        candidate = observations(args.triangle_render, LATENCY_SECONDS)
        report['triangle_polarity_candidate'] = dict(
            input=identity(args.triangle_render),
            render_manifest=identity(args.triangle_render.with_suffix('.render.json')),
            observations=candidate, shape_errors_db=shape_errors(hardware, candidate),
            qualification='Independent cross-preset check of a candidate selected from Dist Bs 1; '
                'no additional parameter fit to Moogie 1. Relative hardware phase is unmeasured.')
        report['excerpt_spectrum']['triangle_polarity'] = excerpt_spectrum(args.triangle_render)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    plot_report(hardware, render, args.output.with_suffix('.png'))
    for name, result in (('hardware', hardware), ('production', render)):
        for n in range(3):
            row = min((r for r in result['rows'] if r['note'] == n),
                      key=lambda r: abs(r['time'] - .15))
            print(name, n, np.round(row['ratio_db'], 3), 'bound excess',
                  round(row['pulse_bound_excess_db'], 3))
    for model in report['conditional_models']:
        print(model['name'], model['parameters'], model['rms_db_by_note'])


if __name__ == '__main__':
    main()
