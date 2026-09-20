#!/usr/bin/env python3
"""Freeze seven predeclared triangle hypotheses and replay named hardware cases.

Third-party audio, generated MIDI, source copies and renderers remain in the
selected output directory. All input comparisons must be manifest-verified.
This discrete diagnostic sweep neither changes production nor selects a winner.
Selection is exploratory: the five triangle presets have already been inspected
and are not an untouched confirmation set.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from scipy.io import wavfile

from build_timbre_candidate import build_candidate
from compare_hardware import renderer_provenance, validate_audio
from evaluate_timbre_matrix import band_shape, load_run, spectral_residual


ROOT = Path(__file__).resolve().parents[1]
RENDER_SETTINGS = {
    'sample_rate': 44100,
    'tail_seconds': 2.0,
    'master_level': 100,
    'tempo_policy': 'preserve-patch',
    'midi_channel': 1,
}

# Preserve declaration order so profile generation and report ordering remain
# stable even when candidate builds run concurrently.
TRIALS = {
    'triangle-half': {'wave_gain': [1, 1, 1, .5, 1]},
    'triangle-one-half': {'wave_gain': [1, 1, 1, 1.5, 1]},
    'triangle-invert-half': {'wave_gain': [1, 1, 1, -.5, 1]},
    'triangle-invert': {'wave_gain': [1, 1, 1, -1, 1]},
    'triangle-invert-one-half': {'wave_gain': [1, 1, 1, -1.5, 1]},
    'triangle-quarter': {'phase_cycles': [0, 0, 0, .25, 0]},
    'triangle-three-quarter': {'phase_cycles': [0, 0, 0, .75, 0]},
}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_profile(trial, waves):
    return {
        'version': 1,
        'id': trial,
        'evidence': (
            'Experimental discrete cross-preset waveform hypothesis; not a hardware '
            'calibration. Original presets and estimated MIDI remain unchanged.'),
        'waves': waves,
    }


def load_comparisons(sources, baseline_provenance):
    """Verify the comparison runs and measure each original baseline once."""
    cases = {}
    for source in sources:
        for key, row in load_run(source).items():
            if key in cases:
                raise ValueError('Duplicate comparison case: ' + key)
            if row['renderer_provenance'] != baseline_provenance:
                raise ValueError(
                    'Comparison was not rendered by the supplied frozen baseline: ' + key)

            directory = source / key
            metadata = json.loads((directory / 'septum-raw.render.json').read_text())
            if any(metadata['settings'].get(name) != value
                   for name, value in RENDER_SETTINGS.items()):
                raise ValueError('Baseline settings differ from the fixed sweep settings: ' + key)
            hardware_rate, hardware = wavfile.read(directory / 'hardware-excerpt-raw.wav')
            sample_rate, baseline = wavfile.read(directory / 'septum-raw.wav')
            frames = row['comparison_frames']
            if hardware_rate != 44100 or sample_rate != 44100:
                raise ValueError('The sweep requires 44.1 kHz hardware and baseline audio: ' + key)
            if len(hardware) != frames or len(baseline) < frames:
                raise ValueError('Comparison frame count disagrees with baseline audio: ' + key)
            shape = band_shape(hardware, sample_rate)
            baseline_residual = spectral_residual(
                shape, band_shape(baseline[:frames], sample_rate))
            cases[key] = (directory, row, shape, baseline_residual)
    return cases


def write_design(output, cases):
    write_json(output / 'design.json', {
        'trials': TRIALS,
        'selection': (
            'No selection from aggregate score. Dist initial diagnostic motivates '
            'the discrete candidates. Selection is exploratory: all five triangle '
            'presets were previously inspected and are not an untouched confirmation '
            'set. Cases without active triangle oscillators are regression controls.'),
        'cases': list(cases),
        'limitations': (
            'Estimated MIDI/velocity, unknown phase history and capture; whole-band '
            'metrics are secondary, not an overall-fidelity criterion. Sexy triangle '
            'fundamental near 19.16 Hz lies below the band metric\'s 25 Hz floor.'),
    })


def render_case(key, case, renderer, render_directory):
    """Replay unchanged estimated MIDI/preset inputs with fixed render settings."""
    directory, row, shape, baseline_residual = case
    wav = render_directory / (key + '.wav')
    command = [
        sys.executable, str(ROOT / 'Tools/render_midi.py'),
        '--renderer', str(renderer),
        '--syx', str(directory / 'original-patch.syx'),
        '--midi', str(directory / 'reconstructed-performance.mid'),
        '--output', str(wav),
        '--sample-rate', '44100', '--tail', '2', '--master-level', '100',
        '--tempo-policy', 'preserve-patch', '--strict',
    ]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
    metadata = json.loads(wav.with_suffix('.render.json').read_text())
    if metadata['degraded_replay']:
        raise ValueError('Candidate render degraded MIDI replay: ' + key)
    if metadata['output']['latency_samples'] != row['retained_engine_latency_samples']:
        raise ValueError('Candidate render latency differs from the baseline: ' + key)

    sample_rate, audio = wavfile.read(wav)
    if sample_rate != 44100:
        raise ValueError('Candidate audio is not 44.1 kHz: ' + key)
    if len(audio) < row['comparison_frames']:
        raise ValueError('Candidate audio is shorter than the comparison: ' + key)
    actual_sha256 = sha256(wav)
    if metadata['output']['sha256'] != actual_sha256:
        raise ValueError('Candidate output hash disagrees with its render manifest: ' + key)
    validate_audio(audio)
    candidate_residual = spectral_residual(
        shape, band_shape(audio[:row['comparison_frames']], sample_rate))
    return {
        'id': key,
        'baseline': baseline_residual,
        'candidate': candidate_residual,
        'delta_rmse_db': (candidate_residual['band_shape_rmse_db']
                          - baseline_residual['band_shape_rmse_db']),
        'identical_raw': actual_sha256 == row['files']['septum-raw.wav'],
        'render_sha256': metadata['output']['sha256'],
        'original_comparison_sha256': sha256(directory / 'comparison.json'),
    }


def run_trial(trial, waves, output, baseline_provenance, cases):
    """Freeze one model, render every case, and retain its verified provenance."""
    profile = make_profile(trial, waves)
    profile_path = output / (trial + '.json')
    write_json(profile_path, profile)
    build = output / trial
    manifest = build_candidate(profile_path, build)
    renderer = build / 'SeptumRenderMidi'
    provenance = renderer_provenance(renderer)
    baseline_sources = baseline_provenance['build_manifest']['source']['input_sha256']
    if manifest['source']['input_sha256'] != baseline_sources:
        raise ValueError('Candidate source snapshot differs from the baseline: ' + trial)

    render_directory = build / 'renders'
    render_directory.mkdir()
    rows = [render_case(key, case, renderer, render_directory)
            for key, case in cases.items()]
    if renderer_provenance(renderer) != provenance:
        raise ValueError(
            'Candidate renderer or frozen inputs changed during the sweep: ' + trial)

    result = {'trial': trial, 'profile': profile, 'renderer': provenance, 'cases': rows}
    write_json(build / 'results.json', result)
    print(trial, [(row['id'], round(row['delta_rmse_db'], 3))
                  for row in rows if not row['identical_raw']], flush=True)
    return result


def run_sweep(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sources = [path.resolve() for path in args.comparison]
    baseline_path = args.baseline.resolve()
    baseline_provenance = renderer_provenance(baseline_path)
    cases = load_comparisons(sources, baseline_provenance)
    write_design(output, cases)

    def run_declared_trial(item):
        return run_trial(*item, output, baseline_provenance, cases)

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(run_declared_trial, TRIALS.items()))

    for source in sources:
        load_run(source)
    if renderer_provenance(baseline_path) != baseline_provenance:
        raise ValueError('Baseline renderer or frozen inputs changed during the sweep')
    write_json(output / 'results.json', results)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, type=Path,
                        help='frozen baseline renderer with manifest.json')
    parser.add_argument('--comparison', required=True, action='append', type=Path,
                        help='baseline comparison run; may be repeated')
    parser.add_argument('--output', required=True, type=Path, help='new directory')
    parser.add_argument('--jobs', type=int, default=3)
    args = parser.parse_args(argv)
    if not 1 <= args.jobs <= 8:
        parser.error('--jobs must be between 1 and 8')
    run_sweep(args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
