#!/usr/bin/env python3
"""Render approximate factory-sound recreations with explicitly estimated MIDI.

Uses local, hash-verified Roland MP3s and reviewed case JSON files. Builds
patches through Septum's own codec and renders through its existing MIDI tool.
No downloaded factory-bank data, DSP fitting, or hardware-equivalence claim.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

import numpy as np
from scipy.io import wavfile

from compare_hardware import audio_stats, listening_copy, write_midi
from extract_reference_patch import BLOCK_SIZES
from render_midi import parse_smf

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def validate_case(case):
    if not re.fullmatch(r'factory-preset-[a-d][1-8]', case['id']):
        raise ValueError('Unexpected factory reference identifier')
    if case.get('midi_status') != 'reconstructed_not_original':
        raise ValueError('Every performance must be explicitly estimated')
    for key in ('source_start_seconds', 'duration_seconds'):
        value = case[key]
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError(f'Invalid {key}')
    if not 0 < case['duration_seconds'] <= 60:
        raise ValueError('Use a reviewed excerpt of at most 60 seconds')
    design = case['patch_design']
    if design['status'] != 'approximate_factory_recreation':
        raise ValueError('Preset status must identify an approximate recreation')
    if not re.fullmatch(r'APX [\x20-\x7e]{1,8}', design['name']):
        raise ValueError('Patch names must begin APX and fit 12 ASCII characters')
    if not isinstance(design['base_program'], str):
        raise ValueError('Missing native starting preset')
    for field, value in design['parameters'].items():
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z][A-Za-z0-9]*)*', field):
            raise ValueError('Invalid native patch member path')
        if type(value) not in (bool, int, float) or not math.isfinite(value):
            raise ValueError('Patch values must be finite numbers or booleans')
    if not case.get('method') or not case.get('uncertainties') or not design.get('rationale'):
        raise ValueError('Reconstruction method, rationale and uncertainty are required')


def build_patches(cases, output, library):
    """Compile reviewed numeric member assignments; reject silent range clamps."""
    source = [
        '#include "DSP/SeptumPresets.h"', '#include "DSP/SeptumSysEx.h"',
        '#include <fstream>', '#include <stdexcept>', '#include <iostream>',
        'using namespace septum;',
        'Patch base(const std::string& name) {',
        'if(name=="INIT PATCH") return initPatch();',
        'for(const auto& x: factoryPatches()) if(x.name==name) return x.patch;',
        'throw std::runtime_error("Unknown native base: "+name); }',
        'void write(const std::string& path,const std::vector<std::uint8_t>& data) {',
        'std::ofstream f(path,std::ios::binary); f.write((const char*)data.data(),data.size());',
        'if(!f) throw std::runtime_error("Cannot write patch"); }',
        'int main(int argc,char**argv) { try { if(argc!=2) return 2;',
        'std::string root=argv[1]; std::vector<std::uint8_t> bank;'
    ]
    for index, case in enumerate(cases):
        design = case['patch_design']
        source += ['{', f'auto p=base({json.dumps(design["base_program"])});',
                   f'p.name={json.dumps(design["name"])};']
        for field, value in design['parameters'].items():
            literal = str(int(value)) if isinstance(value, bool) else repr(value)
            source.append(f'p.{field}=static_cast<decltype(p.{field})>({literal});')
        source.append('clampToDocumentedRanges(p);')
        for field, value in design['parameters'].items():
            literal = str(int(value)) if isinstance(value, bool) else repr(value)
            message = json.dumps(f'{case["id"]}: clamped {field}')
            source.append(f'if(static_cast<double>(p.{field})!={literal}) throw std::runtime_error({message});')
        source += ['auto decoded=initPatch();',
                   'for(const auto& packet:sysex::encodePatchToSysExPackets(p))',
                   'if(!sysex::decodeSysExMessage(packet.data(),packet.size(),decoded)) throw std::runtime_error("Patch round trip failed");']
        for field in design['parameters']:
            message = json.dumps(f'{case["id"]}: SysEx cannot preserve {field}')
            source.append(f'if(decoded.{field}!=p.{field}) throw std::runtime_error({message});')
        source += [
            f'write(root+"/{case["id"]}/approximate-patch.syx",sysex::encodePatchToSyxBuffer(p));',
            f'auto bytes=sysex::encodePatchToSyxBuffer(p,sysex::addrUserPatchBase+{index}*sysex::userPatchStride);',
            'bank.insert(bank.end(),bytes.begin(),bytes.end());', '}'
        ]
    source += ['write(root+"/approximate-factory-recreations.syx",bank); return 0;',
               '} catch(const std::exception&e) { std::cerr<<e.what()<<"\\n"; return 1; }}']
    folder = output / 'patch-build'
    folder.mkdir()
    cpp = folder / 'build-patches.cpp'
    cpp.write_text('\n'.join(source) + '\n')
    binary = folder / 'build-patches'
    command = ['c++', '-O2', '-std=c++20', '-I', str(ROOT / 'Source'),
               str(cpp), str(library), '-o', str(binary)]
    run = subprocess.run(command, capture_output=True, text=True)
    (folder / 'build.log').write_text(run.stdout + run.stderr)
    if run.returncode:
        raise RuntimeError(f'Patch construction failed: {folder / "build.log"}')
    subprocess.run([str(binary), str(output)], check=True)
    return {'compiler_command': command, 'library_sha256': digest(library),
            'generated_source_sha256': digest(cpp), 'builder_sha256': digest(binary)}


def validate_syx(path):
    data = path.read_bytes()
    position = 0
    for block, size in enumerate(BLOCK_SIZES):
        message = data[position:position + size + 13]
        if (len(message) != size + 13 or message[:7] != bytes.fromhex('f0411000001612')
                or message[7:11] != bytes((16, 0, block, 0)) or message[-1] != 247
                or any(value > 127 for value in message[1:-1])
                or sum(message[7:-1]) % 128):
            raise ValueError(f'Incomplete or invalid patch block {block}: {path}')
        position += size + 13
    if position != len(data):
        raise ValueError('Trailing patch data')


def render_one(case, ref, output, renderer, ffmpeg):
    folder = output / case['id']
    source = ROOT / ref['audio']['local_path']
    if digest(source) != ref['audio']['sha256'] or source.stat().st_size != ref['audio']['bytes']:
        raise ValueError(f'Hardware source changed: {source}')
    shutil.copyfile(source, folder / 'roland-original.mp3')
    save_json(folder / 'reconstruction.json', case)
    save_json(folder / 'patch-design.json', case['patch_design'])
    patch = folder / 'approximate-patch.syx'
    validate_syx(patch)
    midi = folder / 'estimated-performance.mid'
    write_midi(midi, case)
    parsed = parse_smf(midi.read_bytes())
    note_ons = [e for e in parsed['events'] if e['kind'] == 'midi'
                and e['hex'].startswith('90') and e['hex'][4:] != '00']
    if len(note_ons) != len(case['notes']):
        raise ValueError('Estimated MIDI does not preserve the case note count')
    raw_render = folder / 'septum-raw.wav'
    render_command = [sys.executable, str(ROOT / 'Tools/render_midi.py'),
                      '--renderer', str(renderer), '--midi', str(midi), '--syx', str(patch),
                      '--output', str(raw_render), '--tail', '2', '--tempo-policy',
                      'preserve-patch', '--master-level', '100', '--keyboard-mode']
    rendered = subprocess.run(render_command, capture_output=True, text=True)
    (folder / 'render.log').write_text(rendered.stdout + rendered.stderr)
    if rendered.returncode:
        raise RuntimeError(f'Render failed: {folder / "render.log"}')
    full_hardware = folder / 'hardware-decoded-full.wav'
    subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-i', str(source),
                    '-ar', '44100', '-ac', '2', '-c:a', 'pcm_f32le', str(full_hardware)], check=True)
    sr, hardware = wavfile.read(full_hardware)
    render_sr, software = wavfile.read(raw_render)
    start, length = round(case['source_start_seconds'] * sr), round(case['duration_seconds'] * sr)
    hardware, software = hardware[start:start + length], software[:length]
    if sr != 44100 or render_sr != sr or len(hardware) != length or len(software) != length:
        raise ValueError('Invalid excerpt or sample rate')
    if not np.isfinite(hardware).all() or not np.isfinite(software).all():
        raise ValueError('Non-finite audio')
    if np.sqrt(np.mean(software.astype(float) ** 2)) < 1e-7:
        raise ValueError(f'Silent recreation: {case["id"]}')
    hm, hg = listening_copy(hardware)
    sm, sg = listening_copy(software)
    shared = min(1., .98 / max(float(np.max(abs(hm))), float(np.max(abs(sm)))))
    hm, sm = hm * shared, sm * shared
    wavfile.write(folder / 'hardware-excerpt-raw.wav', sr, hardware.astype(np.float32))
    wavfile.write(folder / 'hardware-listen.wav', sr, hm.astype(np.float32))
    wavfile.write(folder / 'septum-listen.wav', sr, sm.astype(np.float32))
    a, b = hm.copy(), sm.copy()
    fade = np.linspace(0, 1, min(221, length // 2))[:, None]
    for y in (a, b):
        y[:len(fade)] *= fade
        y[-len(fade):] *= fade[::-1]
    wavfile.write(folder / 'hardware-then-septum.wav', sr,
                  np.concatenate([a, np.zeros((sr // 2, 2)), b]).astype(np.float32))
    report = {
        'case': case, 'reference': ref,
        'qualification': 'Approximate factory sound recreation and estimated MIDI; not identical factory data or a controlled DSP fidelity benchmark.',
        'midi_classification': 'ESTIMATED', 'exact_original_performance_midi_available': False,
        'preset_classification': 'APPROXIMATE', 'exact_factory_preset_available': False,
        'raw_statistics': {'hardware': audio_stats(hardware, sr), 'software': audio_stats(software, sr)},
        'listening_transform': {'method': 'Independent whole-excerpt RMS scalar gains, then shared peak attenuation; no EQ, compression or time warp.',
                                'target_rms_dbfs': -20, 'hardware_gain': float(hg * shared),
                                'software_gain': float(sg * shared), 'shared_peak_gain': shared,
                                'sequential_ab_only_fade_samples': len(fade), 'sequential_ab_gap_seconds': .5},
        'alignment': 'Estimated events on the hardware excerpt timeline; engine latency retained; no post-render alignment.',
        'render_manifest': 'septum-raw.render.json',
        'files': {p.name: digest(p) for p in folder.iterdir() if p.is_file()}
    }
    save_json(folder / 'comparison.json', report)
    return report


def write_page(results, output):
    cards = []
    e = html.escape
    for result in results:
        case, ref = result['case'], result['reference']
        id_ = case['id']
        limits = ''.join(f'<li>{e(str(x))}</li>' for x in case['uncertainties'])
        rationale = ''.join(f'<li>{e(str(x))}</li>' for x in case['patch_design']['rationale'])
        cards.append(f'''<section id="{id_}"><p class="slot">FACTORY TARGET · {e(ref['factory_preset']['slot'])}</p>
<h2>{e(ref['name'])}</h2><p class="badge">Preset: APPROXIMATE · MIDI: ESTIMATED</p>
<p>{case['duration_seconds']:g}s excerpt from {case['source_start_seconds']:g}s · {len(case['notes'])} estimated note events</p>
<div class="player" data-root="{id_}"><button data-play="hardware-listen.wav">A · Roland hardware</button>
<button data-play="septum-listen.wav">B · Septum recreation</button><button data-stop>Stop</button>
<audio controls preload="none" src="{id_}/hardware-listen.wav" aria-label="{e(ref['name'])} comparison"></audio><p role="status"></p></div>
<p class="links"><a href="{id_}/estimated-performance.mid" download>Estimated MIDI</a> ·
<a href="{id_}/approximate-patch.syx" download>Approximate preset (SysEx)</a> ·
<a href="{id_}/hardware-then-septum.wav">Sequential A/B</a> ·
<a href="{id_}/septum-raw.wav">Raw render</a> · <a href="{id_}/roland-original.mp3">Full Roland demo</a> ·
<a href="{id_}/comparison.json">Provenance</a></p>
<details><summary>How this was reconstructed</summary><p>{e(case['method'])}</p><ul>{limits}</ul>
<h3>Approximate preset design</h3><ul>{rationale}</ul><a href="{id_}/patch-design.json">Parameter recipe</a></details></section>''')
    page = '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SH-201 factory sound recreations</title>
<style>:root{color-scheme:dark}body{max-width:1080px;margin:40px auto;padding:0 24px;background:#111916;color:#ecf1e8;font:16px/1.6 system-ui}h1{font-size:clamp(30px,5vw,48px);line-height:1.15;letter-spacing:-.035em}h2{font-size:27px;margin:0 0 8px}.intro{max-width:850px;color:#b9c9bf}.warning{background:#30291b;border:1px solid #7b613a;border-radius:10px;padding:18px 22px;margin:24px 0;color:#f2d7a6}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}section{padding:24px;border:1px solid #39473e;border-radius:12px;background:#17211c;min-width:0}.slot{font-size:12px;letter-spacing:.1em;color:#bdda9d;margin:0 0 5px}.badge{font-size:13px;color:#f4d08f;font-weight:650}button{padding:9px 12px;font:inherit;font-size:13px;border:1px solid #708367;border-radius:6px;background:#283629;color:#edf4df;margin:0 5px 8px 0;cursor:pointer}button[aria-pressed=true]{background:#d5e8a6;color:#162013}audio{display:block;width:100%;margin-top:8px}a{color:#c3dba4;text-underline-offset:3px}.links,details{font-size:13px}.links{line-height:1.9}details{border-top:1px solid #39473e;padding-top:12px}summary{cursor:pointer}ul{padding-left:20px}li{margin-bottom:8px}[role=status]{font-size:12px;color:#ecca8b}footer{padding:30px 0;color:#bac9bd}@media(max-width:800px){.grid{grid-template-columns:1fr}body{padding:0 16px;margin-top:25px}}:focus-visible{outline:2px solid #e2eca4;outline-offset:4px}</style></head><body>
<p class="slot">ROLAND SH-201 / SEPTUM</p><h1>Factory sound recreations</h1>
<p class="intro">__COUNT__ factory targets, recreated with Septum's current synthesis engine. Switch A/B at the same playback position. Each pair uses the same excerpt length and estimated musical phrase.</p>
<div class="warning"><strong>All presets are APPROXIMATE. All performance MIDI is ESTIMATED.</strong>
<p>No authentic factory patch dump or original performance MIDI was available. These are listening experiments with independently authored presets, not exact factory replicas. Arpeggiated output notes, uncertain chord voicings and assumed effect triggers are explained on each card.</p></div>
<p class="intro">Whole-excerpt RMS levels are matched with gain only. Raw renders and recipes are included. Preset, MIDI and recording-chain differences all affect the result; this comparison cannot isolate engine fidelity.</p>
<p><a href="sh201-factory-recreations.zip" download>Download all audio, approximate presets and estimated MIDI</a> · <a href="approximate-factory-recreations.syx" download>Approximate 17-sound SysEx bank</a></p>
<div class="grid">__CARDS__</div><footer>Hardware source: <a href="https://www.roland.com/global/products/sh-201/">Roland SH-201 audio library</a> · <a href="dataset-manifest.json">Dataset manifest</a></footer>
<script>let generation=0;document.querySelectorAll('.player').forEach(p=>{const a=p.querySelector('audio'),s=p.querySelector('[role=status]');
const clear=()=>p.querySelectorAll('[data-play]').forEach(b=>b.setAttribute('aria-pressed','false'));
const sync=()=>p.querySelectorAll('[data-play]').forEach(b=>b.setAttribute('aria-pressed',String(!a.paused&&!a.ended&&a.getAttribute('src')===p.dataset.root+'/'+b.dataset.play)));
a.addEventListener('play',()=>document.querySelectorAll('audio').forEach(x=>{if(x!==a){x.pause();x.onloadedmetadata=null;}}));
a.addEventListener('play',sync);a.addEventListener('pause',sync);
a.addEventListener('ended',clear);a.addEventListener('error',()=>{s.textContent='Audio could not be loaded.';});
p.querySelectorAll('[data-play]').forEach(b=>b.onclick=()=>{const t=a.ended?0:a.currentTime,request=++generation;
document.querySelectorAll('audio').forEach(x=>{x.pause();x.onloadedmetadata=null;});s.textContent='';
a.onloadedmetadata=()=>{if(request!==generation)return;a.currentTime=Math.min(t,Math.max(0,a.duration-.001));a.play().catch(e=>{if(request===generation)s.textContent=e.message;});};
a.preload='auto';a.src=p.dataset.root+'/'+b.dataset.play;a.load();clear();});
p.querySelector('[data-stop]').onclick=()=>{++generation;a.onloadedmetadata=null;a.pause();a.currentTime=0;clear();};});</script></body></html>'''
    (output / 'index.html').write_text(page.replace('__COUNT__', str(len(results))).replace('__CARDS__', '\n'.join(cards)).replace('Approximate 17-sound', f'Approximate {len(results)}-sound'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path, help='New output directory')
    parser.add_argument('--renderer', type=Path, default=ROOT / 'build-fidelity/SeptumRenderMidi')
    parser.add_argument('--dsp-library', type=Path, default=ROOT / 'build-fidelity/libSeptumDSP.a')
    parser.add_argument('--case', type=Path, action='append')
    args = parser.parse_args()
    case_paths = args.case or sorted((ROOT / 'Docs/fidelity/reconstructions/factory').glob('*.json'))
    if not case_paths or len(case_paths) > 32:
        parser.error('Provide 1–32 reviewed reconstruction cases')
    cases = [json.loads(path.read_text()) for path in case_paths]
    for case in cases:
        validate_case(case)
    if len({c['id'] for c in cases}) != len(cases):
        raise ValueError('Duplicate reconstruction identifiers')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    for case in cases:
        (output / case['id']).mkdir()
    renderer, library = args.renderer.resolve(), args.dsp_library.resolve()
    identities = {str(p.relative_to(ROOT)): digest(p) for p in sorted((ROOT / 'Source/DSP').glob('*')) if p.is_file()}
    identities[str(renderer)] = digest(renderer)
    identities[str(library)] = digest(library)
    build = build_patches(cases, output, library)
    catalog = json.loads((ROOT / 'Docs/fidelity/factory-recordings.json').read_text())
    results = []
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise ValueError('FFmpeg is required')
    for case in cases:
        ref = next(r for r in catalog['recordings'] if r['id'] == case['reference_id'])
        results.append(render_one(case, ref, output, renderer, ffmpeg))
        print(f'{case["id"]}: rendered {len(case["notes"])} estimated notes', flush=True)
    write_page(results, output)
    for path, expected in identities.items():
        if digest(ROOT / path) != expected:
            raise ValueError(f'Input changed during rendering: {path}')
    manifest = {'schema_version': 1, 'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'case_count': len(results), 'midi_classification': {'exact': 0, 'estimated': len(results)},
                'preset_classification': {'exact_factory': 0, 'approximate': len(results)},
                'shipping_dsp_modified': False, 'build': build, 'source_sha256': identities,
                'tool_sha256': {name: digest(ROOT / 'Tools' / name) for name in ['recreate_factory_demos.py', 'compare_hardware.py', 'render_midi.py']},
                'catalog_sha256': digest(ROOT / 'Docs/fidelity/factory-recordings.json'),
                'cases': [{'id': r['case']['id'], 'name': r['reference']['name'], 'duration_seconds': r['case']['duration_seconds'],
                           'note_count': len(r['case']['notes']), 'report': r['case']['id'] + '/comparison.json'} for r in results],
                'files': {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob('*'))
                          if p.is_file() and p.name != 'build-patches'}}
    save_json(output / 'dataset-manifest.json', manifest)
    archive = output / 'sh201-factory-recreations.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(output.rglob('*')):
            if path.is_file() and path != archive and path.name != 'build-patches':
                bundle.write(path, path.relative_to(output))
    print(json.dumps({'output': str(output), 'cases': len(results), 'archive_bytes': archive.stat().st_size}))


if __name__ == '__main__':
    main()
