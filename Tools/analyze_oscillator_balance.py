#!/usr/bin/env python3
"""Check an oscillator-only BALANCE hypothesis on frozen public comparisons.

All presets and reconstructed MIDI remain unchanged. SupaJuce's disjoint
square families provide a conditional ratio estimate; Class A's octave saws
are an independent source-family check. Broad 13-case scores are secondary.
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
from scipy.linalg import lstsq
from scipy.optimize import minimize_scalar

from analyze_supajuce_resonance import H, fit_window, response
from analyze_supajuce_brightness import DAMPING
from compare_hardware import renderer_provenance, validate_audio
from evaluate_timbre_matrix import load_run, band_shape, spectral_residual

ROOT = Path(__file__).resolve().parents[1]
SR = 44100
RUNS = ['baseline-comparison', 'class-a-comparison', 'sexy-back-baseline', 'trancefloor-baseline']
PAIRS = {'supa-juce-1': [(2, 3), (6, 5), (6, 7), (10, 9), (10, 11)],
         'class-a': [(2, 3), (4, 3), (4, 5), (6, 5), (6, 7),
                     (8, 7), (8, 9), (10, 9), (10, 11), (12, 11)]}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def measure(y, center, width, frequency):
    start, end = round((center-width/2)*SR), round((center+width/2)*SR)
    if start < 0 or end > len(y):
        raise ValueError('Measurement window outside audio')
    x = y[start:end].astype(float)
    t = np.arange(start, end)/SR-center
    count = min(64, int(.45*SR/frequency))
    columns = [np.ones(len(t)), t/width]
    for n in range(1, count+1):
        phase = 2*np.pi*n*frequency*t
        columns.extend([np.cos(phase), np.sin(phase)])
    matrix = np.column_stack(columns)
    # Pivoted QR avoids a reproducible NumPy SVD nonconvergence on one
    # finite baseline window. Rank rejection is explicit; no data are skipped.
    c, _, rank, _ = lstsq(matrix, x, lapack_driver='gelsy')
    if rank != matrix.shape[1]:
        raise ValueError('Rank-deficient harmonic measurement')
    amplitude = np.hypot(c[2::2], c[3::2])
    if amplitude[1] <= 1e-9 or not np.isfinite(amplitude).all():
        raise ValueError('Silent or nonfinite harmonic measurement')
    ratio = 20*np.log10(np.maximum(amplitude[H-1], 1e-30)/amplitude[1])
    return {'amplitude': amplitude.tolist(), 'frequency': float(frequency),
            'harmonic_ratio_db': ratio[1:].tolist(),
            'square_removed_response_db': (ratio+20*np.log10(H/2)).tolist(),
            'residual_power': float(np.mean((x-matrix@c)**2)/max(np.var(x), 1e-30))}


def family_ratios(observed, pairs):
    a = np.array(observed['amplitude'])
    return np.array([20*np.log10(a[even-1]/max(a[odd-1], 1e-30)) for even, odd in pairs])


def statistics(values):
    return {'min': float(min(values)), 'median': float(np.median(values)),
            'max': float(max(values))}


def analyze_families(key, directory, candidate_audio, metadata):
    manifests = json.loads((directory/'comparison.json').read_text())
    case = manifests['case']
    hardware_rate, hardware = wavfile.read(directory/'hardware-decoded-full.wav')
    baseline_rate, baseline = wavfile.read(directory/'septum-raw.wav')
    candidate_rate, candidate = wavfile.read(candidate_audio)
    if not hardware_rate == baseline_rate == candidate_rate == SR:
        raise ValueError('Harmonic measurement sample rate mismatch')
    signals = {'hardware': hardware, 'baseline': baseline, 'candidate': candidate}
    for signal in signals.values():
        validate_audio(signal)
    latencies = {'hardware': 0, 'baseline': metadata['retained_engine_latency_samples']/SR,
                 'candidate': metadata['retained_engine_latency_samples']/SR}
    windows = []
    if key == 'supa-juce-1':
        for index, note in enumerate(case['notes']):
            for elapsed in (.055, .070, .085):
                for width in (.025, .035, .045):
                    if elapsed+width/2 <= note['off']-note['on']-.004:
                        windows.append((index, note['on']+elapsed, width))
    else:
        # These hardware-selected stable intervals predate this experiment.
        prior = json.loads((ROOT/'Docs/fidelity/source-audits/class-a-transcription-2026-09-20.json').read_text())
        for index, row in enumerate(prior['windows']):
            if index < 2:
                continue  # insufficient lower-oscillator cycles; already weak in transcription
            first, last = row['window_seconds']
            centers = [(first+last)/2] if index < 9 else [.93, 1.02, 1.07]
            for center in centers:
                for width in (.025, .035, .045):
                    if first <= center-width/2 and center+width/2 <= last:
                        windows.append((index, center, width))
    frequencies = {}
    for label, signal in signals.items():
        for index in sorted({w[0] for w in windows}):
            note = case['notes'][index]
            selected = [w for w in windows if w[0] == index]
            _, center, width = selected[len(selected)//2]
            if key == 'supa-juce-1':
                center, width = note['on']+.0675, .04
            nominal = 440*2**((note['note']-12-69)/12)
            y = signal.mean(axis=1)
            fit = minimize_scalar(lambda f: measure(y, center+latencies[label], width, f)['residual_power'],
                                  bounds=(nominal*.985, nominal*1.015), method='bounded')
            frequencies[(label,index)] = float(fit.x)
    rows = []
    for index, center, width in windows:
        for ch, channel in enumerate(['left', 'right', 'mid']):
            row = {'note_index': index, 'center_seconds': center, 'width_seconds': width,
                   'channel': channel, 'observations': {}, 'errors': {}}
            for label, signal in signals.items():
                y = signal[:,ch] if ch < 2 else signal.mean(axis=1)
                obs = measure(y, center+latencies[label], width, frequencies[(label,index)])
                obs['family_pair_ratios_db'] = family_ratios(obs, PAIRS[key]).tolist()
                if key == 'supa-juce-1':
                    fitted = fit_window(obs, 'lp24_equal', fixed_damping=DAMPING)
                    odd = np.arange(1,12,2)
                    a = np.array(obs['amplitude'])
                    transfer = (response(odd*obs['frequency'], fitted['cutoff_hz'], DAMPING, 'lp24_equal')
                                -response(np.array([2*obs['frequency']]), fitted['cutoff_hz'], DAMPING, 'lp24_equal')[0])
                    gain = 20*np.log10(a[odd-1]*odd/a[1])-transfer
                    obs['conditional_filter_fit'] = fitted
                    obs['conditional_lower_to_upper_db_by_odd'] = gain.tolist()
                    obs['conditional_upper_to_lower_ratio'] = float(10**(-np.median(gain[1:4])/20))
                row['observations'][label] = obs
            target = np.array(row['observations']['hardware']['family_pair_ratios_db'])
            for label in ('baseline','candidate'):
                error = np.array(row['observations'][label]['family_pair_ratios_db'])-target
                row['errors'][label] = {'rmse_db': float(np.sqrt(np.mean(error**2))),
                                         'residual_db': error.tolist()}
            rows.append(row)
    summary = []
    for index in sorted({w[0] for w in windows}):
        selected = [r for r in rows if r['note_index'] == index]
        entry = {'note_index': index, 'observations': len(selected),
                 'baseline_error_db': statistics([r['errors']['baseline']['rmse_db'] for r in selected]),
                 'candidate_error_db': statistics([r['errors']['candidate']['rmse_db'] for r in selected]),
                 'improved_observations': sum(r['errors']['candidate']['rmse_db']<r['errors']['baseline']['rmse_db'] for r in selected)}
        if key == 'supa-juce-1':
            entry['conditional_upper_to_lower_ratio'] = {
                label: statistics([r['observations'][label]['conditional_upper_to_lower_ratio'] for r in selected])
                for label in signals}
        summary.append(entry)
    return {'id':key, 'harmonic_pairs':PAIRS[key], 'summary_by_note':summary, 'windows':rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--baseline-root', type=Path,
                        default=ROOT/'build-fidelity/public-match-2026-09-20')
    parser.add_argument('--output', type=Path, required=True, help='new directory')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    provenance = renderer_provenance(args.candidate)
    build = json.loads((args.candidate.parent/'manifest.json').read_text())
    original = json.loads((args.baseline_root/'baseline/manifest.json').read_text())
    if build['source']['experimental_modification']['original_source_sha256'] != original['source']['input_sha256']:
        raise ValueError('Candidate was not built from the frozen baseline source')
    cases = {}
    for run in RUNS:
        directory = args.baseline_root/run
        for key,row in load_run(directory).items():
            if key in cases:
                raise ValueError('Duplicate comparison case')
            cases[key] = (directory/key,row)
    report = {'schema_version':1, 'status':'experimental; no shipping change',
              'script_sha256':sha(__file__), 'renderer':provenance,
              'design': 'SupaJuce disjoint square families motivate balance dominance; Class A octave saws independently validate. All other noncentered oscillator balances are cross-preset tests. Six centered oscillator mixes are identity controls; no endpoint-only fixture is asserted.',
              'limits': ['Original performance MIDI, controller state, phase history and recording processing remain unknown.',
                         'Supa cutoff fits use upper-square harmonics only; lower harmonics estimate gain. The result is conditional on the current filter family and ideal square spectrum.',
                         'Class A and Supa have published effects. Neighboring harmonic ratios reduce smooth filter/recording coloration but do not remove comb notches.',
                         'Overlapping channels/windows are sensitivity checks, not independent recordings. Broad bands are not an overall fidelity score.'],
              'cases':[], 'families':{}}
    for key,(directory,row) in cases.items():
        wav = out/(key+'.wav')
        midi_sha256 = sha(directory/'reconstructed-performance.mid')
        patch_sha256 = sha(directory/'original-patch.syx')
        command = [sys.executable,str(ROOT/'Tools/render_midi.py'),'--renderer',str(args.candidate.resolve()),
                   '--syx',str(directory/'original-patch.syx'),'--midi',str(directory/'reconstructed-performance.mid'),
                   '--output',str(wav),'--sample-rate','44100','--tail','2','--master-level','100',
                   '--tempo-policy','preserve-patch','--strict']
        subprocess.run(command,check=True,stdout=subprocess.DEVNULL)
        metadata = json.loads(wav.with_suffix('.render.json').read_text())
        if (metadata['inputs']['renderer']['sha256'] != provenance['sha256']
                or renderer_provenance(args.candidate) != provenance
                or metadata['inputs']['midi']['sha256'] != midi_sha256
                or metadata['inputs']['sysex']['sha256'] != patch_sha256
                or sha(directory/'reconstructed-performance.mid') != midi_sha256
                or sha(directory/'original-patch.syx') != patch_sha256
                or metadata['output']['sha256'] != sha(wav)):
            raise ValueError('Renderer, input or output identity changed during render')
        if metadata['degraded_replay'] or metadata['output']['latency_samples'] != row['retained_engine_latency_samples']:
            raise ValueError('Render replay or latency mismatch')
        sr,hardware = wavfile.read(directory/'hardware-excerpt-raw.wav')
        rate,baseline = wavfile.read(directory/'septum-raw.wav')
        candidate_rate,candidate = wavfile.read(wav)
        if not sr == rate == candidate_rate == SR:
            raise ValueError('Comparison sample rate mismatch')
        for signal in (hardware, baseline, candidate):
            validate_audio(signal)
        shape = band_shape(hardware,sr)
        n = row['comparison_frames']
        if len(candidate) < n or len(baseline) < n or len(hardware) != n:
            raise ValueError('Comparison audio length mismatch')
        before = spectral_residual(shape,band_shape(baseline[:n],sr))
        after = spectral_residual(shape,band_shape(candidate[:n],sr))
        report['cases'].append({'id':key, 'before':before, 'candidate':after,
            'delta_rmse_db':after['band_shape_rmse_db']-before['band_shape_rmse_db'],
            'identical_raw':sha(wav)==row['files']['septum-raw.wav'],
            'candidate_audio_sha256':sha(wav), 'baseline_audio_sha256':row['files']['septum-raw.wav'],
            'original_comparison_sha256':sha(directory/'comparison.json'),
            'midi_sha256':midi_sha256,
            'patch_sha256':patch_sha256, 'render_command':command})
        print(key, round(before['band_shape_rmse_db'],3), '->', round(after['band_shape_rmse_db'],3),flush=True)
    (out/'broad-results.json').write_text(json.dumps(report,indent=2)+'\n')
    for key in PAIRS:
        directory,row = cases[key]
        report['families'][key] = analyze_families(key,directory,out/(key+'.wav'),row)
        print(key, report['families'][key]['summary_by_note'],flush=True)
    if renderer_provenance(args.candidate) != provenance:
        raise ValueError('Renderer or frozen candidate build changed during analysis')
    (out/'analysis.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__ == '__main__':
    main()
