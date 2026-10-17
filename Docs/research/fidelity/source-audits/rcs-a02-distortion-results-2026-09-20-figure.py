#!/usr/bin/env python3
"""Render the retained A02 diagnostic summary without third-party media."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch


def main():
    stem = Path(__file__).with_name('rcs-a02-distortion-results-2026-09-20')
    data = json.loads(stem.with_suffix('.json').read_text())['figure_data']
    rows = data['rows']
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'svg.hashsalt': 'rcs-a02-distortion-2026-09-20'})
    fig, axes = plt.subplots(1, 2, figsize=(13.4, 12.3), sharey=True)
    colors = {-22: '#176D9C', -32: '#BF681C', 'phase': '#596475'}
    y_positions = [i if i < 12 else i+1.1 for i in range(len(rows))]
    for ax, metric, title in zip(axes, ('h3_h2_db', 'h4_h2_db'), ('Third / second harmonic', 'Fourth / second harmonic')):
        hardware = data['hardware'][metric]
        ax.axvspan(hardware['min'], hardware['max'], color='#009E73', alpha=.17, zorder=0)
        ax.axvline(hardware['median'], color='#008B66', linewidth=1.4, zorder=1)
        for y, row in zip(y_positions, rows):
            stats = row[metric]
            color = colors[row['depth']] if row['group'] == 'mechanism' else colors['phase']
            ax.plot([stats['min'], stats['max']], [y, y], color=color, linewidth=2.4, solid_capstyle='round', zorder=2)
            ax.plot(stats['median'], y, marker='o', color=color, markersize=5.4, zorder=3)
        ax.axhline(11.85, color='#CBD0D6', linewidth=.9)
        ax.set_title(title, fontsize=12, weight='bold', pad=13)
        ax.set_xlabel(metric.upper().replace('_DB', '').replace('_', '/')+' amplitude ratio (dB)', labelpad=10)
        ax.set_xlim(-28, 0)
        ax.set_xticks(range(-25, 1, 5))
        ax.grid(axis='x', alpha=.19)
        ax.set_ylim(y_positions[-1]+.9, -1)
        ax.tick_params(axis='y', length=0, pad=10)
    axes[0].set_yticks(y_positions, [r['label'] for r in rows])
    axes[0].text(-28, 12.45, 'Separate phase screen: original preset / current attack',
                 fontsize=9, weight='bold', color='#424D59', va='center')
    fig.suptitle('RCS A02: late harmonic shape remains a diagnostic, not a match',
                 fontsize=16, weight='bold', x=.50, y=.967)
    fig.text(.5, .934, '24 distortion cells and 8 fixed pulse phases · same author performance · no fitted gain or alignment',
             ha='center', fontsize=11, color='#46515E')
    handles = [Patch(facecolor='#009E73', alpha=.22, edgecolor='none', label='Hardware observed range'),
               Line2D([], [], marker='o', color=colors[-22], label='Published depth −22', linewidth=2),
               Line2D([], [], marker='o', color=colors[-32], label='Temporary depth −32', linewidth=2),
               Line2D([], [], marker='o', color=colors['phase'], label='Phase nuisance check', linewidth=2)]
    fig.legend(handles=handles, loc='lower center', bbox_to_anchor=(.52, .125), ncol=2,
               frameon=False, fontsize=10, columnspacing=2.6, handlelength=2)
    fig.text(.08, .091,
             'Dots: medians. Bars: minimum–maximum across eight fixed late-note windows; not confidence intervals.\n'
             'Mechanism rows pool current and 100 ms attacks (16 observations). Hardware pools two encodes × three channels\n'
             'of one performance (48 observations). H2 normalization assumes a clean Lower sine and linear output summation.',
             fontsize=9.2, va='top', color='#46515E', linespacing=1.45)
    fig.text(.08, .014,
             'Closer late ratios do not repair first-note powers or gate-sensitive closure. No shipping model or phase selected.\n'
             'Source: rcs-a02-distortion-results-2026-09-20.json · fixed windows end before 21.877 s.',
             fontsize=9.2, va='bottom', color='#263440', linespacing=1.45)
    fig.subplots_adjust(left=.325, right=.96, top=.881, bottom=.225, wspace=.14)
    fig.savefig(stem.with_suffix('.png'), dpi=180, metadata={'Software': 'Matplotlib; retained diagnostic data'})
    fig.savefig(stem.with_suffix('.svg'), metadata={'Date': None})
    plt.close(fig)


if __name__ == '__main__':
    main()
