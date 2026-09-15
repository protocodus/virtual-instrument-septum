#!/usr/bin/env python3
"""Preserve hardware-qualified alias comparisons and plot their time spread."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def statistics(values):
    x=np.asarray(values)
    return dict(observations=len(values),median=float(np.median(x)),
                rms=float(np.sqrt(np.mean(x*x))),p10=float(np.percentile(x,10)),
                p90=float(np.percentile(x,90))) if len(values) else None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True,help='new directory')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    data=json.loads(args.input.read_text());groups=data['groups']
    compact={k:v for k,v in data.items() if k!='groups'}
    compact.update(summary_tool_sha256=sha(__file__),full_analysis_sha256=sha(args.input),groups=[])
    for group in groups:
        compact['groups'].append({k:v for k,v in group.items() if k!='windows'})
    comparisons=[]
    for model in [g for g in groups if g['id'].startswith('engine')]:
        hardware=next(g for g in groups if g['id']==('hardware-lp24' if model['id'].endswith('lp24') else 'hardware-lp12'))
        eligible={(r['note'],r['parent_harmonic']) for r in hardware['summary']['44100']['repeated_lines']}
        rows=[]
        for window in hardware['windows']:
            candidate=next(w for w in model['windows'] if w['note']==window['note'] and w['offset_seconds']==window['offset_seconds'])
            for line in window['tested_alias_lines']:
                if line['rate_hypothesis_hz']!=44100 or (window['note'],line['parent_harmonic']) not in eligible:continue
                other=next(r for r in candidate['tested_alias_lines'] if r['rate_hypothesis_hz']==44100 and r['parent_harmonic']==line['parent_harmonic'])
                rows.append(dict(note=window['note'],offset_seconds=window['offset_seconds'],
                    parent_harmonic=line['parent_harmonic'],frequency_hz=line['expected_hz'],
                    hardware_peak_hz=line['peak_hz'],hardware_db=line['relative_h1_db'],
                    hardware_background_db=line['local_median_relative_h1_db'],
                    model_peak_hz=other['peak_hz'],model_db=other['relative_h1_db'],
                    model_background_db=other['local_median_relative_h1_db'],
                    model_local_prominence_db=other['local_prominence_db'],
                    model_interior_peak=other['genuine_interior_local_peak'],
                    model_resolved_above_background=bool(other['genuine_interior_local_peak'] and other['local_prominence_db']>=12),
                    model_passes_threshold=other['passes_line_threshold'],
                    model_minus_hardware_db=other['relative_h1_db']-line['relative_h1_db'],
                    below_two_fundamentals=bool(line['expected_hz']<2*window['nominal_fundamental_hz'])))
        comparisons.append(dict(id=model['id'],hardware_qualified_line_windows=len(rows),
            model_minus_hardware_db=statistics([r['model_minus_hardware_db'] for r in rows]),
            low_alias_bins_model_minus_hardware_db=statistics([r['model_minus_hardware_db'] for r in rows if r['below_two_fundamentals']]),
            interpretation='Fixed predicted-bin residual levels. A model line below -75dBc can still be resolved above its much lower PCM background; separate flags preserve this distinction. A bin lacking a genuine local peak or12dB prominence is a residual upper-bound proxy, not a precise oscillator-line amplitude.',
            measurements=rows))
    compact['engine_comparisons']=comparisons
    diagnostics=[]
    for hardware in groups[:2]:
        frequencies=[];prominences=[];background=[];other=[];count={}
        for window in hardware['windows']:
            for line in window['tested_alias_lines']:
                if line['rate_hypothesis_hz']==44100 and line['passes_line_threshold']:
                    frequencies.append(abs(line['peak_error_hz']));prominences.append(line['local_prominence_db'])
                    background.append(line['local_median_relative_h1_db'])
            for peak in window['diagnostic_nonharmonic_peaks']:
                base=window['nominal_fundamental_hz'];f=peak['frequency_hz']
                candidates=[]
                for sign in (-1,1):
                    h=round((44100+sign*f)/base);pred=sign*(h*base-44100)
                    candidates.append((abs(f-pred),sign,h))
                error,sign,h=min(candidates)
                key=('Fs-h*f0' if sign==-1 else 'h*f0-Fs') if error<=6 else 'outside_first_44100_branches'
                count[key]=count.get(key,0)+1
                if error>6:
                    other.append(dict(note=window['note'],offset_seconds=window['offset_seconds'],**peak,
                                      nearest_44100_branch_error_hz=error,
                                      half_fundamental_hz=base/2))
        diagnostics.append(dict(id=hardware['id'],detected_44100_peak_absolute_error_hz=statistics(frequencies),
            detected_44100_local_prominence_db=statistics(prominences),
            detected_44100_background_relative_h1_db=statistics(background),
            strongest_12_residual_peaks_per_window_classification=count,
            outside_first_branch_peaks=other))
    compact['hardware_diagnostics']=diagnostics
    # Positive recovery error measures the analysis/codec check, not uncertainty
    # of hardware line amplitudes or of the unknown original encoder.
    compact['injected_recovery']=[]
    for group in groups:
        if not group['id'].startswith('injected'):continue
        errors=[]
        injected={(r['note'],r['parent_harmonic']) for r in group['injections']}
        for window in group['windows']:
            errors.extend(r['relative_h1_db']+60 for r in window['tested_alias_lines']
                          if r['rate_hypothesis_hz']==44100 and (window['note'],r['parent_harmonic']) in injected)
        compact['injected_recovery'].append(dict(id=group['id'],amplitude_error_db=statistics(errors),
                                                max_abs_error_db=float(np.max(np.abs(errors)))))
    (out/'results.json').write_text(json.dumps(compact,indent=2)+'\n')
    fig,axes=plt.subplots(1,3,figsize=(14,4.5),layout='constrained',sharey=True)
    hardware=groups[0]
    for ax,note in zip(axes,(69,84,93)):
        eligible={r['parent_harmonic'] for r in hardware['summary']['44100']['repeated_lines'] if r['note']==note}
        for identifier,label,color,style in (('hardware-lp12','Hardware LP12','#1464a0','-'),
                 ('engine-production-lp12','Production','#b23b35','-'),
                 ('engine-dry-hz-35ms-lp12','Frozen Hz fixture','#dd9022','--')):
            group=next((g for g in groups if g['id']==identifier),None)
            if group is None:continue
            rows=[w for w in group['windows'] if w['note']==note]
            lines=[]
            for h in eligible:
                measured=[r for w in rows for r in w['tested_alias_lines'] if r['rate_hypothesis_hz']==44100 and r['parent_harmonic']==h]
                if measured:lines.append((measured[0]['expected_hz'],min(r['relative_h1_db'] for r in measured),max(r['relative_h1_db'] for r in measured)))
            lines=np.array(sorted(lines));select=lines[:,0]<=8000;lines=lines[select]
            ax.plot(lines[:,0],lines[:,1:3].mean(axis=1),label=label,color=color,ls=style,lw=1.8)
            ax.fill_between(lines[:,0],lines[:,1],lines[:,2],color=color,alpha=.16)
        ax.set(title=f'MIDI {note}',xlabel='Predicted 44.1 kHz fold frequency (Hz)',xlim=(300,8000),ylim=(-110,-38))
        ax.grid(alpha=.18)
    axes[0].set_ylabel('Residual line level relative to H1 (dB)')
    axes[0].legend(fontsize=8,loc='lower right')
    fig.suptitle('Classic Saw: hardware-qualified lines; shaded ranges span the two fixed time windows',fontsize=11)
    fig.savefig(out/'alias-comparison.png',dpi=160);plt.close(fig)
    print(json.dumps(dict(comparisons=[{k:v for k,v in c.items() if k!='measurements'} for c in comparisons],
                         diagnostics=diagnostics,injected_recovery=compact['injected_recovery']),indent=2))


if __name__=='__main__':main()
