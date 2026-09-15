#!/usr/bin/env python3
"""Verify and summarize both frozen 201vsJP8000 opening hypotheses."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import assess_hardware_equivalence as assess
from summarize_reverb_validation import reference_mask_diagnostics
from verify_reverb_validation_run import independent_metrics, compare_numeric

MODELS = ('gain-1', 'gain-0.5', 'gain-0.25')
CASE_IDS = ('201-vs-jp8000-held-opening', '201-vs-jp8000-c3-release-opening')
COLORS = ('#85948c', '#167554', '#b87136')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    original = json.loads((a.run/'results.json').read_text())
    if tuple(c['id'] for c in original['cases']) != CASE_IDS:
        raise ValueError('Expected both frozen opening hypotheses in declared order')
    errors, rows = {}, []
    fig, axes = plt.subplots(2, 2, figsize=(13, 7), constrained_layout=True)
    for col, c in enumerate(original['cases']):
        base = a.run/'baseline-corpus'/c['id']
        directory = a.run/'cases'/c['id']
        if (sha(base/'comparison.json') != c['comparison_sha256'] or
                sha(base/'hardware-excerpt-raw.wav') != c['comparison']['files']['hardware-excerpt-raw.wav']):
            raise ValueError('Source or comparison receipt changed')
        sr, full_reference = assess.read_audio(base/'hardware-excerpt-raw.wav')
        start, end = c['evaluation_samples']
        lag, gain = c['calibration']['candidate_lag_samples'], c['calibration']['candidate_gain']
        reference = full_reference[start:end]
        candidates, checks = {}, []
        for name in MODELS:
            path = directory/(name+'.wav')
            receipt_path = path.with_suffix('.render.json')
            receipt = json.loads(receipt_path.read_text())
            if (sha(path) != c['models'][name]['wav_sha256']
                    or sha(receipt_path) != c['models'][name]['receipt_sha256']
                    or receipt['output']['sha256'] != sha(path)
                    or receipt['ignored_events'] or receipt['degraded_replay']
                    or receipt['output']['active_voices_at_end']):
                raise ValueError('Render identity/replay guard failed')
            rate, full = assess.read_audio(path)
            if rate != sr or abs(full).max() >= 1:
                raise ValueError('Render format or headroom failed')
            if name == 'gain-1':
                fit = assess.fit_transform(full_reference, full, sr,
                    c['calibration']['calibration_frames'], .05)
                if fit != c['calibration']:
                    raise ValueError('Run used another alignment implementation')
            candidates[name] = full[start+lag:end+lag]*gain
            compare_numeric(independent_metrics(reference, candidates[name], sr),
                c['models'][name]['measurements'], errors, c['id']+'/'+name)
            checks.append(dict(model=name, frames=len(full), peak=float(abs(full).max()),
                wav_sha256=sha(path), receipt_sha256=sha(receipt_path), finite=True,
                active_voices_at_end=0, ignored_events=0, degraded_replay=False))
        masked = reference_mask_diagnostics(reference, candidates, sr)
        rows.append(dict(id=c['id'], calibration=c['calibration'], evaluation_samples=[start, end],
            models={name:dict(primary=c['models'][name]['measurements']['summary'],
                candidate_prefix_gain_sensitivity=c['models'][name]['candidate_prefix_gain_sensitivity']['summary'],
                reference_only_masks=masked[name]) for name in MODELS}, verified_renders=checks))
        for name, y, color in [('Hardware recording', reference, '#262c30')] + [
                (name, candidates[name], color) for name, color in zip(MODELS, COLORS)]:
            env = assess.rms_envelope(y, 441, 110)
            times = (start + 220 + np.arange(len(env))*110)/sr
            axes[0,col].plot(times, 20*np.log10(np.maximum(env, 1e-8)), label=name, color=color)
        axes[0,col].set(title=('C3 held through crop' if col==0 else 'C3 release at .390 s'),
            xlabel='Original recording clock / s', ylabel='10 ms RMS / dBFS')
        axes[0,col].legend(fontsize=8)
        for name, color in zip(MODELS, COLORS):
            ms = c['models'][name]['measurements']['multi_resolution_stft']
            axes[1,col].plot([m['window_samples'] for m in ms],
                [m['spectral_convergence'] for m in ms], 'o-', label=name, color=color)
        axes[1,col].set(xlabel='STFT window / samples', ylabel='Unmasked spectral convergence',
            xscale='log', xticks=[512,2048,8192], xticklabels=['512','2048','8192'])
        for ax in axes[:,col]:
            ax.grid(alpha=.16)
    fig.suptitle('201vsJP8000: one SINGLE preset with HF damping −10 dB\n'
        'Both uncertain gates retained; one corrected prefix alignment/gain per case shared across models')
    fig.savefig(a.output/'201-reverb-followup.png', dpi=140)
    plt.close(fig)
    result = dict(status='exploratory_confounded_comparison_not_equivalence',
        source_results_sha256=sha(a.run/'results.json'), protocol=original['protocol'],
        tool_sha256=sha(__file__), assessment_tool_sha256=sha(assess.__file__),
        independent_metric_max_error=max(errors.values()), independent_numeric_checks=len(errors),
        reference_mask_scope='Post-score diagnostic: hardware-only activity, candidate-only energy still counted by primary unmasked SC.',
        cases=rows)
    (a.output/'summary.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    for row in rows:
        print(row['id'], row['calibration']['candidate_lag_samples'],
              {name: row['models'][name]['primary'] for name in MODELS})
    print('Independent metrics maximum error', max(errors.values()))


if __name__ == '__main__':
    main()
