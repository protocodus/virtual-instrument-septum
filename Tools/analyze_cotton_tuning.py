#!/usr/bin/env python3
"""Audit Cotton Wool's oscillator spacing against local, hash-pinned Roland audio.

No downloads, synthesis changes, EQ, normalization or inferred MIDI playback.
Requires NumPy, SciPy, Matplotlib and ffmpeg. Optional diagnostic WAVs are
explicitly identified as modified-preset/reconstructed-MIDI comparisons.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
from scipy import signal
from scipy.io import wavfile
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
SR = 44100


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def spectrum(audio, start, end):
    x = audio[round(start * SR):round(end * SR)].astype(float)
    window = np.hanning(len(x))
    f = np.fft.rfftfreq(1048576, 1 / SR)
    amplitudes = abs(np.fft.rfft(x * window[:, None], 1048576, axis=0)) * 2 / window.sum()
    # Average channel power, never sum channels: anti-phase material survives.
    power = np.mean(amplitudes ** 2, axis=1)
    return f, power, amplitudes


def peak(f, power, low, high):
    inds = np.flatnonzero((f >= low) & (f <= high))
    i = inds[np.argmax(power[inds])]
    return {'frequency_hz': float(f[i]), 'amplitude_dbfs': float(10 * np.log10(max(power[i], 1e-30)))}


def stats(audio):
    f, p = signal.welch(audio.astype(float), SR, nperseg=65536, axis=0)
    p = p.mean(axis=1)
    bands = {}
    for lo, hi in ((5, 10), (10, 20), (20, 30), (30, 40), (40, 80), (80, 160), (160, 1000), (40, 16000)):
        power = p[(f >= lo) & (f < hi)].sum() * (f[1] - f[0])
        bands[f'{lo}-{hi}'] = float(10 * np.log10(max(power, 1e-30)))
    ratio = p[(f >= 20) & (f < 40)].sum() / max(p[(f >= 40) & (f < 16000)].sum(), 1e-30)
    f8, p8 = signal.welch(audio.astype(float), SR, nperseg=8192, axis=0)
    p8 = p8.mean(axis=1)
    selected = (f8 >= 20) & (f8 <= 16000)
    return {'band_power_dbfs': bands, '20_40_over_40_16000_db': float(10 * np.log10(max(ratio, 1e-30))),
            'centroid_20_16000_hz_welch8192': float(np.sum(f8[selected] * p8[selected]) / p8[selected].sum()),
            'rms_dbfs': float(10 * np.log10(np.mean(audio.astype(float) ** 2)))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--comparison', type=Path, required=True,
                        help='existing Cotton Wool comparison with raw hardware and Septum WAVs')
    parser.add_argument('--diagnostics', type=Path,
                        help='optional scratch directory from the explicitly modified octave-gap experiment')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    catalog_path = ROOT / 'Docs/fidelity/hardware-reference-catalog.json'
    catalog = json.loads(catalog_path.read_text())
    corpus, retained = [], {}
    for record in catalog['recordings']:
        path = args.sources / record['local_filename']
        if digest(path) != record['sha256']:
            raise ValueError(f'Source hash mismatch: {path}')
        raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path),
                                       '-f', 'f32le', '-ac', '2', '-ar', str(SR), 'pipe:1'])
        audio = np.frombuffer(raw, dtype='<f4').reshape(-1, 2).astype(float)
        corpus.append({'id': record['id'], 'name': record['title'], 'source_url': record['url'],
                       'sha256': record['sha256'], 'seconds': len(audio) / SR, **stats(audio)})
        if record['id'] in ('pad-01', 'bass-04'):
            retained[record['id']] = audio
    windows = []
    cases = [('pad-01', a, a + .235, 65.15) for a in (.145, 4.145, 8.145, 12.145)]
    cases += [('pad-01', 2.8, 3.35, hz) for hz in (154.94, 173.91, 219.11)]
    cases += [('bass-04', .55, .8, 32.3), ('bass-04', 1.15, 1.4, 38.5),
              ('bass-04', 3.65, 3.85, 57.9), ('bass-04', 5.0, 5.3, 38.7)]
    for ident, start, end, expected in cases:
        f, power, channels = spectrum(retained[ident], start, end)
        base = peak(f, power, expected * .975, expected * 1.025)
        f0 = base['frequency_hz']
        harmonics = [peak(f, power, f0 * h * .975, f0 * h * 1.025) for h in range(1, 9)]
        channel_harmonics = [[peak(f, channels[:, c] ** 2, f0 * h * .975, f0 * h * 1.025)
                              for h in range(1, 9)] for c in range(2)]
        windows.append({'recording_id': ident, 'start_seconds': start, 'end_seconds': end,
                        'expected_low_peak_hz': expected, 'harmonic_band_peaks': harmonics,
                        'channel_harmonic_band_peaks': channel_harmonics,
                        'second_over_low_frequency_ratio': harmonics[1]['frequency_hz'] / f0})
    comparisons = []
    audio_cases = [('hardware', args.comparison / 'hardware-excerpt-raw.wav'),
                   ('production_before_tuning_revision', args.comparison / 'septum-raw.wav')]
    if args.diagnostics:
        audio_cases += [('diagnostic_midi_plus12_only', args.diagnostics / 'notes-plus12-only.wav'),
                        ('diagnostic_midi_plus12_coarse_minus12', args.diagnostics / 'coarse-minus12-notes-plus12.wav')]
    for name, path in audio_cases:
        rate, audio = wavfile.read(path)
        if rate != SR:
            raise ValueError('Comparison sample rate mismatch')
        comparisons.append({'name': name, 'path': str(path.resolve()), 'sha256': digest(path),
                            'start_seconds': 0, 'duration_seconds': 5, **stats(audio[:5 * SR])})
    report = {
        'schema_version': 1, 'status': 'recording evidence; original MIDI and recording patch revision unverified',
        'script_sha256': digest(Path(__file__)), 'catalog_sha256': digest(catalog_path),
        'method': {'sample_rate': SR, 'decode': 'ffmpeg float32 stereo, no gain or EQ',
                   'spectral_windows': 'Hann, FFT zero-padded to1048576; reported bin peaks, not fitted precise oscillator frequencies',
                   'stereo': 'mean channel power; independent left/right peaks also retained',
                   'band_power': 'Welch65536, Hann,50% overlap, constant detrend; integrate rectangular band masks',
                   'centroid': 'Welch8192 for compatibility with existing comparisons',
                   'limits': 'Short notes, glide, detuned stacks, effects, other notes and MP3 artifacts limit oscillator isolation. Higher harmonic bins may contain overlapping notes.'},
        'corpus': corpus, 'harmonic_windows': windows, 'first_five_second_comparisons': comparisons,
        'diagnostic_provenance': json.loads((args.diagnostics / 'diagnostic-provenance.json').read_text())
                                 if args.diagnostics else None,
        'conclusions': [
            'Cotton Wool supports a sine fundamental plus a harmonic stack approximately one octave higher, not the three-octave separation implied by literal coarse decoding.',
            'Pedal Bs1 has the same published oscillator settings and independently shows approximately octave-spaced low and upper peaks.',
            'The32 demos do not support one common steep low-frequency removal as the explanation for Cotton; several retain substantial20–30Hz power. This does not establish an unprocessed recording chain.',
            'The evidence motivates testing WIDE-dependent coarse decoding and raising the Cotton reconstruction notes one octave. It does not determine exact coarse quantization or prove the original MIDI.'],
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'cotton-tuning-audit.json').write_text(json.dumps(report, indent=2) + '\n')
    fig, axes = plt.subplots(3, 1, figsize=(11, 10), layout='constrained')
    for ax, ident, start, end, title in (
            (axes[0], 'pad-01', .145, .38, 'Cotton Wool: isolated first note'),
            (axes[1], 'bass-04', .55, .8, 'Pedal Bs 1: independent preset with identical oscillator settings')):
        f, power, _ = spectrum(retained[ident], start, end)
        ax.plot(f, 10 * np.log10(np.maximum(power, 1e-15)), color='#315c86')
        ax.set(xlim=(15, 600), ylim=(-105, -8), xscale='log', ylabel='Hann amplitude / dBFS',
               xlabel='Frequency / Hz', title=f'{title} ({start}-{end} s)')
        ax.grid(alpha=.2)
    values = sorted(corpus, key=lambda r: r['20_40_over_40_16000_db'])
    axes[2].bar(range(len(values)), [r['20_40_over_40_16000_db'] for r in values],
                color=['#d28b35' if r['id'] in ('pad-01', 'bass-04') else '#738ba1' for r in values])
    axes[2].set_xticks(range(len(values)), [r['name'] for r in values], rotation=80, fontsize=7)
    axes[2].set(ylabel='20-40 Hz / 40 Hz-16 kHz power / dB', title='All32 official demo files, complete recordings')
    axes[2].grid(axis='y', alpha=.2)
    fig.suptitle('Cotton Wool tuning audit: recordings support an octave-spacing correction', fontsize=13)
    fig.savefig(args.output / 'cotton-tuning-audit.png', dpi=150)
    plt.close(fig)
    print(args.output / 'cotton-tuning-audit.json')


if __name__ == '__main__':
    main()
