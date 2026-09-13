#!/usr/bin/env python3
"""Labeled SupaJuce diagnostic grid: change resonance/cutoff, retain MIDI/settings.

This creates modified-preset experiments, not original-preset comparisons.
Fits first note's upper square harmonic ratios only; reports all other notes.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from analyze_supajuce_octaves import measure

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def change_preset(data, cutoff, resonance):
    out = bytearray()
    changes = []
    for raw in data.split(b'\xf7'):
        if not raw: continue
        frame = bytearray(raw + b'\xf7')
        if len(frame) < 13 or frame[:7] != bytes((0xf0,0x41,0x10,0,0,0x16,0x12)):
            raise ValueError('Expected full SH-201 DT1 frames')
        if frame[9:11] == b'\x01\0':
            for offset,value,name in ((0x13,cutoff,'cutoff'),(0x16,resonance,'resonance')):
                old=frame[11+offset]
                if old != value:
                    frame[11+offset]=value
                    changes.append(dict(block='upper',offset=offset,parameter=name,before=old,after=value))
            frame[-2]=(-sum(frame[7:-2]))&127
        out.extend(frame)
    return bytes(out),changes


def errors(reference,rendered):
    result=[]
    for a,b in zip(reference['rows'],rendered['rows']):
        indexes=np.array([2,6,10,14,18,22])-1
        x,y=np.array(a['amplitude'])[indexes],np.array(b['amplitude'])[indexes]
        er=20*np.log10(np.maximum(y[1:]/y[0],1e-30)/(np.maximum(x[1:]/x[0],1e-30)))
        result.append(dict(note_index=a['note_index'],errors_db=er.tolist(),rmse_db=float(np.sqrt(np.mean(er*er)))))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--comparison',type=Path,required=True)
    p.add_argument('--renderer',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--cutoffs',type=int,nargs='+',default=[27,31,35,39])
    p.add_argument('--resonances',type=int,nargs='+',default=[40,64,80,96,112])
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    comparison=json.loads((a.comparison/'comparison.json').read_text())
    notes=comparison['case']['notes']
    hardware=measure(a.comparison/'hardware-decoded-full.wav',notes,0)
    syx=(a.comparison/'original-patch.syx').read_bytes();rows=[]
    for cutoff in a.cutoffs:
      for resonance in a.resonances:
        if not 0<=cutoff<=127 or not 0<=resonance<=127: raise ValueError('Control outside range')
        dest=a.output/f'cutoff-{cutoff}-resonance-{resonance}';dest.mkdir()
        patch,changes=change_preset(syx,cutoff,resonance)
        (dest/'diagnostic.syx').write_bytes(patch)
        command=[sys.executable,str(ROOT/'Tools/render_midi.py'),'--renderer',str(a.renderer.resolve()),'--midi',str((a.comparison/'reconstructed-performance.mid').resolve()),'--syx',str((dest/'diagnostic.syx').resolve()),'--output',str((dest/'render.wav').resolve()),'--tempo-policy','preserve-patch','--master-level','100','--tail','2','--strict']
        run=subprocess.run(command,capture_output=True,text=True)
        (dest/'render.log').write_text(run.stdout+run.stderr)
        if run.returncode: raise RuntimeError(dest/'render.log')
        manifest=json.loads((dest/'render.render.json').read_text())
        measurement=measure(dest/'render.wav',notes,manifest['output']['latency_samples']/44100)
        row=dict(cutoff=cutoff,resonance=resonance,parameter_modifications=changes,
                 manifest_sha256=digest(dest/'render.render.json'),manifest=manifest,
                 measurement=measurement,errors=errors(hardware,measurement))
        rows.append(row)
        (dest/'measurement.json').write_text(json.dumps(row,indent=2)+'\n')
        print(cutoff,resonance,[round(v['rmse_db'],2) for v in row['errors']],flush=True)
    best=min(rows,key=lambda r:r['errors'][0]['rmse_db'])
    report=dict(status='modified-preset diagnostic grid; no shipping source changes',
                source_comparison_sha256=digest(a.comparison/'comparison.json'),
                original_sysex_sha256=hashlib.sha256(syx).hexdigest(),
                hardware=hardware,rows=rows,
                selection='Only first note H6/H10/H14/H18/H22 relative to H2 selects the candidate. Other notes are evaluation, not independent recordings.',
                best_first_note=dict(cutoff=best['cutoff'],resonance=best['resonance']),
                limitations=['Recorded patch revision, MIDI/controller performance and recording chain are not authenticated.',
                             'Unknown balance/recording gain cancels in within-oscillator ratios, but delay/reverb, MP3 encoding and time-varying filter remain.',
                             'A best grid point is not an identified general hardware control law.'],
                script_sha256=digest(Path(__file__)))
    (a.output/'grid.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__': main()
