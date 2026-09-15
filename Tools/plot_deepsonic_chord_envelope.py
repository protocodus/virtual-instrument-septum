#!/usr/bin/env python3
"""Plot frozen cutoff curves and independent late-chord holdouts."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from analyze_deepsonic_chord_envelope import prediction


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=json.loads(args.results.read_text())
    rows=[r for r in result['observations'] if r['valid'] and r['width']==.08]
    parameters=result['frozen_parameters']
    names={'exponential_log_cutoff':'Exponential in log cutoff',
           'exponential_hz_with_floor':'Exponential in Hz + floor'}
    colors={'exponential_log_cutoff':'#b24a25','exponential_hz_with_floor':'#167c80'}
    fig,axes=plt.subplots(1,2,figsize=(11.5,4.7),gridspec_kw={'width_ratios':[1,1.2]})
    time=np.linspace(.1,.665,500)
    for name,p in parameters.items():
        axes[0].plot(time,[prediction(name,p,t) for t in time],label=names[name],color=colors[name],lw=2)
    axes[0].axvspan(.1,.34,color='#dde3e8',alpha=.7,label='Original fitting interval')
    for slope,marker,color in ((12,'o','#174976'),(24,'s','#8c4075')):
        group=[r for r in rows if r['slope']==slope]
        axes[0].scatter([r['offset'] for r in group],[r['cutoff_over_f0'] for r in group],
                        s=24,marker=marker,color=color,label=f'LP{slope} chord holdouts',zorder=3)
    axes[0].set(xlabel='Seconds after MIDI note-on',ylabel='Cutoff / target note frequency',
                title='Parameters frozen from the first single note',xlim=(.08,.68),ylim=(1,6.6))
    axes[0].legend(frameon=False,fontsize=8,loc='upper right')
    late=np.linspace(.42,.655,200)
    log_curve=parameters['exponential_log_cutoff']
    hz_curve=parameters['exponential_hz_with_floor']
    axes[1].plot(late,[1200*np.log2(prediction('exponential_log_cutoff',log_curve,t)/
                      prediction('exponential_hz_with_floor',hz_curve,t)) for t in late],
                 color=colors['exponential_log_cutoff'],lw=2,label='Frozen log-cutoff curve')
    axes[1].axhline(0,color=colors['exponential_hz_with_floor'],lw=2,label='Frozen Hz + floor curve')
    for slope,marker,color,jitter in ((12,'o','#174976',-.002),(24,'s','#8c4075',.002)):
        group=[r for r in rows if r['slope']==slope]
        residual=[-r['frozen_model_predictions']['exponential_hz_with_floor']['error_cents'] for r in group]
        axes[1].scatter([r['offset']+jitter for r in group],residual,
                        s=35,marker=marker,color=color,label=f'LP{slope} measured chords',zorder=3)
    axes[1].set(xlabel='Seconds after MIDI note-on',ylabel='Cents relative to frozen Hz + floor curve',
                title='Later measurements separate the two curves',xlim=(.42,.655),ylim=(-220,110))
    axes[1].legend(frameon=False,fontsize=8,loc='lower left')
    for ax in axes:
        ax.spines[['top','right']].set_visible(False)
        ax.grid(axis='y',alpha=.18)
    fig.suptitle('SH-201 dry Q0 recording: isolated E harmonics inside held C-major chords',fontsize=12)
    fig.text(.5,.015,'24 accepted 80 ms windows · Four chords in two octaves · No curve refitting · Cutoff cents are not audio-equivalence scores',
             ha='center',fontsize=8,color='#555555')
    fig.tight_layout(rect=(0,.045,1,.94))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(args.output,dpi=180)


if __name__=='__main__':main()
