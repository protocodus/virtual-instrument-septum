#!/usr/bin/env python3
"""Verify original-preset before/after pairs and build the resonance listening page."""
import argparse
import hashlib
import html
import json
import shutil
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_text())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--before',type=Path,required=True)
    p.add_argument('--after',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    results=[];sections=[]
    for case in ['supa-juce-1','dist-bs-1','moogie-1','cotton-wool']:
        before=a.before/case;after=a.after/case
        old,new=read(before/'comparison.json'),read(after/'comparison.json')
        bm,am=read(before/'septum-raw.render.json'),read(after/'septum-raw.render.json')
        for file in ['original-patch.syx','reconstructed-performance.mid','hardware-excerpt-raw.wav']:
            if sha(before/file)!=sha(after/file):raise ValueError('Pair differs: '+case+'/'+file)
        if bm['settings']!=am['settings'] or bm['degraded_replay'] or am['degraded_replay']:
            raise ValueError('Replay settings differ or contain degraded replay')
        for root,m in [(before,bm),(after,am)]:
            assert sha(root/'septum-raw.wav')==m['output']['sha256']
        assert old['case']==new['case'] and old['parameter_modifications']==new['parameter_modifications']==[]
        unchanged=sha(before/'septum-raw.wav')==sha(after/'septum-raw.wav')
        result={'case':case,'reference':new['reference'],'same_midi_sysex_verified':True,
                'original_midi_available':False,'reconstruction_sha256':new['reconstruction_file_sha256'],
                'before_manifest_sha256':sha(before/'septum-raw.render.json'),
                'after_manifest_sha256':sha(after/'septum-raw.render.json'),
                'before_inputs':bm['inputs'],'after_inputs':am['inputs'],
                'before_output_sha256':bm['output']['sha256'],'after_output_sha256':am['output']['sha256'],
                'byte_identical':unchanged,'before_statistics':old['raw_excerpt_statistics'],
                'after_statistics':new['raw_excerpt_statistics'],'limits':new['comparison_limits']}
        results.append(result)
        dest=a.output/case;dest.mkdir(exist_ok=True)
        for source,name in [(after/'hardware-listen.wav','hardware.wav'),(before/'septum-listen.wav','before.wav'),(after/'septum-listen.wav','after.wav')]:shutil.copy2(source,dest/name)
        label='Resonance correction is audible here.' if case=='supa-juce-1' else 'Small change: this patch uses very little resonance.' if case=='dist-bs-1' else 'Zero-resonance control: before and after WAV files are byte-identical.'
        tracks=''.join(f'<div><label>{title}</label><audio controls preload="metadata" src="{case}/{key}.wav"></audio><button data-track="{key}" type="button">Switch to {title}</button></div>' for key,title in [('hardware','Roland hardware'),('after','Corrected Septum'),('before','Previous Septum')])
        limits=''.join('<li>'+html.escape(x)+'</li>' for x in new['case']['uncertainties'])
        sections.append(f'<section><h2>{html.escape(new["reference"]["patch_name"])}</h2><p>{label} Both Septum versions use identical reconstructed MIDI and the unchanged published preset.</p><div class="tracks">{tracks}</div><p class="status" aria-live="polite">Switch buttons preserve playback position.</p><details><summary>Reconstruction limits</summary><ul>{limits}</ul></details></section>')
    x=np.geomspace(.1,4,800);k=2-2.04*np.sqrt(40/127);newk=2*(k/2)**1.5
    def response(a,b):return -20*np.log10(np.hypot(1-x*x,a*x)*np.hypot(1-x*x,b*x))
    fig,ax=plt.subplots(figsize=(9,3.3),layout='constrained');fig.patch.set_facecolor('#121a1d');ax.set_facecolor('#121a1d')
    ax.semilogx(x,response(k,1.2),color='#e99591',label='Previous model')
    ax.semilogx(x,response(newk,np.clip(newk,.5,1.2)),color='#91dbb7',label='Corrected model')
    ax.set_ylim(-40,16);ax.set_xlim(.1,4);ax.set_xlabel('Warped frequency / filter natural frequency',color='#dce6e7');ax.set_ylabel('Gain (dB)',color='#dce6e7');ax.set_title('24 dB low-pass at resonance 40 · calculated small-signal shape',color='#edf5f4');ax.tick_params(colors='#c8d7da');ax.grid(alpha=.2);legend=ax.legend(facecolor='#202b2e',edgecolor='#4e666c',labelcolor='#dce6e7')
    for spine in ax.spines.values():spine.set_color('#627679')
    fig.savefig(a.output/'response.png',dpi=160);plt.close(fig)
    manifest={'schema_version':1,'status':'production resonance correction with paired original-preset renders',
              'listening_processing':'Whole-excerpt scalar RMS matching from comparison manifests; no EQ, compression or time warp.',
              'comparison_limit':'Original hardware performance MIDI, exact recording patch revision and recording processing remain unverified.',
              'results':results,'source_code_sha256':{str(p):sha(p) for p in [Path('Source/DSP/SeptumEngine.cpp'),Path('Source/DSP/SeptumEngine.h')]},
              'script_sha256':sha(Path(__file__))}
    (a.output/'production-resonance-comparison.json').write_text(json.dumps(manifest,indent=2)+'\n')
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SH-201 · resonance correction</title><style>
:root{color-scheme:dark;font-family:system-ui,sans-serif;background:#101618;color:#edf4f4}body{max-width:1100px;margin:auto;padding:40px 24px}h1{font-size:clamp(28px,4vw,43px);letter-spacing:-.04em}h2{font-size:25px;margin:0 0 14px}.kicker{color:#91dbb7;text-transform:uppercase;letter-spacing:.12em;font-size:12px}p{line-height:1.65;color:#bdcccf;max-width:900px}section{background:#1a2427;border:1px solid #34474c;border-radius:14px;padding:26px;margin:25px 0}.tracks{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:22px}label{display:block;margin:14px 0;font-size:14px}audio{width:100%;height:40px}button{width:100%;padding:11px;margin-top:12px;background:#264638;color:#edfff5;border:1px solid #67917b;border-radius:7px;cursor:pointer}button:hover,button:focus-visible{background:#39654f;outline:2px solid #91dbb7}.status,details{font-size:13px;color:#b9cbd0}details{line-height:1.6}summary{cursor:pointer}li{margin:8px 0}img{max-width:100%;border-radius:10px}a{color:#91dbb7}@media(max-width:740px){body{padding:24px 14px}.tracks{grid-template-columns:1fr}section{padding:20px}}
</style><main><div class="kicker">SH-201 fidelity · resonance</div><h1>A stronger filter peak</h1><p>The revised voice filter adds more resonant emphasis in both stages of its 24 dB mode. At resonance 40, its calculated peak rises from 2.2 dB to 10.8 dB. The second stage is limited to Q 2 to keep high settings controlled.</p><p>This is a recording-informed calibration. Hardware filter topology and the complete control curve remain unverified. The remaining cutoff and envelope differences are audible, especially in the lead.</p><img src="response.png" alt="Calculated low-pass response: the corrected filter has a stronger peak at resonance 40"><p><strong>Level-matched listening copies.</strong> MIDI is explicitly reconstructed, not the recovered original performance. Both Septum versions use the same MIDI and original presets.</p>'''+''.join(sections)+'''<p><a href="production-resonance-comparison.json">Input identities, raw statistics and comparison limits</a></p></main><script>
for(const section of document.querySelectorAll('section')){const tracks=[...section.querySelectorAll('audio')];let active=null;for(const track of tracks)track.addEventListener('play',()=>{for(const other of document.querySelectorAll('audio'))if(other!==track)other.pause();active=track;section.querySelector('.status').textContent='Playing '+track.previousElementSibling.textContent;});for(const button of section.querySelectorAll('button'))button.addEventListener('click',async()=>{const next=tracks.find(x=>x.src.endsWith('/'+button.dataset.track+'.wav'));const time=active?.currentTime||0;if(active)active.pause();next.currentTime=Math.min(time,Number.isFinite(next.duration)?Math.max(0,next.duration-.01):time);try{await next.play();}catch(e){section.querySelector('.status').textContent=e.message;}});}
</script></html>'''
    (a.output/'index.html').write_text(page)
    print(a.output/'index.html')

if __name__=='__main__':main()
