#!/usr/bin/env python3
"""Retain compact invariance evidence and visualize qualified slope changes."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compact_window(row):
    result={k:v for k,v in row.items() if k not in ('harmonics','harmonic_amplitudes','relative_h1_db','saw_slope_removed_db','coefficient_snr_proxy_db')}
    for field in ('harmonic_amplitudes','relative_h1_db','saw_slope_removed_db','coefficient_snr_proxy_db'):
        result[field+'_h1_h8']=row[field][:8]
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--invariance',type=Path,required=True)
    parser.add_argument('--q50',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True,help='new directory')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    j=json.loads(args.invariance.read_text());q=json.loads(args.q50.read_text())
    result={k:v for k,v in j.items() if k not in ('hardware','controls')}
    result.update(summary_tool_sha256=sha(__file__),full_invariance_sha256=sha(args.invariance),full_q50_sha256=sha(args.q50))
    result['hardware']={k:v for k,v in j['hardware'].items() if k!='windows'}
    result['hardware']['windows_h1_h8']=[compact_window(r)for r in j['hardware']['windows']]
    result['controls']=[]
    for c in j['controls']:
        small={k:v for k,v in c.items() if k!='windows'}
        if c['id'].startswith('invariant'):
            errors=[]
            for r in c['windows']:
                if r['purpose']=='invariance' and r['frequency_policy']=='frozen_refined':
                    errors.extend((np.array(r['saw_slope_removed_db'][:8])-np.array([0,-1,-3,-6,-17,-23,-13,-16])).tolist())
            small['known_shape_recovery_all_h1_h8']=dict(observations=len(errors),
                rms_error_db=float(np.sqrt(np.mean(np.square(errors)))),max_abs_error_db=float(np.max(np.abs(errors))))
        result['controls'].append(small)
    result['q50']={k:v for k,v in q.items() if k!='harmonic_windows'}
    result['q50']['harmonic_windows_h1_h8']=[compact_window(r)for r in q['harmonic_windows']]
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
    for note,color in ((69,'#8c564b'),(84,'#9467bd'),(86,'#2ca02c'),(88,'#ff7f0e'),(91,'#1464a0'),(93,'#d62728')):
        s=next(s for s in j['hardware']['note_summaries']if s['note']==note)
        rows=[r for r in s['slope_divergence']if r['frequency_policy']=='frozen_refined']
        for ax in axes:
            ax.grid(alpha=.2)
        valid=[r for r in rows if r['common_harmonics_still_eligible']]
        axes[0].plot([r['offset_seconds']for r in valid],[r['rms_db']for r in valid],'.-',color=color,label=str(note))
        # Fixed H2..H4 stay reliable farther into the falling filter.
        valid=[r for r in rows if r['fixed_h2_h4_still_eligible']]
        axes[1].plot([r['offset_seconds']for r in valid],[r['fixed_h2_h4']['rms_db']for r in valid],'.-',color=color,label=str(note))
    axes[0].set(title='Q0: qualified H2–H8',xlabel='Seconds after original MIDI onset',ylabel='LP24 vs LP12 normalized-harmonic RMS difference (dB)',yscale='log',ylim=(.005,20))
    axes[1].set(title='Q0: fixed H2–H4',xlabel='Seconds after original MIDI onset',yscale='log',ylim=(.001,10))
    axes[0].legend(title='Played MIDI',ncol=2,fontsize=8)
    fig.suptitle('40 ms windows: early convergence ends at different times for different pitches',fontsize=11)
    fig.savefig(out/'invariance.png',dpi=160);plt.close(fig)
    print('Preserved source/control identities, H1–H8 observations, and Q50 contrary evidence.')


if __name__=='__main__':main()
