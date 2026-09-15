#!/usr/bin/env python3
"""Export the fixed W4/production/hardware dry listening comparison.

No fitting or audio rendering. Source-clock crop and gains come from the frozen
W4 scoring protocol. One peak-only attenuation applies to all six exports.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import numpy as np
from scipy.io import wavfile
import assess_saw_w4_engine as frozen

ROOT=Path(__file__).resolve().parents[1]

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(path,value):
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-root',type=Path,default=ROOT/'build-fidelity/saw-w4-engine/candidate-dry-01')
    parser.add_argument('--baseline-root',type=Path,default=ROOT/'build-fidelity/envelope-hypothesis/dry-v2')
    parser.add_argument('--sources',type=Path,default=ROOT/'build-fidelity/deepsonic')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--official-results',type=Path,help='Optional frozen all-ten-preset comparison; reuse its existing shared listening transforms')
    args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    cache=out/'source-cache';cache.mkdir()
    if frozen.LAG!=-1406 or frozen.GAINS!={12:4.137125725839024,24:3.870462967942607}:
        raise ValueError('Frozen listening lag or shared gains changed')
    if frozen.EXCLUDED!=(826875,848925) or frozen.TRAIN!=(66150,85444):
        raise ValueError('Frozen calibration intervals changed')
    candidate_root=args.candidate_root.resolve()
    manifest_path=candidate_root/'manifest.json';candidate_manifest=json.loads(manifest_path.read_text())
    if candidate_manifest['status']!='complete':raise ValueError('Candidate is not frozen and complete')
    catalog=json.loads(frozen.high.CATALOG.read_text())
    ffmpeg=Path(shutil.which('ffmpeg')).resolve()
    groups=[];signals={};provenance=[]
    for slope in (12,24):
        name=f'roland_sh-201_-_filter_demo_-_lpf{slope}_q000.mp3'
        entry=next(r for r in catalog['assets']if Path(r['path']).name==name)
        original=frozen.artifact(args.sources/name,entry['sha256'])
        decoded=cache/f'hardware-lp{slope}.wav'
        command=[str(ffmpeg),'-hide_banner','-loglevel','error','-nostdin','-i',original['path'],'-c:a','pcm_f32le',str(decoded)]
        subprocess.run(command,check=True)
        rate,hardware=wavfile.read(decoded)
        if rate!=frozen.SR or hardware.dtype!=np.float32 or hardware.ndim!=1 or not np.isfinite(hardware).all():
            raise ValueError('Original mono44.1k float32 decode changed')
        production=frozen.load_model(args.baseline_root/f'audio/production/lp{slope}',frozen.high.WAV_HASH[slope])
        if production['provenance']['patch']['sha256']!=frozen.high.PATCH_HASH[slope]:
            raise ValueError('Production recipe changed')
        candidate=frozen.load_model(candidate_root/f'lp{slope}',candidate_manifest['renders'][f'lp{slope}']['sha256'],production['receipt'])
        candidate_proof=frozen.candidate_provenance(candidate_root,candidate,slope)
        start=max(0,-frozen.LAG)
        end=min(len(hardware),len(production['audio'])-frozen.LAG,len(candidate['audio'])-frozen.LAG)
        if end<=start:raise ValueError('No common listening support')
        arrays={'hardware':hardware[start:end].astype(float),
                'production':production['audio'][start+frozen.LAG:end+frozen.LAG]*frozen.GAINS[slope],
                'w4':candidate['audio'][start+frozen.LAG:end+frozen.LAG]*frozen.GAINS[slope]}
        signals[slope]=arrays
        groups.append(dict(id=f'lp{slope}',kind='dry',title=f'Dry saw · LP{slope}',slope=slope,sample_rate=rate,frames=end-start,hardware_start_sample=start,
            hardware_end_sample=end,source_start_seconds=start/rate,source_end_seconds=end/rate,
            engine_source_samples=[start+frozen.LAG,end+frozen.LAG],
            gain_calibration_source_samples=list(frozen.TRAIN),coefficient_training_source_samples=list(frozen.EXCLUDED),gain_interval_seconds=[v/rate for v in frozen.TRAIN],
            coefficient_interval_seconds=[v/rate for v in frozen.EXCLUDED],lag_samples=frozen.LAG,
            context='Dry single saw · original 124-note MIDI',byte_identity_control=False,
            jumps=[dict(label=l,time=t)for l,t in [('Beginning',start/rate),('Level calibration',1.5),('Middle register',8.5),('High-note check',18.25),('Fitted note',18.75),('Chords',22.)]],tracks=[]))
        provenance.append(dict(slope=slope,original_mp3={**original,'url':entry['url']},decode=frozen.artifact(decoded),
            decode_command=command,production=production['provenance'],candidate=candidate['provenance'],candidate_source=candidate_proof))
    # No per-source loudness target or candidate gain adjustment is introduced.
    peak=max(float(np.max(np.abs(x)))for tracks in signals.values()for x in tracks.values())
    attenuation=min(1.,.98/peak)if peak>0 else 1.
    verification=[]
    for g in groups:
        slope=g['slope'];g['common_attenuation_db']=float(20*np.log10(attenuation));g['attenuation_policy']='One peak-only attenuation shared by all six dry tracks'
        for identity,array in signals[slope].items():
            filename=f'lp{slope}-{identity}.wav';expected=(array*attenuation).astype(np.float32)
            wavfile.write(out/filename,frozen.SR,expected)
            sr,actual=wavfile.read(out/filename)
            if sr!=frozen.SR or actual.dtype!=np.float32 or not np.array_equal(actual,expected):
                raise AssertionError('Export differs from exact declared float32 transform')
            if len(actual)!=g['frames']or float(np.max(np.abs(actual)))>=1.:
                raise AssertionError('Export duration or clipping guard failed')
            item=dict(id=identity,file=filename,sha256=sha(out/filename),frames=len(actual),
                reference_gain=1. if identity=='hardware'else frozen.GAINS[slope],
                common_attenuation=attenuation,peak=float(np.max(np.abs(actual))),
                float32_sample_sha256=hashlib.sha256(actual.astype('<f4').tobytes()).hexdigest())
            g['tracks'].append(item)
            verification.append(dict(slope=slope,exact_float32_transform=True,maximum_export_error=0.,**item))
    official_provenance=None
    if args.official_results:
        official_path=args.official_results.resolve();official=json.loads(official_path.read_text())
        expected_ids=frozen.FACTORY_SAW|frozen.FACTORY_CONTROL
        if {c['id']for c in official['cases']}!=expected_ids or len(official['cases'])!=10:
            raise ValueError('The complete ten-preset cohort is required')
        if official['selection']['sha256']!=candidate_manifest['selection']['sha256']:
            raise ValueError('Official and dry candidates differ')
        for case in official['cases']:
            identity=case['id'];inp=case['input'];listen=case['listening'];lag=inp['lag_samples']
            if listen['primary_fixed_gain_only']is not True or case['fixed_gain']!=inp['fixed_current_production_gain']:
                raise ValueError('Official listening did not use fixed production gain')
            raw={}
            for key,ref in [('hardware',inp['hardware']),('production',inp['current_wav']),('w4',case['candidate_render']['wav'])]:
                frozen.artifact(ref['path'],ref['sha256']);sr,data=wavfile.read(ref['path'])
                if sr!=frozen.SR or data.dtype!=np.float32 or data.ndim!=2 or data.shape[1]!=2 or not np.isfinite(data).all():
                    raise ValueError('Official raw stereo float32 changed')
                raw[key]=data.astype(float)
            for ref in inp['source_files'].values():frozen.artifact(ref['path'],ref['sha256'])
            render_receipt_ref=case['candidate_render']['render_receipt'];frozen.artifact(render_receipt_ref['path'],render_receipt_ref['sha256'])
            rendered=json.loads(Path(render_receipt_ref['path']).read_text())
            if rendered['output']['sha256']!=case['candidate_render']['wav']['sha256']or rendered['inputs']['midi']['sha256']!=inp['source_files']['reconstructed-performance.mid']['sha256']or rendered['inputs']['sysex']['sha256']!=inp['source_files']['original-patch.syx']['sha256']:
                raise ValueError('Official original preset or reconstructed performance changed')
            config_ref=case['candidate_render']['coefficients'];frozen.artifact(config_ref['path'],config_ref['sha256'])
            cfg=json.loads(Path(config_ref['path']).read_text());selected=json.loads(Path(candidate_manifest['selection']['path']).read_text())
            if cfg['ramp']!=1 or cfg['phase_cycles_training_note91']!=0 or [*cfg['negative'],*cfg['positive']]!=selected['candidate_coefficients']:
                raise ValueError('Official candidate source changed')
            start,end=listen['reference_samples'];expected_start=max(0,-lag);expected_end=min(len(raw['hardware']),len(raw['production'])-lag,len(raw['w4'])-lag)
            if [start,end]!=[expected_start,expected_end]or end-start!=listen['frames']:
                raise ValueError('Official listening support changed')
            offset=inp['case']['source_start_seconds'];common=listen['common_attenuation']
            if not 0<common<=1:raise ValueError('Invalid saved audition attenuation')
            g=dict(id=identity,kind='official',title=inp['case']['title'].replace(' — ',' · '),sample_rate=frozen.SR,frames=end-start,
                source_start_seconds=offset+start/frozen.SR,source_end_seconds=offset+end/frozen.SR,
                hardware_start_sample=start,hardware_end_sample=end,hardware_excerpt_source_offset_seconds=offset,
                engine_source_samples=[start+lag,end+lag],lag_samples=lag,
                gain_interval_seconds=[offset+v/frozen.SR for v in inp['calibration_reference_samples']],coefficient_interval_seconds=None,
                evaluation_interval_seconds=[offset+v/frozen.SR for v in inp['evaluation_samples']],
                byte_identity_control=inp['byte_identity_control'],context='Original named preset · reconstructed MIDI'+(' · unchanged-source control'if inp['byte_identity_control']else''),
                common_attenuation_db=float(20*np.log10(common)),attenuation_policy='Saved benchmark audition attenuation shared by all three tracks',
                uncertainties=inp['uncertainty'],tracks=[])
            g['jumps']=[dict(label='Beginning',time=g['source_start_seconds']),dict(label='Later check',time=g['evaluation_interval_seconds'][0])]
            for key,ref in listen['files'].items():
                export_id='hardware'if key=='original'else key
                frozen.artifact(ref['path'],ref['sha256']);sr,actual=wavfile.read(ref['path'])
                expected=(raw[export_id][start:end]if export_id=='hardware'else raw[export_id][start+lag:end+lag]*case['fixed_gain'])*common
                if sr!=frozen.SR or not np.array_equal(actual,expected.astype(np.float32))or np.max(np.abs(actual))>=1:
                    raise ValueError('Official saved audition transform differs from exact fixed-policy source')
                filename=f'{identity}-{export_id}.wav';shutil.copyfile(ref['path'],out/filename)
                item=dict(id=export_id,file=filename,sha256=sha(out/filename),frames=len(actual),reference_gain=1. if export_id=='hardware'else case['fixed_gain'],common_attenuation=common,peak=float(np.max(np.abs(actual))),float32_sample_sha256=hashlib.sha256(actual.astype('<f4').tobytes()).hexdigest())
                g['tracks'].append(item);verification.append(dict(case=identity,exact_float32_transform=True,maximum_export_error=0.,**item))
            if g['byte_identity_control']:
                if inp['current_wav']['sha256']!=case['candidate_render']['wav']['sha256']or next(t['sha256']for t in g['tracks']if t['id']=='production')!=next(t['sha256']for t in g['tracks']if t['id']=='w4'):
                    raise ValueError('Required no-Saw byte identity failed')
            groups.append(g)
        official_provenance=dict(results=frozen.artifact(official_path),protocol=official['protocol'],selection=official['selection'],cases=[dict(id=c['id'],input=c['input'],candidate_render=c['candidate_render'],listening=c['listening'])for c in official['cases']])
    template=Path(__file__).with_name('saw_w4_listening.html')
    receipt=dict(status='fixed_listening_comparison_not_hardware_equivalence',groups=groups,
        source_revision=frozen.REVISION,lag_samples=frozen.LAG,lag_convention='hardware[t] versus engine[t-1406]',
        fixed_shared_gains=frozen.GAINS,common_audition_attenuation=attenuation,
        common_attenuation_db=float(20*np.log10(attenuation)),pre_attenuation_peak=peak,
        source_clock='Displayed position is original recording time. Dry recordings omit the first1406 unpaired hardware samples. Named presets add the saved source excerpt offset and retain their own frozen common support.',
        gain_policy='Dry: production and W4 share frozen note36 gain per slope and one peak-only attenuation across six tracks. Official: copied saved primary-fixed-production-gain listening files, with their existing common per-case audition attenuation.',
        phase_policy='Both engine outputs use canonical phase0; no listening phase fitting.',
        training_intervals=dict(gain_source_samples=list(frozen.TRAIN),source_coefficients_source_samples=list(frozen.EXCLUDED)),
        source_status='Original124-note MIDI; documented dry single-Saw recipe reconstruction; original rawpatch and capture-chain details remain uncertain.',
        transport='All three decoded buffers start on one AudioContext timestamp/offset. Source switching changes only gains with12ms fade. Source-clock seek/slope changes retain the same source time.',
        builder=frozen.artifact(__file__),template=frozen.artifact(template),
        scorer=frozen.artifact(frozen.__file__),scorer_dependencies=[frozen.artifact(ROOT/'Tools'/n)for n in ['assess_production_high_note_saw.py','assess_hardware_equivalence.py','render_midi.py']],
        candidate_manifest=frozen.artifact(manifest_path),acquisition_catalog=frozen.artifact(frozen.high.CATALOG),
        decoder=dict(**frozen.artifact(ffmpeg),version=subprocess.check_output([str(ffmpeg),'-version'],text=True).splitlines()[0]),
        provenance=provenance,official_provenance=official_provenance,export_verification=verification)
    save(out/'manifest.json',receipt)
    ui=dict(groups=groups,lag_samples=frozen.LAG,common_attenuation_db=receipt['common_attenuation_db'],
            gain_interval_seconds=[v/frozen.SR for v in frozen.TRAIN],coefficient_interval_seconds=[v/frozen.SR for v in frozen.EXCLUDED])
    (out/'index.html').write_text(template.read_text().replace('__MANIFEST__',json.dumps(ui,allow_nan=False)))
    save(out/'build-receipt.json',dict(manifest_sha256=sha(out/'manifest.json'),html_sha256=sha(out/'index.html'),
        exported_audio_sha256={t['file']:t['sha256']for g in groups for t in g['tracks']},script_sha256=sha(__file__)))
    print(json.dumps(dict(index=str(out/'index.html'),manifest=str(out/'manifest.json'),attenuation_db=receipt['common_attenuation_db'],groups=[dict(id=g['id'],frames=g['frames'])for g in groups]),indent=2))

if __name__=='__main__':main()
