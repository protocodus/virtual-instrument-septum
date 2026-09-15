#!/usr/bin/env python3
"""Summarize frozen new-preset reverb checks, with reference-only mask diagnostics."""
import argparse
import hashlib
import json
from pathlib import Path
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
import numpy as np
from scipy import signal
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import assess_hardware_equivalence as assess

MODELS = ('gain-1', 'gain-0.5', 'gain-0.25')
COLORS = ('#83958a', '#167554', '#b87136')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reference_mask_diagnostics(reference, candidates, sr):
    """Keep bins/support identical across models, using hardware activity only.

    This is a post-score sensitivity, not a replacement for the frozen primary
    evaluation. It omits spurious energy where only the model is active; the
    unmasked primary spectral convergence still includes that energy.
    """
    answer = {name: {'spectra': [], 'envelopes': []} for name in candidates}
    for nfft in (512, 2048, 8192):
        def spectrum(x):
            return np.abs(signal.stft(x, fs=sr, window='hann', nperseg=nfft,
                noverlap=nfft*3//4, boundary=None, padded=False, axis=0)[2])
        a = spectrum(reference)
        floor = max(a.max()*1e-4, 1e-30)
        mask = a >= max(a.max()*1e-3, 1e-30)
        for name, candidate in candidates.items():
            b = spectrum(candidate)
            delta = abs(20*np.log10(np.maximum(b, floor)/np.maximum(a, floor)))
            answer[name]['spectra'].append(dict(window=nfft, bins=int(mask.sum()),
                mean_db=float(delta[mask].mean()), p95_db=float(np.percentile(delta[mask], 95))))
    floor = max(abs(reference).max()*1e-4, 1e-30)
    for seconds in (.01, .05):
        window, hop = round(seconds*sr), round(.005*sr)
        a = assess.rms_envelope(reference, window, hop)
        mask = a >= max(a.max()*1e-3, 1e-30)
        for name, candidate in candidates.items():
            b = assess.rms_envelope(candidate, window, hop)
            delta = abs(20*np.log10(np.maximum(b, floor)/np.maximum(a, floor)))
            answer[name]['envelopes'].append(dict(window=window, bins=int(mask.sum()),
                mean_db=float(delta[mask].mean()), p95_db=float(np.percentile(delta[mask], 95))))
    for row in answer.values():
        row['summary'] = dict(log_spectral_error_db_mean=float(np.mean([x['mean_db'] for x in row['spectra']])),
            envelope_error_db_p95_max=max(x['p95_db'] for x in row['envelopes']))
    return answer


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    result = json.loads((args.run/'results.json').read_text())
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), layout='constrained')
    rows = []
    for case in result['cases']:
        base = args.run/'baseline-corpus'/case['id']
        folder = args.run/'cases'/case['id']
        if (sha(base/'comparison.json') != case['comparison_sha256']
                or sha(base/'hardware-excerpt-raw.wav') != case['comparison']['files']['hardware-excerpt-raw.wav']):
            raise ValueError('Hardware excerpt or comparison receipt changed')
        sr, reference = assess.read_audio(base/'hardware-excerpt-raw.wav')
        start, end = case['evaluation_samples']
        lag = case['calibration']['candidate_lag_samples']
        gain = case['calibration']['candidate_gain']
        reference = reference[start:end]
        candidates = {}
        for name in MODELS:
            if sha(folder/(name+'.wav')) != case['models'][name]['wav_sha256']:
                raise ValueError('Candidate changed')
            rate, y = assess.read_audio(folder/(name+'.wav'))
            if rate != sr:
                raise ValueError('Rate mismatch')
            candidates[name] = y[start+lag:end+lag]*gain
        supplementary = reference_mask_diagnostics(reference, candidates, sr)
        rows.append(dict(id=case['id'], calibration=case['calibration'], evaluation_samples=[start, end],
            models={name: dict(primary=case['models'][name]['measurements']['summary'],
                candidate_gain_sensitivity=case['models'][name]['candidate_prefix_gain_sensitivity']['summary'],
                reference_activity_sensitivity=supplementary[name]) for name in MODELS}))
        if case['id'] in ('class-a-nominal', 'ambient-sqr-nominal-v100'):
            ax = axes[0, 0 if case['id']=='class-a-nominal' else 1]
            for name, y, color in [('Original recording', reference, '#242c30')]+[
                    (name, candidates[name], color) for name, color in zip(MODELS, COLORS)]:
                env = assess.rms_envelope(y, 441, 110)
                t = (start+220+np.arange(len(env))*110)/sr
                ax.plot(t, 20*np.log10(np.maximum(env, 1e-8)), label=name, color=color, lw=1.3)
            ax.set(title=case['id'], xlabel='Original recording time (s)', ylabel='10 ms RMS (dBFS)')
            ax.legend(fontsize=8)
    for col, prefix in enumerate(('class-a-', 'ambient-')):
        group = [c for c in rows if c['id'].startswith(prefix)]
        ax = axes[1, col]
        for name, color in zip(MODELS, COLORS):
            ax.plot(range(len(group)), [c['models'][name]['primary']['spectral_convergence_mean'] for c in group],
                    'o-', color=color, label=name)
        ax.set_xticks(range(len(group)), [c['id'].removeprefix(prefix).replace('sqr-', '') for c in group],
                      rotation=35, ha='right', fontsize=8)
        ax.set(ylabel='Unmasked spectral convergence (lower is closer)', xlabel='All frozen reconstruction scenarios')
        ax.legend(fontsize=8)
    for ax in axes.flat:
        ax.grid(alpha=.16)
    fig.suptitle('Two new public presets: smaller spectral residuals, unresolved tail errors\n'
                 'One production-prefix gain and delay per scenario, shared by all three models', fontsize=13)
    fig.savefig(args.output/'new-reverb-validation.png', dpi=150)
    plt.close(fig)
    summary = dict(status='conditional_comparison_not_equivalence', source_results_sha256=sha(args.run/'results.json'),
        tool_sha256=sha(__file__), assessment_tool_sha256=sha(Path(assess.__file__)),
        scope='Twelve scenarios from TWO independent recordings, not twelve independent validations. No best-scenario selection.',
        post_score_sensitivity='Reference-only activity masks keep identical bins across models. This excludes candidate-only energy, retained by unmasked primary spectral convergence.',
        results=rows)
    (args.output/'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
    table=['| Frozen scenario | SC 1 / 0.5 / 0.25 | Log error dB 1 / 0.5 / 0.25 | Envelope P95 dB 1 / 0.5 / 0.25 | Lag ms |',
           '|---|---|---|---|---|']
    for row in rows:
        groups=[]
        for key in ('spectral_convergence_mean', 'log_spectral_error_db_mean', 'envelope_error_db_p95_max'):
            groups.append(' / '.join(f'{row["models"][name]["primary"][key]:.3f}' for name in MODELS))
        boundary=' (bound)' if row['calibration']['alignment_at_search_boundary'] else ''
        table.append(f'| {row["id"]} | '+ ' | '.join(groups)+f' | {1000*row["calibration"]["candidate_lag_seconds"]:.2f}{boundary} |')
    (args.output/'table.md').write_text('\n'.join(table)+'\n')
    print(args.output/'summary.json')


if __name__ == '__main__':
    main()
