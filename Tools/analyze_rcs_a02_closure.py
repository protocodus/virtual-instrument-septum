#!/usr/bin/env python3
"""Measure hardware-only RCS A02 spectral-closure landmarks, not a filter law.

The fixed reconstruction supplies independently selected attack estimates.
No renderer, synthesized spectra, cutoff fit or parameter search is used.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.io import wavfile

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / 'Docs/fidelity/reconstructions/expanded/rcs-a02-moogbass-pw.json'
AUDIT = ROOT / 'Docs/fidelity/source-audits/rcs-a02-hardware-observations-2026-09-20.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def first_sustained_crossing(t, ratio, level, first, last):
    """Require at least 10 ms below threshold, before the gate guard."""
    for i in np.flatnonzero((t >= first) & (t <= last - .010)):
        after = np.searchsorted(t, t[i] + .010)
        if after > i and np.all(ratio[i:after] <= level):
            return float(t[i])
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio', type=Path, required=True,
                        help='verified 19–26s YouTube float-stereo crop')
    parser.add_argument('--output', type=Path, required=True, help='new directory')
    args = parser.parse_args()
    evidence = json.loads(AUDIT.read_text())
    if sha(args.audio) != evidence['sources']['youtube_crop_float_wav']['sha256']:
        raise ValueError('Audio differs from hardware-observation crop')
    sr, audio = wavfile.read(args.audio)
    if (sr != 44100 or audio.shape != (7 * sr, 2)
            or audio.dtype.kind != 'f' or not np.isfinite(audio).all()
            or not np.any(audio)):
        raise ValueError('Expected finite nonzero 44.1kHz stereo crop')
    case = json.loads(CASE.read_text())
    if sha(CASE) != evidence['sources']['selected_reconstruction']['sha256']:
        raise ValueError('Reconstruction differs from hardware selection')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    channels = {'left': audio[:, 0], 'right': audio[:, 1],
                'mid': audio.mean(axis=1)}
    rows, traces = [], []
    for window in (512, 1024, 2048):
        for channel, y in channels.items():
            f, t, z = signal.stft(y, sr, window='hann', nperseg=window,
                                 noverlap=window-44, boundary=None)
            t = t + 19
            lo = np.sum(abs(z[(f > 300) & (f < 1500)])**2, axis=0)
            hi = np.sum(abs(z[(f > 1500) & (f < 12000)])**2, axis=0)
            ratio = 10*np.log10(np.maximum(hi, 1e-20)/np.maximum(lo, 1e-20))
            # A 5 ms median suppresses single-frame pulse-phase variation.
            ratio = signal.medfilt(ratio, 5)
            for index, note in enumerate(case['notes']):
                onset = case['source_start_seconds'] + note['on']
                release = case['source_start_seconds'] + note['off']
                # Avoid attributing adjacent-note/gate transients to closure.
                last = release - .030
                for onset_shift in (-.010, 0, .010):
                    assumed_onset = onset + onset_shift
                    early = (t >= assumed_onset+.015) & (t <= assumed_onset+.035)
                    reference = float(np.median(ratio[early]))
                    landmarks = {}
                    for drop in (10, 20, 30):
                        crossing = first_sustained_crossing(
                            t, ratio, reference-drop, assumed_onset+.035, last)
                        landmarks[str(drop)] = (None if crossing is None else {
                            'absolute_seconds': crossing,
                            'elapsed_seconds': crossing-assumed_onset})
                    rows.append({'note_index': index, 'window_samples': window,
                                 'channel': channel, 'onset_shift_seconds': onset_shift,
                                 'early_ratio_db': reference,
                                 'last_allowed_time_seconds': last,
                                 'ratio_drop_landmarks_db': landmarks})
                if window == 1024 and channel == 'mid':
                    keep = (t >= onset) & (t <= release)
                    traces.append({'note_index': index,
                                   'elapsed_seconds': (t[keep]-onset).tolist(),
                                   'ratio_db': ratio[keep].tolist()})
    summaries = []
    for index in range(len(case['notes'])):
        selected = [r for r in rows if r['note_index'] == index]
        summary = {'note_index': index, 'observations': len(selected), 'landmarks': {}}
        for drop in (10, 20, 30):
            found = [r['ratio_drop_landmarks_db'][str(drop)]['elapsed_seconds']
                     for r in selected if r['ratio_drop_landmarks_db'][str(drop)] is not None]
            summary['landmarks'][str(drop)] = {
                'observed_count': len(found), 'censored_count': len(selected)-len(found),
                'elapsed_seconds_min_median_max': (None if not found else
                    [float(min(found)), float(np.median(found)), float(max(found))])}
        summaries.append(summary)
    result = {'schema_version': 1, 'status': 'hardware-only spectral timing; not a calibrated attack law',
              'inputs': {'audio_sha256': sha(args.audio), 'case_sha256': sha(CASE),
                         'script_sha256': sha(__file__)},
              'method': {'bands_hz': [[300, 1500], [1500, 12000]],
                         'windows_samples': [512, 1024, 2048], 'hop_samples': 44,
                         'channels': list(channels), 'onset_shifts_seconds': [-.010, 0, .010],
                         'early_reference_elapsed_seconds': [.015, .035],
                         'sustained_threshold_seconds': .010, 'gate_guard_seconds': .030,
                         'interpretation': 'Each landmark is a relative spectral-ratio drop. Filter cutoff, overdrive and changing layer balance can alter this trajectory; elapsed time is not the filter attack duration.'},
              'summary_by_note': summaries, 'observations': rows, 'mid_traces': traces}
    (out/'analysis.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(summaries, indent=2))


if __name__ == '__main__':
    main()
