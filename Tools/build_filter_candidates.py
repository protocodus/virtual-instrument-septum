#!/usr/bin/env python3
"""Build isolated production-linear and experimental-exponential filter renderers.

The builder never modifies shipping source. The default linear profile uses
the current production implementation; its timing is a conditional recording
fit, not a verified SH-201 algorithm. The exponential profile is experimental.
Default times reproduce the two existing Moogie diagnostic profiles: a linear
control segment of 0.4189852819747085 s and an exponential control time constant
of 0.26557632184918367 s, both at raw filter decay 49. Other control values are
provisional interpolations. Attack, sustain, release and amplifier envelopes
retain their shipping implementations.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LINEAR = 0.4189852819747085
DEFAULT_EXPONENTIAL = 0.26557632184918367
FIT = ROOT / 'Docs/fidelity/source-audits/filter-envelope-conditional-fit.json'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def replace_once(text, old, new, label):
    if text.count(old) != 1:
        raise ValueError(f'{label}: expected exactly one unchanged shipping anchor; review the experiment')
    return text.replace(old, new, 1)


def candidate_sources(source, header, linear, seconds):
    # Validate the filter-only selector even for the unchanged production copy.
    if source.count('tone.filterEnvRelease, Envelope::DecayShape::Linear);') != 2:
        raise ValueError('Expected the two production linear filter configure calls; review the experiment')
    anchor = '        constexpr double fittedDuration = 0.4189852819747085;'
    if header.count(anchor) != 1:
        raise ValueError('Expected the production filterDecaySeconds fit; review the experiment')
    if linear:
        header = replace_once(header, anchor,
                              f'        constexpr double fittedDuration = {seconds!r};',
                              'Linear filter duration')
    else:
        source = replace_once(source,
            '    if (decayShape == DecayShape::Linear)\n'
            '    {\n'
            '        const double samples = std::max (1.0, mapping::filterDecaySeconds (d) * sr);\n'
            '        decayStep = (1.0 - sustain) / samples;\n'
            '        // A live sustain increase must also converge, including sustain=1\n'
            '        // where the peak-to-sustain downward step is zero. Keep the current\n'
            '        // level and use a zero-to-sustain rise over the same mapped duration.\n'
            '        sustainRiseStep = sustain / samples;\n'
            '    }',
            '    if (decayShape == DecayShape::Linear)\n'
            '    {\n'
            '        // Isolated experiment: the two filter configure calls select Linear.\n'
            '        // Use the fitted exponential comparison instead; amp stays unchanged.\n'
            '        decayShape = DecayShape::Exponential;\n'
            '        decayCoeff = std::exp (-1.0 / (sr\n'
            f'            * mapping::decaySeconds (d) * ({seconds!r} / mapping::decaySeconds (49))));\n'
            '    }', 'Exponential filter configure')
    return source, header


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='new directory; existing paths are refused')
    parser.add_argument('--dsp-library', type=Path, default=ROOT / 'build-fidelity/libSeptumDSP.a',
                        help='built shipping SeptumDSP archive for unchanged codec/preset objects')
    parser.add_argument('--compiler', default='c++', help='C++20 compiler executable (no shell flags)')
    parser.add_argument('--linear-seconds', type=float, default=DEFAULT_LINEAR,
                        help='raw49 duration; default uses the production 419 ms fit at full precision')
    parser.add_argument('--exponential-seconds', type=float, default=DEFAULT_EXPONENTIAL,
                        help='experimental raw49 time constant; default266 ms at full precision')
    args = parser.parse_args()
    try:
        if not math.isfinite(args.linear_seconds) or not 0.002 < args.linear_seconds < 12:
            raise ValueError('--linear-seconds must be finite and between0.002 and12')
        if not math.isfinite(args.exponential_seconds) or not 0 < args.exponential_seconds < 120:
            raise ValueError('--exponential-seconds must be finite and between0 and120')
        compiler = shutil.which(args.compiler)
        if compiler is None:
            raise ValueError(f'Compiler not found: {args.compiler}')
        compiler = str(Path(compiler).resolve())
        archive = args.dsp_library.resolve()
        inputs = {path.relative_to(ROOT).as_posix(): path.read_bytes()
                  for path in sorted((ROOT / 'Source/DSP').glob('*.h'))}
        for name in ('Source/DSP/SeptumEngine.cpp', 'Tools/RenderMidi.cpp'):
            inputs[name] = (ROOT / name).read_bytes()
        archive_bytes = archive.read_bytes()
        profiles = []
        for name, shape, seconds, linear in (
                ('linear-slow', 'linear_control', args.linear_seconds, True),
                ('exponential-slow', 'exponential_control', args.exponential_seconds, False)):
            source, header = candidate_sources(inputs['Source/DSP/SeptumEngine.cpp'].decode(),
                                               inputs['Source/DSP/SeptumEngine.h'].decode(), linear, seconds)
            files = {name: data for name, data in inputs.items() if name.startswith('Source/')}
            files['Source/DSP/SeptumEngine.cpp'] = source.encode()
            files['Source/DSP/SeptumEngine.h'] = header.encode()
            files['RenderMidi.cpp'] = inputs['Tools/RenderMidi.cpp']
            profiles.append((name, shape, seconds, files))
        # Validate anchors and read all dependencies before creating anything.
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=False)
        support = output / 'support/libSeptumDSP.a'
        support.parent.mkdir()
        support.write_bytes(archive_bytes)
        compiler_version = subprocess.check_output([compiler, '--version'], text=True).strip()
        common = {
            'schema_version': 2, 'status': 'isolated comparison renderer',
            'builder_sha256': digest(Path(__file__).read_bytes()),
            'shipping_source_sha256': {name: digest(data) for name, data in inputs.items()},
            'support_library': {'original_path': str(archive), 'copied_path': str(support),
                                'sha256': digest(archive_bytes)},
            'compiler': {'path': compiler, 'version': compiler_version,
                         'platform': platform.platform(), 'machine': platform.machine()},
            'conditional_fit_evidence': {'path': str(FIT), 'sha256': digest(FIT.read_bytes())}
                                        if FIT.exists() else None,
            'fitted_raw_control': 49,
            'fitting': 'Default times fit first Moogie low note only under current LP24/base/depth assumptions; two other notes held out.',
            'unmeasured': 'Other decay controls use provisional interpolation; source waveform and recording assumptions remain. These are not verified Roland algorithms.',
            'isolation': 'This build copies source and support objects; it does not modify shipping source or preset data.',
        }
        for name, shape, seconds, files in profiles:
            directory = output / name
            for relative, data in files.items():
                destination = directory / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
            executable = directory / 'SeptumRenderMidi'
            command = [compiler, '-std=c++20', '-O3', '-I', str(directory / 'Source'),
                       '-I', str(directory / 'Source/DSP'), str(directory / 'RenderMidi.cpp'),
                       str(directory / 'Source/DSP/SeptumEngine.cpp'), str(support), '-o', str(executable)]
            result = subprocess.run(command, capture_output=True, text=True)
            (directory / 'build.log').write_text(result.stdout + result.stderr)
            if result.returncode:
                raise ValueError(f'Build failed: {directory / "build.log"}')
            profile = {**common, 'profile': name, 'shape': shape, 'time_seconds': seconds,
                       'profile_status': 'production linear implementation' if name == 'linear-slow'
                                         and seconds == DEFAULT_LINEAR else 'experimental comparison',
                       'time_source': 'production conditional-fit default' if name == 'linear-slow'
                                      and seconds == DEFAULT_LINEAR else 'pinned conditional-fit default' if seconds == (
                           DEFAULT_LINEAR if name == 'linear-slow' else DEFAULT_EXPONENTIAL)
                           else 'explicit experimental override',
                       'time_definition': 'full linear control-segment duration' if name == 'linear-slow'
                                          else 'exponential control time constant (not time to -60 dB)',
                       'compile_command': command,
                       'source_sha256': {relative: digest(data) for relative, data in files.items()},
                       'renderer_sha256': digest(executable.read_bytes())}
            (directory / 'profile.json').write_text(json.dumps(profile, indent=2) + '\n')
            print(f'Built {name} ({profile["profile_status"]}): {executable}', flush=True)
        if any((ROOT / name).read_bytes() != data for name, data in inputs.items()):
            raise ValueError('Shipping source changed during the build; reject this run')
        if archive.read_bytes() != archive_bytes:
            raise ValueError('Shipping DSP archive changed during the build; reject this run')
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
