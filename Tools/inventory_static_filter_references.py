#!/usr/bin/env python3
"""Inventory the 24 named factory recordings using the current C++ SysEx codec.

Requires local originals pinned by hardware-reference-catalog.json. Never
modifies their parameters. This is a source-selection audit, not a cutoff fit.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from extract_reference_patch import encode_syx, parse_bank, read_bank

ROOT = Path(__file__).resolve().parents[1]
WAVES = ('Saw', 'Square', 'Pulse', 'Triangle', 'Sine', 'Noise',
         'Feedback', 'SuperSaw', 'ExternalInput')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(path, expected):
    actual = sha(path)
    if actual != expected:
        raise ValueError(f'Original hash mismatch: {path}')
    return actual


def annotate(tone, raw, common):
    for osc, offset in (('osc1', 0), ('osc2', 6)):
        o = tone[osc]
        o['wave_name'] = WAVES[o['wave']]
        o['signed_coarse_raw'] = raw[offset+2]-64
        o['coarse_units'] = 'physical semitones, current SysEx codec'
        o['net_coarse_and_tone_octave_semitones'] = o['coarse']+12*tone['octaveShift']
        o['mixed_in'] = tone['balance'] < 63 if osc == 'osc1' else tone['balance'] > -63
    tone['filter_lfo_depths'] = [tone[l]['depth1'] if tone[l]['destination1']==2 else 0
                                for l in ('lfo1','lfo2')]
    tone['zero_filter_envelope_lfo_and_velocity'] = (tone['filterEnvDepth']==0
        and tone['cutoffVelocitySens']==0 and not any(tone['filter_lfo_depths']))
    tone['active_effect_sends'] = {
        'delay': tone['delayDepth'] if common['delayOn'] else 0,
        'reverb': tone['reverbDepth'] if common['reverbOn'] else 0}
    tone['model_base_cutoff_hz_diagnostic'] = 20*2**(tone['cutoff']*10/127)
    tone['model_base_cutoff_status'] = 'current voiced law; not a measurement'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='new directory')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    catalog_path = ROOT/'Docs/fidelity/hardware-reference-catalog.json'
    catalog = json.loads(catalog_path.read_text())
    helper = ROOT/'Tools/inspect_named_reference_patch.cpp'
    binary = out/'inspect-patch'
    command = ['c++','-std=c++20','-O2','-I'+str(ROOT/'Source/DSP'),str(helper),
               str(ROOT/'Source/DSP/SeptumSysEx.cpp'),
               str(ROOT/'Source/DSP/SeptumPresets.cpp'),'-o',str(binary)]
    subprocess.run(command,check=True)
    banks = {}
    for b in catalog['banks']:
        if b['id']=='fx':
            continue
        path = args.sources/b['local_filename']
        verify(path,b['sha256'])
        data, member = read_bank(path)
        if hashlib.sha256(data).hexdigest()!=b['bank_sha256'] or member!=b['archive_member']:
            raise ValueError('Original bank member identity mismatch')
        banks[b['id']] = (b,parse_bank(data))
    rows = []
    for recording in catalog['recordings']:
        if recording.get('association_status')!='named_patch_on_official_page':
            continue
        bank, patches = banks[recording['bank_id']]
        name, blocks = patches[recording['patch_number']-1]
        if name!=recording['patch_name']:
            raise ValueError('Original patch name mismatch')
        verify(args.sources/recording['local_filename'],recording['sha256'])
        rawfile = out/(recording['id']+'.blocks')
        rawfile.write_bytes(b''.join(blocks[:5]))
        decoded = json.loads(subprocess.check_output([str(binary),str(rawfile)],text=True))
        rawfile.unlink()
        active = ([('upper','lower')[decoded['keyboardPart']]]
                  if decoded['keyboardMode']==0 else ['upper','lower'])
        for part, block in (('upper',1),('lower',2)):
            decoded[part]['active_by_keyboard_mode'] = part in active
            annotate(decoded[part],blocks[block],decoded)
        rows.append(dict(id=recording['id'],name=name,
            recording={k:recording[k] for k in ('url','sha256','local_filename','source_page_url')},
            bank={k:bank[k] for k in ('url','sha256','bank_sha256','archive_member')},
            patch_number=recording['patch_number'],
            unmodified_sysex_sha256=hashlib.sha256(encode_syx(blocks)).hexdigest(),
            active_parts=active,
            static_filter_parts=[p for p in active if decoded[p]['zero_filter_envelope_lfo_and_velocity']],
            decoded=decoded))
    if len(rows)!=24:
        raise ValueError(f'Expected 24 named references; got {len(rows)}')
    decodes = []
    for title in ('Juicy Fat','Sequence Bs'):
        matches = [r for r in rows if r['name'].replace(' ','').lower()==title.replace(' ','').lower()]
        if len(matches)!=1:
            raise ValueError(f'Cannot identify {title}')
        r=matches[0]
        wav=out/(r['id']+'.wav')
        cmd=['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-i',
             str((args.sources/r['recording']['local_filename']).resolve()),
             '-ar','44100','-ac','2','-c:a','pcm_f32le',str(wav)]
        subprocess.run(cmd,check=True)
        decodes.append(dict(id=r['id'],path=str(wav),sha256=sha(wav),command=cmd,
                            original_mp3_sha256=r['recording']['sha256']))
    result=dict(schema_version=1,status='source inventory; no DSP or patch changes',
        catalog_sha256=sha(catalog_path),tool_sha256=sha(__file__),
        decoder_helper_sha256=sha(helper),compile_command=command,
        decoder_inputs=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in
                        [ROOT/'Source/DSP/SeptumSysEx.cpp',ROOT/'Source/DSP/SeptumPatch.h',
                         ROOT/'Source/DSP/SeptumPresets.cpp']],
        coarse_tune_convention='Current C++ decodeTonePatch; WIDE-off signed raw/3 rounded to physical semitone; tone octave added separately.',
        static_definition='Stored filter depth, both routed filter LFO depths and filter velocity sensitivity all zero. Unknown external controllers may still move cutoff.',
        unknowns=catalog['unknowns'],references=rows,decoded_audio=decodes)
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    for r in rows:
        print(r['name'],r['active_parts'],[(p,r['decoded'][p]['cutoff'],r['decoded'][p]['keyFollow']) for p in r['static_filter_parts']])


if __name__=='__main__':
    main()
