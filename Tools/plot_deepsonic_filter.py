#!/usr/bin/env python3
"""Plot the dry SH-201 filter-shape audit, without embedding original audio."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    data = json.loads(args.results.read_text())
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    for ax, slope in zip(axes, (12, 24)):
        for name, label, color, xshift in (
            ('production', 'Previous response', '#a84b42', -.17),
            ('rounded_candidate', 'Damping 1.2', '#197d91', .17),
        ):
            rows = [r for r in data['models'][name]['windows']
                    if r['slope'] == slope and not r['training']
                    and r['shift'] == 0 and r['width'] == .08]
            times = sorted(set(r['on'] for r in rows))
            values = [np.sqrt(np.mean([r['fit_h2_h8_rmse_db']**2
                                      for r in rows if r['on'] == on]))
                      for on in times]
            ax.bar(np.arange(len(times))+xshift, values, .32, color=color, label=label)
            labels = [f"{next(r['note'] for r in rows if r['on'] == on)}\n{on:g}s" for on in times]
        ax.set(xticks=np.arange(len(times)), xticklabels=labels,
               title=f'LP{slope}: notes excluded from damping fit',
               xlabel='MIDI note / onset in original sequence', ylim=(0, 2.05))
        ax.grid(axis='y', alpha=.2)
        ax.set_axisbelow(True)
        ax.legend(frameon=False, fontsize=9)
    axes[0].set_ylabel('H2–H8 relative-amplitude RMSE (dB)')
    fig.suptitle('Dry hardware recordings favor less damping at resonance zero', fontsize=13)
    fig.text(.5, .015, 'One saw; original MIDI; recipe only, no hardware SysEx. '
             'Cutoff fitted per window. This is filter-shape evidence.', ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .055, 1, .94))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=160)


if __name__ == '__main__':
    main()
