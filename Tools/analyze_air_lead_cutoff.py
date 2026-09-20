#!/usr/bin/env python3
"""Conditional static-cutoff experiment from the public Air Lead 1 recording.

Fit only one opening window, freeze that cutoff across pitches, and retain
unfitted harmonics, channels, windows and full-engine errors. This is not a
measured global Roland cutoff table. It never changes production DSP.
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
from scipy.interpolate import PchipInterpolator
from scipy.io import wavfile
from scipy.optimize import minimize_scalar

from analyze_air_lead_resonance import harmonics, response, shelf_response
from build_timbre_candidate import validate_profile
from compare_hardware import audio_stats, write_midi
from extract_reference_patch import read_bank, parse_bank, encode_syx

ROOT = Path(__file__).resolve().parents[1]
H = np.arange(2, 13, 2)
K = 2 * ((2 - 2.04 * np.sqrt(44 / 127)) / 2) ** 1.5
CENTERS = (.065, .075, .085, .095, .175, .27, .5, .6, .7,
           1.245, 1.37, 1.55, 1.85, 2.2, 2.75, 3.2)
WIDTHS = (.03, .04, .05)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def default_cutoff(raw):
    return 20 * 2 ** (np.asarray(raw) * (10 / 127))


def prediction(window, base_cutoff, note):
    fc = base_cutoff * 2 ** (.5 * (note - 60) / 12)
    f = H * window['saw_fundamental_hz']
    db = response(f, fc, K, max(.5, min(K, 1.2))) + shelf_response(f)
    return db - db[0]


def fit_cutoff(window, note):
    target = np.array(window['saw_slope_removed_relative_h2_db'])
    def objective(x):
        return np.sum((prediction(window, np.exp(x), note)[1:4] - target[1:4]) ** 2)
    result = minimize_scalar(objective, bounds=np.log([200, 6000]), method='bounded')
    # Resonant response can give multiple minima. Check every coarse-grid
    # minimum rather than reporting a failed one-dimensional boundary fit.
    grid = np.linspace(np.log(200), np.log(6000), 65)
    values = [objective(x) for x in grid]
    for i in range(1, len(grid) - 1):
        if values[i] <= values[i - 1] and values[i] <= values[i + 1]:
            local = minimize_scalar(objective, bounds=(grid[i - 1], grid[i + 1]), method='bounded')
            if local.fun < result.fun - 1e-8:
                result = local
    return float(np.exp(result.x))


def metrics(error):
    return {'h4_h6_h8_rmse_db': float(np.sqrt(np.mean(error[1:4] ** 2))),
            'withheld_h10_h12_rmse_db': float(np.sqrt(np.mean(error[4:] ** 2))),
            'h4_to_h12_rmse_db': float(np.sqrt(np.mean(error[1:] ** 2))),
            'h4_to_h12_residual_db': error[1:].tolist()}


def measure(audio, sr, center, width, guess=311.127):
    window = harmonics(audio, sr, center, width, guess)
    if (not np.isfinite(window['saw_slope_removed_relative_h2_db']).all()
            or window['harmonic_amplitudes'][0] <= 1e-9):
        raise ValueError('Nonfinite or silent harmonic measurement')
    return window


def make_profile(base):
    table = default_cutoff(np.arange(128))
    # Preserving low controls and the maximum is an experimental design
    # choice. Only raw91 is inferred here. No unmeasured point is a claim
    # about hardware; PCHIP is just a monotone interpolation hypothesis.
    curve = PchipInterpolator([64, 91, 127],
                              np.log2([table[64], base, table[127]]))
    table[65:] = np.exp2(curve(np.arange(65, 128)))
    profile = {'version': 1, 'id': 'experimental-air-lead-cutoff',
               'evidence': 'Experimental single-preset conditional cutoff anchor: '
               'Air Lead 1 raw91, opening mid 75ms/50ms H4/H6/H8 fit with current '
               'resonance and voiced LOW FREQ shelf; original MIDI/capture unknown. '
               'Raw0..64 and127 retain incumbent values by design, not hardware '
               'measurement. Log-frequency PCHIP64/91/127 is an unverified '
               'interpolation. No shipping-model recommendation.',
               'filter': {'cutoff_hz': table.tolist()}}
    validate_profile(profile)
    return profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', type=Path,
                        default=ROOT / 'build-fidelity/hardware-benchmark/sources')
    parser.add_argument('--output', type=Path, required=True, help='new directory')
    parser.add_argument('--profile-output', type=Path, help='write a new candidate profile')
    parser.add_argument('--baseline', type=Path, help='frozen baseline renderer')
    parser.add_argument('--candidate', type=Path, help='frozen candidate renderer')
    args = parser.parse_args()
    if bool(args.baseline) != bool(args.candidate):
        parser.error('--baseline and --candidate must be supplied together')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    audit = json.loads((ROOT / 'Docs/fidelity/source-audits/air-lead-resonance.json').read_text())
    audio = args.sources / 'TOP8_AirLead1.mp3'
    bank = args.sources / 'SH-201_Patch_LEAD.zip'
    if sha(audio) != audit['reference']['audio_sha256'] or sha(bank) != audit['reference']['bank_sha256']:
        raise ValueError('Reference source identity differs from audited original')
    name, blocks = parse_bank(read_bank(bank)[0])[2]
    syx = encode_syx(blocks)
    if name != 'Air Lead 1' or hashlib.sha256(syx).hexdigest() != audit['reference']['original_syx_sha256']:
        raise ValueError('Original patch identity changed')
    patch_path = out / 'original-patch.syx'
    patch_path.write_bytes(syx)
    case_path = ROOT / 'Docs/fidelity/reconstructions/expanded/air-lead-1.json'
    case = json.loads(case_path.read_text())
    midi = out / 'reconstructed-performance.mid'
    write_midi(midi, case)
    hardware_path = out / 'hardware-decoded-full.wav'
    decode = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-i', str(audio),
              '-ar', '44100', '-ac', '2', '-c:a', 'pcm_f32le', str(hardware_path)]
    subprocess.run(decode, check=True)
    sr, hardware = wavfile.read(hardware_path)
    if not np.isfinite(hardware).all() or np.max(np.abs(hardware)) <= 1e-9:
        raise ValueError('Nonfinite or silent hardware audio')
    channels = {'left': hardware[:, 0], 'right': hardware[:, 1], 'mid': hardware.mean(axis=1)}
    training = measure(channels['mid'], sr, .075, .05)
    anchor = fit_cutoff(training, 63)
    profile = make_profile(anchor)
    local_profile = out / 'experimental-air-lead-cutoff.json'
    local_profile.write_text(json.dumps(profile, indent=2) + '\n')
    if args.profile_output:
        with args.profile_output.open('x') as dest:
            dest.write(local_profile.read_text())
    result = {
        'schema_version': 1, 'status': 'experimental; no production DSP change',
        'reference': audit['reference'],
        'inputs': {'script_sha256': sha(__file__), 'patch_sha256': sha(patch_path),
                   'midi_sha256': sha(midi), 'reconstruction_sha256': sha(case_path),
                   'profile_sha256': sha(local_profile),
                   'reconstruction': str(case_path), 'decode_command': decode},
        'training': {'window': training, 'channel': 'mid', 'nominal_midi': 63,
                     'fit_harmonics': [4, 6, 8], 'withheld_harmonics': [10, 12],
                     'base_cutoff_raw91_hz': anchor,
                     'incumbent_raw91_hz': float(default_cutoff(91)),
                     'change_octaves': float(np.log2(anchor / default_cutoff(91))),
                     'fixed_stage_damping': float(K)},
        'limits': [
            'Only raw91 has a recording-derived conditional anchor. The rest of the table is a design hypothesis.',
            'Original performance MIDI, velocities/controllers/system state and recording chain are unavailable.',
            'Triangle contributes no even harmonics in the assumed source model; isolated hardware triangle is unmeasured.',
            'Current resonance topology, LOW FREQ shelf and output chain remain assumptions.',
            'Overlapping windows and stereo channels are sensitivity checks, not independent hardware recordings.',
            'Preserving low controls does not validate a global curve; independent presets above raw64 are required.',
            'Full-engine render uses unchanged published effects and estimated gates; no post-render EQ or time warping.',
        ], 'windows': [], 'renders': {},
    }
    render_audio = {}
    frozen_sources = None
    for label, renderer in [('baseline', args.baseline), ('candidate', args.candidate)]:
        if renderer is None:
            continue
        build_path = renderer.parent / 'manifest.json'
        build = json.loads(build_path.read_text())
        saved_profile = json.loads((renderer.parent / 'profile.json').read_text())
        if build['renderer']['sha256'] != sha(renderer):
            raise ValueError('Renderer does not match its frozen build manifest')
        if label == 'baseline':
            if build['profile']['enabled_sections'] or build['profile']['reference_rate_hz'] is not None:
                raise ValueError('Baseline must have all experimental sections disabled')
            frozen_sources = build['source']['input_sha256']
        elif (saved_profile != profile or build['source']['input_sha256'] != frozen_sources):
            raise ValueError('Candidate profile or original source snapshot differs from experiment')
        wav = out / f'{label}-raw.wav'
        command = [sys.executable, str(ROOT / 'Tools/render_midi.py'), '--renderer', str(renderer.resolve()),
                   '--midi', str(midi), '--syx', str(patch_path), '--output', str(wav),
                   '--sample-rate', str(sr), '--tail', '2', '--master-level', '100',
                   '--tempo-policy', 'preserve-patch', '--strict']
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
        rate, y = wavfile.read(wav)
        if rate != sr or not np.isfinite(y).all() or np.max(np.abs(y)) <= 1e-9:
            raise ValueError('Invalid rendered audio')
        manifest = json.loads(wav.with_suffix('.render.json').read_text())
        latency = manifest['output']['latency_samples'] / sr
        render_audio[label] = (y, latency)
        result['renders'][label] = {'renderer_sha256': sha(renderer), 'audio_sha256': sha(wav),
                                    'build_manifest_sha256': sha(build_path),
                                    'original_source_sha256': build['source']['input_sha256'],
                                    'command': command, 'latency_seconds': latency,
                                    'stats': audio_stats(y, sr)}
    for center in CENTERS:
        note = next(n['note'] for n in case['notes'] if n['on'] <= center < n['off'])
        guess = 440 * 2 ** ((note - 69) / 12)
        for width in WIDTHS:
            for channel, audio_channel in channels.items():
                window = measure(audio_channel, sr, center, width, guess)
                target = np.array(window['saw_slope_removed_relative_h2_db'])
                window.update(channel=channel, nominal_midi=note,
                              training_window=center == .075 and width == .05 and channel == 'mid',
                              separately_fitted_cutoff_raw91_hz=fit_cutoff(window, note),
                              analytic={}, rendered={})
                for label, base in [('baseline', default_cutoff(91)), ('candidate', anchor)]:
                    window['analytic'][label] = metrics(prediction(window, base, note) - target)
                for label, (y, latency) in render_audio.items():
                    sample = y[:, 0] if channel == 'left' else y[:, 1] if channel == 'right' else y.mean(axis=1)
                    observed = measure(sample, sr, center + latency, width, guess)
                    error = np.array(observed['saw_slope_removed_relative_h2_db']) - target
                    window['rendered'][label] = {'window': observed, **metrics(error)}
                result['windows'].append(window)
    for method in ('analytic', 'rendered'):
        if method == 'rendered' and not render_audio:
            continue
        result[f'{method}_summary'] = {}
        for group, select in [('opening_note', lambda w: w['center_seconds'] < .14),
                              ('heldout_notes', lambda w: w['center_seconds'] >= .14),
                              ('all', lambda w: True)]:
            selected = [w for w in result['windows'] if select(w) and not w['training_window']]
            summary = {'window_count': len(selected)}
            for metric in ('h4_to_h12_rmse_db', 'withheld_h10_h12_rmse_db'):
                for label in ('baseline', 'candidate'):
                    values = [w[method][label][metric] for w in selected]
                    summary[f'{label}_{metric}'] = {'median': float(np.median(values)),
                                                    'min': float(min(values)), 'max': float(max(values))}
                summary[f'improved_windows_{metric}'] = sum(
                    w[method]['candidate'][metric] < w[method]['baseline'][metric] for w in selected)
            result[f'{method}_summary'][group] = summary
    (out / 'analysis.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'anchor_hz': anchor, 'profile': str(local_profile),
                      'analysis': str(out / 'analysis.json'),
                      'analytic': result['analytic_summary'],
                      'rendered': result.get('rendered_summary')}, indent=2))


if __name__ == '__main__':
    main()
