#!/usr/bin/env python3
"""Apply the predeclared hardware spectral-closure metric to frozen renders.

No gain fitting, EQ, onset fitting, time warp, or DSP changes. Missing crossings
remain censored; a threshold elapsed time is not a filter attack duration.
"""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal
from scipy.io import wavfile

import analyze_rcs_a02_closure as hardware_metric


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pin(path):
    return {'path': str(Path(path).resolve()), 'sha256': sha(path)}


def load(path):
    return json.loads(Path(path).read_text())


def checked_audio(path):
    sr, audio = wavfile.read(path)
    if (sr != 44100 or audio.ndim != 2 or audio.shape[1] != 2
            or audio.dtype.kind != 'f' or not np.isfinite(audio).all()
            or not np.any(audio)):
        raise ValueError(f'Expected finite nonzero float stereo 44.1kHz: {path}')
    return sr, audio


def measure(audio, sr, time_origin, case):
    """Same operations/constants as the pinned original hardware analysis."""
    channels = {'left': audio[:, 0], 'right': audio[:, 1],
                'mid': audio.mean(axis=1)}
    rows, traces = [], []
    for window in (512, 1024, 2048):
        for channel, y in channels.items():
            f, t, z = signal.stft(y, sr, window='hann', nperseg=window,
                                 noverlap=window-44, boundary=None)
            t = t + time_origin
            lo = np.sum(abs(z[(f > 300) & (f < 1500)])**2, axis=0)
            hi = np.sum(abs(z[(f > 1500) & (f < 12000)])**2, axis=0)
            ratio = signal.medfilt(10*np.log10(
                np.maximum(hi, 1e-20)/np.maximum(lo, 1e-20)), 5)
            if not np.isfinite(ratio).all():
                raise ValueError('Non-finite ratio trace')
            for index, note in enumerate(case['notes']):
                onset = case['source_start_seconds'] + note['on']
                release = case['source_start_seconds'] + note['off']
                last = release - .030
                for shift in (-.010, 0, .010):
                    assumed_onset = onset + shift
                    early = (t >= assumed_onset+.015) & (t <= assumed_onset+.035)
                    if not np.any(early):
                        raise ValueError('No frames in predeclared early reference')
                    reference = float(np.median(ratio[early]))
                    landmarks = {}
                    for drop in (10, 20, 30):
                        crossing = hardware_metric.first_sustained_crossing(
                            t, ratio, reference-drop, assumed_onset+.035, last)
                        landmarks[str(drop)] = (None if crossing is None else {
                            'absolute_seconds': crossing,
                            'elapsed_seconds': crossing-assumed_onset})
                    rows.append({'note_index': index, 'window_samples': window,
                                 'channel': channel, 'onset_shift_seconds': shift,
                                 'early_ratio_db': reference,
                                 'last_allowed_time_seconds': last,
                                 'ratio_drop_landmarks_db': landmarks})
                if window == 1024 and channel == 'mid':
                    keep = (t >= onset) & (t <= release)
                    reference = float(np.median(ratio[(t >= onset+.015)
                                                      & (t <= onset+.035)]))
                    traces.append({'note_index': index,
                                   'elapsed_seconds': (t[keep]-onset).tolist(),
                                   'ratio_db': ratio[keep].tolist(),
                                   'low_band_power': lo[keep].tolist(),
                                   'high_band_power': hi[keep].tolist(),
                                   'early_ratio_db': reference})
    return rows, traces


def key(row):
    return tuple(row[k] for k in ('note_index', 'window_samples', 'channel',
                                 'onset_shift_seconds'))


def trace_diagnostics(traces, case):
    """Explain censoring in the fixed central trace; never rank by these values."""
    result = []
    for trace, note in zip(traces, case['notes'], strict=True):
        times = np.array(trace['elapsed_seconds'])
        ratio = np.array(trace['ratio_db'])
        high = np.array(trace['high_band_power'])
        low = np.array(trace['low_band_power'])
        keep = (times >= .035) & (times <= note['off']-note['on']-.030)
        relative = ratio[keep]-trace['early_ratio_db']
        below = relative <= -10
        padded = np.r_[False, below, False]
        starts = np.flatnonzero(padded[1:] & ~padded[:-1])
        ends = np.flatnonzero(~padded[1:] & padded[:-1])
        longest = (0 if not len(starts) else int(max(ends-starts)))
        result.append({'note_index': trace['note_index'],
                       'window_samples': 1024, 'channel': 'mid', 'onset_shift_seconds': 0,
                       'early_ratio_db': trace['early_ratio_db'],
                       'minimum_relative_ratio_change_db': float(min(relative)),
                       'maximum_relative_ratio_change_db': float(max(relative)),
                       'high_band_min_power': float(min(high[keep])),
                       'low_band_min_power': float(min(low[keep])),
                       'high_band_floor_count': int(sum(high[keep] <= 1e-20)),
                       'low_band_floor_count': int(sum(low[keep] <= 1e-20)),
                       'longest_contiguous_below_10db_frame_count': longest,
                       'longest_contiguous_below_10db_grid_coverage_seconds': longest*44/44100,
                       'interpretation': 'Descriptive trace check only; no fallback winner selection. Frame-count coverage is not an interpolated crossing or attack duration.'})
    return result


def summarize(rows, hardware):
    hw = {key(row): row for row in hardware}
    result = []
    for index in sorted({r['note_index'] for r in rows}):
        selected = [r for r in rows if r['note_index'] == index]
        summary = {'note_index': index, 'observations': len(selected), 'landmarks': {}}
        for drop in ('10', '20', '30'):
            observed, errors, pairs = [], [], []
            for row in selected:
                soft = row['ratio_drop_landmarks_db'][drop]
                real = hw[key(row)]['ratio_drop_landmarks_db'][drop]
                if soft is not None:
                    observed.append(soft['elapsed_seconds'])
                if soft is not None and real is not None:
                    errors.append(soft['elapsed_seconds']-real['elapsed_seconds'])
                pairs.append((soft is not None, real is not None))
            summary['landmarks'][drop] = {
                'observed_count': len(observed), 'censored_count': len(selected)-len(observed),
                'elapsed_seconds_min_median_max': (None if not observed else
                    [float(min(observed)), float(np.median(observed)), float(max(observed))]),
                'both_observed_count': sum(s and h for s, h in pairs),
                'hardware_only_observed_count': sum(not s and h for s, h in pairs),
                'software_only_observed_count': sum(s and not h for s, h in pairs),
                'both_censored_count': sum(not s and not h for s, h in pairs),
                'paired_mean_absolute_error_seconds': (None if not errors else
                                                       float(np.mean(np.abs(errors)))),
                'paired_signed_error_seconds_min_median_max': (None if not errors else
                    [float(min(errors)), float(np.median(errors)), float(max(errors))])}
        result.append(summary)
    return result


def verify_render(path, case, baseline_metadata=None, baseline_sources=None):
    meta_path = path.with_suffix('.render.json')
    meta = load(meta_path)
    comparison_path = path.parent/'comparison.json'
    comparison = load(comparison_path)
    if comparison['case'] != case:
        raise ValueError('Rendered case differs from fixed hardware reconstruction')
    if sha(path) != meta['output']['sha256']:
        raise ValueError('Rendered audio hash mismatch')
    for item in meta['inputs'].values():
        if sha(item['path']) != item['sha256']:
            raise ValueError(f'Render input hash mismatch: {item["path"]}')
    provenance = comparison['renderer_provenance']
    manifest_path = Path(provenance['build_manifest_path'])
    if sha(manifest_path) != provenance['build_manifest_sha256']:
        raise ValueError('Build manifest hash mismatch')
    manifest = load(manifest_path)
    for relative, expected in manifest['frozen_sha256'].items():
        if sha(manifest_path.parent/relative) != expected:
            raise ValueError(f'Frozen source hash mismatch: {relative}')
    renderer = meta['inputs']['renderer']
    if renderer['sha256'] != manifest['renderer']['sha256']:
        raise ValueError('Renderer differs from frozen build')
    if baseline_sources is not None and manifest['source']['input_sha256'] != baseline_sources:
        raise ValueError('Probe original source map differs from baseline')
    if baseline_metadata is not None:
        for field in ('settings', 'midi', 'replay_events', 'replay_event_counts'):
            if meta[field] != baseline_metadata[field]:
                raise ValueError(f'Probe replay changed {field}')
        for field in ('midi', 'sysex'):
            if meta['inputs'][field]['sha256'] != baseline_metadata['inputs'][field]['sha256']:
                raise ValueError(f'Probe changed {field} bytes')
    sr, audio = checked_audio(path)
    output = meta['output']
    peak = float(np.max(abs(audio)))
    if (output['frames'] != len(audio) or output['sample_rate'] != sr
            or output['latency_samples'] != 93 or output['latency_compensated']
            or output['normalised'] or output['active_voices_at_end'] != 0
            or meta['degraded_replay'] or abs(output['peak']-peak) > 1e-8
            or comparison['retained_engine_latency_samples'] != 93):
        raise ValueError('Render timing, integrity or replay status differs from expected')
    verified = {'audio': pin(path), 'render_manifest': pin(meta_path),
                'comparison_manifest': pin(comparison_path),
                'build_manifest': pin(manifest_path), 'renderer': renderer,
                'midi': meta['inputs']['midi'], 'sysex': meta['inputs']['sysex'],
                'original_source_sha256': manifest['source']['input_sha256'],
                'frozen_source_sha256': manifest['frozen_sha256'],
                'profile': manifest['profile'], 'all_frozen_sources_verified': True,
                'integrity': {'sample_rate': sr, 'frames': len(audio), 'finite': True,
                              'nonzero': True, 'peak': peak,
                              'samples_at_or_above_full_scale': int(np.sum(abs(audio) >= 1)),
                              'active_voices_at_end': 0, 'degraded_replay': False},
                'latency_samples': 93, 'latency_seconds': 93/sr}
    return sr, audio, meta, manifest['source']['input_sha256'], verified


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hardware-analysis', type=Path, required=True)
    parser.add_argument('--hardware-audio', type=Path, required=True)
    parser.add_argument('--case', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--probe', action='append', default=[], metavar='LABEL=WAV')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    hardware = load(args.hardware_analysis)
    case = load(args.case)
    if (sha(args.hardware_audio) != hardware['inputs']['audio_sha256']
            or sha(args.case) != hardware['inputs']['case_sha256']
            or sha(hardware_metric.__file__) != hardware['inputs']['script_sha256']):
        raise ValueError('Predeclared hardware metric or inputs changed')
    sr, audio = checked_audio(args.hardware_audio)
    if audio.shape != (7*sr, 2):
        raise ValueError('Hardware must be original 19–26-second crop')
    rows, traces = measure(audio, sr, 19, case)
    if rows != hardware['observations']:
        raise ValueError('Hardware remeasurement does not exactly reproduce existing metric')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    results = {}
    baseline_metadata = baseline_sources = None
    inputs = [('baseline', args.baseline)]
    for value in args.probe:
        label, path = value.split('=', 1)
        if not label or label in [name for name, _ in inputs]:
            raise ValueError('Probe labels must be nonempty and unique')
        inputs.append((label, Path(path)))
    for label, path in inputs:
        sr, audio, meta, source_map, provenance = verify_render(
            path, case, baseline_metadata, baseline_sources)
        if baseline_metadata is None:
            baseline_metadata, baseline_sources = meta, source_map
        measured, software_traces = measure(
            audio, sr, case['source_start_seconds']-93/sr, case)
        results[label] = {'provenance': provenance,
                          'summary_by_note': summarize(measured, rows),
                          'central_trace_diagnostics': trace_diagnostics(software_traces, case),
                          'observations': measured, 'mid_traces': software_traces}
    first_note = {name: item['summary_by_note'][0] for name, item in results.items()}
    complete = []
    for name, row in first_note.items():
        lm = row['landmarks']
        if all(lm[d]['both_observed_count'] == row['observations'] for d in lm):
            complete.append((float(np.mean([lm[d]['paired_mean_absolute_error_seconds']
                                           for d in lm])), name))
    ranking = [{'label': name, 'first_note_paired_mae_seconds': error}
               for error, name in sorted(complete)]
    report = {'schema_version': 1,
              'status': 'conditional spectral-closure comparison; not a calibrated attack law',
              'inputs': {'hardware_analysis': pin(args.hardware_analysis),
                         'hardware_audio': pin(args.hardware_audio), 'case': pin(args.case),
                         'hardware_metric_script': pin(hardware_metric.__file__),
                         'comparison_script': pin(__file__)},
              'method': {**hardware['method'],
                         'hardware_time_origin_seconds': 19,
                         'software_time_mapping': 'source_start + STFT time − 93/44100 seconds',
                         'latency_compensation': 'Subtract known retained renderer latency from time coordinates only; no signal shift, EQ, gain or timing fit.',
                         'frame_grid': 'Each original PCM uses its own fixed44-sample hop; no interpolation to fit crossings.',
                         'selection': 'Rank first-note probes only when every paired landmark is observed; censored timing remains unknown.'},
              'hardware_metric_reproduced_exactly': True,
              'hardware_summary_by_note': hardware['summary_by_note'],
              'hardware_central_trace_diagnostics': trace_diagnostics(traces, case),
              'hardware_mid_traces': traces, 'renders': results,
              'first_note_complete_landmark_ranking': ranking,
              'first_note_winner': (ranking[0]['label'] if ranking else None),
              'interpretation': ('No probe has every first-note landmark observed; missing crossings are censored, not zero, so no complete-landmark timing winner is identified.' if not ranking else
                                 'Best timing among the evaluated complete-landmark probes is conditional on this one reconstruction and metric.'),
              'limitations': case['uncertainties'] + [
                  'The other four notes are sensitivity observations from the same performance, not independent recordings.',
                  'Channels, windows and onset shifts are correlated analysis settings, not independent experimental trials.',
                  'Spectral-ratio closure reflects filter, drive and layer balance jointly. Crossing elapsed time is not filter attack duration.',
                  'The ratio metric cancels constant gain; raw unnormalised WAVs were used with no EQ or parameter fitting.']}
    (out/'analysis.json').write_text(json.dumps(report, indent=2)+'\n')
    fig, axes = plt.subplots(len(case['notes']), 1, figsize=(11, 13), sharex=False)
    for index, axis in enumerate(axes):
        for label, series in [('hardware', traces)] + [(k, v['mid_traces']) for k, v in results.items()]:
            trace = series[index]
            axis.plot(np.array(trace['elapsed_seconds'])*1000,
                      np.array(trace['ratio_db'])-trace['early_ratio_db'], label=label,
                      linewidth=2 if label == 'hardware' else 1)
        note = case['notes'][index]
        axis.axvspan(15, 35, color='grey', alpha=.12)
        axis.axvline((note['off']-note['on']-.030)*1000, color='black', linestyle=':')
        for level in (-10, -20, -30):
            axis.axhline(level, color='grey', alpha=.3)
        axis.set(title=f'Note{index+1}:1024-sample mid channel, zero onset shift',
                 xlabel='Elapsed from reconstructed onset (ms)', ylabel='Ratio change (dB)',
                 xlim=(0, (note['off']-note['on'])*1000))
        axis.grid(alpha=.2)
    axes[0].legend(ncol=3)
    fig.tight_layout()
    fig.savefig(out/'closure-traces.png', dpi=140)
    print(json.dumps({'output': str(out), 'first_note': first_note,
                      'complete_landmark_ranking': ranking}, indent=2))


if __name__ == '__main__':
    main()
