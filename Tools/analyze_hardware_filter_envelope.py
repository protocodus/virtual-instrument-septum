#!/usr/bin/env python3
"""Conditional filter-envelope analysis of the official Moogie1 hardware demo.

This does not calibrate SH-201 parameters or alter/render the instrument. It fits
hardware harmonic-ratio trajectories under explicitly assumed LP24 and waveform
models. Original MIDI, capture processing and isolated triangle spectrum remain
unknown. Inputs are local PCM WAV files; this tool downloads nothing.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.optimize import minimize_scalar

NOTES = ((.029, .391), (.939, 1.305), (1.901, 2.231))
HARMONICS = np.array((4, 6, 8))
BASE_HZ = 20 * 2 ** (30 * 10 / 127)
PEAK_HZ = BASE_HZ * 2 ** (22 * 10 / 63)
DECAY_SECONDS = .002 * 6000 ** (49 / 127)
CURRENT_TAU = DECAY_SECONDS / np.log(1000)


def harmonic_fit(y, sr, start, end, fundamental):
    first, last = round(start * sr), round(end * sr)
    x = y[first:last:4].astype(float)
    t = np.arange(first, last, 4) / sr - start
    columns = [np.ones(len(t)), t - t.mean()]
    for harmonic in range(1, 13):
        phase = 2 * np.pi * fundamental * harmonic * t
        columns.extend((np.cos(phase), np.sin(phase)))
    matrix = np.column_stack(columns)
    coefficients = np.linalg.lstsq(matrix, x, rcond=None)[0]
    amplitudes = np.hypot(coefficients[2::2], coefficients[3::2])
    residual = np.mean((x - matrix @ coefficients) ** 2)
    residual /= max(np.mean((x - x.mean()) ** 2), 1e-30)
    return amplitudes, float(residual)


def extract(y, sr, width=.04, shift=0):
    rows = []
    for index, (on, off) in enumerate(NOTES):
        frequency = minimize_scalar(
            lambda f: harmonic_fit(y, sr, on + .03, off - .02, f)[1],
            bounds=(38, 39), method='bounded').x
        first = max(.04, width / 2 + .01)
        for t in np.arange(first, off - on - .035 - width / 2, .01):
            amplitude, residual = harmonic_fit(
                y, sr, on + t - width / 2 + shift,
                on + t + width / 2 + shift, frequency)
            ratio = 20 * np.log10(np.maximum(amplitude[HARMONICS - 1], 1e-30)
                                 / max(amplitude[1], 1e-30))
            rows.append(dict(note=index, time=float(t), frequency=float(frequency),
                             ratio_db=ratio.tolist(), fit_residual=residual))
    return rows


def response_db(frequency, cutoff, topology='svf'):
    x = frequency / cutoff
    if topology == 'butterworth':
        return -10 * np.log10(1 + x ** 8)
    # Analog equivalent of the current two SVF stages at resonance0:
    # damping2 and1.2. At these frequencies the exact44.1kHzTPT prewarp
    # changes magnitude by at most0.006dB over cutoff20..20000Hz.
    return (-10 * np.log10((1 - x * x) ** 2 + 4 * x * x)
            - 10 * np.log10((1 - x * x) ** 2 + 1.44 * x * x))


def predicted_ratios(rows, shape, time, topology='svf'):
    t = np.array([r['time'] for r in rows])
    frequency = np.array([r['frequency'] for r in rows])[:, None]
    if shape == 'linear_control':
        cutoff = BASE_HZ * (PEAK_HZ / BASE_HZ) ** np.maximum(1 - t / time, 0)
    elif shape == 'exponential_hz':
        cutoff = BASE_HZ + (PEAK_HZ - BASE_HZ) * np.exp(-t / time)
    else:
        cutoff = BASE_HZ * (PEAK_HZ / BASE_HZ) ** np.exp(-t / time)
    cutoff = cutoff[:, None]
    return (response_db(frequency * HARMONICS, cutoff, topology)
            - response_db(frequency * 2, cutoff, topology))


def evaluate(rows, shape, time, topology, training_note=0):
    observed = np.array([r['ratio_db'] for r in rows])
    predicted = predicted_ratios(rows, shape, time, topology)
    train = np.array([r['note'] == training_note for r in rows])
    # Only training-note measurements estimate constant oscillator/capture
    # offsets. Held-out notes retain these same offsets, with no refitting.
    offsets = (observed[train] - predicted[train]).mean(axis=0)
    residual = observed - predicted - offsets
    rms = {str(i): float(np.sqrt(np.mean(residual[
        np.array([r['note'] == i for r in rows])] ** 2))) for i in range(3)}
    return dict(shape=shape, time_seconds=float(time), topology=topology,
                training_note=training_note, ratio_offsets_db=offsets.tolist(),
                rms_residual_db_by_note=rms,
                predicted_ratio_db=(predicted + offsets).tolist())


def fit_time(rows, shape, topology='svf', training_note=0):
    def objective(time):
        result = evaluate(rows, shape, time, topology, training_note)
        return result['rms_residual_db_by_note'][str(training_note)] ** 2
    optimum = minimize_scalar(objective, bounds=(.05, .8), method='bounded')
    return evaluate(rows, shape, optimum.x, topology, training_note)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hardware', required=True, type=Path,
                        help='decoded full official Moogie1 WAV')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    sr, audio = wavfile.read(args.hardware)
    if audio.dtype.kind in 'iu':
        raise ValueError('Use decoded float PCM WAV, not integer PCM')
    y = audio.mean(axis=1) if audio.ndim == 2 else audio
    if len(y) / sr < NOTES[-1][1]:
        raise ValueError('Hardware input is shorter than the analyzed passage')
    rows = extract(y, sr)
    results = []
    for topology in ('svf', 'butterworth'):
        results.extend((evaluate(rows, 'exponential_control', CURRENT_TAU, topology),
                        evaluate(rows, 'exponential_control', DECAY_SECONDS, topology)))
        for shape in ('exponential_control', 'linear_control', 'exponential_hz'):
            results.append(fit_time(rows, shape, topology))
    sensitivity = []
    for width, shift in ((.03, 0), (.06, 0), (.08, 0), (.04, -.02), (.04, .02)):
        alternate_rows = extract(y, sr, width, shift)
        for shape in ('exponential_control', 'linear_control', 'exponential_hz'):
            result = fit_time(alternate_rows, shape)
            result.pop('predicted_ratio_db')
            sensitivity.append(dict(width=width, shift=shift, **result))
    report = dict(schema_version=1, status='conditional analysis, not calibrated hardware',
                  input=str(args.hardware), sha256=hashlib.sha256(
                      args.hardware.read_bytes()).hexdigest(), sample_rate=sr,
                  input_notes=NOTES, ratios=['H4/H2', 'H6/H2', 'H8/H2'],
                  model_base_hz=BASE_HZ, model_peak_hz=PEAK_HZ,
                  base_and_peak_source='unchanged Septum mapping, not manufacturer measurements',
                  observations=rows, model_results=results, sensitivity=sensitivity,
                  qualification='Assumes symmetric lower square/triangle and linear processing. '
                  'Only note0 fits timing and constant ratio offsets; notes1,2 are held out. '
                  'No original MIDI, raw recording chain or isolated hardware waveforms. '
                  'Overlapping frames are correlated; sensitivity ranges are not confidence intervals.')
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'conditional-filter-envelope.json').write_text(
        json.dumps(report, indent=2) + '\n')
    for result in results:
        print(result['topology'], result['shape'],
              round(result['time_seconds'], 6), result['rms_residual_db_by_note'])


if __name__ == '__main__':
    main()
