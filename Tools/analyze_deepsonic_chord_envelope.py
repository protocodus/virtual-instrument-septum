#!/usr/bin/env python3
"""Test frozen envelope curves using uncontaminated thirds of long MIDI chords.

Nearby partials are modeled as one nuisance cluster. A clustered target
partial is never used as an isolated target harmonic. No curve parameter,
per-note time shift, source tuning or recording EQ is fitted.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
import numpy as np
from scipy.io import wavfile

from analyze_deepsonic_filter import CATALOG, digest, fit_cutoff, errors, rms
from render_midi import parse_smf

CHORDS = ((22., (60,64,67), 64), (22.75, (48,52,55), 52),
          (24., (60,65,69), 69), (24.75, (48,53,57), 57),
          (26.75, (50,55,59), 59), (28., (60,64,67), 64),
          (28.75, (48,52,55), 52))
OFFSETS = (.46,.54,.62)
WIDTHS = (.06,.08,.10)
MODELS = ('exponential_log_cutoff', 'exponential_hz_with_floor')


def fundamental(note):
    return 440*2**((note-69)/12)


def measure_chord(y, sr, center, width, notes, target, spacing=1.5):
    """Joint clustered quadratures with independent local linear ramps.

    Frequency separation below 1.5/width Hz merges adjacent partials. Each
    merged cluster is only a nuisance component, including when it contains
    a target harmonic. Independent target H1/H2/H3 are required downstream.
    """
    members = sorted([dict(note=n, harmonic=h, frequency_hz=fundamental(n)*h)
                      for n in notes for h in range(1, int(8000/fundamental(n))+1)],
                     key=lambda r:r['frequency_hz'])
    groups = []
    for member in members:
        if groups and member['frequency_hz']-groups[-1][-1]['frequency_hz'] < spacing/width:
            groups[-1].append(member)
        else:
            groups.append([member])
    a, b = round((center-width/2)*sr), round((center+width/2)*sr)
    if a < 0 or b > len(y):
        raise ValueError('Window outside signal')
    x = y[a:b].astype(float)
    t = np.arange(a,b)/sr-center
    u = t/(width/2)
    columns = [np.ones(len(t)),u]
    for group in groups:
        f = np.mean([r['frequency_hz'] for r in group])
        co, si = np.cos(2*np.pi*f*t), np.sin(2*np.pi*f*t)
        columns.extend((co,si,u*co,u*si))
    matrix = np.column_stack(columns)
    coeff, _, _, singular = np.linalg.lstsq(matrix,x,rcond=None)
    condition = float(singular[0]/singular[-1])
    if condition > 100:
        raise ValueError(f'Ill-conditioned chord fit: {condition}')
    residual = x-matrix@coeff
    residual_power = float(np.mean(residual**2)/max(np.var(x),1e-30))
    variance = float(np.sum(residual**2)/(len(x)-len(coeff)))
    inverse_gram = np.linalg.inv(matrix.T@matrix)
    target_rows, contaminated = [], []
    for i, group in enumerate(groups):
        for member in group:
            if member['note'] != target:
                continue
            if len(group) != 1:
                contaminated.append(dict(harmonic=member['harmonic'], members=group))
                continue
            j = 2+4*i
            amplitude = float(np.hypot(coeff[j],coeff[j+1]))
            # Conservative quadrature standard-error proxy. This assumes
            # white residual noise; synthetic and width controls also check
            # deterministic leakage, which this proxy cannot guarantee away.
            uncertainty = float(np.sqrt(variance*(inverse_gram[j,j]+inverse_gram[j+1,j+1])))
            target_rows.append(dict(harmonic=member['harmonic'], amplitude=amplitude,
                                    noise_proxy_amplitude=uncertainty,
                                    snr_proxy_db=float(20*np.log10(amplitude/max(uncertainty,1e-30)))))
    target_rows.sort(key=lambda r:r['harmonic'])
    if not target_rows or target_rows[0]['harmonic'] != 1:
        raise ValueError('Target fundamental is contaminated')
    h = np.array([r['harmonic'] for r in target_rows])
    amplitude = np.array([r['amplitude'] for r in target_rows])
    ratio = 20*np.log10(np.maximum(amplitude,1e-30)/amplitude[0])
    return dict(harmonics=h.tolist(), amplitude=amplitude.tolist(),
                harmonic_ratio_db=ratio.tolist(), saw_slope_removed_db=(ratio+20*np.log10(h)).tolist(),
                fundamental_hz=fundamental(target), snr_proxy_db=[r['snr_proxy_db'] for r in target_rows],
                condition_number=condition, fit_residual_power=residual_power,
                cluster_count=len(groups), modeled_source_partials=len(members),
                contamination_exclusions=contaminated, minimum_cluster_spacing_hz=spacing/width)


def fit_target(row, slope):
    hs = row['harmonics']
    rejected = []
    if row['fit_residual_power'] > .01:
        rejected.append('over_1_percent_unexplained_power')
    for h in (1,2,3):
        if h not in hs:
            rejected.append(f'H{h}_not_isolated')
        elif row['snr_proxy_db'][hs.index(h)] < 20:
            rejected.append(f'H{h}_under_20dB_noise_proxy')
        elif h > 1 and row['harmonic_ratio_db'][hs.index(h)] <= -45:
            rejected.append(f'H{h}_under_relative_floor')
    if rejected:
        return dict(valid=False,rejection=rejected)
    indices = [hs.index(h) for h in (1,2,3)]
    train = {key:[row[key][i] for i in indices] for key in (
        'harmonics','harmonic_ratio_db','saw_slope_removed_db')}
    train['fundamental_hz'] = row['fundamental_hz']
    fitted = fit_cutoff(train,[1.2]*(slope//12))
    step = .001
    derivative = (errors(train,fitted['cutoff_hz']*2**step,[1.2]*(slope//12))-
                  errors(train,fitted['cutoff_hz']*2**-step,[1.2]*(slope//12)))/(2*step)
    sensitivity = float(np.sqrt(np.mean(derivative[1:]**2)))
    # A nearly flat passband can determine harmonic amplitudes accurately
    # while leaving cutoff essentially unidentified. Require useful local
    # response sensitivity before interpreting a cutoff in cents.
    identifiable = sensitivity >= 1.
    full_error = errors(row,fitted['cutoff_hz'],[1.2]*(slope//12))
    upper = [i for i,h in enumerate(hs) if 5 <= h <= 8 and
             row['harmonic_ratio_db'][i] > -45 and row['snr_proxy_db'][i] >= 20]
    return dict(valid=identifiable,rejection=[] if identifiable else ['cutoff_response_under_1dB_per_octave'],
                cutoff_response_db_per_octave=sensitivity,cutoff_hz=fitted['cutoff_hz'],
                cutoff_over_f0=fitted['cutoff_hz']/row['fundamental_hz'],
                fit_h2_h3_rmse_db=fitted['fit_h2_h8_rmse_db'],
                withheld_harmonics=[hs[i] for i in upper],
                withheld_error_db=[float(full_error[i]) for i in upper])


def prediction(name, p, t):
    if name == 'exponential_log_cutoff':
        return float(np.exp(p[0]+p[1]*np.exp(-t/p[2])))
    if name == 'exponential_hz_with_floor':
        return float(p[0]+p[1]*np.exp(-t/p[2]))
    raise ValueError(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources',type=Path,required=True)
    parser.add_argument('--envelope-results',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    envelope = json.loads(args.envelope_results.read_text())
    frozen = {name:envelope['models'][name]['parameters'] for name in MODELS}
    assets = json.loads(CATALOG.read_text())['assets']
    sources = []
    def verify(filename):
        item = next(r for r in assets if Path(r['path']).name == filename)
        original = args.sources/filename
        if digest(original) != item['sha256']:
            raise ValueError(f'Changed reference: {filename}')
        sources.append(dict(filename=filename,url=item['url'],sha256=item['sha256']))
        return original
    midi = verify('deepsonic_-_filter_demo_-_comparsion_sequence.mid')
    events = parse_smf(midi.read_bytes())['events']
    for on,notes,target in CHORDS:
        for note in notes:
            for when,velocity in ((on,127),(on+.6875,0)):
                if not any(e['kind']=='midi' and abs(e['sample']/44100-when)<1/44100 and
                           bytes.fromhex(e['hex']) == bytes((0x90,note,velocity)) for e in events):
                    raise ValueError('Selected chord/gate does not match original MIDI')
    rows = []
    for slope in (12,24):
        original = verify(f'roland_sh-201_-_filter_demo_-_lpf{slope}_q000.mp3')
        wav = args.output/f'lp{slope}-hardware.wav'
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-i',str(original),
                        '-c:a','pcm_f32le',str(wav)],check=True)
        sr,y = wavfile.read(wav)
        if sr != 44100 or y.ndim != 1 or not np.isfinite(y).all():
            raise ValueError('Unexpected hardware decode')
        for on,notes,target in CHORDS:
            for offset in OFFSETS:
                for width in WIDTHS:
                    row = dict(slope=slope,on=on,notes=list(notes),target_note=target,
                               offset=offset,width=width)
                    try:
                        row.update(measure_chord(y,sr,on+offset,width,notes,target))
                        row.update(fit_target(row,slope))
                    except ValueError as error:
                        row.update(valid=False,rejection=[str(error)])
                    if row['valid']:
                        row['frozen_model_predictions'] = {name:dict(cutoff_over_f0=prediction(name,p,offset),
                            error_cents=float(1200*np.log2(prediction(name,p,offset)/row['cutoff_over_f0'])))
                            for name,p in frozen.items()}
                    rows.append(row)
    summaries = {}
    for width in WIDTHS:
        for slope in (12,24):
            group = [r for r in rows if r['width']==width and r['slope']==slope and r['valid']]
            summaries[f'lp{slope}_{width:g}'] = dict(valid=len(group),attempted=len(CHORDS)*len(OFFSETS),
                fit_h2_h3_rmse_db=rms([r['fit_h2_h3_rmse_db'] for r in group]),
                withheld_harmonic_count=sum(len(r['withheld_error_db']) for r in group),
                withheld_harmonic_rmse_db=rms([e for r in group for e in r['withheld_error_db']]),
                models={name:dict(rmse_cents=rms([r['frozen_model_predictions'][name]['error_cents'] for r in group]),
                    bias_cents=float(np.mean([r['frozen_model_predictions'][name]['error_cents'] for r in group]))) for name in MODELS})
    result = dict(schema_version=1,status='frozen_curve_holdout_test_no_DSP_changes',
        sources=sources,tool_sha256=digest(__file__),envelope_results_sha256=digest(args.envelope_results),
        frozen_parameters=frozen,summary=summaries,observations=rows,
        method=dict(primary_width_seconds=.08,sensitivity_width_seconds=[.06,.10],
                    clustering_threshold='adjacent source partials closer than 1.5 / window_width Hz',
                    required_isolated_partials=[1,2,3],fitted_ratios=['H2/H1','H3/H1'],
                    noise_proxy_threshold_db=20,relative_harmonic_floor_db=-45,
                    condition_number_max=100,unexplained_power_max=.01,
                    minimum_cutoff_response_db_per_octave=1.,
                    cutoff_is_per_window_nuisance=True,frozen_curves_refitted=False),
        limits=['Chord phases are unknown; merged clusters are nuisance components only.',
                'White-residual SNR proxy does not guarantee absence of structured leakage.',
                'No exact patch controls or recording-chain calibration.',
                'Effective cutoff law cannot distinguish envelope-control shape from cutoff mapping.',
                'Nominal time alignment is the same as the frozen single-note fits.'])
    (args.output/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(summaries,indent=2))


if __name__ == '__main__':
    main()
