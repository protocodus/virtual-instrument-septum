#!/usr/bin/env python3
"""Audit SupaJuce filter-envelope brightness against the public hardware demo.

Only first-note frames estimate coefficients. Other notes retain the same
cutoff equation, envelope, key tracking and source law; no held-out fc is fitted
when scoring those predictions. Per-frame cutoff inversions are diagnostics.
Neither shipping sources nor presets are modified by this script.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

from analyze_supajuce_resonance import (
    H, SR, fit_window, harmonics, identity, observations, predict, read_audio,
)


ATTACK = .001 * 5000**(3/127)
SUSTAIN = 74/127
POWER = np.log((.4189852819747085-.002)/(12-.002))/np.log(49/127)
DURATION = .002 + (12-.002)*(61/127)**POWER
DAMPING = 2*((2-2.04*np.sqrt(40/127))*.5)**1.5


def cutoff(row, coefficient=10., duration=DURATION):
    """Continuous counterpart of the current held-note filter control law."""
    elapsed = row['elapsed']
    envelope = min(elapsed/ATTACK, 1.) if elapsed < ATTACK else max(
        SUSTAIN, 1-(elapsed-ATTACK)*(1-SUSTAIN)/duration)
    octave = np.log2(20) + 27*10/127 + .5*(row['played_note']-60)/12
    return float(np.clip(2**(octave + envelope*31/63*coefficient), 5, .45*SR))


def extended_observations(path, notes, latency=0):
    rows = observations(path, notes, latency)
    audio = read_audio(path).mean(axis=1)
    anchor = next(r for r in rows if r['note'] == 4)
    for elapsed in (.125, .175, .200, .225, .300, .400, .500):
        row = dict(anchor, elapsed=elapsed, center=notes[4]['on']+elapsed+latency)
        rows.append(row | harmonics(audio, row['center'], row['width'], row['frequency']))
    return sorted(rows, key=lambda r: (r['note'], r['elapsed']))


def ratios(row, coefficient, duration):
    return predict(row, cutoff(row, coefficient, duration), DAMPING, 'lp24_equal')


def equation_fit(rows, fit_duration=False):
    train = [r for r in rows if r['note'] == 0 and r['elapsed'] <= .100]
    def objective(v):
        return np.concatenate([ratios(r, v[0], np.exp(v[1]) if fit_duration else DURATION)
            - np.array(r['harmonic_ratio_db']) for r in train])
    fit = least_squares(objective, [12., np.log(DURATION)] if fit_duration else [12.],
        bounds=([6., np.log(.05)], [18., np.log(5.)]) if fit_duration else ([6.], [18.]))
    return dict(coefficient=float(fit.x[0]),
                decay_seconds=float(np.exp(fit.x[1])) if fit_duration else float(DURATION))


def summary(errors):
    return dict(early_rms_db_by_note={str(n):float(np.sqrt(np.mean([
            np.array(r['errors_db'])**2 for r in errors
            if r['note']==n and r['elapsed'] <= .100]))) for n in range(6)},
        long_note_frames=[r for r in errors if r['note']==4 and r['elapsed']>.100])


def equation_score(rows, coefficient, decay_seconds=DURATION):
    errors = []
    for r in rows:
        e = ratios(r, coefficient, decay_seconds)-np.array(r['harmonic_ratio_db'])
        errors.append(dict(note=r['note'], elapsed=r['elapsed'],
            cutoff_hz=cutoff(r, coefficient, decay_seconds), errors_db=e.tolist(),
            rms_db=float(np.sqrt(np.mean(e*e)))))
    return dict(coefficient=float(coefficient), decay_seconds=float(decay_seconds),
                **summary(errors), frames=errors)


def render_score(hardware, rendered):
    if [(r['note'],r['elapsed']) for r in hardware] != [(r['note'],r['elapsed']) for r in rendered]:
        raise ValueError('Mismatched analysis windows')
    errors = []
    for hw, sw in zip(hardware, rendered):
        e = np.array(sw['harmonic_ratio_db'])-np.array(hw['harmonic_ratio_db'])
        errors.append(dict(note=hw['note'], elapsed=hw['elapsed'], errors_db=e.tolist(),
                           rms_db=float(np.sqrt(np.mean(e*e)))))
    return dict(**summary(errors), frames=errors)


def inversions(rows):
    out = []
    for row in rows:
        fitted = fit_window(row, 'lp24_equal', fixed_damping=DAMPING)
        base = np.log2(20) + 27*10/127 + .5*(row['played_note']-60)/12
        envelope = max(SUSTAIN, 1-(row['elapsed']-ATTACK)*(1-SUSTAIN)/DURATION)
        implied = (np.log2(fitted['cutoff_hz'])-base)*63/(31*envelope)
        out.append(dict(note=row['note'], elapsed=row['elapsed'],
            implied_coefficient=float(implied), **fitted))
    return out


def plot(result, path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    for ax, note in zip(axes[:2], (0, 4)):
        rows = [r for r in result['cutoff_inversions'] if r['note']==note]
        for good in (True, False):
            points = [r for r in rows if (r['rms_db'] <= 3)==good]
            ax.scatter([r['elapsed']*1000 for r in points], [r['cutoff_hz'] for r in points],
                       c='black' if good else '.6', marker='o' if good else 'x',
                       label='Hardware inversion' if good else 'Poor LPF fit (>3 dB RMS)')
        for coefficient, color in ((10, 'C0'), (12, 'C1')):
            times = np.linspace(.025, .11 if note==0 else .52, 160)
            pitch = result['notes'][note]['note']
            ax.plot(times*1000, [cutoff(dict(elapsed=t, played_note=pitch), coefficient)
                                for t in times], c=color, label=f'Depth coefficient {coefficient}')
        ax.set(title=f'Note {note+1}: {"training" if note==0 else "held-out long note"}',
               xlabel='Time after estimated onset (ms)', ylabel='Cutoff (Hz)', ylim=(2000,10000))
        ax.grid(alpha=.2)
    axes[0].legend(fontsize=7)
    ax = axes[2]
    for key, color in (('10','C0'), ('12','C1'), ('14','C2')):
        entry = result['rendered_candidates'][key]
        ax.plot(np.arange(1,7), list(entry['score']['early_rms_db_by_note'].values()),
                'o-', color=color, label=f'Depth coefficient {key}')
    ax.set(title='Actual renders: upper-square ratios', xlabel='Note (only note 1 trained)',
           ylabel='H6–H30 / H2 RMS error (dB)', xticks=np.arange(1,7))
    ax.grid(alpha=.2)
    ax.legend(fontsize=7)
    fig.suptitle('SupaJuce 1: envelope depth corrects the early peak; late motion remains uncertain')
    fig.tight_layout()
    fig.savefig(path, dpi=170)
    plt.close(fig)


def harmonic_panels(result):
    panels = []
    for note, elapsed, title in ((0,.070,'First note · 70 ms'),
                                (4,.150,'Held-out D · 150 ms'),
                                (4,.250,'Held-out D · 250 ms')):
        hardware = next(r for r in result['hardware_observations']
                        if r['note']==note and r['elapsed']==elapsed)
        panel = dict(note=note, elapsed=elapsed, title=title,
            harmonic_indices=H.tolist(), frequency_hz=(H*hardware['frequency']).tolist(),
            hardware_ratio_db=[0.]+hardware['harmonic_ratio_db'],
            normalization='Each signal divided by its own H2 amplitude; no EQ or other gain fit.')
        for coefficient in ('10','12'):
            rendered = next(r for r in result['rendered_candidates'][coefficient]['observations']
                            if r['note']==note and r['elapsed']==elapsed)
            panel[f'depth{coefficient}_ratio_db'] = [0.]+rendered['harmonic_ratio_db']
        panels.append(panel)
    return panels


def plot_harmonics(panels, path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1,3,figsize=(12,4),sharey=True)
    for ax, panel in zip(axes,panels):
        for field, label, color, marker in (
                ('hardware_ratio_db','Roland hardware','#222222','o'),
                ('depth10_ratio_db','Before · depth coefficient 10','#3579ad','x'),
                ('depth12_ratio_db','Candidate · depth coefficient 12','#db7830','s')):
            ax.plot(np.array(panel['frequency_hz'])/1000, panel[field], color=color,
                    marker=marker, markersize=4, linewidth=1.5, label=label)
        ax.set(title=panel['title'],xlabel='Upper-square harmonic frequency (kHz)',ylim=(-70,8))
        ax.grid(alpha=.18)
    axes[0].set_ylabel('Amplitude relative to H2 (dB)')
    axes[0].legend(fontsize=8,loc='lower left')
    axes[2].text(.97,.94,'Late hardware notches remain\nDelay/reverb enabled',
                 transform=axes[2].transAxes,ha='right',va='top',fontsize=8)
    fig.suptitle('SupaJuce 1 · original published preset, reconstructed MIDI\n'
                 'Measured H2, H6, …, H30; each signal normalized only to its H2 amplitude',fontsize=11)
    fig.tight_layout()
    path.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(path,dpi=180)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidates', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--harmonic-figure', type=Path)
    args = parser.parse_args()
    base = args.candidates/'depth-10/supa-juce-1'
    manifest = json.loads((base/'comparison.json').read_text())
    notes = manifest['case']['notes']
    hardware_path = base/'hardware-decoded-full.wav'
    rows = extended_observations(hardware_path, notes)
    decoded_patch = dict(cutoff=27, resonance=40, keyfollow=50, cutoff_velocity=0,
        depth=31, attack=3, decay=61, sustain=74, release=63,
        amp_release=0, delay=True, reverb=True, slope_db=24)
    one = equation_fit(rows)
    two = equation_fit(rows, True)
    candidates = {}
    for coefficient in (10,12,14):
        directory = args.candidates/f'depth-{coefficient}/supa-juce-1'
        comparison = json.loads((directory/'comparison.json').read_text())
        for filename in ('original-patch.syx', 'reconstructed-performance.mid', 'hardware-decoded-full.wav'):
            if identity(directory/filename)['sha256'] != identity(base/filename)['sha256']:
                raise ValueError(f'Candidate changed shared input: {filename}')
        path = directory/'septum-raw.wav'
        measured = extended_observations(path, notes, comparison['retained_engine_latency_samples']/SR)
        profile_path = args.candidates.parent/'renderers'/f'depth-{coefficient}'/'profile.json'
        candidates[str(coefficient)] = dict(input=identity(path), comparison=identity(directory/'comparison.json'),
            score=render_score(rows, measured), observations=measured,
            renderer_profile=identity(profile_path) if profile_path.exists() else None,
            production_cutoff_recovery=[dict(note=r['note'], elapsed=r['elapsed'],
                **fit_window(r, 'lp24_equal', fixed_damping=DAMPING, source='polyblep'))
                for r in measured if r['note']==0])
    inverted = inversions(rows)
    reference_cutoff = next(r['cutoff_hz'] for r in inverted if r['note']==0 and r['elapsed']==.070)
    keyfollow_checks = []
    for note in range(1,6):
        inferred = next(r['cutoff_hz'] for r in inverted if r['note']==note and r['elapsed']==.070)
        distance = notes[note]['note']-notes[0]['note']
        keyfollow_checks.append(dict(note=note, midi_distance=distance,
            observed_cutoff_ratio=inferred/reference_cutoff,
            current_predicted_ratio=2**(.5*distance/12),
            apparent_keyfollow_percent=float(100*12*np.log2(inferred/reference_cutoff)/distance)))
    slopes = {}
    for n in range(6):
        subset = [r for r in inverted if r['note']==n and r['elapsed']<=.100]
        slope, intercept = np.polyfit([r['elapsed'] for r in subset],
                                      np.log2([r['cutoff_hz'] for r in subset]), 1)
        slopes[str(n)] = dict(octaves_per_second=float(slope), extrapolated_peak_hz=float(2**intercept))
    sensitivity = []
    for width, channel in ((.02,'mean'),(.04,'mean'),(.03,'0'),(.03,'1')):
        alternate = observations(hardware_path, notes[:1], width=width, channel=channel)
        sensitivity.append(dict(width=width, channel=channel, **equation_fit(alternate)))
    onset_sensitivity = []
    for offset in (-.015, .015):
        # Keep the measured audio and its physical center fixed; vary only the
        # unknown note age supplied to the envelope equation.
        alternate = [dict(r, elapsed=r['elapsed']+offset) for r in rows if r['note']==0]
        # Keep all five original training observations when testing their age.
        def residual(v):
            return np.concatenate([ratios(r,v[0],DURATION)-np.array(r['harmonic_ratio_db']) for r in alternate])
        fitted = least_squares(residual, [12.], bounds=([6.],[18.]))
        onset_sensitivity.append(dict(note_age_offset_seconds=offset, coefficient=float(fitted.x[0])))
    result = dict(schema_version=1, status='conditional empirical envelope-depth audit; no shipping edits',
        reference=manifest['reference'], bank=manifest['bank'], notes=notes, decoded_patch=decoded_patch,
        inputs=dict(hardware=identity(hardware_path), patch=identity(base/'original-patch.syx'),
                    reconstructed_midi=identity(base/'reconstructed-performance.mid')),
        analysis=dict(harmonics=H.tolist(), anchor=2, sample_rate=SR, window_seconds=.03,
            current_damping=float(DAMPING), second_stage='same damping; current floor .5 inactive at resonance40',
            source='ideal square amplitude1/n, no per-harmonic offsets or gain fit',
            training='Only first note 40/55/70/85/100ms. Other notes freeze the entire fitted control law.',
            decay_seconds=float(DURATION), attack_seconds=float(ATTACK), sustain=float(SUSTAIN)),
        hardware_observations=rows, cutoff_inversions=inverted,
        keyfollow_same_age_diagnostic=keyfollow_checks,
        equation_candidates={str(c):equation_score(rows,c) for c in (10,12,14)},
        first_note_depth_only_fit=one | dict(score=equation_score(rows, **one)),
        first_note_depth_and_duration_diagnostic=two | dict(score=equation_score(rows, **two)),
        early_inferred_log_cutoff_slopes=slopes,
        current_log_cutoff_slope_octaves_per_second=float(-31*10/63*(1-SUSTAIN)/DURATION),
        coefficient12_log_cutoff_slope_octaves_per_second=float(-31*12/63*(1-SUSTAIN)/DURATION),
        rendered_candidates=candidates, width_channel_sensitivity=sensitivity,
        onset_age_sensitivity=onset_sensitivity,
        sustain_release_limits=dict(longest_note_seconds=notes[4]['off']-notes[4]['on'],
            current_time_to_sustain_seconds=float(ATTACK+DURATION),
            amp_release60db_seconds=.002,
            conclusion='No note lasts until the current filter sustain plateau. Amp release0 silences dry sound in ~2ms, so subsequent filter-release shape is not observable independently of wet effects.'),
        identifiability=[
            'At depth31, coefficient12 means5.90476 peak octaves. It does not measure the full-scale endpoint or intermediate/negative depth taper.',
            'Under an exponential cutoff map, adding raw cutoff units and adding octaves are exactly equivalent after a scalar conversion; these data cannot identify the implementation domain.',
            'A constant base-cutoff shift, keyfollow-pivot shift and depth offset are confounded within one depth31 patch. Cross-patch evidence is needed; this fit retains the existing base map and pivot60.',
            'Held-out note scores here freeze cutoff, depth, timing and keyfollow. Per-frame inversions reported separately are diagnostics, not held-out predictions.',
            'Later long-note isolated harmonic notches violate this smooth LPF family; enabled delay/reverb can interfere with decaying dry harmonics.',
            'Original MIDI, overlap, velocity, controllers, global tuning, capture processing and precise recorded patch revision remain unknown. Onsets are reconstructed and windows overlap.',
            'Coefficient-only and coefficient+duration fits diagnose the same first-note data. A better two-parameter fit is not independent evidence for a new decay map.',
            'The TPT warping and ideal square source are assumptions about hardware. Previous resonance audit documents analog-warp and polyBLEP sensitivity.',
            'Candidate comparison manifests hash the contemporaneous shipping sources; renderer profile source_sha256 records the exact modified experiment source.'],
        tools=dict(script=identity(Path(__file__)), harmonic_helper=identity(Path(__file__).with_name('analyze_supajuce_resonance.py'))))
    result['harmonic_figure_panels'] = harmonic_panels(result)
    if args.harmonic_figure:
        plot_harmonics(result['harmonic_figure_panels'],args.harmonic_figure)
        result['harmonic_figure'] = identity(args.harmonic_figure)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    plot(result,args.output.with_suffix('.png'))
    print('depth-only',one,'depth+duration diagnostic',two)
    print('sensitivity',sensitivity,onset_sensitivity)
    for coefficient, candidate in candidates.items():
        print('render',coefficient,candidate['score']['early_rms_db_by_note'])
        print('long note',[(r['elapsed'],round(r['rms_db'],2)) for r in candidate['score']['long_note_frames']])


if __name__ == '__main__':
    main()
