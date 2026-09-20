#!/usr/bin/env python3
"""Build one frozen oscillator-only BALANCE experiment; never edit production.

Normalize a linear crossfade so the stronger oscillator remains at unity.
The quieter gain becomes (63-|balance|)/(63+|balance|). The original shared
tone-balance function, center, endpoints and all other DSP remain unchanged.
"""
import argparse
import hashlib
import json
from pathlib import Path

from build_timbre_candidate import ROOT, _sources, build_candidate


OLD = '''    const double legGain1 = mapping::balanceLegGain (tone.balance, true);
    const double legGain2 = mapping::balanceLegGain (tone.balance, false);'''
NEW = '''    // Experimental oscillator-only normalized linear crossfade.
    // Shared part/tone BALANCE continues to use its incumbent law.
    const auto oscillatorLegGain = [] (int balance, bool firstLeg) noexcept
    {
        const bool dominant = balance <= 0 ? firstLeg : ! firstLeg;
        const double magnitude = std::abs (balance);
        return dominant ? 1.0 : (63.0 - magnitude) / (63.0 + magnitude);
    };
    const double legGain1 = oscillatorLegGain (tone.balance, true);
    const double legGain2 = oscillatorLegGain (tone.balance, false);'''


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='new directory')
    parser.add_argument('--compiler', default='c++')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    staging = output / 'staged-source'
    snapshot = _sources(ROOT)
    original = snapshot['Source/DSP/SeptumEngine.cpp'].decode()
    if original.count(OLD) != 1:
        raise ValueError('Expected exactly one oscillator balance integration point')
    modified = original.replace(OLD, NEW).encode()
    audit = {
        'status': 'experimental; not a hardware calibration or shipping change',
        'mechanism': 'oscillator-only normalized linear crossfade',
        'stronger_gain': 1,
        'quieter_gain': '(63-abs(balance))/(63+abs(balance))',
        'unchanged': ['shared tone/part balance mapping', 'center gains',
                      'endpoint gains', 'all patch bytes and other DSP'],
        'original_source_sha256': {name: sha(data) for name, data in snapshot.items()},
        'changed_file': 'Source/DSP/SeptumEngine.cpp',
        'changed_file_before_sha256': sha(snapshot['Source/DSP/SeptumEngine.cpp']),
        'changed_file_after_sha256': sha(modified),
        'exact_original_text': OLD, 'exact_replacement_text': NEW,
        'script_sha256': sha(Path(__file__).read_bytes()),
    }
    for name, data in snapshot.items():
        path = staging / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(modified if name == audit['changed_file'] else data)
    profile = {'version': 1, 'id': 'experimental-oscillator-balance-linear',
               'evidence': 'Experimental normalized linear oscillator BALANCE law '
               'from a staged source variant. No timbre API section enabled; '
               'explicit source-edit provenance is in source.experimental_modification. '
               'Not a recovered Roland law or shipping recommendation.'}
    profile_path = output / 'profile.json'
    profile_path.write_text(json.dumps(profile, indent=2) + '\n')
    (output / 'experiment.json').write_text(json.dumps(audit, indent=2) + '\n')
    manifest = build_candidate(profile_path, output / 'renderer',
                               compiler=args.compiler, source_root=staging)
    manifest['source']['experimental_modification'] = audit
    manifest['integration'] = ('Builder copied the staged oscillator-only source variant; '
                               'the exact prior edit and original production hashes are '
                               'recorded in source.experimental_modification. No shipping file changed.')
    (output / 'renderer/manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    if _sources(ROOT) != snapshot:
        raise ValueError('Production source changed during the experiment')
    print(json.dumps({'renderer': str(output / 'renderer/SeptumRenderMidi'),
                      'manifest': str(output / 'renderer/manifest.json'),
                      'experiment': str(output / 'experiment.json')}))


if __name__ == '__main__':
    main()
