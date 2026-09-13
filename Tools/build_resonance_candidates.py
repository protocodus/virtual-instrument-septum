#!/usr/bin/env python3
"""Build isolated resonance hypotheses; shipping source and original presets stay unchanged."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def sha(data): return hashlib.sha256(data).hexdigest()


def replace_once(source,old,new):
    if source.count(old)!=1: raise ValueError('Shipping source anchor changed; review candidate: '+old)
    return source.replace(old,new,1)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    inputs={str(p.relative_to(ROOT)):p.read_bytes() for p in (ROOT/'Source/DSP').glob('*.h')}
    for name in ('Source/DSP/SeptumEngine.cpp','Tools/RenderMidi.cpp','build-fidelity/libSeptumDSP.a'):
        inputs[name]=(ROOT/name).read_bytes()
    profiles=[]
    for name,power,coupled in [('baseline',1.,False),('single-strong',2.7,False),('coupled',1.6,True),('bounded-coupled',1.5,True)]:
        source=inputs['Source/DSP/SeptumEngine.cpp'].decode()
        # Normalize either the pre-correction or promoted source to the historical
        # control. The AUDIO FILTER still uses the original mapping in both.
        if 'mapping::voiceResonanceDamping (tone.resonance)' in source:
            source=replace_once(source,'mapping::voiceResonanceDamping (tone.resonance)', 'mapping::resonanceDamping (tone.resonance)')
            source=replace_once(source,'mapping::voiceSecondStageDamping (k)', 'mapping::filterSecondStageDamping')
        if name!='baseline':
            source=replace_once(source,'    const double resonanceTarget = mapping::resonanceDamping (tone.resonance);',
                '    const double legacyDamping = mapping::resonanceDamping (tone.resonance);\n'
                f'    const double resonanceTarget = legacyDamping > 0.0 ? 2.0 * std::pow (legacyDamping * 0.5, {power}) : legacyDamping;')
            if coupled:
                source=replace_once(source,'            const double k2 = mapping::filterSecondStageDamping;',
                    ('            const double k2 = std::clamp (k, 0.5, mapping::filterSecondStageDamping);' if name=='bounded-coupled'
                     else '            const double k2 = std::min (mapping::filterSecondStageDamping, k);'))
        dest=a.output/name;dest.mkdir()
        for rel,data in inputs.items():
            target=dest/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        (dest/'Source/DSP/SeptumEngine.cpp').write_text(source)
        binary=dest/'SeptumRenderMidi'
        command=['c++','-O3','-std=c++20','-I',str(dest/'Source'),'-I',str(dest/'Source/DSP'),str(dest/'Tools/RenderMidi.cpp'),str(dest/'Source/DSP/SeptumEngine.cpp'),str(dest/'build-fidelity/libSeptumDSP.a'),'-o',str(binary)]
        r=subprocess.run(command,capture_output=True,text=True);(dest/'build.log').write_text(r.stdout+r.stderr)
        if r.returncode: raise RuntimeError(dest/'build.log')
        record={'name':name,'positive_damping_power':power,'second_stage':'clamp(k1,.5,1.2)' if name=='bounded-coupled' else 'min(1.2,k1)' if coupled else 'fixed1.2','renderer_sha256':sha(binary.read_bytes()),'renderer':str(binary.resolve()),'source_sha256':{rel:sha((dest/rel).read_bytes()) for rel in inputs},'command':command,'status':'historical pre-correction control' if name=='baseline' else 'isolated empirical resonance hypothesis; cutoff and envelopes unchanged'}
        (dest/'profile.json').write_text(json.dumps(record,indent=2)+'\n');profiles.append(record);print(name,flush=True)
    for rel,data in inputs.items():
        if (ROOT/rel).read_bytes()!=data: raise RuntimeError('Input changed during build: '+rel)
    (a.output/'profiles.json').write_text(json.dumps({'shipping_source_hashes':{r:sha(d) for r,d in inputs.items()},'script_sha256':sha(Path(__file__).read_bytes()),'profiles':profiles},indent=2)+'\n')

if __name__=='__main__':main()
