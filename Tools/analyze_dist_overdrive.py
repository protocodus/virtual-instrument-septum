#!/usr/bin/env python3
"""Isolated Dist Bs 1 overdrive/oscillator diagnostics, never a hardware fit.

Copy the current DSP source, build predeclared one-factor interventions, replay
the original patch and reconstructed MIDI, and compare gain-invariant harmonic
ratios on one diagnostic note and two held-out notes. All modified source,
renderer hashes, PCM, input hashes and measurements are retained. No shipping
source or original patch is changed. NumPy/SciPy/Matplotlib are required.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

# Tiny, tall least-squares problems are slower with a large BLAS thread pool.
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
import numpy as np
from scipy.io import wavfile
from scipy.optimize import minimize_scalar
from scipy import signal
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
PROFILES = {
    'production': 'Unchanged production source',
    'compensation-minus-02': 'Post-clip compensation exponent -0.2 instead of -0.4',
    'compensation-zero': 'Remove post-clip gain compensation, preserving clipper input',
    'pregain-16db': 'DRIVE maximum pre-gain +16dB instead of +32dB; compensation unchanged',
    'pregain-48db': 'DRIVE maximum pre-gain +48dB instead of +32dB; compensation unchanged',
    'hard-clip': 'Replace tanh with symmetric hard clip, retaining first-order ADAA',
    'saw-polarity': 'Invert the saw waveform; its harmonic magnitudes before mixing are unchanged',
    'triangle-polarity': 'Invert the triangle waveform; its isolated harmonic magnitudes are unchanged',
    'triangle-quarter-phase': 'Offset the triangle waveform by a quarter cycle relative to pulse/saw',
    'pulse-quadratic': 'Preserve pulse-duty endpoints, replace linear control curve with square',
    'pulse-square-root': 'Preserve pulse-duty endpoints, replace linear control curve with square root',
    'upper-only': 'Mute lower after its amp envelope, before the shared output path',
    'lower-only': 'Mute upper after its amp envelope, before the shared output path',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def replace(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Expected one source anchor: ' + old[:90])
    return text.replace(old, new, 1)


def sources(source, header, profile):
    if profile.startswith('compensation-'):
        exponent = '-0.2' if profile.endswith('02') else '0.0'
        header = replace(header, 'overdriveCompensationExponent = -0.4;',
                         'overdriveCompensationExponent = ' + exponent + ';')
    elif profile.startswith('pregain-'):
        limit = '16.0' if '16' in profile else '48.0'
        header = replace(header, '(drive / 127.0) * (32.0 / 20.0)',
                         '(drive / 127.0) * (' + limit + ' / 20.0)')
    elif profile == 'hard-clip':
        source = replace(source, '        const double integral = logCosh (input);',
            '        const double integral = std::abs (input) <= 1.0 ? 0.5 * input * input\n'
            '                                                           : std::abs (input) - 0.5;')
        source = replace(source, '? std::tanh (0.5 * (input + previousInput))',
                         '? std::clamp (0.5 * (input + previousInput), -1.0, 1.0)')
    elif profile == 'saw-polarity':
        source = replace(source, 'value -= polyBlep (phase, inc);\n'
                                 '                return { value, wrapped, wrapOffset };',
                                 'value -= polyBlep (phase, inc);\n'
                                 '                return { -value, wrapped, wrapOffset };')
    elif profile.startswith('triangle-'):
        begin = source.index('            case Waveform::Triangle:\n')
        end = source.index('            case Waveform::Sine:\n', begin)
        triangle = source[begin:end]
        if profile == 'triangle-polarity':
            triangle = triangle.replace('return { value, wrapped, wrapOffset };',
                                        'return { -value, wrapped, wrapOffset };')
        else:
            triangle = triangle.replace('double value = phase < 0.5',
                                        'const double wavePhase = frac (phase + 0.25);\n'
                                        '                double value = wavePhase < 0.5')
            triangle = triangle.replace('4.0 * phase', '4.0 * wavePhase')
            triangle = triangle.replace('polyBlamp (phase, inc)', 'polyBlamp (wavePhase, inc)')
            triangle = triangle.replace('frac (phase + 0.5)', 'frac (wavePhase + 0.5)')
        source = source[:begin] + triangle + source[end:]
    elif profile.startswith('pulse-'):
        exponent = '2.0' if profile == 'pulse-quadratic' else '0.5'
        header = replace(header, '0.5 + 0.45 * (value / 127.0)',
                         '0.5 + 0.45 * std::pow (value / 127.0, ' + exponent + ')')
    elif profile in ('upper-only', 'lower-only'):
        part = 'Upper' if profile == 'upper-only' else 'Lower'
        source = replace(source, 'mono[i] = static_cast<float> (filtered * env);',
            'mono[i] = static_cast<float> (filtered * env * (voice.part == Part::'
            + part + ' ? 1.0 : 0.0));')
    elif profile != 'production':
        raise ValueError(profile)
    return source, header


def harmonic_fit(y, sr, start, end, f0):
    a, b = round(start * sr), round(end * sr)
    x = y[a:b:4].astype(float)
    t = np.arange(a, b, 4) / sr - start
    columns = [np.ones(len(t)), t - t.mean()]
    for harmonic in range(1, 13):
        columns += [np.cos(2 * np.pi * f0 * harmonic * t),
                    np.sin(2 * np.pi * f0 * harmonic * t)]
    basis = np.column_stack(columns)
    coeff = np.linalg.lstsq(basis, x, rcond=None)[0]
    residual = float(np.mean((x - basis @ coeff) ** 2) / np.var(x))
    amplitude = np.hypot(coeff[2::2], coeff[3::2])
    return {'amplitude': amplitude.tolist(),
            'relative_h1_db': (20 * np.log10(np.maximum(amplitude / amplitude[0], 1e-15))).tolist(),
            'phase_radians': np.arctan2(-coeff[3::2], coeff[2::2]).tolist(),
            'residual_power_fraction': residual}


def measure(path, case, latency_samples=0):
    sr, stereo = wavfile.read(path)
    if not np.issubdtype(stereo.dtype, np.floating):
        raise ValueError('Expected floating PCM')
    y = stereo.mean(axis=1).astype(float)
    records = []
    for index, note in enumerate(case['notes']):
        on, off = note['on'] + latency_samples / sr, note['off'] + latency_samples / sr
        nominal = 440 * 2 ** ((note['note'] - 36 - 69) / 12)
        result = minimize_scalar(lambda f: harmonic_fit(y, sr, on + .03, off - .02, f)
                                 ['residual_power_fraction'],
                                 bounds=(nominal * .97, nominal * 1.03), method='bounded')
        windows = []
        for shift in (-.01, 0, .01):
            for label, start, end in (('early', on + .035, on + .115),
                                      ('late', off - .105, off - .025)):
                windows.append({'label': label, 'timing_shift_seconds': shift,
                                'start': start + shift, 'end': end + shift,
                                **harmonic_fit(y, sr, start + shift, end + shift, result.x)})
        records.append({'index': index, 'role': 'diagnostic' if index == 0 else 'held_out',
                        'note': note['note'], 'fundamental_hz': float(result.x),
                        'full_residual_power_fraction': float(result.fun), 'windows': windows})
    f, p = signal.welch(stereo[:round(case['duration_seconds'] * sr)], sr, nperseg=8192, axis=0)
    p = p.mean(axis=1)
    use = (f >= 20) & (f <= 16000)
    return {'sample_rate': sr, 'peak': float(np.max(np.abs(stereo))),
            'centroid_20_16000_hz': float(np.sum(f[use] * p[use]) / np.sum(p[use])),
            'notes': records}


def compare(measurement, reference):
    rows = []
    for test, ref in zip(measurement['notes'], reference['notes']):
        # Each test uses the same window shift; no independent time alignment.
        by_shift = []
        for shift in (-.01, 0, .01):
            errors = []
            for a, b in zip(test['windows'], ref['windows']):
                if a['timing_shift_seconds'] == shift:
                    errors += (np.array(a['relative_h1_db'][1:8])
                               - np.array(b['relative_h1_db'][1:8])).tolist()
            by_shift.append({'shift_seconds': shift,
                             'h2_to_h8_rmse_db': float(np.sqrt(np.mean(np.square(errors))))})
        rows.append({'index': test['index'], 'role': test['role'], 'timing_sensitivity': by_shift})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comparison', type=Path, required=True, help='Dist Bs 1 comparison directory')
    parser.add_argument('--output', type=Path, required=True, help='new directory')
    parser.add_argument('--dsp-library', type=Path, default=ROOT / 'build-fidelity/libSeptumDSP.a')
    parser.add_argument('--profile', action='append', choices=tuple(PROFILES))
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args()
    casefile = args.comparison / 'comparison.json'
    original = json.loads(casefile.read_text())
    if original['case']['id'] != 'dist-bs-1':
        raise ValueError('Only the declared three-note Dist reconstruction is supported')
    inputs = {p.name: p.read_bytes() for p in (ROOT / 'Source/DSP').glob('*.h')}
    inputs['SeptumEngine.cpp'] = (ROOT / 'Source/DSP/SeptumEngine.cpp').read_bytes()
    inputs['RenderMidi.cpp'] = (ROOT / 'Tools/RenderMidi.cpp').read_bytes()
    source, header = inputs['SeptumEngine.cpp'].decode(), inputs['SeptumEngine.h'].decode()
    profiles = args.profile or list(PROFILES)
    candidates = {name: sources(source, header, name) for name in profiles}
    reference_names = ('original-patch.syx', 'reconstructed-performance.mid', 'hardware-excerpt-raw.wav')
    for name in reference_names:
        if sha((args.comparison / name).read_bytes()) != original['files'][name]:
            raise ValueError('Changed input: ' + name)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    support = output / 'libSeptumDSP.a'
    support.write_bytes(args.dsp_library.read_bytes())
    for name in reference_names:
        shutil.copyfile(args.comparison / name, output / name)
    compiler = shutil.which('c++')
    manifest = {'schema_version': 1, 'status': 'diagnostic only; no shipping changes',
                'method': 'Predeclared one-factor interventions; first note diagnostic, two notes held out. '
                          'Joint 12-harmonic least squares plus DC/linear trend, per-note fundamental estimated '
                          'from residual minimum. H2-H8/H1 RMSE is descriptive, not a sound-quality score.',
                'limits': original['comparison_limits'] + [
                    'All notes belong to one MP3 and patch; held-out notes are not independent hardware captures.',
                    'Published documentation does not specify pre-gain, compensation, clip transfer, or oscillator phase.',
                    'Unknown recording EQ can change individual harmonic ratios; no unique nonlinear algorithm is identified.'],
                'builder_sha256': sha(Path(__file__).read_bytes()),
                'source_sha256': {n: sha(v) for n, v in inputs.items()},
                'support_sha256': sha(support.read_bytes()),
                'reference_sha256': {n: sha((output / n).read_bytes()) for n in reference_names},
                'compiler': subprocess.check_output([compiler, '--version'], text=True).strip(),
                'case': original['case'], 'reference': original['reference'], 'profiles': {}}
    reference = measure(output / 'hardware-excerpt-raw.wav', original['case'])
    manifest['hardware'] = reference

    def build(name):
        directory = output / name
        directory.mkdir()
        (directory / 'DSP').mkdir()
        edited_source, edited_header = candidates[name]
        data = {**inputs, 'SeptumEngine.cpp': edited_source.encode(), 'SeptumEngine.h': edited_header.encode()}
        for filename, content in data.items():
            ((directory if filename == 'RenderMidi.cpp' else directory / 'DSP') / filename).write_bytes(content)
        executable = directory / 'SeptumRenderMidi'
        command = [compiler, '-std=c++20', '-O3', '-I', str(directory), str(directory / 'RenderMidi.cpp'),
                   str(directory / 'DSP/SeptumEngine.cpp'), str(support), '-o', str(executable)]
        compiled = subprocess.run(command, text=True, capture_output=True)
        (directory / 'build.log').write_text(compiled.stdout + compiled.stderr)
        compiled.check_returncode()
        wav = directory / 'render.wav'
        render = [sys.executable, str(ROOT / 'Tools/render_midi.py'), '--renderer', str(executable),
                  '--midi', str(output / 'reconstructed-performance.mid'), '--syx', str(output / 'original-patch.syx'),
                  '--output', str(wav), '--tempo-policy', 'preserve-patch', '--strict']
        result = subprocess.run(render, text=True, capture_output=True)
        (directory / 'render.log').write_text(result.stdout + result.stderr)
        result.check_returncode()
        measurement = measure(wav, original['case'], original['retained_engine_latency_samples'])
        return name, {'description': PROFILES[name], 'compile_command': command, 'render_command': render,
                      'source_sha256': {n: sha(v) for n, v in data.items()},
                      'renderer_sha256': sha(executable.read_bytes()), 'wav_sha256': sha(wav.read_bytes()),
                      'measurements': measurement, 'comparison': compare(measurement, reference)}

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for name, result in pool.map(build, profiles):
            manifest['profiles'][name] = result
            rmses = [round(n['timing_sensitivity'][1]['h2_to_h8_rmse_db'], 2) for n in result['comparison']]
            print(name, round(result['measurements']['centroid_20_16000_hz'], 2), rmses, flush=True)
    if 'production' in manifest['profiles']:
        manifest['production_reproduces_reference_render_bytes'] = (
            manifest['profiles']['production']['wav_sha256'] == original['files']['septum-raw.wav'])
    (output / 'results.json').write_text(json.dumps(manifest, indent=2) + '\n')
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), layout='constrained')
    for index, ax in enumerate(axes):
        hw = [w for w in reference['notes'][index]['windows']
              if w['timing_shift_seconds'] == 0 and w['label'] == 'early'][0]
        ax.plot(range(2, 9), hw['relative_h1_db'][1:8], 'ko-', lw=2, label='Hardware')
        for name in profiles:
            if name in ('upper-only', 'lower-only'):
                continue
            note = manifest['profiles'][name]['measurements']['notes'][index]
            win = [w for w in note['windows'] if w['timing_shift_seconds'] == 0 and w['label'] == 'early'][0]
            ax.plot(range(2, 9), win['relative_h1_db'][1:8], '.-', label=name, alpha=.8)
        ax.set(xlabel='Harmonic number', ylabel='Amplitude relative to fundamental (dB)',
               title=('Diagnostic' if index == 0 else 'Held-out') + f' note {index + 1}')
        ax.grid(alpha=.2)
    axes[-1].legend(fontsize=7)
    fig.savefig(output / 'harmonics.png', dpi=150)
    return 0


if __name__ == '__main__':
    sys.exit(main())
