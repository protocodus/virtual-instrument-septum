#!/usr/bin/env python3
"""Conditional Air Lead 1 resonance audit using the official named recording.

No DSP is edited. Even harmonics are interpreted as a saw behind LP24, assuming
a symmetric triangle contributes no even harmonics. Effects/capture response
remain confounders. Numerical Q fits are conditional, not Roland calibration.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
import numpy as np
from scipy.io import wavfile
from scipy.optimize import brentq, least_squares, minimize_scalar
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from extract_reference_patch import read_bank, parse_bank, encode_syx
from compare_hardware import write_midi

ROOT = Path(__file__).resolve().parents[1]
HARMONICS = np.arange(2, 13, 2)
CENTERS = (.065, .075, .085, .095)
WIDTHS = (.03, .04, .05)
OTHER_NOTES = ((.175, 415.305), (.27, 466.164), (.5, 622.254),
               (.6, 622.254), (.7, 622.254), (4.98, 622.254))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def harmonics(y, sr, center, width, guess=311.127):
    start, end = round((center - width / 2) * sr), round((center + width / 2) * sr)
    t = np.arange(end - start) / sr
    window = np.hanning(len(t))
    x = y[start:end].astype(float) * window
    def amplitude(frequency):
        return float(2 * abs(np.dot(x, np.exp(-2j * np.pi * frequency * t))) / sum(window))
    f2 = minimize_scalar(lambda f: -amplitude(f), bounds=(guess * 1.94, guess * 2.06),
                         method='bounded').x
    measured = np.array([amplitude(f2 * h / 2) for h in HARMONICS])
    normalized = 20 * np.log10(measured * HARMONICS / (measured[0] * 2))
    return {'center_seconds': center, 'width_seconds': width, 'saw_fundamental_hz': f2 / 2,
            'harmonic_amplitudes': measured.tolist(),
            'saw_slope_removed_relative_h2_db': normalized.tolist()}


def response(frequencies, fc, k, k2=1.2, sr=44100):
    r = np.tan(np.pi * np.asarray(frequencies) / sr) / np.tan(np.pi * fc / sr)
    return -10 * np.log10(((1 - r * r) ** 2 + (k * r) ** 2)
                         * ((1 - r * r) ** 2 + (k2 * r) ** 2))


def shelf_response(frequencies, sr=44100):
    # Exact response of the current voiced200Hz/+8dB LOW FREQ boost.
    a = 2 * np.pi * 200 / sr
    coefficient = a / (1 + a)
    z_inverse = np.exp(-2j * np.pi * np.asarray(frequencies) / sr)
    lowpass = coefficient / (1 - (1 - coefficient) * z_inverse)
    return 20 * np.log10(abs(1 + (10 ** (8 / 20) - 1) * lowpass))


def fit(window, family, power=None, include_shelf=False):
    frequency = np.array([2, 4, 6, 8]) * window['saw_fundamental_hz']
    target = np.array(window['saw_slope_removed_relative_h2_db'][:4])
    old_k = 2 - 2.04 * np.sqrt(44 / 127)
    variable_k = family in ('free-first-stage', 'free-both-stages')
    def parameters(x):
        fc = np.exp(x[0])
        if variable_k:
            k = np.exp(x[1])
        elif family == 'production':
            k = old_k
        else:
            k = 2 * (old_k / 2) ** power
        k2 = k if family == 'free-both-stages' else min(1.2, k) if family == 'coupled-power' else 1.2
        return fc, k, k2
    def errors(x):
        fc, k, k2 = parameters(x)
        db = response(frequency, fc, k, k2)
        if include_shelf:
            db += shelf_response(frequency)
        return (db - db[0] - target)[1:]
    results = []
    for fc in (650, 1000, 1300, 1800, 3000):
        for k in ((.15, .5, 1.2) if variable_k else (old_k,)):
            start = np.log([fc, k] if variable_k else [fc])
            lower = np.log([100, .01] if variable_k else [100])
            upper = np.log([15000, 4] if variable_k else [15000])
            results.append(least_squares(errors, start, bounds=(lower, upper)))
    best = min(results, key=lambda result: sum(result.fun ** 2))
    fc, k, k2 = parameters(best.x)
    return {'family': family, 'power': power, 'include_current_voiced_shelf': include_shelf,
            'cutoff_hz': float(fc), 'k': float(k),
            'k2': float(k2), 'Q_first_stage': float(1 / k), 'Q_second_stage': float(1 / k2),
            'shape_rmse_db': float(np.sqrt(np.mean(best.fun ** 2))),
            'residual_h4_h6_h8_db': best.fun.tolist()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='new directory')
    parser.add_argument('--renderers', type=Path, help='optional baseline/single-strong/coupled directories')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    audio = args.sources / 'TOP8_AirLead1.mp3'
    bank = args.sources / 'SH-201_Patch_LEAD.zip'
    data, member = read_bank(bank)
    name, blocks = parse_bank(data)[2]
    if name != 'Air Lead 1':
        raise ValueError('Unexpected reference patch')
    tone = blocks[1]
    if (tone[0], tone[6], tone[1], tone[7], tone[2], tone[8], tone[0x3c], tone[0x16]) != (3, 0, 0, 0, 100, 100, 63, 44):
        raise ValueError('Changed source patch')
    original_syx = out / 'original-patch.syx'
    original_syx.write_bytes(encode_syx(blocks))
    dry_blocks = list(blocks)
    common = bytearray(dry_blocks[0])
    common[0x1c] = common[0x1d] = 0
    dry_blocks[0] = bytes(common)
    dry_syx = out / 'effects-off-diagnostic.syx'
    dry_syx.write_bytes(encode_syx(dry_blocks))
    decoded = out / 'hardware.wav'
    command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-i', str(audio),
               '-ar', '44100', '-ac', '2', '-c:a', 'pcm_f32le', str(decoded)]
    subprocess.run(command, check=True)
    sr, stereo = wavfile.read(decoded)
    result = {'schema_version': 1, 'status': 'conditional diagnostic; no shipping changes',
              'reference': {'name': name, 'record': 3,
                  'page': 'https://www.rolandus.com/go/sh-201_patches/patch_lead.html',
                  'audio_url': 'https://www.rolandus.com/go/sh-201_patches/mp3/LEAD/TOP8_AirLead1.mp3',
                  'bank_url': 'https://www.rolandus.com/go/sh-201_patches/shl/SH-201_Patch_LEAD.zip',
                  'audio_sha256': sha(audio), 'bank_sha256': sha(bank), 'member': member,
                  'original_syx_sha256': sha(original_syx), 'decode_command': command},
              'script_sha256': sha(Path(__file__)),
              'engine_header_sha256': sha(ROOT / 'Source/DSP/SeptumEngine.h'),
              'codec_sha256': sha(ROOT / 'Source/DSP/SeptumSysEx.cpp'),
              'patch': {'active_part': 'upper only', 'waves': ['Triangle', 'Saw'],
                  'signed_coarse_raw': [36, 36], 'wide': [False, False],
                  'physical_coarse_current_codec': [12, 12], 'tone_octave_shift': -1,
                  'net_octave_and_coarse_semitones': [0, 0], 'filter': 'LP24', 'cutoff': 91,
                  'resonance': 44, 'keyfollow': 50, 'filter_env_depth': 0, 'filter_velocity': 0,
                  'filter_lfo_depths': [0, 0], 'overdrive': False, 'low_frequency': 'BOOST',
                  'triangle_pitch_env_depth': 3, 'lfo1_pitch_depths': [5, 7],
                  'amp_attack': 10, 'delay_on': True, 'reverb_on': True,
                  'delay_send': 35, 'reverb_send': 88, 'delay_time_raw': 47, 'reverb_predelay_raw': 10},
              'method': 'Hann-window complex projection at even harmonics2..12, fundamental inferred '
                        'from second-harmonic peak. Remove the saw1/h amplitude slope and normalize toH2. '
                        'Fits use H2/H4/H6/H8 only, TPT LP24 with one shared cutoff, no fitted EQ.',
              'limits': ['Triangle-even exclusion assumes a symmetric triangle, whose actual isolated hardware spectrum is unmeasured.',
                         'Delay/reverb are enabled; opening windows are not proven dry. Effects can produce comb coloration.',
                         'Original MIDI/controllers/system settings, exact patch revision and capture chain are unavailable.',
                         'Small differential oscillator pitch LFO and triangle pitch envelope are active.',
                         'Q depends on assumed topology; cutoff is separately fitted and not a claimed physical knob calibration.'],
              'windows': [], 'other_note_windows': [], 'renders': []}
    for channel, y in [('left', stereo[:, 0]), ('right', stereo[:, 1]), ('mid', stereo.mean(axis=1))]:
        for center in CENTERS:
            for width in WIDTHS:
                window = harmonics(y, sr, center, width)
                window['channel'] = channel
                window['fits'] = [fit(window, family, power, include_shelf) for include_shelf in (False, True)
                                 for family, power in (('production', None), ('free-first-stage', None),
                                     ('free-both-stages', None), ('coupled-power', 1.5), ('coupled-power', 1.6))]
                result['windows'].append(window)
    for center, frequency in OTHER_NOTES:
        for width in WIDTHS:
            window = harmonics(stereo.mean(axis=1), sr, center, width, frequency)
            window['channel'] = 'mid'
            window['qualification'] = 'Other-pitch/phrase check; not used to select a common resonance power. Cutoff is refitted; wet/capture conditions remain.'
            window['fits'] = [fit(window, family, power, include_shelf) for include_shelf in (False, True)
                             for family, power in (('production', None), ('free-first-stage', None),
                                 ('free-both-stages', None), ('coupled-power', 1.5), ('coupled-power', 1.6))]
            result['other_note_windows'].append(window)
    selected = next(w for w in result['windows'] if w['channel'] == 'mid'
                    and w['center_seconds'] == .075 and w['width_seconds'] == .05)
    frequencies = np.array([2, 4]) * selected['saw_fundamental_hz']
    cutoffs = np.geomspace(50, 16000, 100000)
    old_k = 2 - 2.04 * np.sqrt(44 / 127)
    def max_contrast(k):
        return float(np.max(response(frequencies[1], cutoffs, k)
                            - response(frequencies[0], cutoffs, k)))
    measured_min = min(w['saw_slope_removed_relative_h2_db'][1] for w in result['windows'])
    k_bound = brentq(lambda k: max_contrast(k) - measured_min, .01, 2)
    result['contrast_bound'] = {'production_k': float(old_k), 'production_Q': float(1 / old_k),
        'production_filter_only_maximum_h4_h2_contrast_db': max_contrast(old_k),
        'hardware_minimum_contrast_across_windows_channels_db': measured_min,
        'conditional_minimum_Q_with_fixed_second_stage': float(1 / k_bound),
        'qualification': 'Filter-only bound assumes saw1/h and no added frequency-dependent effects/capture gain; it is not a bound on the full patch.'}
    if args.renderers:
        case = {'title': 'Air Lead opening-note estimate; original MIDI unavailable', 'duration_seconds': .145,
                'notes': [{'note': 63, 'on': .05, 'off': .14, 'velocity': 100, 'note_off_velocity': 64}]}
        midi = out / 'opening-note-reconstructed.mid'
        write_midi(midi, case)
        result['reconstruction'] = {**case, 'midi_sha256': sha(midi),
            'qualification': 'Only opening note; sounding~309Hz and net coarse/octave0 support MIDI63. '
                             'Onset .05s and gate end .14s are estimates±15ms; velocity100 unknown. '
                             'Later notes, controllers and initial oscillator phase are omitted.'}
        for profile in ('baseline', 'single-strong', 'coupled'):
            binary = args.renderers / profile / 'SeptumRenderMidi'
            for patch_label, syx in [('original', original_syx), ('effects-off-diagnostic', dry_syx)]:
                wav = out / (profile + '-' + patch_label + '.wav')
                render_command = [sys.executable, str(ROOT / 'Tools/render_midi.py'), '--renderer', str(binary),
                    '--midi', str(midi), '--syx', str(syx), '--output', str(wav),
                    '--tempo-policy', 'preserve-patch', '--strict']
                subprocess.run(render_command, check=True, stdout=subprocess.DEVNULL)
                rate, rendered = wavfile.read(wav)
                windows = [harmonics(rendered.mean(axis=1), rate, center + 93 / rate, width)
                           for center in CENTERS for width in WIDTHS]
                result['renders'].append({'profile': profile, 'patch_status': patch_label,
                    'syx_sha256': sha(syx), 'renderer_sha256': sha(binary), 'wav_sha256': sha(wav),
                    'render_command': render_command, 'latency_samples': 93,
                    'peak': float(np.max(abs(rendered))), 'windows': windows})
    (out / 'analysis.json').write_text(json.dumps(result, indent=2) + '\n')
    fig, ax = plt.subplots(figsize=(10, 5.6), layout='constrained')
    observed = np.array([w['saw_slope_removed_relative_h2_db'][:4] for w in result['windows']])
    x = np.array([2, 4, 6, 8])
    ax.plot(x, selected['saw_slope_removed_relative_h2_db'][:4], 'ko-', lw=2, label='Hardware; saw slope removed')
    ax.fill_between(x, observed.min(0), observed.max(0), color='black', alpha=.12,
                    label='30–50ms windows;65–95ms centers;L/R/mid')
    for f in selected['fits']:
        if not f['include_current_voiced_shelf']:
            continue
        r = response(x * selected['saw_fundamental_hz'], f['cutoff_hz'], f['k'], f['k2'])
        r += shelf_response(x * selected['saw_fundamental_hz'])
        label = f['family'] + (f' {f["power"]}' if f['power'] else '')
        ax.plot(x, r - r[0], '.--', label=f'{label}: Q={f["Q_first_stage"]:.2f}, fc={f["cutoff_hz"]:.0f}Hz')
    ax.set(xlabel='Even harmonic number', ylabel='Saw-slope-removed amplitude / H2 (dB)',
           title='Air Lead 1: fits include current voiced LOW FREQ shelf; effects/capture remain confounders', xticks=x)
    ax.grid(alpha=.2)
    ax.legend(fontsize=8)
    fig.savefig(out / 'conditional-fits.png', dpi=160)
    print('contrast', result['contrast_bound'])
    for f in selected['fits']:
        print(f)
    for r in result['renders']:
        v=[w['saw_slope_removed_relative_h2_db'][1] for w in r['windows']]
        print(r['profile'], r['patch_status'], 'contrast range', min(v), max(v))


if __name__ == '__main__':
    main()
