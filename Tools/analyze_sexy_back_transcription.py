#!/usr/bin/env python3
"""Check Sexy Back note hypotheses using only official audio and bank bytes.

This is a transcription/provenance check, not a DSP comparison or filter fit.
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
from scipy.signal import butter, sosfiltfilt, stft

from extract_reference_patch import parse_bank, read_bank


ROOT = Path(__file__).resolve().parents[1]
WINDOWS = ((.150, .325), (.485, .555), (.860, .985))
GATE_REGIONS = ((.020, .390), (.390, .650), (.760, 1.150))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def peak(frequencies, magnitude, expected, span=.025):
    indices = np.flatnonzero((frequencies >= expected * (1 - span))
                             & (frequencies <= expected * (1 + span)))
    index = indices[np.argmax(magnitude[indices])]
    return float(frequencies[index]), float(magnitude[index])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    case_path = ROOT / 'Docs/fidelity/reconstructions/expanded/sexy-back.json'
    case = json.loads(case_path.read_text())
    catalog = json.loads((ROOT / 'Docs/fidelity/hardware-reference-catalog.json').read_text())
    reference = next(row for row in catalog['recordings'] if row['id'] == 'bass-06')
    bank = next(row for row in catalog['banks'] if row['id'] == 'bass')
    audio_path, bank_path = (args.sources / row['local_filename'] for row in (reference, bank))
    if sha(audio_path) != reference['sha256'] or sha(bank_path) != bank['sha256']:
        raise ValueError('Audio or bank does not match pinned official source')
    bank_data, member = read_bank(bank_path)
    name, blocks = parse_bank(bank_data)[5]
    if name != 'Sexy Back' or blocks[0][17] != 1:
        raise ValueError('Expected the original dual-mode Sexy Back preset')
    patch = []
    for label, tone in zip(('upper', 'lower'), blocks[1:3], strict=True):
        oscillators = []
        for start in (0, 6):
            raw = tone[start + 2] - 64
            wide = bool(tone[start + 1])
            physical = raw if wide else int(np.sign(raw) * np.floor(abs(raw / 3) + .5))
            oscillators.append(dict(waveform_raw=tone[start], wide=wide, raw_coarse_byte=tone[start + 2],
                signed_raw_coarse=raw, current_codec_semitones=physical,
                fine_cents=tone[start + 3] - 64, pitch_envelope_depth=tone[start + 5] - 64))
        patch.append(dict(part=label, oscillators=oscillators, tone_octave=tone[60] - 64,
            cutoff=tone[19], slope_db=24 if tone[18] else 12, resonance=tone[22],
            filter_env_depth=tone[27] - 64, filter_velocity=tone[21] - 64,
            lfo_depths=[tone[i] - 64 for i in (46, 48, 56, 58)],
            amp_velocity=tone[31] - 64, portamento=bool(tone[61]), portamento_time=tone[62],
            mono_raw=tone[63], overdrive=bool(tone[28]), low_frequency_mode_raw=tone[16],
            delay_send=tone[37]))
    wav_path = args.output / 'hardware-decoded.wav'
    command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-i', str(audio_path),
               '-ar', '44100', '-ac', '2', '-c:a', 'pcm_f32le', str(wav_path)]
    subprocess.run(command, check=True)
    rate, stereo = wavfile.read(wav_path)
    if rate != 44100 or stereo.ndim != 2 or not np.isfinite(stereo).all():
        raise ValueError('Unexpected decoded hardware PCM')
    signal = stereo.mean(axis=1).astype(float)
    rows = []
    for event, (start, end) in zip(case['notes'], WINDOWS, strict=True):
        base = 440 * 2 ** ((event['note'] - 69) / 12)
        expected = [base * 2 ** ((o['current_codec_semitones'] + 12 * part['tone_octave']
                                 + o['fine_cents'] / 100) / 12)
                    for part in patch for o in part['oscillators']]
        segment = signal[round(start * rate):round(end * rate)]
        magnitude = abs(np.fft.rfft(segment * np.hanning(len(segment)), 131072))
        frequencies = np.fft.rfftfreq(131072, 1 / rate)
        oscillator_peaks = [peak(frequencies, magnitude, f, .08 if f < 50 else .04) for f in expected]
        saw_peaks = [peak(frequencies, magnitude, expected[3] * h) for h in range(1, 5)]
        rows.append(dict(window_seconds=[start, end], estimated_midi=event['note'],
            expected_frequencies_upper1_upper2_lower1_lower2_hz=expected,
            nearby_oscillator_peak_hz=[p[0] for p in oscillator_peaks],
            nearby_oscillator_peak_db_relative_window_max=[float(20 * np.log10(
                max(p[1], 1e-30) / max(magnitude))) for p in oscillator_peaks],
            lower_saw_expected_hz=expected[3], lower_saw_harmonic_peak_hz=[p[0] for p in saw_peaks],
            lower_saw_median_harmonic_implied_hz=float(np.median(
                [p[0] / h for h, p in enumerate(saw_peaks, 1)]))))
    bandpassed = sosfiltfilt(butter(3, [300, 5000], btype='bandpass', fs=rate, output='sos'), signal)
    gates = []
    for low, high in GATE_REGIONS:
        times = np.arange(low, high, .001)
        rms = np.array([np.sqrt(np.mean(bandpassed[round((t - .001) * rate):
                            round((t + .001) * rate)] ** 2)) for t in times])
        threshold = float(np.percentile(rms, 80) * .2)
        active = times[rms > threshold]
        gates.append(dict(search_region_seconds=[low, high], threshold_rms=threshold,
                          first_above_seconds=float(active[0]), last_above_seconds=float(active[-1])))
    report = dict(schema_version=1, status='hardware-only transcription; original MIDI unavailable',
        source=dict(audio_url=reference['url'], audio_sha256=sha(audio_path), bank_url=bank['url'],
                    bank_archive_sha256=sha(bank_path), archive_member=member,
                    bank_sha256=hashlib.sha256(bank_data).hexdigest()),
        script_sha256=sha(Path(__file__)), case_sha256=sha(case_path), decode_command=command,
        patch=patch, settled_windows=rows, bandpassed_energy_boundaries=gates,
        method='Manually selected settled hardware windows; Hann FFT local peaks around expected '
               'oscillator families and four lower-saw harmonics. Two-ms RMS at 1-ms hops in '
               '300–5000 Hz supplies independent energy gate evidence. No engine audio or DSP fitting.',
        limitations=case['uncertainties'] + [
            'The lower saw and upper supersaw harmonics overlap; local peak positions are family '
            'evidence, not independently isolated oscillator frequencies. Short low-frequency windows '
            'have poor precision; the second note is too short to resolve the ~19-Hz oscillator.'])
    (args.output / 'audit.json').write_text(json.dumps(report, indent=2) + '\n')
    frequencies, times, transformed = stft(signal[:round(1.2 * rate)], rate,
                                           nperseg=2048, noverlap=1872, nfft=4096)
    fig, axes = plt.subplots(2, 1, figsize=(11, 6), sharex=True, gridspec_kw={'height_ratios': [3, 1]})
    axes[0].pcolormesh(times, frequencies, 20 * np.log10(np.maximum(abs(transformed), 1e-8)),
                       shading='auto', vmin=-65, vmax=-10)
    axes[0].set(yscale='log', ylim=(15, 4000), ylabel='Frequency (Hz)',
                title='Sexy Back hardware: three estimated Eb2 / MIDI 39 notes')
    energy_times = np.arange(.002, 1.2, .002)
    energy = [np.sqrt(np.mean(signal[round((t - .001) * rate):round((t + .001) * rate)] ** 2))
              for t in energy_times]
    axes[1].plot(energy_times, energy)
    for axis in axes:
        for event in case['notes']:
            axis.axvline(event['on'], color='green', alpha=.5)
            axis.axvline(event['off'], color='red', alpha=.5)
    axes[1].set(xlim=(0, 1.2), xlabel='Original hardware timeline (seconds)', ylabel='2-ms RMS')
    axes[1].grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(args.output / 'hardware-note-evidence.png', dpi=150)
    print(json.dumps({'report': str(args.output / 'audit.json'), 'notes': len(rows),
                      'lower_saw_family_hz': [r['lower_saw_median_harmonic_implied_hz'] for r in rows]}, indent=2))


if __name__ == '__main__':
    main()
