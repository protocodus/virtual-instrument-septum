#!/usr/bin/env python3
"""Source-only Patch06 feasibility; no renderer, MIDI reconstruction or rate fit.

Inspect creator card boundaries, exact official LFO labels and descriptive
brightness sensitivities. This deliberately does not select an LFO period from
fewer than two plausible cycles with unknown performance/capture processing.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal
from scipy.io import wavfile

from inspect_rcs_acid_sources import MEDIA_FILES


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sources',type=Path,required=True)
    p.add_argument('--extraction',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    extraction=json.loads((a.extraction/'results.json').read_text())
    if extraction['tool_sha256'] != sha(Path(__file__).with_name('inspect_rcs_acid_sources.py')):
        raise ValueError('Re-run the reviewed source extractor first')
    for name,expected in MEDIA_FILES.items():
        if sha(a.sources/name)!=expected:raise ValueError('Original source changed: '+name)
    wav=a.extraction/'source-full.wav'
    if sha(wav)!=extraction['video']['decoded_sha256']:raise ValueError('Decode changed')
    sr,y=wavfile.read(wav)
    if sr!=44100 or y.ndim!=2 or y.shape[1]!=2 or not np.isfinite(y).all():
        raise ValueError('Unexpected audio')
    patch=next(row for row in extraction['presets']if row['member']=='TB-303 06.she')
    lfo=patch['official_lfo_labels']['upper'][0]
    if (lfo != dict(waveform='SIN',destination1='FILTER',depth1=30,
            destination2='AMP',depth2=0,rate_raw=21,key_trigger=0,tempo_sync=0)
            or patch['common']['keyboardMode']!=0 or patch['common']['keyboardPart']!=0):
        raise ValueError('Patch06 active routing changed')
    video=a.sources/'7jW2GIgOOv8-video.mp4'
    command=['ffmpeg','-v','error','-nostdin','-i',str(video),'-vf',
             'crop=160:40:80:220,format=gray','-f','rawvideo','-']
    pixels=np.frombuffer(subprocess.check_output(command),np.uint8).reshape(-1,6400).astype(float)
    # These native-video ROI/template choices were established by inspecting
    # the numbered card, before any model audio or timing fit.
    x=pixels-pixels[1775]  # 71.00 s: label absent.
    template=x[1875]     # 75.00 s: visually verified Patch06 card.
    amplitude=x@template/(template@template)
    residual=np.linalg.norm(x-amplitude[:,None]*template,axis=1)/np.linalg.norm(template)
    frames=np.arange(len(x));mask=(frames>=1750)&(frames<2150)&(amplitude>.95)&(residual<.06)
    selected=np.flatnonzero(mask)
    if not np.array_equal(selected,np.arange(1794,2120)):
        raise ValueError('Observed Patch06 video-card coverage changed')
    bounds=[selected[0]/25,(selected[-1]+1)/25]
    lo,hi=bounds
    # Extract four exact neighboring frames to make the boundary reviewable.
    frame_command=['ffmpeg','-v','error','-nostdin','-i',str(video),'-vf',
        'select=eq(n\\,1793)+eq(n\\,1794)+eq(n\\,2119)+eq(n\\,2120),tile=2x2',
        '-frames:v','1',str(a.output/'card-boundaries.png')]
    subprocess.run(frame_command,check=True)
    crop=y[round(lo*sr):round(hi*sr)]
    hop=44;blocks=crop[:len(crop)//hop*hop].reshape(-1,hop,2)
    times=(np.arange(len(blocks))+.5)*hop/sr+lo
    rms=np.sqrt(np.mean(blocks*blocks,axis=(1,2)))
    peaks,_=signal.find_peaks(rms,height=.10,distance=round(.38*sr/hop),prominence=.06)
    peak_times=times[peaks]
    bands=[(300,900),(900,3000),(3000,7000)]
    rows=[]
    for peak in peak_times:
        observations=[]
        for offset in (.06,.12,.18):
            sa,sb=[round((peak+offset+d)*sr)for d in(-.03,.03)]
            if not round(lo*sr)<=sa<sb<=round(hi*sr):raise ValueError('Feature escapes source support')
            v=y[sa:sb];w=np.hanning(len(v));f=np.fft.rfftfreq(len(v),1/sr)
            power=np.mean(abs(np.fft.rfft(v*w[:,None],axis=0))**2,axis=1)
            low=power[(f>=40)&(f<200)].sum()
            ratios=[float(10*np.log10(power[(f>=bl)&(f<bh)].sum()/low))for bl,bh in bands]
            observations.append(dict(offset_from_rms_peak_seconds=offset,samples=[sa,sb],
                                      band_to_40_200hz_db=ratios))
        rows.append(dict(rms_peak_source_seconds=float(peak),observations=observations))
    values=np.array([[r['band_to_40_200hz_db']for r in row['observations']]for row in rows])
    fig,axes=plt.subplots(3,1,figsize=(12,8),sharex=True,layout='constrained')
    for j,ax in enumerate(axes):
        for i,offset in enumerate((.06,.12,.18)):
            ax.plot(peak_times,values[:,i,j],'-o',ms=3,label=f'RMS peak +{offset:.2f} s')
        ax.set(ylabel=f'{bands[j][0]}–{bands[j][1]} / 40–200 Hz, dB')
        ax.grid(alpha=.3);ax.legend(fontsize=8)
    axes[0].set_title('Patch06 source only: note-age sensitivity prevents a clean rate anchor')
    axes[-1].set(xlabel='Original audio clock / s',xlim=bounds)
    fig.savefig(a.output/'source-brightness.png',dpi=140);plt.close(fig)
    result=dict(schema_version=1,status='No static-cutoff anchor; insufficient clean cycles for a raw21 LFO-period anchor.',
        source_extraction_sha256=sha(a.extraction/'results.json'),tool_sha256=sha(__file__),
        original_media_sha256=MEDIA_FILES,decoded_sha256=sha(wav),patch=patch,
        video_card=dict(frame_rate=25,first_inclusive_frame=1794,last_inclusive_frame=2119,
            visible_seconds=bounds,duration_seconds=hi-lo,blank_template_frame=1775,
            patch06_template_frame=1875,roi_xywh=[80,220,160,40],
            match_amplitude_minimum=.95,match_relative_residual_maximum=.06,
            observed_relative_residual_maximum=float(residual[selected].max()),
            extraction_command=command,frame_command=frame_command,
            caveat='Exact visible text bounds; the absent labels before/after and unknown edit synchronization prevent calling them exact sound/patch switch times.'),
        feature_protocol=dict(source_only_exploratory_feasibility=True,rate_fit_performed=False,
            note_events_reconstructed=False,period_selected=False,
            source_support_seconds=bounds,rms_block_samples=hop,
            peak_policy=dict(height=.10,prominence=.06,minimum_spacing_seconds=.38),
            window='60ms symmetric Hann; stereo powers averaged before band ratios',
            bands_hz=bands,normalizer_hz=[40,200],offsets_after_rms_peak_seconds=[.06,.12,.18],
            limitations='RMS peaks are acoustic landmarks, not identified MIDI events. Broad bands are descriptive, not phase-invariant harmonic estimates or filter transfer functions.'),
        acoustic_landmarks=rows,summary=dict(landmarks=len(rows),
            rms_peak_spacing_median_seconds=float(np.median(np.diff(peak_times))),
            within_peak_offset_range_db_median_by_band=np.median(np.ptp(values,axis=1),axis=0).tolist(),
            within_peak_offset_range_db_maximum_by_band=np.max(np.ptp(values,axis=1),axis=0).tolist()),
        conclusions=[
            'Official destination1 raw2 is FILTER, not PW1. The sine LFO has rawrate21, depth+30, key trigger off, sync off; its free phase is unknown.',
            'The source contains changing brightness, consistent with active filter modulation, but card-only video cannot exclude additional manual/MIDI automation or edited/processed capture.',
            'The 13.04s visible-card support contains fewer than two cycles of the approximately7.3s current interpolation hypothesis. This duration alone does not measure the hardware period.',
            'Beat-conditioned brightness depends strongly on offset and band. The strongest low-frequency transients and additional line families do not provide an authenticated isolated same-note saw input; backing/performance, note gates and delay remain confounded.',
            'Do not fit a raw21 correction, LFO depth, cutoff81 conversion or filter resonance from this audit. No matched render or MIDI reconstruction was produced.',
            'Patch03 is also unsuitable for isolated filter response: its original overdrive switch is on at depth127, with delay and portamento active.'])
    result['output_sha256']={name:sha(a.output/name)for name in('card-boundaries.png','source-brightness.png')}
    (a.output/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(a.output/'results.json')


if __name__=='__main__':main()
