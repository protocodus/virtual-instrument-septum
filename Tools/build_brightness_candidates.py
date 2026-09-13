#!/usr/bin/env python3
"""Build isolated filter-envelope range hypotheses from frozen source copies.

The historical control is 10 octaves at depth 63. No preset or MIDI is changed.
The mapping is empirical, not a recovered Roland parameter table.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--depths', type=float, nargs='+', default=[10, 12, 14])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    inputs = {str(p.relative_to(ROOT)): p.read_bytes()
              for p in (ROOT / 'Source/DSP').glob('*.h')}
    for name in ('Source/DSP/SeptumEngine.cpp', 'Tools/RenderMidi.cpp',
                 'build-fidelity/libSeptumDSP.a'):
        inputs[name] = (ROOT / name).read_bytes()
    profiles = []
    for depth in args.depths:
        if not 0 < depth <= 24:
            raise ValueError('Envelope range must be positive and at most 24 octaves')
        name = f'depth-{depth:g}'
        dest = args.output / name
        dest.mkdir()
        for rel, data in inputs.items():
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        header_path = dest / 'Source/DSP/SeptumEngine.h'
        pattern = r'(inline double filterEnvOctaves \(int depth\) noexcept\s*\{\s*return depth \* \()[0-9.]+( / 63\.0\);)'
        header, count = re.subn(pattern, lambda m: m[1] + repr(float(depth)) + m[2],
                                header_path.read_text())
        if count != 1:
            raise ValueError('Filter envelope mapping anchor changed; review candidate builder')
        header_path.write_text(header)
        binary = dest / 'SeptumRenderMidi'
        command = ['c++', '-O3', '-std=c++20', '-I', str(dest / 'Source'),
                   '-I', str(dest / 'Source/DSP'), str(dest / 'Tools/RenderMidi.cpp'),
                   str(dest / 'Source/DSP/SeptumEngine.cpp'),
                   str(dest / 'build-fidelity/libSeptumDSP.a'), '-o', str(binary)]
        run = subprocess.run(command, capture_output=True, text=True)
        (dest / 'build.log').write_text(run.stdout + run.stderr)
        if run.returncode:
            raise RuntimeError(dest / 'build.log')
        record = {'name': name, 'filter_envelope_max_octaves': depth,
                  'status': 'historical control' if depth == 10 else 'isolated empirical hypothesis',
                  'renderer': str(binary.resolve()), 'renderer_sha256': sha(binary.read_bytes()),
                  'command': command,
                  'source_sha256': {rel: sha((dest / rel).read_bytes()) for rel in inputs}}
        (dest / 'profile.json').write_text(json.dumps(record, indent=2) + '\n')
        profiles.append(record)
        print(name, flush=True)
    for rel, data in inputs.items():
        if (ROOT / rel).read_bytes() != data:
            raise RuntimeError('Input changed during build: ' + rel)
    (args.output / 'profiles.json').write_text(json.dumps({
        'shipping_source_hashes': {rel: sha(data) for rel, data in inputs.items()},
        'script_sha256': sha(Path(__file__).read_bytes()), 'profiles': profiles,
        'limits': 'Only filter-envelope range changes. Cutoff, resonance, envelope timing, '
                  'oscillators, effects and external AUDIO FILTER are held fixed.'}, indent=2) + '\n')


if __name__ == '__main__':
    main()
