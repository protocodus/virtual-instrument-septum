#!/usr/bin/env python3
"""Verify paired original-preset renders and present the envelope-range correction."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import shutil


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--figure', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    results, sections = [], []
    for case in ('supa-juce-1', 'cotton-wool', 'moogie-1', 'dist-bs-1'):
        before, after = args.before / case, args.after / case
        old, new = read(before / 'comparison.json'), read(after / 'comparison.json')
        bm, am = read(before / 'septum-raw.render.json'), read(after / 'septum-raw.render.json')
        for name in ('original-patch.syx', 'reconstructed-performance.mid', 'hardware-excerpt-raw.wav'):
            if sha(before / name) != sha(after / name):
                raise ValueError('Mismatched paired input: ' + case + '/' + name)
        if bm['settings'] != am['settings'] or bm['degraded_replay'] or am['degraded_replay']:
            raise ValueError('Replay settings differ or replay is degraded: ' + case)
        if old['case'] != new['case'] or old['parameter_modifications'] or new['parameter_modifications']:
            raise ValueError('Performance or patch differs: ' + case)
        for folder, manifest in ((before, bm), (after, am)):
            if sha(folder / 'septum-raw.wav') != manifest['output']['sha256']:
                raise ValueError('Output identity differs: ' + str(folder))
        dest = args.output / case
        dest.mkdir(exist_ok=True)
        for source, name in ((after / 'hardware-listen.wav', 'hardware.wav'),
                             (before / 'septum-listen.wav', 'before.wav'),
                             (after / 'septum-listen.wav', 'after.wav')):
            shutil.copy2(source, dest / name)
        result = {'case': case, 'reference': new['reference'], 'same_midi_sysex_verified': True,
                  'original_midi_available': False,
                  'reconstruction_sha256': new['reconstruction_file_sha256'],
                  'before_inputs': bm['inputs'], 'after_inputs': am['inputs'],
                  'before_manifest_sha256': sha(before / 'septum-raw.render.json'),
                  'after_manifest_sha256': sha(after / 'septum-raw.render.json'),
                  'before_output_sha256': bm['output']['sha256'],
                  'after_output_sha256': am['output']['sha256'],
                  'before_statistics': old['raw_excerpt_statistics'],
                  'after_statistics': new['raw_excerpt_statistics'],
                  'limits': new['comparison_limits']}
        results.append(result)
        tracks = ''.join(f'<div><label>{title}</label><audio controls preload="metadata" '
                         f'src="{case}/{key}.wav"></audio><button data-track="{key}">'
                         f'Switch to {title}</button></div>'
                         for key, title in (('hardware', 'Roland hardware'),
                                            ('after', 'Corrected Septum'),
                                            ('before', 'Previous Septum')))
        limits = ''.join('<li>' + html.escape(x) + '</li>' for x in new['case']['uncertainties'])
        note = {'supa-juce-1': 'The envelope opens the resonant filter farther, restoring the upper harmonics.',
                'cotton-wool': 'An independent pad comparison. Velocity and Super Saw balance remain uncertain.',
                'moogie-1': 'A smaller change. Oscillator and filter-shape differences remain.',
                'dist-bs-1': 'A smaller change. Relative oscillator phase and distortion remain unresolved.'}[case]
        sections.append(f'<section><h2>{html.escape(new["reference"]["patch_name"])}</h2>'
                        f'<p>{note}</p><div class="tracks">{tracks}</div>'
                        '<p class="status" aria-live="polite">Switch buttons preserve playback position.</p>'
                        f'<details><summary>Reconstruction limits</summary><ul>{limits}</ul></details></section>')
    shutil.copy2(args.figure, args.output / 'harmonics.png')
    manifest = {'schema_version': 1, 'status': 'production filter-envelope range correction',
                'comparison_limit': 'Reconstructed MIDI; original performance, exact recorded patch revision '
                                    'and recording processing remain unverified.',
                'listening_processing': 'Whole-excerpt scalar RMS matching; no EQ, compression or time warp.',
                'filter_envelope_max_octaves': {'before': 10, 'after': 12},
                'results': results, 'figure_sha256': sha(args.figure),
                'script_sha256': sha(Path(__file__))}
    (args.output / 'production-brightness-comparison.json').write_text(json.dumps(manifest, indent=2) + '\n')
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SH-201 · envelope brightness correction</title><style>
:root{color-scheme:dark;font-family:system-ui,sans-serif;background:#101618;color:#edf4f4}
body{max-width:1100px;margin:auto;padding:38px 24px}h1{font-size:clamp(28px,4vw,42px);letter-spacing:-.035em}
h2{font-size:25px;margin:0 0 14px}p{line-height:1.65;color:#bdcccf;max-width:930px}
section{border-top:1px solid #506368;padding:25px 0;margin:25px 0}.tracks{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:22px}
label{display:block;margin:14px 0;font-size:14px}audio{width:100%;height:40px}
button{width:100%;padding:11px;margin-top:12px;background:#264638;color:#edfff5;border:1px solid #67917b;cursor:pointer}
button:hover,button:focus-visible{background:#39654f;outline:2px solid #91dbb7}.status,details{font-size:13px;color:#b9cbd0}
details{line-height:1.6}summary{cursor:pointer}li{margin:8px 0}img{max-width:100%;background:#fff}a{color:#91dbb7}
@media(max-width:740px){body{padding:24px 14px}.tracks{grid-template-columns:1fr}}</style><main>
<h1>The filter envelope opens farther</h1>
<p>The envelope's modulation range was too small. Its maximum now spans 12 octaves instead of 10.
At SupaJuce's published depth 31, the modeled cutoff around 70 ms rises from about 3.8 kHz to 7.3 kHz,
close to the peak position inferred from the recording. The cutoff knob and resonance retain their previous calibration.</p>
<p>This is an empirical calibration against named Roland demos. It improves the match without establishing Roland's exact DSP.
Later envelope motion, oscillator balance and the recording effects still differ.</p>
<img src="harmonics.png" alt="Measured upper-square harmonic ratios in the hardware, previous Septum and corrected Septum">
<p><strong>Level-matched listening copies · same presets · identical reconstructed MIDI.</strong>
The original performance MIDI is unavailable. Each Septum pair uses unchanged published SysEx and the same replay settings.
Listening copies use one constant gain per excerpt, without EQ or time stretching.</p>''' + ''.join(sections) + '''
<p><a href="production-brightness-comparison.json">Input identities, raw statistics and comparison limits</a></p></main>
<script>for(const section of document.querySelectorAll('section')){const tracks=[...section.querySelectorAll('audio')];let active=null;
for(const track of tracks)track.addEventListener('play',()=>{for(const other of document.querySelectorAll('audio'))if(other!==track)other.pause();
active=track;section.querySelector('.status').textContent='Playing '+track.previousElementSibling.textContent;});
for(const button of section.querySelectorAll('button'))button.addEventListener('click',async()=>{
const next=tracks.find(x=>x.src.endsWith('/'+button.dataset.track+'.wav'));const time=active&&!active.ended?active.currentTime:0;
if(active)active.pause();next.currentTime=Math.min(time,Number.isFinite(next.duration)?Math.max(0,next.duration-.01):time);
try{await next.play();}catch(e){section.querySelector('.status').textContent=e.message;}});}</script></html>'''
    (args.output / 'index.html').write_text(page)
    print(args.output / 'index.html')


if __name__ == '__main__':
    main()
