#!/usr/bin/env python3
"""Verify and present paired WIDE-pitch benchmark runs; no audio synthesis or EQ."""
import argparse
import hashlib
import html
import json
import shutil
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import welch


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text())


def band_ratio(path, duration):
    sr, y = wavfile.read(path)
    y = y[:round(sr * duration)].astype(np.float64)
    f, p = welch(y, sr, nperseg=min(65536, len(y)), axis=0)
    p = p.mean(axis=1)
    return float(10 * np.log10(p[(f >= 20) & (f < 40)].sum()
                              / p[(f >= 40) & (f <= 16000)].sum()))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, required=True,
                    help='Directory containing before/ and after/ benchmark runs')
    ap.add_argument('--historical-filter-after', type=Path)
    args = ap.parse_args()
    output = args.root / 'player'
    output.mkdir(exist_ok=True)
    results, sections = [], []
    for case_id in ('cotton-wool', 'supa-juce-1', 'moogie-1', 'dist-bs-1'):
        before, after = (args.root / stage / case_id for stage in ('before', 'after'))
        b, a = (read_json(p / 'comparison.json') for p in (before, after))
        bm, am = (read_json(p / 'septum-raw.render.json') for p in (before, after))
        for name in ('original-patch.syx', 'reconstructed-performance.mid'):
            assert digest(before / name) == digest(after / name), (case_id, name)
        assert a['case'] == b['case'] and a['parameter_modifications'] == b['parameter_modifications'] == []
        assert bm['degraded_replay'] is False and am['degraded_replay'] is False
        for directory, manifest in ((before, bm), (after, am)):
            assert digest(directory / 'septum-raw.wav') == manifest['output']['sha256']
            for kind, name in (('midi', 'reconstructed-performance.mid'), ('sysex', 'original-patch.syx')):
                assert digest(directory / name) == manifest['inputs'][kind]['sha256']
        result = {'case_id': case_id, 'same_midi_and_original_preset_verified': True,
                  'midi_status': 'reconstructed_not_original',
                  'inputs': am['inputs'], 'before_renderer': bm['inputs']['renderer'],
                  'before_output_sha256': bm['output']['sha256'],
                  'after_output_sha256': am['output']['sha256'],
                  'reconstruction_sha256': a['reconstruction_file_sha256'],
                  'reference': a['reference'],
                  'power_centroid_20_16000_hz': {
                      'hardware': a['raw_excerpt_statistics']['hardware']['power_spectral_centroid_20_16000_hz'],
                      'before': b['raw_excerpt_statistics']['septum']['power_spectral_centroid_20_16000_hz'],
                      'after': a['raw_excerpt_statistics']['septum']['power_spectral_centroid_20_16000_hz']},
                  'limits': a['comparison_limits']}
        if case_id == 'cotton-wool':
            result['power_20_40_over_40_16000_db'] = {
                'hardware': band_ratio(after / 'hardware-excerpt-raw.wav', a['case']['duration_seconds']),
                'before': band_ratio(before / 'septum-raw.wav', a['case']['duration_seconds']),
                'after': band_ratio(after / 'septum-raw.wav', a['case']['duration_seconds'])}
        note = ('Both Septum versions play exactly the same revised MIDI and untouched published preset. '
                'The reference performance MIDI is reconstructed, not the recovered original.')
        if case_id in ('moogie-1', 'dist-bs-1'):
            note += (' The earlier transcription compensated for the import error by playing two octaves higher. '
                     'The corrected version uses the revised notes; this fixes pitch mapping, not the remaining bass timbre.')
            if args.historical_filter_after:
                old_id = 'moogie-1-octave-revision' if case_id == 'moogie-1' else case_id
                historical = args.historical_filter_after / old_id / 'septum-raw.wav'
                result['historical_different_midi_output'] = {
                    'path': str(historical), 'sha256': digest(historical),
                    'byte_identical_to_after': digest(historical) == digest(after / 'septum-raw.wav'),
                    'qualification': 'Different MIDI transcription; old notes were 24 semitones higher.'}
        local = output / case_id
        local.mkdir(exist_ok=True)
        for source, dest in ((after / 'hardware-listen.wav', 'hardware.wav'),
                             (before / 'septum-listen.wav', 'before.wav'),
                             (after / 'septum-listen.wav', 'after.wav'),
                             (after / 'comparison.png', 'comparison.png')):
            if source.exists(): shutil.copy2(source, local / dest)
        title = html.escape(a['reference']['patch_name'])
        limits = ''.join('<li>' + html.escape(s) + '</li>' for s in a['case']['uncertainties'])
        controls = ''.join(f'<div><label>{label}</label><audio preload="metadata" controls src="{case_id}/{key}.wav"></audio><button type="button" data-track="{key}">Switch to {label}</button></div>'
                           for key, label in [('hardware', 'Roland hardware'), ('after', 'Corrected Septum'), ('before', 'Previous Septum')])
        sections.append(f'<section><h2>{title}</h2><p>{html.escape(note)}</p><div class="tracks">{controls}</div><p class="status" aria-live="polite">Choose a track. Switch buttons preserve playback position.</p><details><summary>Reconstruction and comparison limits</summary><ul>{limits}</ul></details></section>')
        results.append(result)
    summary = {'schema_version': 1, 'claim': 'Pitch-range correction tested with paired original-preset renders and explicitly reconstructed MIDI.',
               'source_hash_note': 'Binary hashes identify renderers. compare_hardware source_code_sha256 is the checkout observed during rendering, not proof of the preserved baseline binary source.',
               'listening_transform': 'Whole-excerpt RMS matching only, as recorded in each comparison.json. No EQ, compression, time warp or velocity fitting.',
               'results': results}
    (args.root / 'production-pitch-comparison.json').write_text(json.dumps(summary, indent=2) + '\n')
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SH-201 · pitch fidelity comparison</title><style>
:root{color-scheme:dark;font-family:system-ui,sans-serif;background:#101416;color:#eef3f4}body{max-width:1080px;margin:auto;padding:40px 24px}h1{font-size:clamp(28px,4vw,42px);letter-spacing:-.04em;margin:12px 0}h2{font-size:25px;margin:0 0 14px}.kicker{color:#91d1b6;letter-spacing:.13em;font-size:12px;text-transform:uppercase}p{line-height:1.6;color:#b7c5c8;max-width:850px}section{background:#192124;border:1px solid #314044;border-radius:14px;margin:25px 0;padding:26px}.tracks{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px;margin-top:24px}label{display:block;font-size:14px;margin-bottom:12px}audio{width:100%;height:40px}button{margin-top:12px;width:100%;padding:11px;border:1px solid #527466;border-radius:7px;background:#213c31;color:#e6fff1;cursor:pointer}button:hover,button:focus-visible{background:#345d4b;outline:2px solid #91d1b6}details{font-size:14px;color:#b7c5c8;line-height:1.6}summary{cursor:pointer}li{margin:8px 0}.status{font-size:13px}a{color:#91d1b6}@media(max-width:760px){.tracks{grid-template-columns:1fr}body{padding:24px 14px}section{padding:20px}}
</style><main><div class="kicker">SH-201 fidelity · WIDE pitch correction</div><h1>The right oscillator interval</h1><p>Normal-range PITCH was decoded as three octaves instead of one. These comparisons use the corrected range, the original Roland presets, and revised audio-derived MIDI. Cotton Wool and SupaJuce 1 expose the oscillator-spacing error; the bass examples also show what still needs work.</p><p><strong>Listening copies are level matched.</strong> Unknown original MIDI, velocity, effects history and recording processing limit the comparison. No EQ has been added. This is not a bit-exact hardware capture test.</p>''' + ''.join(sections) + '''<p><a href="../production-pitch-comparison.json">Verified input hashes and raw measurements</a></p></main><script>
for(const section of document.querySelectorAll('section')){
 const tracks=[...section.querySelectorAll('audio')];let active=null;
 for(const track of tracks)track.addEventListener('play',()=>{for(const other of document.querySelectorAll('audio'))if(other!==track)other.pause();active=track;section.querySelector('.status').textContent='Playing '+track.previousElementSibling.textContent;});
 for(const button of section.querySelectorAll('button'))button.addEventListener('click',async()=>{const next=tracks.find(a=>a.src.endsWith('/'+button.dataset.track+'.wav'));const time=active?.currentTime||0;if(active)active.pause();next.currentTime=Math.min(time,Number.isFinite(next.duration)?Math.max(0,next.duration-.01):time);try{await next.play();}catch(error){section.querySelector('.status').textContent=error.message;}});
}
</script></html>'''
    (output / 'index.html').write_text(page)
    for result in results:
        print(result['case_id'], result['power_centroid_20_16000_hz'], result.get('power_20_40_over_40_16000_db', ''))
    print(output / 'index.html')


if __name__ == '__main__':
    main()
