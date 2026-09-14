#!/usr/bin/env python3
"""Download and organize free Roland SH-201 patches for local use in Septum.

The repository contains the acquisition recipe, not the third-party patches.
Original parameter bytes are preserved in SysEx alongside native conversions.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
from urllib.parse import quote
import zipfile

from extract_reference_patch import BLOCK_SIZES, HEADER_SIZE, encode_syx, parse_bank, read_bank

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = {'bass': 'Bass', 'lead': 'Leads', 'pad': 'Pads', 'fx': 'Effects'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def safe_name(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    return re.sub(r'\s+', ' ', name).strip().rstrip('. ') or 'Unnamed'


def subcategories(data, count):
    """Read the observed category/comment suffix after validated sound blocks."""
    position, result = HEADER_SIZE, []
    for _ in range(count):
        size = struct.unpack_from('>I', data, position)[0]
        start, end = position + 4, position + 4 + size
        metadata = data[start + sum(BLOCK_SIZES) + 4 * len(BLOCK_SIZES):end]
        # These pinned banks use a printable category followed by four zero
        # bytes (empty librarian comment). Fail closed on a different layout.
        if not metadata.endswith(b'\0' * 4):
            raise ValueError('Unrecognized librarian category/comment suffix')
        label = metadata[:-4].decode('ascii')
        if not label or len(label) > 64 or any(ord(c) < 32 for c in label):
            raise ValueError('Invalid librarian category label')
        result.append(label)
        position = end
    return result


def download(asset, cache):
    path = cache / asset['local_filename']
    if Path(asset['local_filename']).name != asset['local_filename']:
        raise ValueError('Source filenames must be simple basenames')
    def valid(p):
        return p.is_file() and p.stat().st_size == asset['size_bytes'] and sha(p.read_bytes()) == asset['sha256']
    if not valid(path):
        with tempfile.TemporaryDirectory(dir=cache) as temporary:
            candidate = Path(temporary) / path.name
            subprocess.run(['curl', '--fail', '--location', '--silent', '--show-error',
                            '--retry', '2', '--connect-timeout', '15', '--max-time', '90',
                            '--output', str(candidate), asset['url']], check=True)
            if not valid(candidate):
                raise ValueError(f'Source changed; review before updating its hash: {path.name}')
            candidate.replace(path)
    return path


def validate_syx(data, source_blocks):
    position = 0
    for block, payload in enumerate(source_blocks):
        message = data[position:position + len(payload) + 13]
        if (message[:7] != bytes.fromhex('f0411000001612')
                or message[7:11] != bytes((16, 0, block, 0))
                or message[11:-2] != payload or message[-1] != 247
                or sum(message[7:-1]) % 128):
            raise ValueError('Generated SysEx differs from the source parameter blocks')
        position += len(payload) + 13
    if position != len(data):
        raise ValueError('Unexpected trailing SysEx data')


def write_index(output, patches):
    e = html.escape
    groups = defaultdict(lambda: defaultdict(list))
    for patch in patches:
        groups[patch['category']][patch['subcategory']].append(patch)
    cards = []
    for category, subgroups in groups.items():
        sections = []
        for subcategory, entries in sorted(subgroups.items()):
            rows = []
            for patch in entries:
                rows.append(f'<li><span>{patch["source_number"]:03d} · {e(patch["name"])}</span>'
                            f'<a download href="{quote(patch["native_file"])}">Septum</a>'
                            f'<a download href="{quote(patch["sysex_file"])}">SysEx</a></li>')
            sections.append(f'<details><summary>{e(subcategory)} <small>{len(entries)}</small></summary>'
                            f'<ul>{"".join(rows)}</ul></details>')
        cards.append(f'<section><h2>{category} <small>{sum(map(len, subgroups.values()))}</small></h2>'
                     f'<details><summary>Browse {len(subgroups)} sound types</summary>'
                     f'{"".join(sections)}</details></section>')
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>SH-201 free preset collection</title><style>
:root{color-scheme:dark}body{max-width:1050px;margin:48px auto;padding:0 24px;background:#141a17;color:#ecf1e8;font:16px/1.6 system-ui}h1{font-size:42px;line-height:1.15}h2{margin-top:0}a{color:#c5dfa8}p{max-width:850px;color:#c4cdc6}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;align-items:start}section{padding:24px;border:1px solid #455145;border-radius:12px;background:#1c261e}small{color:#b6c6b6;font-size:14px;margin-left:8px}details{border-top:1px solid #455145;padding:12px 0}summary{cursor:pointer}ul{list-style:none;padding:0;font-size:14px}li{display:flex;gap:12px;padding:5px 0}li span{flex:1;min-width:0}footer{margin:30px 0;font-size:13px}@media(max-width:750px){.grid{grid-template-columns:1fr}h1{font-size:32px}}
</style><body><h1>SH-201 free preset collection</h1>
<p>400 downloadable Roland patches, organized into Bass, Leads, Pads and Effects, with the original sound-type labels used as subfolders.</p>
<p>In Septum, click <strong>Load</strong> and choose a <strong>.septum</strong> file. The complete download includes the matching source SysEx and original Roland bank files.</p>
<p><a href="../__ARCHIVE__" download>Download all 400 presets</a> · <a href="README.md">Usage and source notes</a> · <a href="manifest.json">Catalog and provenance</a></p>
<div class="grid">__CARDS__</div><footer>Roland SH-201 Patch 100 sources: <a href="https://www.rolandus.com/go/sh-201_patches/patch_bass.html">Bass</a> · <a href="https://www.rolandus.com/go/sh-201_patches/patch_lead.html">Leads</a> · <a href="https://www.rolandus.com/go/sh-201_patches/patch_pad.html">Pads</a> · <a href="https://www.rolandus.com/go/sh-201_patches/patch_fx.html">Effects</a>. Additional published patches; not the hardware factory bank. Original SysEx payloads are preserved; the native conversion report identifies any representation differences.</footer></body></html>'''
    (output / 'index.html').write_text(page.replace('__CARDS__', ''.join(cards)).replace('__ARCHIVE__', quote(output.name + '.zip')), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'out/presets/SH-201 Patch 100')
    parser.add_argument('--cache', type=Path, default=ROOT / 'out/preset-source-cache')
    parser.add_argument('--catalog', type=Path, default=ROOT / 'Docs/presets/free-sh201-sources.json')
    parser.add_argument('--converter', type=Path, default=ROOT / 'build-fidelity/SeptumConvertPresets')
    args = parser.parse_args()
    output, cache, converter = args.output.resolve(), args.cache.resolve(), args.converter.resolve()
    archive = output.with_name(output.name + '.zip')
    if output.exists() or archive.exists():
        parser.error('Choose a new output directory and archive name; existing packs are never overwritten')
    if not converter.is_file():
        parser.error('Build SeptumConvertPresets first or pass --converter')
    catalog = json.loads(args.catalog.read_text())
    assets = catalog['banks']
    if {a['id'] for a in assets} != set(CATEGORIES) or len(assets) != 4:
        raise ValueError('Expected exactly the four reviewed Patch 100 banks')
    cache.mkdir(parents=True, exist_ok=True)
    sources = {a['id']: download(a, cache) for a in assets}
    output.mkdir(parents=True)
    source_folder = output / 'Sources'
    source_folder.mkdir()
    patches, conversions = [], []
    seen_paths = set()
    for asset in sorted(assets, key=lambda a: list(CATEGORIES).index(a['id'])):
        original = sources[asset['id']]
        data, member = read_bank(original)
        if member != asset['archive_member'] or sha(data) != asset['bank_sha256']:
            raise ValueError('Unexpected source librarian bank')
        bank = parse_bank(data)
        if len(bank) != 100:
            raise ValueError('Expected 100 source patches')
        labels = subcategories(data, len(bank))
        shutil.copyfile(original, source_folder / original.name)
        for number, ((name, blocks), label) in enumerate(zip(bank, labels), 1):
            relative = Path(CATEGORIES[asset['id']]) / safe_name(label) / f'{number:03d} {safe_name(name)}'
            native = output / (str(relative) + '.septum')
            syx_path = output / 'SysEx' / (str(relative) + '.syx')
            if str(relative).casefold() in seen_paths:
                raise ValueError('Colliding preset filenames')
            seen_paths.add(str(relative).casefold())
            native.parent.mkdir(parents=True, exist_ok=True)
            syx_path.parent.mkdir(parents=True, exist_ok=True)
            syx = encode_syx(blocks)
            validate_syx(syx, blocks)
            syx_path.write_bytes(syx)
            conversions.append({'input': str(syx_path), 'output': str(native)})
            patches.append({'id': f'{asset["id"]}-{number:03d}', 'name': name,
                            'category': CATEGORIES[asset['id']], 'subcategory': label,
                            'category_source': 'Original Roland bank and librarian memo',
                            'source_bank': asset['id'], 'source_number': number,
                            'source_parameter_sha256': sha(b''.join(blocks)),
                            'sound_sha256_without_name': sha(blocks[0][12:] + b''.join(blocks[1:])),
                            'sysex_file': syx_path.relative_to(output).as_posix(),
                            'native_file': native.relative_to(output).as_posix(),
                            'source_parameter_bytes_preserved_in_sysex': True})
    write_json(output / 'conversion-inputs.json', conversions)
    result = subprocess.run([str(converter), '--manifest', str(output / 'conversion-inputs.json')], capture_output=True, text=True)
    (output / 'conversion.log').write_text(result.stderr, encoding='utf-8')
    if result.returncode:
        raise RuntimeError('Native conversion failed: ' + result.stderr[-2000:])
    conversion_report = json.loads(result.stdout)
    write_json(output / 'native-conversion-report.json', conversion_report)
    reports = {r['output']: r for r in conversion_report['conversions']}
    if len(reports) != len(patches):
        raise ValueError('Converter did not report every preset exactly once')
    for patch in patches:
        converted = reports[str(output / patch['native_file'])]
        if not converted['native_roundtrip_verified'] or not converted['arpeggio_grid_verified']:
            raise ValueError('Native reload or arpeggio verification failed')
        patch['native_parameter_normalizations'] = converted['source_parameter_differences']
        patch['native_roundtrip_verified'] = True
        for key in ('native_file', 'sysex_file'):
            path = output / patch[key]
            if not path.is_file() or not path.stat().st_size:
                raise ValueError('Missing converted file: ' + str(path))
            patch[key.replace('_file', '_sha256')] = sha(path.read_bytes())
    sound_groups = defaultdict(list)
    for patch in patches:
        sound_groups[patch['sound_sha256_without_name']].append(patch['id'])
    manifest = {'schema_version': 1, 'collection': 'Roland SH-201 Patch 100', 'patch_count': len(patches),
                'category_counts': dict(Counter(p['category'] for p in patches)),
                'source_catalog': catalog, 'patches': patches,
                'native_presets_with_normalized_parameters': sum(bool(p['native_parameter_normalizations']) for p in patches),
                'identical_sound_groups': [g for g in sound_groups.values() if len(g) > 1],
                'converter_sha256': sha(converter.read_bytes()),
                'builder_sha256': sha(Path(__file__).read_bytes()),
                'native_conversion_report': 'native-conversion-report.json',
                'factory_bank': False, 'shipping_programs_changed': False}
    write_json(output / 'manifest.json', manifest)
    readme = '''# Roland SH-201 Patch 100 for Septum

400 free-to-download additional Roland patches, organized by the original bank categories and librarian sound-type labels.

## Load a preset

Use Septum's **Load** button and choose a `.septum` file under **Bass**, **Leads**, **Pads** or **Effects**. Each folder contains sound-type subfolders. The leading number preserves the original bank position. System settings use Septum's defaults; the converted file saves the imported patch and arpeggio grid.

Matching `.syx` files under **SysEx** preserve all 22 source parameter blocks exactly. **Sources** contains the untouched Roland ZIPs, each with its original librarian bank and patch-list PDF. These are additional published sounds, not factory presets and not manually recreated patches.

## Conversion details

The native converter validates each import, saves through Septum's own preset API, reloads it and verifies the native patch and complete arpeggio grid. Native fields use Septum's current representation: some source coarse-tuning knob positions normalize to integer semitones. `native-conversion-report.json` records these differences. The source SysEx remains unchanged. Software playback is not a claim of hardware audio equivalence.

## Sources

Downloaded directly from Roland's SH-201 Patch 100 pages. `manifest.json` records source URLs, hashes, names, categories and output hashes. Roland did not identify individual designers in these four downloads. These files remain third-party data; this local collection does not place them under Septum's source-code license. The inspected downloads provide no separate public software-redistribution grant.

Open `index.html` for a browsable catalog. This pack does not replace Septum's built-in programs.
'''
    (output / 'README.md').write_text(readme, encoding='utf-8')
    write_index(output, patches)
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(output.rglob('*')):
            if path.is_file():
                bundle.write(path, (Path(output.name) / path.relative_to(output)).as_posix())
    print(json.dumps({'output': str(output), 'archive': str(archive), 'patches': len(patches),
                      'categories': manifest['category_counts'], 'archive_bytes': archive.stat().st_size}))


if __name__ == '__main__':
    main()
