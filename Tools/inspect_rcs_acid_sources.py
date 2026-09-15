#!/usr/bin/env python3
"""Inspect the creator-published RCS Acid SHE files and associated source audio.

This is a source-only feasibility audit. It neither renders Septum nor treats
the downloaded presets as authenticated captures of the recording state.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal
from scipy.io import wavfile
from extract_reference_patch import BLOCK_SIZES, encode_syx

ZIP_HASH = 'c713703c0fc3b548135f8a8cc5a66d63e6d41e5ec7aac420c65d088983c316b6'
XML_HASH = '758f8e3ee019eb99678bda29af1d80e2c09353493dc65c659d5ff25f89de085d'
EDITOR_FILES = {
    'Resource.xml.utf8.txt': 'bfb6c0f9a1c8cdd1d0b5047bb9701798bc7150e28f4e751690329b6e698d5e5c',
    'PatchLfo.xml.utf8.txt': '538694059dd7b563c37e471c790620eb5a54f28a663eecb22f3729b44a185a02'}
MEDIA_FILES = {
    '7jW2GIgOOv8.m4a': '7b0e82d0f0edd1ad7ca43d1aadf44485aa6ab3ef59d2dcdfac20526d0f0d7dcf',
    '7jW2GIgOOv8.info.json': 'd6eda4192d528a52ab05e60c0c5f9fbe4ab0b78b87e43478adbf0e9020aef827',
    '7jW2GIgOOv8-video.mp4': 'c3eb7568c1fa4e9e77ddaa0facc6ed58564c45b634b0dc91fae5d0a3c1f1bd07',
    '7jW2GIgOOv8-video.info.json': 'a79c6a47a922f1bff5050b40a9a82b97186714dbb5a1a1be0c0dd38f149c56bc'}
TYPES = ['PatchCommon', 'PatchTone', 'PatchTone', 'PatchDelay',
         'PatchReverb', 'PatchArpeggioCommon'] + ['PatchArpeggioPattern'] * 16


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def address(value):
    n = 0
    for byte in value.split():
        n = (n << 7) + int(byte, 16)
    return n


def decode_fields(data, struct):
    result, anomalies = {}, []
    for field in struct.findall('value'):
        offset, size = address(field.findtext('address')), address(field.findtext('size'))
        raw = data[offset:offset + size]
        if len(raw) != size:
            raise ValueError('Truncated schema field')
        kind, name = field.findtext('type'), field.findtext('name')
        if kind == 'string':
            value = raw.decode('ascii').rstrip(' \0')
        elif kind == 'int1x7':
            if size != 1:
                raise ValueError('Unexpected seven-bit integer width')
            value = raw[0]
        elif kind in ('int2x4', 'int3x4', 'int4x4'):
            if any(x > 15 for x in raw):
                raise ValueError('Non-nibble value in packed integer')
            value = 0
            for x in raw:
                value = (value << 4) | x
        else:
            raise ValueError('Unsupported official schema field: ' + kind)
        bounds = field.findtext('range')
        if bounds:
            low, high = map(int, bounds.split(','))
            if not low <= value <= high:
                anomalies.append(dict(field=name, value=value, declared_range=[low, high]))
        result[name] = value
    return result, anomalies


def official_lfo_tables(directory):
    for name, expected in EDITOR_FILES.items():
        if sha(directory/name) != expected:
            raise ValueError('Previously audited official LFO resource changed: '+name)
    def xml(name):
        return ET.fromstring((directory/name).read_text().replace('encoding="Shift_JIS"', 'encoding="UTF-8"'))
    resource = xml('Resource.xml.utf8.txt')
    tables = {t.findtext('name'): [v.strip() for v in t.findtext('table').split(',')]
              for t in resource.findall('stringTable')}
    expected = dict(lfoDestination1Table=['PITCH1','PW1','FILTER','AUDIO-FIL'],
                    lfoDestination2Table=['PITCH2','PW2','AMP'],
                    lfoWaveFormTable=['TRI','SIN','SAW','SQR','TRP','S&H','RANDOM'])
    panel = xml('PatchLfo.xml.utf8.txt')
    controls = {c.findtext('name'): c for c in panel.iter('control')}
    for key, values in expected.items():
        if tables[key] != values:
            raise ValueError('Official LFO enum order changed')
    for dest in (1,2):
        key = f'lfoDestination{dest}'
        control = controls[key+'-comboButton']
        if control.findtext('stringTableRef') != key+'Table' or not control.findtext('valueRef').endswith(key+'[$id]'):
            raise ValueError('Official destination binding changed')
        if controls[f'lfoDepth{dest}-staticTextPicture'].findtext('offsetValue') != '-64':
            raise ValueError('Official signed depth offset changed')
    return expected


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sources', type=Path, required=True)
    p.add_argument('--editor-xml', type=Path, required=True,
                   help='Audited BufferModel XML reading copy; sibling Resource and PatchLfo reading copies are required')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    archive = a.sources / 'rcs-acid-original.zip'
    if sha(archive) != ZIP_HASH or sha(a.editor_xml) != XML_HASH:
        raise ValueError('Original archive or previously audited official XML changed')
    lfo_tables = official_lfo_tables(a.editor_xml.parent)
    for name, expected in MEDIA_FILES.items():
        if sha(a.sources/name) != expected:
            raise ValueError('Original creator media identity changed: '+name)
    tree = ET.fromstring(a.editor_xml.read_text().replace('encoding="Shift_JIS"', 'encoding="UTF-8"'))
    schema = {s.findtext('type'): s for s in tree.findall('structType')}
    if address(schema['SystemCommon'].findtext('size')) != 29:
        raise ValueError('Unexpected System size')
    if [address(schema[t].findtext('size')) for t in TYPES] != list(BLOCK_SIZES):
        raise ValueError('Official schema disagrees with the audited MIDI block sizes')
    rows = []
    with zipfile.ZipFile(archive) as z:
        members = sorted(n for n in z.namelist() if n.endswith('.she'))
        if len(members) != 9:
            raise ValueError('Expected all nine creator presets')
        for name in members:
            raw = z.read(name)
            if (len(raw) != 256 + 29 + sum(BLOCK_SIZES)
                    or raw[:16] != b'KoaDataFile00001'
                    or raw[16:80].rstrip(b' ') != b'fm'
                    or raw[80:96].rstrip(b' ') != b'SH-201'
                    or any(raw[96:256]) or any(x > 127 for x in raw[256:])):
                raise ValueError('Unexpected observed SHE layout: ' + name)
            system, anomalies = decode_fields(raw[256:285], schema['SystemCommon'])
            pos, blocks, fields = 285, [], []
            for size, kind in zip(BLOCK_SIZES, TYPES):
                block = raw[pos:pos + size]
                pos += size
                decoded, invalid = decode_fields(block, schema[kind])
                anomalies.extend(dict(block=len(blocks), **v) for v in invalid)
                blocks.append(block)
                fields.append(decoded)
            if pos != len(raw) or anomalies:
                raise ValueError('Schema validation failed: ' + repr(anomalies))
            syx = encode_syx(blocks)
            destination = a.output / (Path(name).stem + '.syx')
            destination.write_bytes(syx)
            rows.append(dict(member=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                sysEx_sha256=sha(destination), native_block_sizes=list(BLOCK_SIZES),
                schema_range_anomalies=anomalies, system=system,
                common=fields[0], upper=fields[1], lower=fields[2], delay=fields[3],
                reverb=fields[4], arpeggio=fields[5],
                official_lfo_labels={part: [dict(
                    waveform=lfo_tables['lfoWaveFormTable'][tone[f'lfoType[{i}]']],
                    destination1=lfo_tables['lfoDestination1Table'][tone[f'lfoDestination1[{i}]']],
                    depth1=tone[f'lfoDepth1[{i}]']-64,
                    destination2=lfo_tables['lfoDestination2Table'][tone[f'lfoDestination2[{i}]']],
                    depth2=tone[f'lfoDepth2[{i}]']-64,
                    rate_raw=tone[f'lfoRate[{i}]'], key_trigger=tone[f'lfoKeyTrigger[{i}]'],
                    tempo_sync=tone[f'lfoTempoSyncSwitch[{i}]']) for i in (0,1)]
                    for part,tone in [('upper',fields[1]),('lower',fields[2])]},
                interpretation='Observed packed container layout, validated against every official field range; not an Editor export round-trip.'))
    audio = a.sources / '7jW2GIgOOv8.m4a'
    metadata = a.sources / '7jW2GIgOOv8.info.json'
    info = json.loads(metadata.read_text())
    if info['id'] != '7jW2GIgOOv8':
        raise ValueError('Different creator recording')
    decoded = a.output / 'source-full.wav'
    command = ['ffmpeg', '-v', 'error', '-i', str(audio), '-c:a', 'pcm_f32le', str(decoded)]
    subprocess.run(command, check=True)
    rate, stereo = wavfile.read(decoded)
    if rate != 44100 or stereo.ndim != 2 or stereo.shape[1] != 2 or not np.isfinite(stereo).all():
        raise ValueError('Unexpected source audio format')
    f, t, spectrum = signal.spectrogram(stereo, rate, window='hann', nperseg=8192,
        noverlap=8192-2205, detrend=False, scaling='density', axis=0)
    spectrum = spectrum.mean(axis=1)  # Stereo powers, avoiding downmix cancellation.
    band = (f >= 30) & (f <= 12000)
    hop = 441
    times = np.arange(len(stereo)//hop) * .01
    rms = np.sqrt(np.mean(stereo[:len(times)*hop].reshape(-1, hop, 2)**2, axis=(1,2)))
    fig, axes = plt.subplots(2, 1, figsize=(15, 7), constrained_layout=True, sharex=True)
    axes[0].plot(times, 20*np.log10(np.maximum(rms, 1e-8)), linewidth=.65)
    axes[0].set(ylabel='10 ms stereo RMS / dBFS', ylim=(-90, 0), title='RCS SH-201 Acid demo: source-only overview')
    axes[1].pcolormesh(t, f[band], 10*np.log10(np.maximum(spectrum[band], 1e-14)),
        shading='auto', cmap='magma', vmin=-100, vmax=-30)
    axes[1].set(xlabel='Original recording clock / s', ylabel='Hz', yscale='log', ylim=(30, 12000))
    fig.savefig(a.output/'source-overview.png', dpi=140)
    plt.close(fig)
    receipt = dict(status='source_only_feasibility_not_a_hardware_match', tool_sha256=sha(__file__),
        helper_sha256=sha(Path(__file__).with_name('extract_reference_patch.py')),
        original_media_sha256=MEDIA_FILES,
        decoder=dict(path=shutil.which('ffmpeg'), sha256=sha(shutil.which('ffmpeg')),
            version=subprocess.check_output(['ffmpeg','-version'], text=True).splitlines()[0]),
        archive=dict(url='https://www.rcssound.com/download.php?kod=8', sha256=sha(archive)),
        creator_page='https://www.rcssound.com/index.php?page=8',
        video=dict(url=info['webpage_url'], title=info['title'], upload_date=info['upload_date'],
            format_id='140', audio_sha256=sha(audio), metadata_sha256=sha(metadata),
            decode_command=command, decoded_sha256=sha(decoded), rate=rate, frames=len(stereo)),
        official_editor=dict(url='https://static.roland.com/assets/media/dmg/SH201_Editor110_osx.dmg',
            xml_reading_copy_sha256=sha(a.editor_xml), provenance='Docs/fidelity/source-audits/oscillator-semantics.md'),
        official_lfo_resources=dict(sha256=EDITOR_FILES, tables=lfo_tables,
            binding='PatchLfo destination combo controls bind raw fields directly to Resource enum tables; displayed depths use offset -64.'),
        presets=rows, arp_all_off=all(r['common']['arpeggioSwitch']==0 for r in rows),
        limits=['No performed MIDI is included in the archive.',
            'The numbered video cards associate patches with passages but do not display live controls.',
            'No exact recorded patch revision, processing chain, or controller state is authenticated.',
            'Published description says eight patches, title/archive and video cards contain nine.'])
    (a.output/'results.json').write_text(json.dumps(receipt, indent=2, allow_nan=False)+'\n')
    print(a.output/'results.json')


if __name__ == '__main__':
    main()
