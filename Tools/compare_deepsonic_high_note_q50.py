#!/usr/bin/env python3
"""Check whether the Q50-labelled captures share Q0's high-note open state.

No raw resonance value, maximum cutoff or waveform candidate is fitted.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import numpy as np
from scipy.io import wavfile
import analyze_deepsonic_high_note_invariance as invariant
import analyze_deepsonic_saw_aliases as aliases
from render_midi import parse_smf


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True,help='new directory')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    catalog=json.loads(invariant.CATALOG.read_text());sources=[];audio={};decodes=[]
    def verify(name):
        item=next(a for a in catalog['assets'] if Path(a['path']).name==name)
        path=args.sources/name
        if sha(path)!=item['sha256']:raise ValueError('Changed original source')
        sources.append(item);return path
    midi=verify('deepsonic_-_filter_demo_-_comparsion_sequence.mid')
    starts=[]
    for e in parse_smf(midi.read_bytes())['events']:
        if e['kind']=='midi':
            b=bytes.fromhex(e['hex'])
            if b[0]&240==144 and b[2]>0:starts.append((e['sample']/44100,b[1],b[2]))
    selected=((18.25,93,127),(18.75,91,127))
    if not all(n in starts for n in selected):raise ValueError('Original MIDI note changed')
    for resonance in (0,50):
        for slope in (12,24):
            mp3=verify(f'roland_sh-201_-_filter_demo_-_lpf{slope}_q{resonance:03}.mp3')
            wav=out/f'q{resonance:03}-lp{slope}.wav'
            command=['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-i',str(mp3),'-c:a','pcm_f32le',str(wav)]
            subprocess.run(command,check=True);sr,y=wavfile.read(wav)
            if sr!=44100 or y.ndim!=1:raise ValueError('Unexpected source format')
            audio[resonance,slope]=y;decodes.append(dict(command=command,wav_sha256=sha(wav)))
    rows=[];alias_rows=[];frequencies=[]
    for on,note,velocity in selected:
        nominal=invariant.fundamental(note)
        refined=invariant.estimate_frequency(audio[0,12],on,note)
        frequencies.append(dict(note=note,q0_lp12_first_window_frozen_hz=refined,nominal_hz=nominal))
        for resonance in (0,50):
            for slope in (12,24):
                for policy,frequency in (('nominal',nominal),('q0_frozen_refined',refined)):
                    windows=[(.08,.10),(.08,.16)]+[(.04,t)for t in (.08,.12,.16,.20)]
                    if note==91:windows.append((.04,.24))
                    for width,offset in windows:
                        rows.append(dict(note=note,on_seconds=on,recording_resonance_label=resonance,slope=slope,
                            frequency_policy=policy,**invariant.measure(audio[resonance,slope],on,offset,width,frequency,nominal)))
                for offset in (.10,.16):
                    alias_rows.append(dict(recording_resonance_label=resonance,slope=slope,
                                           **aliases.measure(audio[resonance,slope],on,note,offset)))
    summaries=[]
    for on,note,velocity in selected:
        for policy in ('nominal','q0_frozen_refined'):
            windows=sorted(set((r['width_seconds'],r['offset_seconds'])for r in rows if r['note']==note))
            for width,offset in windows:
                selected_rows=[r for r in rows if r['note']==note and r['frequency_policy']==policy
                               and r['width_seconds']==width and r['offset_seconds']==offset]
                h=[i for i in range(2,9) if all(r['relative_h1_db'][i-1]>-55 and r['coefficient_snr_proxy_db'][i-1]>=20 for r in selected_rows)]
                def values(q,s):return next(r for r in selected_rows if r['recording_resonance_label']==q and r['slope']==s)
                comparisons=[]
                for label,left,right in (('Q50LP12_minus_Q0LP12',(50,12),(0,12)),
                                         ('Q50LP24_minus_Q0LP24',(50,24),(0,24)),
                                         ('Q0LP24_minus_Q0LP12',(0,24),(0,12)),
                                         ('Q50LP24_minus_Q50LP12',(50,24),(50,12))):
                    delta=np.array(values(*left)['relative_h1_db'])[:8]-np.array(values(*right)['relative_h1_db'])[:8]
                    comparisons.append(dict(label=label,h2_h8_db=delta[1:].tolist(),
                                            **invariant.stats(delta[np.array(h)-1])))
                summaries.append(dict(note=note,frequency_policy=policy,width_seconds=width,offset_seconds=offset,
                    common_eligible_harmonics=h,max_fit_residual_power_fraction=max(r['residual_power_fraction']for r in selected_rows),
                    whole_window_harmonic_model_valid=all(r['residual_power_fraction']<.01 for r in selected_rows),
                    comparisons=comparisons))
    alias_comparisons=[]
    for on,note,velocity in selected:
        for slope in (12,24):
            q0=[r for r in alias_rows if r['note']==note and r['slope']==slope and r['recording_resonance_label']==0]
            eligible={r['parent_harmonic']for r in aliases.summary(q0)['44100']['repeated_lines']}
            comparisons=[]
            for offset in (.10,.16):
                a=next(r for r in q0 if r['offset_seconds']==offset)
                b=next(r for r in alias_rows if r['note']==note and r['slope']==slope and r['recording_resonance_label']==50 and r['offset_seconds']==offset)
                for h in sorted(eligible):
                    first=next(r for r in a['tested_alias_lines']if r['rate_hypothesis_hz']==44100 and r['parent_harmonic']==h)
                    second=next(r for r in b['tested_alias_lines']if r['rate_hypothesis_hz']==44100 and r['parent_harmonic']==h)
                    comparisons.append(dict(parent_harmonic=h,offset_seconds=offset,frequency_hz=first['expected_hz'],
                        q0_db=first['relative_h1_db'],q50_db=second['relative_h1_db'],
                        q50_minus_q0_db=second['relative_h1_db']-first['relative_h1_db'],
                        q50_harmonic_only_residual_power_fraction=b['residual_power_fraction'],
                        q50_peak_hz=second['peak_hz'],q50_background_db=second['local_median_relative_h1_db'],
                        q50_passes_threshold=second['passes_line_threshold']))
            alias_comparisons.append(dict(note=note,slope=slope,q0_only_mask=sorted(eligible),
                comparisons=comparisons,**invariant.stats([r['q50_minus_q0_db']for r in comparisons])))
    result=dict(schema_version=1,status='secondary original-source high-note state comparison; no DSP changes',
        tool_sha256=sha(__file__),harmonic_helper_sha256=sha(invariant.__file__),alias_helper_sha256=sha(aliases.__file__),
        catalog_sha256=sha(invariant.CATALOG),sources=sources,decodes=decodes,selected_original_notes=selected,
        resonance_label_status='Q050 is the source filename/nominal recipe label; exact raw control value and patch SysEx unavailable.',
        frequency_refinements=frequencies,harmonic_summaries=summaries,harmonic_windows=rows,
        alias_comparisons=alias_comparisons,
        limits=['Normalized spectral convergence identifies an effective output state, not a specific bypass/clamping mechanism.',
                'No original capture chain, encoder history, raw SysEx or exact knob settings.',
                'Q0 alone determines alias eligibility and frequency refinement; Q50 does not tune the test.',
                'Time windows can straddle the end of an early open state, especially the80ms+.16 window.'])
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(harmonic_summaries=summaries,alias_comparisons=alias_comparisons),indent=2))


if __name__=='__main__':main()
