#!/usr/bin/env python3
"""Export a synchronized listening artifact from the frozen dry benchmark."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.io import wavfile


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--experiment',type=Path,required=True)
    p.add_argument('--assessment',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    renders_path=args.experiment/'renders.json';scores_path=args.assessment/'audio-results.json'
    renders=json.loads(renders_path.read_text());scores=json.loads(scores_path.read_text())
    if sha(renders_path)!=scores['protocol']['source_render_manifest_sha256']:
        raise ValueError('Render/assessment identity changed')
    decode_path=args.assessment/'source-cache/decode-manifest.json';decode=json.loads(decode_path.read_text())
    groups=[]
    for slope in (12,24):
        path=args.assessment/f'source-cache/roland_sh-201_-_filter_demo_-_lpf{slope}_q000.wav'
        expected=next(d for d in decode['files'] if d['decoded_sha256']==sha(path))
        rate,h=wavfile.read(path)
        if rate!=44100 or h.ndim!=1 or not np.isfinite(h).all():raise ValueError('Hardware format changed')
        selected=[]
        for identity in ('production','dry-hz-35ms'):
            render=next(r for r in renders['renders'] if r['id']==identity and r['case']==f'lp{slope}')
            score=next(r for r in scores['results'] if r['id']==identity and r['slope']==slope)
            wav=Path(render['wav'])
            if sha(wav)!=render['sha256'] or sha(wav)!=score['render_sha256']:
                raise ValueError('Candidate waveform identity changed')
            sr,c=wavfile.read(wav)
            if sr!=rate or c.ndim!=2 or not np.isfinite(c).all():raise ValueError('Candidate format changed')
            if np.max(abs(c[:,0]-c[:,1]))>1e-7:raise ValueError('Unexpected stereo source')
            if score['lag_samples']!=-1406:raise ValueError('Physical 35ms alignment changed')
            selected.append((identity,c[:,0].astype(float),score))
        start=1406;end=min(len(h),*[len(c)+1406 for _,c,_ in selected])
        signals={'hardware':h[start:end].astype(float)}
        for identity,c,score in selected:signals[identity]=c[start-1406:end-1406]*score['gain']
        attenuation=min(1.,.1/np.sqrt(np.mean(signals['hardware']**2)),.98/max(np.max(abs(x)) for x in signals.values()))
        tracks=[]
        for identity,x in signals.items():
            file=f'lp{slope}-{identity}.wav';data=(x*attenuation).astype(np.float32)
            wavfile.write(out/file,rate,data)
            tracks.append(dict(id=identity,file=file,sha256=sha(out/file),peak=float(max(abs(data))),
                               fitted_gain=1. if identity=='hardware' else next(s['gain'] for i,c,s in selected if i==identity)))
        groups.append(dict(slope=slope,sample_rate=rate,frames=end-start,hardware_start_sample=start,
                           hardware_end_sample=end,common_attenuation=attenuation,tracks=tracks,
                           source_decode=expected,measurements=[s for _,_,s in selected]))
    template=Path(__file__).with_name('dry_benchmark_player.html')
    manifest=dict(status='open_listening_comparison_not_equivalence',groups=groups,
                  renders_sha256=sha(renders_path),assessment_sha256=sha(scores_path),
                  decode_manifest_sha256=sha(decode_path),script_sha256=sha(__file__),template_sha256=sha(template),
                  policy='Frozen -1406-sample alignment and one gain per render from MIDI36 training only; common per-slope playback attenuation; no new timing/gain/phase fit. HTML switching crossfades12ms only during playback.')
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
    # The UI needs transport/file data only; full evidence remains in manifest.json.
    ui=dict(groups=[{k:v for k,v in g.items() if k not in ('measurements','source_decode')} for g in groups])
    (out/'index.html').write_text(template.read_text().replace('__MANIFEST__',json.dumps(ui,allow_nan=False)))
    print(out/'index.html')


if __name__=='__main__':main()
