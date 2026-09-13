#!/usr/bin/env python3
"""Independently audit SupaJuce 1 oscillator spacing before/after WIDE decoding.

Uses existing reference files only. MIDI remains reconstructed; neither
oscillator parameters nor a recording response are fitted. The conditional
played-note inference assumes the published tone octave and system tuning.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform

import numpy as np
import scipy
from scipy.io import wavfile
from scipy.optimize import minimize_scalar
from scipy.signal import welch


def identity(path):
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def audio(path):
    sr, data = wavfile.read(path)
    if sr != 44100 or data.dtype.kind != 'f' or data.ndim != 2:
        raise ValueError('Use the 44.1 kHz stereo float benchmark WAV files')
    if not np.isfinite(data).all():
        raise ValueError('Nonfinite audio')
    return sr, data


def fit(y, sr, start, end, frequency):
    first, last = round(start * sr), round(end * sr)
    x = y[first:last:2].astype(float)
    t = np.arange(first, last, 2) / sr - (start + end) / 2
    columns = [np.ones(len(t)), t]
    count = min(24, int(10000 / frequency))
    for harmonic in range(1, count + 1):
        phase = 2 * np.pi * harmonic * frequency * t
        columns.extend((np.cos(phase), np.sin(phase)))
    matrix = np.column_stack(columns)
    coefficients = np.linalg.lstsq(matrix, x, rcond=None)[0]
    amplitude = np.hypot(coefficients[2::2], coefficients[3::2])
    residual = np.mean((x - matrix @ coefficients) ** 2) / max(np.var(x), 1e-30)
    return amplitude, float(residual)


def measure(path, notes, delay):
    sr, stereo = audio(path)
    y = stereo.mean(axis=1)
    rows = []
    for index, event in enumerate(notes):
        start = event['on'] + .040 + delay
        end = min(event['on'] + .095, event['off'] - .015) + delay
        expected_note = event['note'] - 12  # published Upper tone OCTAVE -1, OSC2 coarse0
        expected_frequency = 440 * 2 ** ((expected_note - 69) / 12)
        frequency = minimize_scalar(lambda f: fit(y, sr, start, end, f)[1],
            bounds=(expected_frequency * .985, expected_frequency * 1.015), method='bounded').x
        amplitude, residual = fit(y, sr, start, end, frequency)
        power = amplitude ** 2
        total = max(np.sum(power), 1e-30)
        octave_family = np.arange(2, len(amplitude) + 1, 4) - 1
        three_octave_family = np.arange(8, len(amplitude) + 1, 16) - 1
        inferred_ratio = 2 if np.sum(power[octave_family]) >= np.sum(power[three_octave_family]) else 8
        rows.append(dict(note_index=index, window_seconds=[start, end],
            inferred_played_note=event['note'], expected_lower_sounding_note=expected_note,
            measured_lower_frequency_hz=float(frequency),
            measured_lower_midi_note=float(69 + 12 * np.log2(frequency / 440)),
            family_inferred_upper_frequency_hz=float(inferred_ratio * frequency),
            inferred_upper_family_ratio=inferred_ratio,
            harmonic_fit_residual_power=residual,
            amplitude=amplitude.tolist(),
            harmonic_db_relative_h1=(20 * np.log10(np.maximum(amplitude, 1e-30)
                                                   / max(amplitude[0], 1e-30))).tolist(),
            harmonic_power_fraction=(power / total).tolist(),
            octave_square_family_power_fraction=float(np.sum(power[octave_family]) / total),
            three_octave_square_family_power_fraction=float(np.sum(power[three_octave_family]) / total),
            upper_square_ratios_h6_h10_h14_to_h2_db=(20 * np.log10(
                np.maximum(amplitude[np.array((6, 10, 14))-1], 1e-30)
                / max(amplitude[1], 1e-30))).tolist()))
    end = round(1.8 * sr)
    frequency, density = welch(stereo[:end], sr, nperseg=8192, axis=0)
    density = density.mean(axis=1)
    band = (frequency >= 20) & (frequency <= 16000)
    return dict(input=identity(path), rows=rows, delay_seconds=delay,
        excerpt_seconds=1.8, power_centroid_20_16000_hz=float(np.sum(
            frequency[band] * density[band]) / np.sum(density[band])))


def compare(hardware, rendered):
    result = []
    for reference, candidate in zip(hardware['rows'], rendered['rows']):
        # Total variation compares normalized harmonic energy, without letting
        # tiny nominally absent harmonics dominate a logarithmic error score.
        a, b = (np.array(x['harmonic_power_fraction']) for x in (reference, candidate))
        count = min(len(a), len(b))
        a, b = a[:count] / a[:count].sum(), b[:count] / b[:count].sum()
        result.append(dict(note_index=reference['note_index'],
            harmonic_energy_total_variation=float(.5 * np.sum(np.abs(a - b))),
            upper_family_ratio_errors_db=(np.array(
                candidate['upper_square_ratios_h6_h10_h14_to_h2_db']) - np.array(
                reference['upper_square_ratios_h6_h10_h14_to_h2_db'])).tolist()))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path,
                        help='wide-pitch-implementation directory with before/after/supa-juce-1')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    before, after = (args.root / x / 'supa-juce-1' for x in ('before', 'after'))
    manifests = [json.loads((path / 'septum-raw.render.json').read_text()) for path in (before, after)]
    comparisons = [json.loads((path / 'comparison.json').read_text()) for path in (before, after)]
    if manifests[0]['settings'] != manifests[1]['settings'] or comparisons[0]['case'] != comparisons[1]['case']:
        raise ValueError('Before/after must use identical replay settings and reconstruction')
    for name in ('original-patch.syx', 'reconstructed-performance.mid', 'hardware-decoded-full.wav'):
        if (before / name).read_bytes() != (after / name).read_bytes():
            raise ValueError(f'Before/after differ: {name}')
    for path, manifest in zip((before, after), manifests):
        if identity(path / 'septum-raw.wav')['sha256'] != manifest['output']['sha256']:
            raise ValueError('Render WAV no longer matches manifest')
    case = comparisons[1]['case']
    notes = case['notes']
    hardware = measure(after / 'hardware-decoded-full.wav', notes, 0)
    old = measure(before / 'septum-raw.wav', notes, manifests[0]['output']['latency_samples'] / 44100)
    new = measure(after / 'septum-raw.wav', notes, manifests[1]['output']['latency_samples'] / 44100)
    report = dict(schema_version=1, status='independent octave-family audit; original MIDI unavailable',
        reference=comparisons[1]['reference'], bank=comparisons[1]['bank'], reconstruction=case,
        unchanged_inputs=[identity(after / x) for x in ('original-patch.syx', 'reconstructed-performance.mid')],
        render_manifests=[identity(path / 'septum-raw.render.json') for path in (before, after)],
        initial_patches=[m['output']['initial_patch'] for m in manifests],
        hardware=hardware, before=old, after=new,
        before_error=compare(hardware, old), after_error=compare(hardware, new),
        interpretation='The hardware contains the odd-harmonic family of a square at twice the lower '
            'square frequency (H2,H6,H10,H14) while H4,H8,H12 are suppressed. The correction moves '
            'OSC1 from eight times OSC2 frequency to twice it. Upper carrier level and higher '
            'harmonic balance still differ from hardware.',
        limitations=['Frequencies refine supplied hardware-only pitch hypotheses within +/-1.5%; '
            'the lowest nonzero harmonic and second-square family jointly support the octave inference.',
            'Played-note inference assumes published Upper tone OCTAVE -1 and unchanged system tuning. '
            'Original notes, velocity, gates, controllers and exact recorded patch revision are unknown.',
            'Delay and reverb are enabled. Later note windows contain earlier notes or tails; their '
            'harmonic-fit residuals are retained. The first window is the strongest isolated check.',
            'Centroid closeness alone is misleading: before was closer in centroid despite placing '
            'the dominant oscillator in the wrong harmonic family.',
            'This endpoint recording supports raw100/WIDEoff at +12 relative semitones. It does '
            'not calibrate intermediate raw values or WIDE-on behavior.'],
        runtime=dict(python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__),
        script_sha256=identity(Path(__file__))['sha256'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    for name, take in (('hardware', hardware), ('before', old), ('after', new)):
        print(name, 'centroid', round(take['power_centroid_20_16000_hz'], 2))
        print('one-octave square-family power fractions', [round(r['octave_square_family_power_fraction'], 4)
                                                           for r in take['rows']])
    print('before total variation', [round(r['harmonic_energy_total_variation'], 4) for r in report['before_error']])
    print('after total variation', [round(r['harmonic_energy_total_variation'], 4) for r in report['after_error']])


if __name__ == '__main__':
    main()
