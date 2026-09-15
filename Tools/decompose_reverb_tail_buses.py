#!/usr/bin/env python3
"""Frozen full-engine bus decomposition and input-halt controls.

Only isolated source copies are instrumented. The complete native output must
match the prior shipping WAV, and the diagnostic output must match the native
output, before any stem or halt measurements are interpreted.
"""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

ROOT=Path(__file__).resolve().parents[1]
SR=44100
CHANNELS=['dryL','dryR','delaySendL','delaySendR','reverbSendL','reverbSendR',
          'upperL','upperR','lowerL','lowerR','upperDelayL','upperDelayR',
          'lowerDelayL','lowerDelayR','upperReverbL','upperReverbR',
          'lowerReverbL','lowerReverbR','effectsL','effectsR','master',
          'panL','panR','analogBeforeLimiterL','analogBeforeLimiterR','tickEnd']


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path,obj):path.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')


def replace_once(text,old,new):
    if text.count(old)!=1:raise ValueError('Frozen instrumentation anchor changed: '+old[:90])
    return text.replace(old,new)


AUDIT_HEADER=r'''#pragma once
#include <cstdlib>
#include <fstream>
#include <string>
#include <cstdint>
namespace septum_audit {
struct Config {
 std::ofstream capture;
 std::string mode="full",halt="none";
 std::int64_t frame=0,haltFrame=-1;
 Config(){const char*p=std::getenv("SEPTUM_AUDIT_CAPTURE");if(p){capture.open(p,std::ios::binary);if(!capture)std::abort();}}
};
inline Config& config(){static Config value;return value;}
}
'''


def instrument(source):
    s=source+'\n'
    s=replace_once(s,'#include "SeptumEngine.h"','#include "SeptumEngine.h"\n#include "AuditBus.h"')
    s=replace_once(s,'std::array<std::array<float, controlInterval>, 2> partLeft {}, partRight {};',
        'std::array<std::array<float, controlInterval>, 2> partLeft {}, partRight {};\n'
        '        float auditDelay[2][2][controlInterval] {}, auditReverb[2][2][controlInterval] {};\n'
        '        double auditEffect[2][controlInterval] {}, auditAnalog[2][controlInterval] {}, auditPan[2][controlInterval] {}, auditMaster[controlInterval] {};')
    anchor='''                sendReverbR_[static_cast<std::size_t> (i)] +=
                    static_cast<float> (r * voice.reverbSendGain);'''
    s=replace_once(s,anchor,anchor+'''
                auditDelay[partIndex][0][i] += static_cast<float> (l * voice.delaySendGain);
                auditDelay[partIndex][1][i] += static_cast<float> (r * voice.delaySendGain);
                auditReverb[partIndex][0][i] += static_cast<float> (l * voice.reverbSendGain);
                auditReverb[partIndex][1][i] += static_cast<float> (r * voice.reverbSendGain);''')
    anchor='''        // -- output stage: documented analog path + master gains -----------'''
    s=replace_once(s,anchor,'''        for(int i=0;i<guarded;++i){auditEffect[0][i]=left[offset+i];auditEffect[1][i]=right[offset+i];}
'''+anchor)
    anchor='''                const double limited = outputLimit (
                    analogOutput_[static_cast<std::size_t> (channel)].processSample (x));'''
    s=replace_once(s,anchor,'''                const double auditPreLimiter = analogOutput_[static_cast<std::size_t> (channel)].processSample (x);
                const double limited = outputLimit (auditPreLimiter);
                auditAnalog[channel][i]=auditPreLimiter;
                auditPan[channel][i]=partPanGain[channel];auditMaster[i]=smoothedMaster_;''')
    anchor='''        elapseArpeggiator (guarded);'''
    s=replace_once(s,anchor,'''        if(septum_audit::config().capture){
            for(int i=0;i<guarded;++i){
                const double row[26]={dryL_[i],dryR_[i],sendDelayL_[i],sendDelayR_[i],sendReverbL_[i],sendReverbR_[i],
                    partLeft[0][i],partRight[0][i],partLeft[1][i],partRight[1][i],
                    auditDelay[0][0][i],auditDelay[0][1][i],auditDelay[1][0][i],auditDelay[1][1][i],
                    auditReverb[0][0][i],auditReverb[0][1][i],auditReverb[1][0][i],auditReverb[1][1][i],
                    auditEffect[0][i],auditEffect[1][i],auditMaster[i],auditPan[0][i],auditPan[1][i],
                    auditAnalog[0][i],auditAnalog[1][i],i+1==guarded?1.:0.};
                septum_audit::config().capture.write(reinterpret_cast<const char*>(row),sizeof(row));
                if(!septum_audit::config().capture)std::abort();
            }
        }
'''+anchor)
    anchor='''            double input = (0.5 * (reverbSendL[i] + reverbSendR[i])
                            + 0.5 * (wetDelayL + wetDelayR)) * reverbWetGain_;'''
    s=replace_once(s,anchor,anchor+'''
            const auto& audit=septum_audit::config();
            if(audit.mode=="direct_reverb") input=0.5*(reverbSendL[i]+reverbSendR[i])*reverbWetGain_;
            if(audit.mode=="delay_reverb") input=0.5*(wetDelayL+wetDelayR)*reverbWetGain_;
            if(audit.haltFrame>=0 && audit.frame+i>=audit.haltFrame){
                if(audit.halt=="reverb") input=0.;
                if(audit.halt=="delay_feed") input=0.5*(reverbSendL[i]+reverbSendR[i])*reverbWetGain_;
            }''')
    anchor='''        outR[i] = static_cast<float> (dryR[i] + wetDelayR
                                      + wetReverbR * mapping::reverbWetReturn * reverbWetGain_);'''
    s=replace_once(s,anchor,anchor+'''
        const auto& audit=septum_audit::config();
        if(audit.mode=="dry"){outL[i]=dryL[i];outR[i]=dryR[i];}
        if(audit.mode=="delay"){outL[i]=static_cast<float>(wetDelayL);outR[i]=static_cast<float>(wetDelayR);}
        if(audit.mode=="direct_reverb" || audit.mode=="delay_reverb"){
            outL[i]=static_cast<float>(wetReverbL*mapping::reverbWetReturn*reverbWetGain_);
            outR[i]=static_cast<float>(wetReverbR*mapping::reverbWetReturn*reverbWetGain_);
        }''')
    anchor='''    delayL_.dampState = flushDenormal (delayL_.dampState);'''
    s=replace_once(s,anchor,'    septum_audit::config().frame += samples;\n'+anchor)
    return s


FIXTURE=r'''#include "DSP/SeptumEngine.h"
#include "DSP/SeptumPresets.h"
#include "DSP/SeptumSysEx.h"
#include "DSP/AuditBus.h"
#include <filesystem>
#include <fstream>
#include <iterator>
#include <memory>
#include <stdexcept>
#include <vector>
#include <iostream>
using Bytes=std::vector<std::uint8_t>;
Bytes readBytes(const std::filesystem::path&p){std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("missing patch");return Bytes(std::istreambuf_iterator<char>(f),{});}
READER
double limit(double x){double a=std::abs(x);if(a<=septum::mapping::outputLimitKnee)return x;double over=a-septum::mapping::outputLimitKnee;double y=septum::mapping::outputLimitKnee+septum::mapping::outputLimitRange*(1.-std::exp(-over*(1./septum::mapping::outputLimitRange)));return x<0?-y:y;}
int main(int argc,char**argv){
 if(argc!=9)return 2;
 auto patch=readCompletePatch(argv[1]);std::ifstream f(argv[2],std::ios::binary);if(!f)return 3;
 auto bytes=std::filesystem::file_size(argv[2]);if(bytes%(26*sizeof(double)))return 4;
 std::vector<std::array<double,26>> bus(bytes/(26*sizeof(double)));f.read(reinterpret_cast<char*>(bus.data()),bytes);if(!f)return 5;
 const int part=std::stoi(argv[4]);auto&a=septum_audit::config();a.mode=argv[5];a.halt=argv[6];a.haltFrame=std::stoll(argv[7]);a.frame=0;
 const double scale=std::stod(argv[8]);
 auto e=std::make_unique<septum::Engine>();e->prepare(44100,256);e->setPatch(patch);e->setMasterLevel(100);e->reset();
 septum::AnalogOutput output[2];for(auto&o:output)o.prepare(44100);
 std::ofstream file(argv[3],std::ios::binary);if(!file)return 6;
 std::size_t pos=0;double maxPre=0.,maxLimited=0.;std::uint64_t nonlinear=0;
 while(pos<bus.size()){
  int n=1;while(pos+n<bus.size() && bus[pos+n-1][25]==0. && n<8)++n;
  if(bus[pos+n-1][25]!=1.)return 7;
  float dryL[8]{},dryR[8]{},delL[8]{},delR[8]{},revL[8]{},revR[8]{},left[8]{},right[8]{};
  for(int i=0;i<n;++i){const auto&r=bus[pos+i];int d=part<0?0:6+part*2,dl=part<0?2:10+part*2,rv=part<0?4:14+part*2;
   bool stop=a.halt=="source"&&a.haltFrame>=0&&std::int64_t(pos+i)>=a.haltFrame;
   double g=stop?0.:scale;dryL[i]=float(r[d]*g);dryR[i]=float(r[d+1]*g);delL[i]=float(r[dl]*g);delR[i]=float(r[dl+1]*g);revL[i]=float(r[rv]*g);revR[i]=float(r[rv+1]*g);
  }
  e->processEffects(dryL,dryR,delL,delR,revL,revR,left,right,n);
  for(int i=0;i<n;++i){float row[6]={left[i],right[i],0,0,0,0};const auto&r=bus[pos+i];
   for(int c=0;c<2;++c){double x=(c?right[i]:left[i])*r[20]*r[21+c];double before=output[c].processSample(x);double after=limit(before);row[2+c]=float(before);row[4+c]=float(after);maxPre=std::max(maxPre,std::abs(before));maxLimited=std::max(maxLimited,std::abs(after));nonlinear+=std::abs(before)>.9;}
   file.write(reinterpret_cast<const char*>(row),sizeof(row));
  }pos+=n;
 }
 if(!file)return 8;
 std::cout<<"{\"frames\":"<<bus.size()<<",\"peak_before_limiter\":"<<maxPre<<",\"peak_limited\":"<<maxLimited<<",\"limited_samples\":"<<nonlinear<<"}\n";
}
'''


def build(out,revision):
    names=subprocess.check_output(['git','ls-tree','-r','--name-only',revision,'Source/DSP'],cwd=ROOT,text=True).splitlines()+['Tools/RenderMidi.cpp']
    hashes={}
    for name in names:
        data=subprocess.check_output(['git','show',revision+':'+name],cwd=ROOT)
        if (ROOT/name).read_bytes()!=data:raise ValueError('Current DSP/renderer differs from requested frozen source: '+name)
        hashes[name]=hashlib.sha256(data).hexdigest()
        for kind in('native','diagnostic'):
            p=out/kind/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    original=(out/'native/Source/DSP/SeptumEngine.cpp').read_text();modified=instrument(original)
    (out/'diagnostic/Source/DSP/SeptumEngine.cpp').write_text(modified)
    h=out/'diagnostic/Source/DSP/SeptumEngine.h';h.write_text(h.read_text().replace('private:','public:'))
    (out/'diagnostic/Source/DSP/AuditBus.h').write_text(AUDIT_HEADER)
    (out/'instrumentation.diff').write_text(''.join(difflib.unified_diff(original.splitlines(True),modified.splitlines(True),fromfile='native/SeptumEngine.cpp',tofile='diagnostic/SeptumEngine.cpp')))
    reader=(out/'native/Tools/RenderMidi.cpp').read_text();reader=reader[reader.index('septum::Patch readCompletePatch ('):reader.index('std::string patchSummary (')]
    (out/'diagnostic/EffectsReplay.cpp').write_text(FIXTURE.replace('READER',reader))
    commands=[]
    for kind in('native','diagnostic'):
        folder=out/kind
        command=['c++','-std=c++20','-O2','-fno-fast-math','-I'+str(folder/'Source'),str(folder/'Tools/RenderMidi.cpp'),*[str(folder/'Source/DSP'/n)for n in('SeptumEngine.cpp','SeptumPresets.cpp','SeptumSysEx.cpp')],'-o',str(folder/'SeptumRenderMidi')]
        subprocess.run(command,check=True);commands.append(command)
    folder=out/'diagnostic';command=['c++','-std=c++20','-O2','-fno-fast-math','-I'+str(folder/'Source'),str(folder/'EffectsReplay.cpp'),*[str(folder/'Source/DSP'/n)for n in('SeptumEngine.cpp','SeptumPresets.cpp','SeptumSysEx.cpp')],'-o',str(folder/'EffectsReplay')]
    subprocess.run(command,check=True);commands.append(command)
    files={str(p.relative_to(out)):sha(p)for p in out.rglob('*')if p.is_file()}
    return dict(revision=revision,original_source_sha256=hashes,commands=commands,files_sha256=files)


def replay(binary,syx,bus,path,part,mode,halt='none',frame=-1,scale=1.):
    command=[str(binary),str(syx),str(bus),str(path),str(part),mode,halt,str(frame),str(scale)]
    p=subprocess.run(command,check=True,capture_output=True,text=True);metadata=json.loads(p.stdout)
    y=np.fromfile(path,dtype='<f4').reshape(-1,6)
    if not np.isfinite(y).all()or len(y)!=metadata['frames']:raise ValueError('Invalid replay')
    return y,dict(command=command,raw_sha256=sha(path),**metadata)


def difference(x,y):
    d=x.astype(float)-y.astype(float)
    return dict(maximum_absolute=float(abs(d).max()),rms=float(np.sqrt(np.mean(d*d))),
        relative_rms=float(np.linalg.norm(d)/max(np.linalg.norm(y),1e-300)))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--revision',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    integration=ROOT/'build-fidelity/hardware-benchmark/reverb-return-integration/run-01/verification.json'
    verified=json.loads(integration.read_text())['render_verification'];cases=[]
    for name,cohort in[('club-bass','legacy'),('ambient-sqr-nominal-v100','prospective'),('cotton-wool','legacy')]:
        row=next(x for x in verified['results']if x['id']==name)
        directory=integration.parent/'renders'/cohort/name;receipt=json.loads((directory/'shipping.render.json').read_text())
        if sha(directory/'shipping.wav')!=row['wav_sha256']or sha(directory/'shipping.render.json')!=row['receipt_sha256']:raise ValueError('Prior native output changed')
        for filename,key in[('original-patch.syx','sysex'),('reconstructed-performance.mid','midi')]:
            if sha(directory/filename)!=row['preserved_input_sha256'][key]:raise ValueError('Prior input changed')
        events=receipt['replay_events'];offs=[]
        for event in events:
            if event['kind']=='tempo':continue
            b=bytes.fromhex(event['value'])
            if event['kind']!='midi'or b[0]&240 not in(128,144):raise ValueError('Unmodeled controller event in replay')
            if b[0]&240==128 or(b[0]&240==144 and b[2]==0):offs.append(event['sample'])
        cases.append(dict(id=name,directory=str(directory),original_wav_sha256=row['wav_sha256'],receipt=receipt,last_note_off_sample=max(offs)))
    protocol=dict(status='Frozen diagnostic decomposition, no coefficient or performance fit.',tool_sha256=sha(__file__),revision=a.revision,
        integration_sha256=sha(integration),cases=cases,bus_fields_float64=CHANNELS,
        decomposition='Capture actual smoothed/ordered per-voice post-filter/AMP buses. Replay exact effects with original tick boundaries and gain/pan streams. Separate Upper/Lower dry,delay,direct-fed reverb,delay-fed reverb. Compare sums before AnalogOutput, before limiter and after limiter; never assume power addition.',
        halts='At final original reconstructed note-off and250ms later: zero source buses, or zero all new reverb input before predelay, or remove only new delay-to-reverb input. Preserve delay/diffuser/FDN states. Not an effects switch or panic.',
        extension='After the existing native render ends with zero active voices, continue effects with zero voice/send input to final gate+6s; gain/pan retain last captured values. No new MIDI or final-hardware-performance transcription.',
        supports=dict(club_matched_source_seconds=[[2.30,2.65],[2.65,3.00],[3.00,3.25]],ambient_matched_source_seconds=[[.405,.775]],cotton_matched_source_seconds=[[1.25,5.00]],synthetic_tail_ages_after_final_gate=[[.09,.44],[.44,.79],[1.05,2.55],[2.55,5.55]]),
        limitations='Cotton original17.25–21.75s and Ambient original11.65–13.15s are not matched by these opening MIDI files. Only Club firstgap overlaps existing reconstructed performance. Component powers do not sum under coherent interference. AnalogOutput is linear small-signal; output limiter and floating-point/state rounding are explicitly checked.')
    save(out/'protocol-before-build.json',protocol)
    builds=out/'builds';builds.mkdir();manifest=build(builds,a.revision);save(builds/'manifest.json',manifest)
    records=[]
    for case in cases:
        name=case['id'];dst=out/name;dst.mkdir();original=Path(case['directory'])
        for file in('original-patch.syx','reconstructed-performance.mid'):shutil.copyfile(original/file,dst/file)
        for kind in('native','diagnostic'):
            command=[sys.executable,str(ROOT/'Tools/render_midi.py'),'--renderer',str(builds/kind/'SeptumRenderMidi'),'--midi',str(dst/'reconstructed-performance.mid'),'--syx',str(dst/'original-patch.syx'),'--output',str(dst/(kind+'.wav')),'--tail','2','--tempo-policy','preserve-patch','--master-level','100']
            env=os.environ.copy();env.pop('SEPTUM_AUDIT_CAPTURE',None)
            if kind=='diagnostic':env['SEPTUM_AUDIT_CAPTURE']=str(dst/'captured-buses.raw')
            subprocess.run(command,check=True,env=env,stdout=subprocess.DEVNULL)
        if not sha(dst/'native.wav')==sha(dst/'diagnostic.wav')==case['original_wav_sha256']:
            raise ValueError('Diagnostic/native/previous complete WAV identity failed: '+name)
        sr,reference=wavfile.read(dst/'native.wav');bus=np.fromfile(dst/'captured-buses.raw',dtype='<f8').reshape(-1,26)
        if sr!=SR or len(bus)!=len(reference)or not np.isfinite(bus).all():raise ValueError('Invalid captured bus')
        if case['receipt']['output']['active_voices_at_end']!=0:raise ValueError('Cannot extend ongoing voices')
        frames=max(len(bus),case['last_note_off_sample']+6*SR)
        extended=np.zeros((frames,26));extended[:len(bus)]=bus;extended[len(bus):,20:23]=bus[-1,20:23]
        for start in range(len(bus),frames,8):extended[min(start+8,frames)-1,25]=1.
        extended.tofile(dst/'replay-buses.raw')
        binary=builds/'diagnostic/EffectsReplay';syx=dst/'original-patch.syx';busfile=dst/'replay-buses.raw'
        full,full_meta=replay(binary,syx,busfile,dst/'full.raw',-1,'full')
        if not np.array_equal(full[:len(bus),:2],bus[:,18:20].astype(np.float32))or not np.array_equal(full[:len(bus),4:],reference):
            raise ValueError('Exact effects/output replay identity failed: '+name)
        stems={};stem_meta={}
        for part in(0,1):
            for mode in('dry','delay','direct_reverb','delay_reverb'):
                key=('upper_'if part==0 else'lower_')+mode
                stems[key],stem_meta[key]=replay(binary,syx,busfile,dst/(key+'.raw'),part,mode)
                wavfile.write(dst/(key+'.wav'),SR,stems[key][:,4:])
        summed=sum(x.astype(float)for x in stems.values())
        sums={label:difference(summed[:,a:b],full[:,a:b])for label,a,b in [('before_output',0,2),('before_limiter',2,4),('after_limiter',4,6)]}
        if sums['before_output']['maximum_absolute']>2e-6 or sums['before_limiter']['maximum_absolute']>2e-6:
            raise ValueError('Stem recombination exceeds float arithmetic guard: '+name)
        halts={};halt_meta={}
        for extra in(0,round(.25*SR)):
            for kind in('source','reverb','delay_feed'):
                key=kind+('_gate'if extra==0 else'_gate_plus250ms')
                halts[key],halt_meta[key]=replay(binary,syx,busfile,dst/(key+'.raw'),-1,'full',kind,case['last_note_off_sample']+extra)
                wavfile.write(dst/(key+'.wav'),SR,halts[key][:,4:])
        record=dict(id=name,native_diagnostic_original_byte_identity=True,original_frames=len(bus),extended_frames=frames,
            original_input_sha256={f:sha(dst/f)for f in('original-patch.syx','reconstructed-performance.mid')},
            native_sha256=sha(dst/'native.wav'),diagnostic_sha256=sha(dst/'diagnostic.wav'),captured_bus_sha256=sha(dst/'captured-buses.raw'),replay_bus_sha256=sha(busfile),
            full=full_meta,stems=stem_meta,recombination=sums,halts=halt_meta,last_note_off_sample=case['last_note_off_sample'])
        save(dst/'receipt.json',record);records.append(record);save(out/'results-partial.json',dict(protocol=protocol,build=manifest,cases=records))
        print(name,'complete: full PCM exact; stems',sums,flush=True)
    save(out/'results.json',dict(protocol=protocol,build=manifest,cases=records,claim='Verified model decomposition only; hardware equivalence and parameter identification remain unestablished.'))


if __name__=='__main__':main()
