#!/usr/bin/env python3
"""Validate a diagnostic triangle-polarity renderer on additional Dist notes.

The six-note reconstruction predates this experiment. The third note's later
pitch bend is absent from the MIDI and is deliberately excluded from analysis.
This is a conditional same-recording validation, not original MIDI replay.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from analyze_dist_overdrive import harmonic_fit, np, wavfile, minimize_scalar
from compare_hardware import write_midi

ROOT = Path(__file__).resolve().parents[1]
EVENTS = ((.112, .379, 63), (.440, .660, 63), (.783, 1.625, 65),
          (1.988, 2.220, 63), (2.358, 2.562, 63), (2.714, 3.034, 65))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profiles', required=True, type=Path)
    parser.add_argument('--comparison', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    midi = args.output / 'six-notes-reconstructed.mid'
    case = {'title': 'Dist Bs 1 six estimated notes; third-note bend not reconstructed',
            'duration_seconds': 3.9, 'notes': [{'on': a, 'off': b, 'note': n,
                 'velocity': 100, 'note_off_velocity': 64} for a, b, n in EVENTS]}
    write_midi(midi, case)
    syx = args.comparison / 'original-patch.syx'
    hardware = args.comparison / 'hardware-decoded-full.wav'
    result = {'schema_version': 1, 'status': 'diagnostic; no shipping changes',
              'method': 'Six notes from pre-existing audio transcription. The opening three were not used '
                        'to select the polarity candidate. Per-note 12-harmonic fits plus DC/linear trend; '
                        'early35–115ms and lateoff−105..off−25ms windows, shifted±10ms. '
                        'Third-note late window excluded because its pitch bend is unreconstructed.',
              'limits': ['Original MIDI, controllers, recording EQ/gain and absolute oscillator phase unknown.',
                         'Extra notes remain from the same MP3 and named patch; not independent captures.',
                         'No source-document calibration of triangle polarity or phase exists.'],
              'reconstruction': case, 'script_sha256': digest(Path(__file__)),
              'input_sha256': {str(p): digest(p) for p in (midi, syx, hardware)}, 'sources': {}}
    paths = {'hardware': hardware}
    for name in ('production', 'triangle-polarity'):
        renderer = args.profiles / name / 'SeptumRenderMidi'
        wav = args.output / (name + '.wav')
        command = [sys.executable, str(ROOT / 'Tools/render_midi.py'), '--renderer', str(renderer),
                   '--syx', str(syx), '--midi', str(midi), '--output', str(wav),
                   '--tempo-policy', 'preserve-patch', '--strict']
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
        paths[name] = wav
        result['sources'][name] = {'renderer_sha256': digest(renderer), 'render_command': command}
    for label, path in paths.items():
        sr, stereo = wavfile.read(path)
        y = stereo.mean(axis=1).astype(float)
        latency = 0 if label == 'hardware' else 93 / sr
        rows = []
        for index, (start, end, note) in enumerate(EVENTS):
            on, off = start + latency, end + latency
            nominal = 440 * 2 ** ((note - 36 - 69) / 12)
            f0 = minimize_scalar(lambda f: harmonic_fit(y, sr, on + .03, on + .18, f)
                                ['residual_power_fraction'], bounds=(nominal * .97, nominal * 1.03),
                                method='bounded').x
            windows = []
            for shift in (-.01, 0, .01):
                intervals = [('early', on + .035, on + .115)]
                if index != 2:
                    intervals += [('late', off - .105, off - .025)]
                for name, a, b in intervals:
                    windows.append({'name': name, 'shift_seconds': shift, 'start': a + shift,
                                    'end': b + shift, **harmonic_fit(y, sr, a + shift, b + shift, f0)})
            rows.append({'index': index, 'note': note, 'on': start, 'fundamental_hz': float(f0),
                         'role': 'extra-opening-note' if index < 3 else 'original-crop-note', 'windows': windows})
        result['sources'].setdefault(label, {}).update({'wav_sha256': digest(path), 'notes': rows})
    for label in ('production', 'triangle-polarity'):
        errors = []
        for test, ref in zip(result['sources'][label]['notes'], result['sources']['hardware']['notes']):
            rmse = []
            for shift in (-.01, 0, .01):
                error = []
                for a, b in zip(test['windows'], ref['windows']):
                    if a['shift_seconds'] == shift:
                        error += (np.array(a['relative_h1_db'][1:8]) - b['relative_h1_db'][1:8]).tolist()
                rmse.append({'shift_seconds': shift, 'h2_to_h8_rmse_db': float(np.sqrt(np.mean(np.square(error))))})
            errors.append({'index': test['index'], 'role': test['role'], 'rmse': rmse})
        result['sources'][label]['comparison'] = errors
        print(label, [round(e['rmse'][1]['h2_to_h8_rmse_db'], 3) for e in errors])
    (args.output / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
