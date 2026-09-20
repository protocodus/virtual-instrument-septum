#!/usr/bin/env python3
"""Audit an estimated Class A opening phrase against hardware audio only.

No renderer is called. The fixed note/window hypotheses were selected from
the official recording's spectral families, not software audio or DSP fitting.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.io import wavfile
from scipy.signal import stft

from extract_reference_patch import parse_bank, read_bank


ROOT = Path(__file__).resolve().parents[1]
WINDOWS = ((.035, .110), (.140, .210), (.258, .292), (.315, .360),
           (.373, .403), (.438, .500), (.550, .605), (.653, .702),
           (.753, .800), (.890, 1.090))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def peak(frequencies, magnitude, expected, span=.035):
    indices = np.flatnonzero((frequencies >= expected * (1 - span))
                             & (frequencies <= expected * (1 + span)))
    index = indices[np.argmax(magnitude[indices])]
    return float(frequencies[index]), float(magnitude[index])


def spectrum(signal, rate, start, end):
    segment = signal[round(start * rate):round(end * rate)].astype(float)
    window = np.hanning(len(segment))
    magnitude = abs(np.fft.rfft(segment * window, 262144))
    return np.fft.rfftfreq(262144, 1 / rate), magnitude


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    case_path = ROOT / 'Docs/fidelity/reconstructions/expanded/class-a.json'
    case = json.loads(case_path.read_text())
    catalog = json.loads((ROOT / 'Docs/fidelity/hardware-reference-catalog.json').read_text())
    reference = next(row for row in catalog['recordings'] if row['id'] == 'lead-01')
    bank = next(row for row in catalog['banks'] if row['id'] == 'lead')
    audio_path = args.sources / reference['local_filename']
    bank_path = args.sources / bank['local_filename']
    if sha(audio_path) != reference['sha256'] or sha(bank_path) != bank['sha256']:
        raise ValueError('Reference or bank hash differs from pinned official source')
    bank_data, member = read_bank(bank_path)
    name, blocks = parse_bank(bank_data)[0]
    tone = blocks[1]
    observed = [tone[i] for i in (0, 1, 2, 3, 5, 6, 7, 8, 9, 11, 59, 60, 61, 63)]
    if name != 'Class A' or observed != [0, 0, 100, 64, 64, 0, 0, 64, 64, 64, 2, 63, 0, 1]:
        raise ValueError('Unexpected Class A oscillator or performance settings')
    wav_path = args.output / 'hardware-decoded.wav'
    command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
               '-i', str(audio_path), '-ar', '44100', '-ac', '2',
               '-c:a', 'pcm_f32le', str(wav_path)]
    subprocess.run(command, check=True)
    rate, stereo = wavfile.read(wav_path)
    if rate != 44100 or stereo.ndim != 2 or not np.isfinite(stereo).all():
        raise ValueError('Unexpected decoded audio')
    signal = stereo.mean(axis=1)
    rows = []
    for note, (start, end) in zip(case['notes'], WINDOWS, strict=True):
        expected = 440 * 2 ** ((note['note'] - 69) / 12)
        frequencies, magnitude = spectrum(signal, rate, start, end)
        harmonic_peaks = [peak(frequencies, magnitude, expected * h)
                          for h in range(1, 7)]
        implied_roots = [frequency / h for h, (frequency, _) in
                         enumerate(harmonic_peaks, 1)]
        inferred_root = float(np.median(implied_roots))
        lower_peak = peak(frequencies, magnitude, expected / 2, .08)
        rows.append(dict(estimated_played_midi=note['note'], window_seconds=[start, end],
                         expected_primary_hz=expected,
                         primary_harmonic_peak_hz=[p[0] for p in harmonic_peaks],
                         median_harmonic_implied_primary_hz=inferred_root,
                         median_primary_cents_error=float(1200 * np.log2(inferred_root / expected)),
                         expected_lower_oscillator_hz=expected / 2,
                         nearby_lower_peak_hz=lower_peak[0],
                         lower_peak_db_relative_primary_peak=float(20 * np.log10(
                             max(lower_peak[1], 1e-30) / max(harmonic_peaks[0][1], 1e-30)))))
    motion = []
    for center in np.arange(1.1, 2.101, .05):
        frequencies, magnitude = spectrum(signal, rate, center - .04, center + .04)
        indices = np.flatnonzero((frequencies > 380) & (frequencies < 455))
        frequency = float(frequencies[indices[np.argmax(magnitude[indices])]])
        motion.append(dict(center_seconds=round(float(center), 3), primary_hz=frequency,
                           semitones_above_G4=float(12 * np.log2(frequency / 391.995436))))
    report = dict(schema_version=1, status='hardware-only transcription audit; MIDI is estimated',
        source=dict(audio_url=reference['url'], audio_sha256=sha(audio_path),
                    bank_url=bank['url'], bank_archive_sha256=sha(bank_path), member=member,
                    bank_sha256=hashlib.sha256(bank_data).hexdigest()),
        case_sha256=sha(case_path), script_sha256=sha(Path(__file__)), decode_command=command,
        patch=dict(active_part='upper', oscillator_waveforms=['saw', 'saw'],
                   raw_coarse_bytes=[100, 64], signed_coarse=[36, 0], wide=[False, False],
                   current_codec_coarse_semitones=[12, 0], tone_octave_shift=-1,
                   net_oscillator_semitones=[0, -12], fine_cents=[0, 0],
                   pitch_envelope_depths=[0, 0], lfo_depths=[tone[i] - 64 for i in (46, 48, 56, 58)],
                   portamento=False, bend_range_semitones=2, mono_mode_raw=1,
                   mono_mode='SOLO+LEGATO',
                   cutoff_velocity_sensitivity=0, amp_velocity_sensitivity=tone[31] - 64,
                   delay_send=24, reverb_send=48),
        method='Six Hann-window FFT harmonic peaks per manually selected settled note window; '
               'median peak/harmonic estimates the primary frequency. Sub-octave peaks are '
               'reported separately. No engine audio, synthesis fitting or controller recovery.',
        windows=rows, later_pitch_motion=motion,
        limitations=case['uncertainties'] + [
            'Sub-octave peaks in short windows are affected by frequency resolution and effects; '
            'some low peaks can contain delayed preceding notes.',
            'The 1.25–1.9 s G4-to-A4 rise is consistent with the published two-semitone bend range, '
            'but the original bend messages or any live patch edits are unverified.'])
    (args.output / 'audit.json').write_text(json.dumps(report, indent=2) + '\n')
    frequencies, times, transformed = stft(signal[:round(2.2 * rate)], rate,
                                           nperseg=2048, noverlap=1960, nfft=8192)
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), gridspec_kw={'height_ratios': [3, 1]})
    axes[0].pcolormesh(times, frequencies, 20 * np.log10(np.maximum(abs(transformed), 1e-8)),
                       shading='auto', vmin=-65, vmax=-10)
    axes[0].set(ylim=(25, 1800), xlim=(0, 1.25), yscale='log', ylabel='Frequency (Hz)',
                title='Class A hardware opening: estimated notes; published patch retained')
    for note in case['notes']:
        axes[0].axvline(note['on'], color='white', alpha=.4, linewidth=.6)
        axes[0].text(note['on'] + .006, 1500, str(note['note']), color='white', fontsize=8)
    axes[0].set_xlabel('Hardware timeline (seconds); labels are estimated played MIDI notes')
    axes[1].plot([r['center_seconds'] for r in motion], [r['semitones_above_G4'] for r in motion])
    axes[1].axvline(case['duration_seconds'], color='red', linestyle='--', label='Reconstruction ends')
    axes[1].set(xlabel='Hardware timeline (seconds)', ylabel='Semitones above G4',
                title='Later pitch movement excluded from the note-only reconstruction')
    axes[1].grid(alpha=.3)
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(args.output / 'hardware-note-evidence.png', dpi=160)
    print(json.dumps({'report': str(args.output / 'audit.json'),
                      'maximum_absolute_cents': max(abs(r['median_primary_cents_error']) for r in rows),
                      'notes': len(rows)}, indent=2))


if __name__ == '__main__':
    main()
