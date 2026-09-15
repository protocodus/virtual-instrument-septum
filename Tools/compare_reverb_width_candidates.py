#!/usr/bin/env python3
"""Test fixed reverb-return width or gain in frozen full-engine preset replays.

Cotton's repeated stereo excess motivates this exploratory family. The other
nine public presets assess generalization; none has authenticated performance
MIDI. No width is selected by this tool and no shipping source is changed.
"""
import argparse
import difflib
import hashlib
import html
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys

os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
import numpy as np
from scipy.io import wavfile

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'b0f6c03'
WIDTHS = (1., .5, .25)
ANCHOR = '''            wetReverbL = reverb_.highCutStateL;
            wetReverbR = reverb_.highCutStateR;'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comparison-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('width', 'gain'), default='width')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    frozen = out/'frozen-source'
    names = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', REVISION,
                                     'Source/DSP'], cwd=ROOT, text=True).splitlines()
    names += ['Tools/'+name for name in ('RenderMidi.cpp', 'build_timbre_candidate.py',
              'render_midi.py', 'assess_hardware_equivalence.py')]
    hashes = {}
    for name in names:
        path = frozen/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(subprocess.check_output(['git', 'show', f'{REVISION}:{name}'], cwd=ROOT))
        hashes[name] = sha(path)
    guard_path = ROOT/'Docs/fidelity/source-audits/final-production-verification-2026-09-15.json'
    guard = {case['id']: case for case in json.loads(guard_path.read_text())['cases']}
    if len(guard) != 10:
        raise ValueError('Expected ten pinned production cases')
    comparisons = sorted(args.comparison_root.glob('*/comparison.json'))
    if {p.parent.name for p in comparisons} != set(guard):
        raise ValueError('Comparison set changed')
    protocol = dict(status='experimental_no_selection', source_revision=REVISION,
        mode=args.mode, scales=list(WIDTHS), hypothesis_context='cotton-wool',
        comparative_cases=sorted(set(guard)-{'cotton-wool'}),
        change=('Only final reverb return: M=(L+R)/2, S=(L-R)/2, L=M+W*S, R=M-W*S. W1 retains original arithmetic.'
                if args.mode=='width' else 'Only final reverb return: multiply both L and R by the same G. G1 retains original arithmetic.'),
        unchanged='Oscillators, filter, envelopes, delay, reverb feedback/diffusion/damping, preset bytes, reconstructed MIDI and render rate.',
        alignment='Production first-quarter envelope fit bounded50ms; same frozen lag for every width.',
        gain='One scalar per render trained on first quarter; production scalar also retained as sensitivity.',
        evaluation='Common remaining three quarters; no STFT frame crosses calibration boundary.',
        limitations='Exploratory evidence follows inspected recordings. Exact recorded preset revision, performance MIDI and capture processing remain uncertain. Return width/gain are hypotheses, not identified hardware parameters. No shipping selection.')
    save(out/'protocol-before-rendering.json', protocol)
    shutil.copyfile(__file__, out/Path(__file__).name)
    save(out/'source-manifest.json', dict(revision=REVISION, input_sha256=hashes,
         tool_sha256=sha(__file__), production_guard_sha256=sha(guard_path)))
    sys.path.insert(0, str(frozen/'Tools'))
    import build_timbre_candidate as builder
    import assess_hardware_equivalence as assess

    builds = {}
    for width in WIDTHS:
        identity = args.mode+'-'+format(width, 'g')
        variant = out/'variant-sources'/identity
        shutil.copytree(frozen, variant)
        engine = variant/'Source/DSP/SeptumEngine.cpp'
        original = engine.read_text()
        if original.count(ANCHOR) != 1:
            raise ValueError('Reverb return integration point changed')
        changed = original
        if width != 1:
            change = f'''
            // Experimental fixed return width; wet mid and FDN remain unchanged.
            const double reverbMid = 0.5 * (wetReverbL + wetReverbR);
            const double reverbSide = 0.5 * (wetReverbL - wetReverbR);
            wetReverbL = reverbMid + {width:.17g} * reverbSide;
            wetReverbR = reverbMid - {width:.17g} * reverbSide;''' if args.mode=='width' else f'''
            // Experimental equal-channel return gain; FDN and wet width unchanged.
            wetReverbL *= {width:.17g};
            wetReverbR *= {width:.17g};'''
            changed = original.replace(ANCHOR, ANCHOR+change)
            engine.write_text(changed)
        mutated = [name for name in names if sha(variant/name) != hashes[name]]
        expected = [] if width == 1 else ['Source/DSP/SeptumEngine.cpp']
        if mutated != expected:
            raise ValueError('Unexpected source mutation')
        (out/(identity+'.diff')).write_text(''.join(difflib.unified_diff(
            original.splitlines(True), changed.splitlines(True),
            fromfile='b0f6c03/SeptumEngine.cpp', tofile=identity+'/SeptumEngine.cpp')))
        profile = out/(identity+'.json')
        save(profile, dict(version=1, id=identity,
             evidence='Experimental reverb '+args.mode+' hypothesis; exact final wet-return change retained in source diff.'))
        builds[identity] = builder.build_candidate(profile, out/'builds'/identity, source_root=variant)
        print('Built', identity, flush=True)

    cases, sections = [], []
    for comparison in comparisons:
        meta = json.loads(comparison.read_text())
        identity = meta['case']['id']
        source, directory = comparison.parent, out/'cases'/identity
        directory.mkdir(parents=True)
        files = ('hardware-excerpt-raw.wav', 'septum-raw.wav', 'original-patch.syx',
                 'reconstructed-performance.mid')
        for name in files:
            if sha(source/name) != meta['files'][name]:
                raise ValueError('Comparison input changed: '+name)
            shutil.copyfile(source/name, directory/name)
        for filename, key in (('septum-raw.wav', 'production_sha256'),
                              ('original-patch.syx', 'patch_sha256'),
                              ('reconstructed-performance.mid', 'midi_sha256')):
            if sha(directory/filename) != guard[identity][key]:
                raise ValueError('Production guard mismatch')
        rate, hardware = assess.read_audio(directory/'hardware-excerpt-raw.wav')
        sr, base_full = assess.read_audio(directory/'septum-raw.wav')
        n = meta['comparison_frames']
        if rate != 44100 or sr != rate or len(hardware) != n or len(base_full) < n:
            raise ValueError('Unexpected coverage or rate')
        base = base_full[:n]
        cal = round(n*.25)
        transform = assess.fit_transform(hardware, base, sr, cal, .05)
        lag = transform['candidate_lag_samples']
        ca, cb = max(0, -lag), min(cal, cal-lag)
        start, end = max(cal, cal-lag), min(n, n-lag)
        record = dict(id=identity, role='hypothesis_context' if identity=='cotton-wool' else 'comparative',
            input_sha256={name: sha(directory/name) for name in files},
            comparison_sha256=sha(comparison), case=meta['case'],
            calibration=transform, calibration_reference_samples=[ca, cb],
            calibration_candidate_samples=[ca+lag, cb+lag], evaluation_samples=[start, end],
            limitations=meta['comparison_limits'], models={})
        sounds = {}
        for width in WIDTHS:
            name = args.mode+'-'+format(width, 'g')
            renderer = out/'builds'/name/'SeptumRenderMidi'
            wav = directory/(name+'.wav')
            command = [sys.executable, str(frozen/'Tools/render_midi.py'), '--renderer', str(renderer),
                       '--midi', str(directory/'reconstructed-performance.mid'),
                       '--syx', str(directory/'original-patch.syx'), '--output', str(wav),
                       '--tempo-policy', 'preserve-patch']
            subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
            cs, candidate = assess.read_audio(wav)
            receipt = json.loads(wav.with_suffix('.render.json').read_text())
            if (cs != sr or candidate.shape != base_full.shape or not np.isfinite(candidate).all()
                    or receipt['ignored_events'] or receipt['output']['active_voices_at_end']):
                raise ValueError('Candidate render guard failed')
            identical = sha(wav) == guard[identity]['production_sha256']
            if width == 1 and not identical:
                raise ValueError('Unchanged width failed production identity')
            c = candidate[:n]
            gain = assess.rms(hardware[ca:cb])/assess.rms(c[ca+lag:cb+lag])
            record['models'][name] = dict(mode=args.mode, scale=width, raw_sha256=sha(wav),
                renderer_sha256=sha(renderer), receipt_sha256=sha(wav.with_suffix('.render.json')),
                command=command, peak=float(abs(candidate).max()), finite=True,
                samples_at_or_above_full_scale=int(np.count_nonzero(abs(candidate)>=1)),
                active_voices_at_end=0, identical_to_production=identical,
                training_gain=gain, training_gain_db=20*math.log10(gain),
                production_max_pcm_difference=float(np.max(abs(candidate-base_full))),
                measurements=assess.measure(hardware[start:end], c[start+lag:end+lag]*gain, sr),
                fixed_production_gain=assess.measure(hardware[start:end],
                    c[start+lag:end+lag]*transform['candidate_gain'], sr))
            sounds[name] = c[start+lag:end+lag]*gain
        listening = {'hardware': hardware[start:end], **sounds}
        scale = min(.1/assess.rms(listening['hardware']),
                    .98/max(float(abs(y).max()) for y in listening.values()))
        for name, y in listening.items():
            wavfile.write(directory/(name+'-listen.wav'), sr, (y*scale).astype(np.float32))
        record['listening_common_gain'] = scale
        save(directory/'result.json', record)
        cases.append(record)
        players = ''.join(f'<p>{html.escape(name)}<br><audio controls preload="none" src="cases/{identity}/{name}-listen.wav"></audio></p>' for name in listening)
        sections.append(f'<section><h2>{html.escape(identity)} ({record["role"]})</h2>{players}</section>')
        print(identity, ' '.join(f'{k}={v["measurements"]["summary"]["spectral_convergence_mean"]:.5f}'
              for k, v in record['models'].items()), flush=True)
    save(out/'results.json', dict(protocol=protocol, source_manifest_sha256=sha(out/'source-manifest.json'),
         build_manifest_sha256={name: sha(out/'builds'/name/'manifest.json') for name in builds},
         all_ten_scale1_byte_identical=True, cases=cases))
    (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Reverb return experiment</title>'
        '<style>body{font:16px system-ui;max-width:900px;margin:40px auto;padding:20px}section{border-top:1px solid #bbb;margin-top:32px}audio{width:100%}</style>'
        '<h1>Experimental reverb return '+args.mode+'</h1><p>Cotton supplies hypothesis context; nine other presets assess generalization. '
        'The same published presets and reconstructed MIDI feed every candidate. Scale1 is the current DSP. '
        +html.escape(protocol['change'])+' '
        'Listening uses the evaluation interval with frozen production timing and first-quarter candidate gain. '
        'No model selection or hardware-equivalence claim.</p>'+''.join(sections))
    print(out/'results.json')


if __name__ == '__main__':
    main()
