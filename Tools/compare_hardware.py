#!/usr/bin/env python3
"""Render audited, explicitly reconstructed SH-201 demo excerpts for comparison.

Requires NumPy, SciPy, Matplotlib, ffmpeg and SeptumRenderMidi. No DSP parameters
are fitted. Original compressed audio, decoded PCM, raw render and listening
copies remain distinct, with hashes and every transformation in the report.
"""
import argparse
import hashlib
import html
import json
import math
import platform
import re
from pathlib import Path
import struct
import subprocess
import sys

import numpy as np
from scipy.io import wavfile
from scipy import signal
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import scipy

from extract_reference_patch import read_bank, parse_bank, encode_syx

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def vlq(value):
    if not 0 <= value <= 0x0fffffff:
        raise ValueError('MIDI delta outside VLQ range')
    result = [value & 127]
    while value >> 7:
        value >>= 7
        result.insert(0, (value & 127) | 128)
    return bytes(result)


def write_midi(path, case):
    # 20,000 ticks/second, independent of the patch's preserved tempo.
    events = []
    for item in case['notes']:
        on, off, note, velocity = item['on'], item['off'], item['note'], item['velocity']
        release_velocity = item.get('note_off_velocity', 0)
        if not (0 <= on < off <= case['duration_seconds'] and 0 <= note <= 127
                and 1 <= velocity <= 127 and int(note) == note and int(velocity) == velocity
                and 0 <= release_velocity <= 127 and int(release_velocity) == release_velocity):
            raise ValueError('Invalid reconstructed note')
        on_tick, off_tick = round(on * 20000), round(off * 20000)
        if off_tick <= on_tick:
            raise ValueError('Note duration vanishes on the MIDI time grid')
        events.extend([(on_tick, 1, bytes([0x90, int(note), int(velocity)])),
                       (off_tick, 0, bytes([0x80, int(note), int(release_velocity)]))])
    if not events:
        raise ValueError('A reconstruction must contain notes')
    name = ('RECONSTRUCTION: ' + case['title']).encode('utf-8')
    track = b'\0\xff\x03' + vlq(len(name)) + name + b'\0\xff\x51\x03\x07\xa1\x20'
    previous = 0
    for tick, _, message in sorted(events):
        track += vlq(tick - previous) + message
        previous = tick
    track += vlq(round(case['duration_seconds'] * 20000) - previous) + b'\xff\x2f\0'
    path.write_bytes(b'MThd' + struct.pack('>IHHH', 6, 0, 1, 10000)
                     + b'MTrk' + struct.pack('>I', len(track)) + track)


def audio_stats(y, sr):
    peak = float(np.max(np.abs(y)))
    rms = float(np.sqrt(np.mean(y.astype(float) ** 2)))
    mid, side = (y[:, 0] + y[:, 1]) / 2, (y[:, 0] - y[:, 1]) / 2
    f, psd = signal.welch(y, sr, nperseg=8192, axis=0)
    spectrum = psd.mean(axis=1)
    band = (f >= 20) & (f <= 16000)
    centroid = float(np.sum(f[band] * spectrum[band]) / max(np.sum(spectrum[band]), 1e-30))
    side_power, mid_power = float(np.mean(side ** 2)), float(np.mean(mid ** 2))
    return {'peak': peak, 'peak_dbfs': 20 * np.log10(max(peak, 1e-15)),
            'rms_dbfs': 20 * np.log10(max(rms, 1e-15)),
            'samples_at_or_above_full_scale': int(np.count_nonzero(abs(y) >= 1)),
            'power_spectral_centroid_20_16000_hz': centroid,
            'identical_stereo_channels': bool(np.array_equal(y[:, 0], y[:, 1])),
            'side_to_mid_db': (10 * np.log10(side_power / mid_power)
                               if side_power > 0 and mid_power > 0 else None)}


def listening_copy(y, target_db=-20):
    rms = np.sqrt(np.mean(y.astype(float) ** 2))
    gain = 10 ** (target_db / 20) / max(rms, 1e-15)
    return y * gain, gain


def plot_comparison(hardware, rendered, sr, directory):
    fig, ax = plt.subplots(3, 1, figsize=(11, 8), layout='constrained')
    plot_data = {'envelope': {}, 'spectrum': {}}
    for y, name, colour in ((hardware, 'Roland hardware demo', '#222222'),
                            (rendered, 'Septum / reconstructed MIDI', '#386a98')):
        # 50 ms exceeds a period of the lowest bass note. These remain RMS
        # traces (including slow offset tails), not isolated amp envelopes.
        window, hop = round(.05 * sr), round(.01 * sr)
        power = np.mean(y.astype(float) ** 2, axis=1)
        envelope = np.sqrt(np.maximum(signal.fftconvolve(power, np.ones(window) / window,
                                                        mode='valid')[::hop], 0))
        t = (np.arange(len(envelope)) * hop + window / 2) / sr
        ax[0].plot(t, 20 * np.log10(np.maximum(envelope, 1e-6)), label=name, color=colour)
        f, p = signal.welch(y, sr, nperseg=8192, axis=0)
        p = p.mean(axis=1)
        ax[1].semilogx(f[1:], 10 * np.log10(np.maximum(p[1:], 1e-15)), color=colour)
        plot_data['envelope'][name] = [t.tolist(), envelope.tolist()]
        plot_data['spectrum'][name] = [f.tolist(), p.tolist()]
    ax[0].set(xlabel='Seconds from excerpt start', ylabel='50 ms RMS / dBFS', ylim=(-65, -5))
    ax[0].legend(frameon=False, loc='lower right')
    ax[1].set(xlabel='Frequency / Hz', ylabel='Power density / dBFS/Hz',
              xlim=(20, 16000), ylim=(-110, -20))
    # Difference of slow spectral envelopes, with each spectrum energy matched.
    f, hp = signal.welch(hardware, sr, nperseg=8192, axis=0)
    _, sp = signal.welch(rendered, sr, nperseg=8192, axis=0)
    edges = np.geomspace(25, 12500, 33)
    centres, differences = [], []
    for low, high in zip(edges[:-1], edges[1:]):
        select = (f >= low) & (f < high)
        h, s = hp[select].sum(), sp[select].sum()
        centres.append(float(np.sqrt(low * high)))
        differences.append(float(10 * np.log10(max(s, 1e-30) / max(h, 1e-30))))
    ax[2].semilogx(centres, differences, color='#386a98')
    ax[2].axhline(0, color='#888888', linewidth=.7)
    ax[2].set(xlabel='Log-band centre / Hz', ylabel='Septum − hardware / dB', xlim=(20,16000))
    for a in ax:
        a.grid(alpha=.18)
    fig.suptitle('Level-matched excerpt comparison — MIDI reconstructed, not original', fontsize=12)
    fig.savefig(directory / 'comparison.png', dpi=150)
    plt.close(fig)
    plot_data['log_band_difference'] = [centres, differences]
    (directory / 'plot-data.json').write_text(json.dumps(plot_data) + '\n')


def render_case(case_path, args, catalog):
    case = json.loads(case_path.read_text())
    if case.get('midi_status') != 'reconstructed_not_original':
        raise ValueError('This tool accepts explicitly labeled reconstructions only')
    start_seconds, duration = case.get('source_start_seconds', 0), case['duration_seconds']
    if not (math.isfinite(start_seconds) and start_seconds >= 0
            and math.isfinite(duration) and 0 < duration <= 600):
        raise ValueError('Excerpt start must be finite and nonnegative; duration must be in (0,600]')
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', case['id']):
        raise ValueError('Case id must be a lowercase slug')
    ref = next(a for a in catalog['recordings'] if a['id'] == case['reference_id'])
    if ref['association_status'] != 'named_patch_on_official_page':
        raise ValueError('A category montage cannot identify a single preset')
    bank = next(a for a in catalog['banks'] if a['id'] == ref['bank_id'])
    for asset in (ref, bank):
        path = args.sources / asset['local_filename']
        if digest(path) != asset['sha256'] or path.stat().st_size != asset['size_bytes']:
            raise ValueError(f'Unverified source: {path}')
    directory = args.output / case['id']
    directory.mkdir(parents=True, exist_ok=False)
    bank_data, member = read_bank(args.sources / bank['local_filename'])
    if member != bank['archive_member'] or hashlib.sha256(bank_data).hexdigest() != bank['bank_sha256']:
        raise ValueError('Extracted librarian bank identity does not match catalog')
    name, blocks = parse_bank(bank_data)[ref['patch_number'] - 1]
    if name != ref['patch_name']:
        raise ValueError('Patch identity does not match reference catalog')
    syx = directory / 'original-patch.syx'
    syx.write_bytes(encode_syx(blocks))
    midi = directory / 'reconstructed-performance.mid'
    write_midi(midi, case)
    raw_render = directory / 'septum-raw.wav'
    subprocess.run([sys.executable, str(ROOT / 'Tools/render_midi.py'),
                    '--renderer', str(args.renderer.resolve()), '--midi', str(midi),
                    '--syx', str(syx), '--output', str(raw_render), '--tail', '2',
                    '--tempo-policy', 'preserve-patch', '--master-level', '100'], check=True)
    hardware_pcm = directory / 'hardware-decoded-full.wav'
    decode_command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
                      '-i', str(args.sources / ref['local_filename']), '-ar', '44100',
                      '-ac', '2', '-c:a', 'pcm_f32le', str(hardware_pcm)]
    subprocess.run(decode_command, check=True)
    sr, hardware_full = wavfile.read(hardware_pcm)
    render_sr, rendered_full = wavfile.read(raw_render)
    if sr != render_sr or sr != 44100:
        raise ValueError('Unexpected sample rate')
    start = round(case.get('source_start_seconds', 0) * sr)
    length = round(case['duration_seconds'] * sr)
    hardware, rendered = hardware_full[start:start + length], rendered_full[:length]
    if len(hardware) != length or len(rendered) != length:
        raise ValueError('Excerpt extends beyond available PCM')
    raw_stats = {'hardware': audio_stats(hardware, sr), 'septum': audio_stats(rendered, sr)}
    hm, hg = listening_copy(hardware)
    sm, sg = listening_copy(rendered)
    # A common extra attenuation preserves relative level if either peaks high.
    shared = min(1., .98 / max(float(np.max(abs(hm))), float(np.max(abs(sm))), 1e-15))
    hm, sm = hm * shared, sm * shared
    wavfile.write(directory / 'hardware-excerpt-raw.wav', sr, hardware.astype(np.float32))
    wavfile.write(directory / 'hardware-listen.wav', sr, hm.astype(np.float32))
    wavfile.write(directory / 'septum-listen.wav', sr, sm.astype(np.float32))
    # Sequential A/B: hardware, half-second silence, Septum. Only edge fades
    # (5 ms) are added here to prevent the excerpt cuts clicking.
    a, b = hm.copy(), sm.copy()
    fade = np.linspace(0, 1, min(221, length // 2))[:, None]
    for y in (a, b):
        y[:len(fade)] *= fade
        y[-len(fade):] *= fade[::-1]
    ab = np.concatenate([a, np.zeros((sr // 2, 2)), b])
    wavfile.write(directory / 'hardware-then-septum.wav', sr, ab.astype(np.float32))
    plot_comparison(hm, sm, sr, directory)
    stats = {'schema_version': 1, 'case': case,
             'qualification': 'same published preset; reconstructed MIDI, not verified original MIDI',
             'reference': ref, 'bank': bank, 'archive_member': member,
             'parameter_modifications': [], 'raw_excerpt_statistics': raw_stats,
             'listening_transform': {'method': 'whole-excerpt RMS matching; no EQ, compression or time warp',
                                     'target_rms_dbfs': -20, 'hardware_gain': float(hg * shared),
                                     'septum_gain': float(sg * shared), 'common_peak_attenuation': shared,
                                     'ab_only_edge_fade_seconds': 221 / sr, 'ab_gap_seconds': .5},
             'alignment': 'transcribed event times on decoded hardware timeline; no post-render alignment',
             'hardware_start_sample': start, 'comparison_frames': length,
             'decode_command': decode_command,
             'retained_engine_latency_samples': json.loads(raw_render.with_suffix('.render.json').read_text())['output']['latency_samples'],
             'catalog_sha256': digest(ROOT / 'Docs/fidelity/hardware-reference-catalog.json'),
             'comparison_limits': catalog['unknowns'] + case['uncertainties'],
             'reconstruction_file_sha256': digest(case_path),
             'runtime': {'python': platform.python_version(), 'numpy': np.__version__,
                         'scipy': scipy.__version__, 'matplotlib': matplotlib.__version__,
                         'ffmpeg': subprocess.check_output(['ffmpeg', '-version'], text=True).splitlines()[0]},
             'source_code_sha256': {str(p.relative_to(ROOT)): digest(p)
                                    for p in sorted((ROOT / 'Source/DSP').glob('*')) if p.is_file()},
             'tool_sha256': {p: digest(ROOT / 'Tools' / p) for p in
                            ('compare_hardware.py', 'render_midi.py', 'RenderMidi.cpp', 'extract_reference_patch.py')},
             'files': {p.name: digest(p) for p in directory.iterdir() if p.is_file()}}
    (directory / 'comparison.json').write_text(json.dumps(stats, indent=2) + '\n')
    return stats


def write_html(results, output):
    sections = []
    for result in results:
        case = result['case']; id_ = html.escape(case['id']); title = html.escape(case['title'])
        notes = ''.join('<p>' + html.escape(note) + '</p>' for note in case['uncertainties'])
        sections.append(f'''<section><h2>{title}</h2>
<p><b>Same published preset · reconstructed MIDI</b> · {case['duration_seconds']:g} seconds</p>
<div class="player" data-root="{id_}">
<button data-play="hardware-listen.wav">Play hardware</button>
<button data-play="septum-listen.wav">Play Septum</button>
<button data-action="stop">Stop</button> <label><input type="checkbox" checked>Match position when switching</label>
<audio controls preload="metadata" src="{id_}/hardware-listen.wav"></audio><p role="status"></p></div>
<details><summary>Reconstruction notes and limits</summary>{notes}</details>
<p><a href="{id_}/hardware-then-septum.wav">Sequential A/B</a> ·
<a href="{id_}/original-patch.syx">Published patch as SysEx</a> ·
<a href="{id_}/reconstructed-performance.mid">Reconstructed MIDI</a> ·
<a href="{id_}/septum-raw.wav">Raw Septum render</a> ·
<a href="{id_}/comparison.json">Provenance and measurements</a> ·
<a href="{result['reference']['source_page_url']}">Roland source page</a></p>
<img src="{id_}/comparison.png" alt="Level-matched envelope and spectral comparison"></section>''')
    page = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SH-201 hardware comparison</title><style>
body{max-width:1050px;margin:45px auto;padding:0 25px;color:#222;background:#fff;font:17px/1.55 system-ui}
h1{font-size:32px;line-height:1.2}h2{font-size:24px}section{border-top:1px solid #aaa;margin-top:40px;padding-top:20px}
a{color:#275679}button{font:inherit;padding:8px 12px;margin:0 8px 8px 0;border:1px solid #777;background:#f4f4f4;cursor:pointer}
button[aria-pressed=true]{background:#222;color:white}audio{display:block;width:100%;margin:15px 0}img{max-width:100%}
label{font-size:14px}p{max-width:90ch}summary{cursor:pointer}details p{font-size:15px}</style><h1>SH-201 hardware comparison</h1>
<p>Official Roland hardware demos compared with Septum playing short audio-derived MIDI reconstructions
and unmodified published Roland presets. No original performance MIDI was found in the audited sources.
These are exploratory listening benchmarks. Timing, velocity, controllers and the recording chain
remain possible causes of differences; the charts do not isolate synthesizer error.</p>
<p>Listening copies match whole-excerpt RMS using scalar gain only. Raw audio and full provenance remain
available. Switching preserves position; oscillator phase is not expected to match.</p>''' + ''.join(sections) + '''
<script>let generation=0;document.querySelectorAll('.player').forEach(p=>{const a=p.querySelector('audio');
const status=p.querySelector('[role=status]');a.addEventListener('play',()=>{
document.querySelectorAll('audio').forEach(x=>{if(x!==a){x.pause();x.onloadedmetadata=null;}})});
a.addEventListener('ended',()=>p.querySelectorAll('[data-play]').forEach(x=>x.setAttribute('aria-pressed',false)));
p.querySelectorAll('[data-play]').forEach(b=>b.onclick=()=>{const t=p.querySelector('input').checked&&!a.ended?a.currentTime:0;
const request=++generation;status.textContent='';document.querySelectorAll('audio').forEach(x=>{x.pause();x.onloadedmetadata=null;});
a.onloadedmetadata=()=>{if(request!==generation)return;a.currentTime=Math.min(t,a.duration||0);
a.play().catch(e=>{if(request===generation)status.textContent='Playback failed: '+e.message;});};
a.onerror=()=>{status.textContent='Unable to decode this audio file.';};a.src=p.dataset.root+'/'+b.dataset.play;
p.querySelectorAll('[data-play]').forEach(x=>x.setAttribute('aria-pressed',x===b));});
p.querySelector('[data-action]').onclick=()=>{++generation;a.onloadedmetadata=null;a.pause();a.currentTime=0;
p.querySelectorAll('[data-play]').forEach(x=>x.setAttribute('aria-pressed',false));};});</script></html>'''
    (output / 'index.html').write_text(page)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', required=True, type=Path)
    parser.add_argument('--renderer', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path, help='new comparison directory')
    parser.add_argument('--case', action='append', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    catalog = json.loads((ROOT / 'Docs/fidelity/hardware-reference-catalog.json').read_text())
    cases = args.case or sorted((ROOT / 'Docs/fidelity/reconstructions/current').glob('*.json'))
    if not cases:
        parser.error('No reconstruction cases supplied')
    results = [render_case(p, args, catalog) for p in cases]
    write_html(results, args.output)
    (args.output / 'summary.json').write_text(json.dumps(results, indent=2) + '\n')
    print(args.output / 'index.html')


if __name__ == '__main__':
    main()
