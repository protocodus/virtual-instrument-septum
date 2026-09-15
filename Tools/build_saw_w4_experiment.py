#!/usr/bin/env python3
"""Isolated complete-engine W4 source experiment; never edits production DSP.

Builds from the fixed reviewed revision. A persistent backend prewarms the
complete engine for each source column, then copies that state before note91.
Hardware coefficient fitting and candidate selection are deliberately absent.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
REVISION = "545b3d37d9cc1f80bf39bc5d0bf49c0cced1d9f6"
MIDI_SHA = "21ea21b9ba3ba14cc205931134fb7a320b09e67821bd3a3c70f97fa2e8b5d99a"
WAV_SHA = {12: "e960507e6c9404554980eceae90d51e1253347d22fbe7e661f48730dce7484da",
           24: "dd505cd6a020417a5b86c52083a8dd6091b3f18edbad7c28a0de431df2356a33"}
PATCH_SHA = {12: "25eeed2e391f033894a009d3d6c6f3289d35f1a01f323a8ade63c029e03ba003",
             24: "c5d12851f4798e8300341a3ccd0b8abe46782f82b3b38cbcc5c4204fd04a173e"}
START, END, ONSET, SR = 828115, 831643, 826875, 44100
KNOTS = [0.]*4 + [i/2 for i in range(1,8) for _ in range(2)] + [4.]*4
NESTED = [1., 2/3, 5/12, 1/12] + [0.]*12

HEADER = r'''#pragma once
// Generated isolated experiment. No hardware identity or shipping change.
#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <stdexcept>
#include <string>
namespace saw_w4 {
struct CopyableAtomic {
    std::atomic<float> value;
    CopyableAtomic(float x=0) noexcept : value(x) {}
    CopyableAtomic(const CopyableAtomic& x) noexcept : value(x.value.load(std::memory_order_relaxed)) {}
    CopyableAtomic& operator=(const CopyableAtomic& x) noexcept { value.store(x.value.load(std::memory_order_relaxed),std::memory_order_relaxed); return *this; }
    float load(std::memory_order order=std::memory_order_seq_cst) const noexcept { return value.load(order); }
    void store(float x,std::memory_order order=std::memory_order_seq_cst) noexcept { value.store(x,order); }
    operator std::atomic<float>&() noexcept { return value; }
};
inline constexpr std::array<double,22> knots {0,0,0,0,.5,.5,1,1,1.5,1.5,2,2,2.5,2.5,3,3,3.5,3.5,4,4,4,4};
struct Config {
    bool enabled=false;
    double ramp=1, phase=0, meanIntegral=0;
    std::array<double,16> negative{}, positive{};
    void integrate() noexcept {
        meanIntegral=0;
        for(int j=0;j<16;++j) meanIntegral+=(negative[j]+positive[j])*(knots[j+4]-knots[j])/4;
    }
};
inline Config config;
struct Stats {
    double sourcePeak=0, statePeak=0, outputInputPeak=0;
    unsigned long long stateLimits=0, outputLimits=0, correctedCalls=0, syncResetCalls=0;
};
inline Stats stats;
inline double curve(double t,const std::array<double,16>& c) noexcept {
    if(t<0 || t>=4) return 0;
    const int span=3+2*static_cast<int>(std::floor(t*2));
    std::array<double,4> d{};
    for(int j=0;j<4;++j) { const int i=span-3+j; d[j]=i<16?c[i]:0; }
    for(int r=1;r<=3;++r) for(int j=3;j>=r;--j) {
        const int i=span-3+j;
        const double a=(t-knots[i])/(knots[i+4-r]-knots[i]);
        d[j]=(1-a)*d[j-1]+a*d[j];
    }
    return d[3];
}
inline double source(double p,double inc,int note) noexcept {
    if(note==91 && config.phase!=0) { p+=config.phase; p-=std::floor(p); }
    double y=config.ramp*(2*p-1)-inc*config.meanIntegral;
    // Complete periodic sum, including overlapping supports at high pitch.
    const int first=static_cast<int>(std::ceil(p-4*inc));
    const int last=static_cast<int>(std::floor(p+4*inc));
    for(int k=first;k<=last;++k) {
        const double t=(p-k)/inc;
        y+=t<0?curve(-t,config.negative):curve(t,config.positive);
    }
    stats.sourcePeak=std::max(stats.sourcePeak,std::abs(y));
    return y;
}
inline Config column(int column,double phase=0) {
    Config c;c.enabled=true;c.ramp=column==1?1:0;c.phase=phase;
    if(column>=2 && column<18) c.negative[column-2]=1;
    if(column>=18 && column<34) c.positive[column-18]=1;
    c.integrate();return c;
}
inline void loadEnvironment() {
    const char* path=std::getenv("SEPTUM_W4_CONFIG");
    if(!path) return;
    std::ifstream in(path);int enabled=0;
    if(!(in>>enabled>>config.ramp>>config.phase) || (enabled!=0 && enabled!=1)) throw std::runtime_error("Invalid W4 native config");
    config.enabled=enabled;
    for(auto& x:config.negative) if(!(in>>x)) throw std::runtime_error("Missing negative W4 coefficient");
    for(auto& x:config.positive) if(!(in>>x)) throw std::runtime_error("Missing positive W4 coefficient");
    double extra;
    if(in>>extra) throw std::runtime_error("Extra W4 native value");
    if(!std::isfinite(config.ramp)||!std::isfinite(config.phase)||config.phase<0||config.phase>=1) throw std::runtime_error("Invalid W4 phase/ramp");
    for(auto x:config.negative) if(!std::isfinite(x)) throw std::runtime_error("Invalid W4 coefficient");
    for(auto x:config.positive) if(!std::isfinite(x)) throw std::runtime_error("Invalid W4 coefficient");
    config.integrate();
}
inline void printStats(std::ostream& out) {
    out<<std::setprecision(17)<<"{\"source_peak\":"<<stats.sourcePeak<<",\"filter_state_peak\":"<<stats.statePeak
       <<",\"output_limiter_input_peak\":"<<stats.outputInputPeak<<",\"filter_limit_calls\":"<<stats.stateLimits
       <<",\"output_limit_calls\":"<<stats.outputLimits<<",\"corrected_saw_calls\":"<<stats.correctedCalls
       <<",\"hard_sync_reset_saw_calls\":"<<stats.syncResetCalls<<"}";
}
inline void saveStats() {
    if(const char* path=std::getenv("SEPTUM_W4_STATS")) {std::ofstream out(path);printStats(out);out<<'\n';}
}
} // namespace saw_w4
'''

BACKEND = r'''#define main retained_native_main
#include "Tools/RenderMidi.cpp"
#undef main
#include <sstream>
int main(int argc,char** argv) {
 try {
    if(argc!=5) throw std::runtime_error("Backend expects patch, events, captureStart, captureEnd");
    const auto initialPatch=readCompletePatch(argv[1]);
    if(initialPatch.delayOn||initialPatch.reverbOn||initialPatch.arpeggio.on) throw std::runtime_error("Dry non-arpeggiated backend only");
    std::uint64_t end=0;
    const auto events=readEvents(argv[2],end,44100ull*3600);
    const auto first=std::stoull(argv[3]),last=std::stoull(argv[4]);
    constexpr std::uint64_t onset=826875;
    if(first!=828115 || last!=831643) throw std::runtime_error("Only frozen training support is allowed");
    std::array<std::unique_ptr<septum::Engine>,34> states;
    std::array<septum::Patch,34> patches;
    std::array<septum::ExternalInput,34> externals;
    std::size_t nextEvent=0;
    while(nextEvent<events.size() && events[nextEvent].sample<onset) ++nextEvent;
    std::array<float,blockSize> left{},right{};
    auto processTo=[&](septum::Engine& engine,std::uint64_t& position,std::uint64_t target,std::vector<float>* capture) {
      while(position<target && (!capture || position<last)) {
        // Use the original renderer's complete256/event-boundary chunks.
        // Do not shorten a process call at the end of the captured window.
        const int count=static_cast<int>(std::min<std::uint64_t>(blockSize,target-position));
        engine.process(left.data(),right.data(),count);
        if(capture) for(int i=0;i<count;++i) if(position+i>=first && position+i<last) (*capture)[position+i-first]=left[i];
        position+=count;
      }
    };
    for(int column=0;column<34;++column) {
      saw_w4::config=saw_w4::column(column);states[column]=std::make_unique<septum::Engine>();
      auto& e=*states[column];auto& p=patches[column];auto& x=externals[column];p=initialPatch;
      e.prepare(44100,blockSize);e.setPatch(p);e.setMasterLevel(100);e.reset();
      std::uint64_t position=0;
      for(std::size_t i=0;i<nextEvent;++i) {const auto& event=events[i];processTo(e,position,event.sample,nullptr);
        if(event.kind=="midi") applyMidi(e,p,x,event.data);else e.setTempoClock(event.tempo);}
      processTo(e,position,onset,nullptr);
    }
    std::cout<<"{\"status\":\"ready\",\"columns\":34,\"rows\":"<<(last-first)<<",\"prewarm_stats\":";
    saw_w4::printStats(std::cout);std::cout<<"}"<<std::endl;
    std::string line;
    while(std::getline(std::cin,line)) {
      if(line=="QUIT") break;
      std::istringstream input(line);std::string verb,path,extra;double phase;
      if(!(input>>verb>>phase>>std::quoted(path)) || verb!="PHASE" || (input>>extra) || !std::isfinite(phase)||phase<0||phase>=1) throw std::runtime_error("Invalid phase request");
      if(std::filesystem::exists(path)) throw std::runtime_error("Backend output exists");
      saw_w4::stats={};
      std::vector<float> matrix((last-first)*34);
      for(int column=0;column<34;++column) {
        saw_w4::config=saw_w4::column(column,phase);
        auto e=std::make_unique<septum::Engine>(*states[column]);auto p=patches[column];auto x=externals[column];
        std::uint64_t position=onset;std::vector<float> capture(last-first);
        for(std::size_t i=nextEvent;i<events.size() && position<last;++i) {
          const auto& event=events[i];processTo(*e,position,event.sample,&capture);
          if(position>=last) break;
          if(event.kind=="midi") applyMidi(*e,p,x,event.data);else e->setTempoClock(event.tempo);
        }
        if(position<last) processTo(*e,position,end+88200,&capture);
        if(e->latencySamples()!=93) throw std::runtime_error("Latency changed");
        for(std::size_t i=0;i<capture.size();++i) matrix[i*34+column]=capture[i];
      }
      std::ofstream output(path,std::ios::binary);output.write(reinterpret_cast<const char*>(matrix.data()),matrix.size()*sizeof(float));output.close();
      if(!output) throw std::runtime_error("Backend matrix write failed");
      std::cout<<"{\"status\":\"ok\",\"phase\":"<<std::setprecision(17)<<phase<<",\"rows\":"<<(last-first)<<",\"columns\":34,\"stats\":";
      saw_w4::printStats(std::cout);std::cout<<"}"<<std::endl;
    }
    return 0;
 } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
'''

PROBE = r'''#include "W4Experiment.h"
#include <iostream>
int main() {
  try {saw_w4::loadEnvironment();double p,inc;int note,corrected;
    while(std::cin>>p>>inc>>note>>corrected) {
      if(!(inc>0 && inc<=.45 && p>=0 && p<1)) throw std::runtime_error("Invalid probe coordinate");
      const double y=corrected?saw_w4::source(p,inc,note):2*p-1;
      std::cout<<std::setprecision(17)<<y<<'\n';
    }return 0;
  } catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
'''

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,data): Path(path).write_text(json.dumps(data,indent=2,allow_nan=False)+"\n")
def pin(path,expected=None):
    path=Path(path).resolve();h=sha(path)
    if expected and h!=expected: raise ValueError(f"Hash mismatch: {path}")
    return {"path":str(path),"sha256":h}
def replace(text,old,new,count=1):
    if text.count(old)!=count: raise ValueError(f"Expected{count} integration points: {old[:80]}")
    return text.replace(old,new)

def config(negative=None,positive=None,*,phase=0.,ramp=1.,enabled=True):
    return dict(version=1,experimental=True,enabled=enabled,ramp=ramp,
                negative=negative if negative is not None else [0.]*16,
                positive=positive if positive is not None else [0.]*16,
                phase_cycles_training_note91=phase)

def write_config(path,values):
    if len(values['negative'])!=16 or len(values['positive'])!=16: raise ValueError('Expected16 coefficients per side')
    numbers=[values['ramp'],values['phase_cycles_training_note91'],*values['negative'],*values['positive']]
    if any(not math.isfinite(x) for x in numbers) or not 0<=numbers[1]<1: raise ValueError('Invalid coefficient or phase')
    path=Path(path);dump(path,values)
    native=path.with_suffix('.native.txt')
    native.write_text(' '.join([str(int(values['enabled']))]+[format(x,'.17g') for x in numbers])+'\n')
    return native

def build(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    source=output/'source';source.mkdir()
    names=subprocess.check_output(['git','ls-tree','-r','--name-only',REVISION,'Source/DSP'],cwd=ROOT,text=True).splitlines()
    names+=['Tools/RenderMidi.cpp','Tools/render_midi.py']
    original={}
    for name in names:
        data=subprocess.check_output(['git','show',f'{REVISION}:{name}'],cwd=ROOT)
        path=source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);original[name]=sha(path)
    cpp=source/'Source/DSP/SeptumEngine.cpp';header=source/'Source/DSP/SeptumEngine.h';renderer=source/'Tools/RenderMidi.cpp'
    text=header.read_text();text=replace(text,'#include <atomic>','#include <atomic>\n#include "W4Experiment.h"')
    text=replace(text,'std::array<std::atomic<float>, 2>','std::array<saw_w4::CopyableAtomic, 2>',2);header.write_text(text)
    text=cpp.read_text()
    text=replace(text,'bool corrected = true, double phaseOffset = 0.0) noexcept','bool corrected = true, double phaseOffset = 0.0, int experimentNote = -1) noexcept')
    text=replace(text,'voice.osc2.noise, true, phaseOffset2);','voice.osc2.noise, true, phaseOffset2, voice.note);')
    text=replace(text,'! osc1SyncReset, phaseOffset1);','! osc1SyncReset, phaseOffset1, voice.note);')
    old='''                if (corrected)
                    value -= polyBlep (position, inc);
                return { value, wrapped, wrapOffset };'''
    new='''                if (corrected)
                {
                    ++saw_w4::stats.correctedCalls;
                    if (saw_w4::config.enabled)
                        value = saw_w4::source (position, inc, experimentNote);
                    else
                        value -= polyBlep (position, inc);
                }
                else ++saw_w4::stats.syncResetCalls;
                return { value, wrapped, wrapOffset };'''
    text=replace(text,old,new)
    text=replace(text,'const double a = std::abs (state);','const double a = std::abs (state);\n                    saw_w4::stats.statePeak = std::max(saw_w4::stats.statePeak,a);\n                    if(a > mapping::filterStateLimit) ++saw_w4::stats.stateLimits;')
    text=replace(text,'const double a = std::abs (x);\n        if (a <= mapping::outputLimitKnee)',
                 'const double a = std::abs (x);\n        saw_w4::stats.outputInputPeak = std::max(saw_w4::stats.outputInputPeak,a);\n        if(a > mapping::outputLimitKnee) ++saw_w4::stats.outputLimits;\n        if (a <= mapping::outputLimitKnee)')
    cpp.write_text(text)
    text=renderer.read_text();text=replace(text,'int main (int argc, char** argv)\n{\n    try\n    {','int main (int argc, char** argv)\n{\n    try\n    {\n        saw_w4::loadEnvironment();')
    text=replace(text,'cleanup.remove = false;','cleanup.remove = false;\n        saw_w4::saveStats();');renderer.write_text(text)
    (source/'W4Experiment.h').write_text(HEADER);(source/'W4Backend.cpp').write_text(BACKEND);(source/'W4Probe.cpp').write_text(PROBE)
    (output/'builder.py').write_bytes(Path(__file__).read_bytes())
    differences={}
    for name in names:
        original_text=subprocess.check_output(['git','show',f'{REVISION}:{name}'],cwd=ROOT,text=True)
        current=(source/name).read_text()
        if current!=original_text:
            import difflib
            differences[name]=''.join(difflib.unified_diff(original_text.splitlines(True),current.splitlines(True),fromfile=REVISION+'/'+name,tofile='experiment/'+name))
    (output/'experimental.diff').write_text('\n'.join(differences.values()))
    compiler=shutil.which('c++');commands=[]
    dsp=sorted(str(p.relative_to(source)) for p in (source/'Source/DSP').glob('*.cpp'))
    for entry,binary,inputs in [('Tools/RenderMidi.cpp','SeptumRenderMidi',dsp),('W4Backend.cpp','W4Backend',dsp),('W4Probe.cpp','W4Probe',[])]:
        command=[compiler,'-std=c++20','-O2','-fno-fast-math','-ISource','-I.',entry,*inputs,'-o',str(output/binary)]
        started=time.monotonic();run=subprocess.run(command,cwd=source,capture_output=True,text=True)
        (output/(binary+'.build.log')).write_text(run.stdout+run.stderr)
        commands.append(dict(command=command,seconds=time.monotonic()-started,returncode=run.returncode))
        if run.returncode: dump(output/'failed-build.json',commands);raise RuntimeError('Build failed: '+binary)
    manifest=dict(experimental=True,revision=REVISION,source_original_sha256=original,
        source_frozen_sha256={str(p.relative_to(source)):sha(p) for p in source.rglob('*') if p.is_file()},
        builder=pin(__file__),binaries={n:pin(output/n) for n in ('SeptumRenderMidi','W4Backend','W4Probe')},
        compiler_version=subprocess.check_output([compiler,'--version'],text=True),commands=commands,
        protocol=dict(width_samples=4,degree=3,continuity_at_interior_knots='C1',knots=KNOTS,
            columns=['unit_ramp']+[f'negative_{i}' for i in range(16)]+[f'positive_{i}' for i in range(16)],
            source_mean='inc * sum_j((negative[j]+positive[j])*(knots[j+4]-knots[j])/4)',
            phase='waveform-only offset on corrected Saw note91; other notes and canonical clock unchanged; final candidate0',
            capture_samples=[START,END],state_snapshot_sample=ONSET,
            backend_storage='little-endian float32 row-major3528x34: zero,ramp,negative16,positive16',
            unchanged='All non-Saw waveforms; corrected=false naive reset; wrap bookkeeping; complete downstream path',
            gates=dict(baseline_sha256=WAV_SHA,linearity_relative_rms=1e-6,linearity_max_absolute=2e-6,
                       source_scalar_absolute=2e-12,source_nesting_absolute=2e-12,matrix_condition_limit=1e6)))
    dump(output/'manifest.json',manifest);return manifest

def checked_build(folder):
    folder=Path(folder).resolve();m=json.loads((folder/'manifest.json').read_text())
    if m['revision']!=REVISION: raise ValueError('Wrong source revision')
    for item in m['binaries'].values(): pin(item['path'],item['sha256'])
    for name,h in m['source_frozen_sha256'].items(): pin(folder/'source'/name,h)
    return folder,m

def event_file(build_dir,midi_path,output):
    sys.path.insert(0,str(Path(build_dir)/'source/Tools'))
    import render_midi
    parsed=render_midi.parse_smf(Path(midi_path).read_bytes())
    events,ignored=render_midi.replay_events(parsed,channel=1,allow_unsupported=True,tempo_policy='preserve-patch')
    Path(output).write_text(f"SEPTUM_RENDER_EVENTS 1 {parsed['end_sample']}\n"+''.join(
        f"{e['sample']} {e['kind']} {e['value']}\n" for e in events),encoding='ascii')
    return parsed,events,ignored

class Backend:
    def __init__(self,build_dir,patch_path,midi_path,*,output_dir):
        self.build,self.manifest=checked_build(build_dir);self.output=Path(output_dir).resolve();self.output.mkdir(parents=True,exist_ok=False)
        self.patch=pin(patch_path,PATCH_SHA[12]);self.midi=pin(midi_path,MIDI_SHA)
        parsed,events,ignored=event_file(self.build,midi_path,self.output/'events.txt')
        if len([e for e in events if e['kind']=='midi'])!=248: raise ValueError('Original248 MIDI events required')
        self.command=[str(self.build/'W4Backend'),str(Path(patch_path).resolve()),str(self.output/'events.txt'),str(START),str(END)]
        self.stderr=(self.output/'backend.stderr').open('w');started=time.monotonic()
        self.process=subprocess.Popen(self.command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.stderr,text=True,bufsize=1)
        line=self.process.stdout.readline()
        if not line: raise RuntimeError('Backend failed to initialize; see stderr')
        self.ready=json.loads(line);self.ready['wall_seconds']=time.monotonic()-started
        dump(self.output/'ready.json',self.ready);self.requests=[];self.last_offset=None
        if self.ready['status']!='ready': raise RuntimeError('Backend not ready')
    def matrix(self,phase):
        import numpy as np
        if not math.isfinite(phase) or not 0<=phase<1: raise ValueError('Phase must be0<=phase<1')
        path=self.output/f"phase-{len(self.requests):05d}.f32";started=time.monotonic()
        self.process.stdin.write(f'PHASE {phase:.17g} {json.dumps(str(path))}\n');self.process.stdin.flush()
        line=self.process.stdout.readline()
        if not line: raise RuntimeError('Backend ended during request; see stderr')
        receipt=json.loads(line);receipt.update(wall_seconds=time.monotonic()-started,file=pin(path))
        raw=np.fromfile(path,dtype='<f4').reshape(END-START,34).astype(np.float64)
        if not np.isfinite(raw).all(): raise ValueError('Nonfinite backend output')
        self.last_offset=raw[:,0].copy();self.requests.append(receipt);dump(self.output/'requests.json',self.requests)
        return raw[:,1:]
    def offset(self,phase=None):
        if phase is not None and (not self.requests or self.requests[-1]['phase']!=phase): self.matrix(phase)
        if self.last_offset is None: raise ValueError('Call matrix(phase) first')
        return self.last_offset.copy()
    def close(self):
        if self.process.poll() is None:
            self.process.stdin.write('QUIT\n');self.process.stdin.flush();self.process.wait(timeout=30)
        self.stderr.close()
        if self.process.returncode: raise RuntimeError('Backend exited unsuccessfully')
    def __enter__(self): return self
    def __exit__(self,*_): self.close()

def open_backend(build_dir,patch_path,midi_path,*,output_dir):
    return Backend(build_dir,patch_path,midi_path,output_dir=output_dir)

def render_vector(build_dir,patch_path,midi_path,values,output_dir,*,allow_unsupported=True):
    build_dir,manifest=checked_build(build_dir);out=Path(output_dir).resolve();out.mkdir(parents=True,exist_ok=False)
    native=write_config(out/'coefficients.json',values)
    shutil.copyfile(patch_path,out/'patch.syx');shutil.copyfile(midi_path,out/'performance.mid')
    env=dict(os.environ,SEPTUM_W4_CONFIG=str(native),SEPTUM_W4_STATS=str(out/'state-stats.json'))
    command=[sys.executable,str(build_dir/'source/Tools/render_midi.py'),'--renderer',str(build_dir/'SeptumRenderMidi'),
             '--midi',str(out/'performance.mid'),'--syx',str(out/'patch.syx'),'--output',str(out/'candidate.wav'),'--tempo-policy','preserve-patch']
    if allow_unsupported: command+=['--allow-unsupported']
    started=time.monotonic();run=subprocess.run(command,env=env,capture_output=True,text=True)
    (out/'render.log').write_text(run.stdout+run.stderr)
    receipt=dict(command=command,wall_seconds=time.monotonic()-started,returncode=run.returncode,
        source_manifest=pin(build_dir/'manifest.json'),coefficients=pin(out/'coefficients.json'),native_config=pin(native))
    if run.returncode: dump(out/'failure.json',receipt);raise RuntimeError('Independent render failed: '+str(out))
    result=json.loads((out/'candidate.render.json').read_text());stats=json.loads((out/'state-stats.json').read_text())
    receipt.update(wav=pin(out/'candidate.wav'),render_receipt=pin(out/'candidate.render.json'),stats=stats,
                   latency_samples=result['output']['latency_samples'],peak=result['output']['peak'],active_voices_at_end=result['output']['active_voices_at_end'])
    if receipt['latency_samples']!=93 or receipt['active_voices_at_end']!=0: raise ValueError('Unexpected renderer latency or remaining voices')
    dump(out/'experiment-render.json',receipt);return receipt

def render_source(build_dir,patch_path,midi_path,coefficients,*,phase=0.,output_dir,phase_note=91,tail=2.):
    """Render independently through original full MIDI; None selects native Saw.

    Coefficient ordering is negative16 then positive16. Ramp stays exactly1.
    Nuisance phase changes only corrected Saw waveform positions for note91.
    """
    if phase_note!=91 or tail!=2.: raise ValueError('Frozen phase_note91 and tail2 required')
    if coefficients is None:
        if phase!=0: raise ValueError('Native baseline phase must remain0')
        values=config(enabled=False)
    else:
        if len(coefficients)!=32: raise ValueError('Expected32 W4 coefficients')
        values=config(list(coefficients[:16]),list(coefficients[16:]),phase=phase)
    render_vector(build_dir,patch_path,midi_path,values,output_dir)
    return Path(output_dir).resolve()/'candidate.wav'

def integration_controls(build_dir,patch_path,midi_path,output_dir):
    """Source-only gates; never reads original hardware audio or fits its data."""
    import numpy as np
    from scipy.interpolate import BSpline
    from scipy.io import wavfile
    from concurrent.futures import ThreadPoolExecutor
    build_dir,build_manifest=checked_build(build_dir)
    out=Path(output_dir).resolve();out.mkdir(parents=True,exist_ok=False)
    nested=np.r_[-np.array(NESTED),NESTED]
    planted=nested+np.r_[.035*np.sin((np.arange(16)+1)*.61),.045*np.cos((np.arange(16)+1)*.47)]
    protocol=dict(scope='source-free scalar, nesting, periodic/DC, engine-copy and linearity gates',
        build_manifest=pin(build_dir/'manifest.json'),tool=pin(__file__),patch=pin(patch_path,PATCH_SHA[12]),midi=pin(midi_path,MIDI_SHA),
        planted_coefficients=planted.tolist(),phases=[0.,.321],hardware_read=False,
        gates=build_manifest['protocol']['gates'],independent_truth='Separate complete MIDI vector renderer; never matrix times planted coefficients as truth')
    dump(out/'protocol-before-controls.json',protocol)
    basis=BSpline(KNOTS,np.eye(18)[:,:16],3,extrapolate=False)
    scalar_rows=[]
    for name,coeff in [('nested',nested),('asymmetric',planted)]:
        cfg=config(coeff[:16].tolist(),coeff[16:].tolist())
        native=write_config(out/(name+'.json'),cfg)
        coordinates=[]
        for inc in (1/256,.039,.1,.125,.15,.25,.45):
            positions=set(np.linspace(0,1,259,endpoint=False))
            for k in range(-2,4):
                for t in set(KNOTS):
                    for sign in (-1,1):
                        edge=k+sign*inc*t
                        for p in (edge-1e-10,edge,edge+1e-10):
                            if 0<=p<1: positions.add(p)
            coordinates.extend((p,inc,91,1) for p in sorted(positions))
        coordinates.extend((p,.1,91,0) for p in (0.,.01,.49,.51,.99))
        env=dict(os.environ,SEPTUM_W4_CONFIG=str(native))
        run=subprocess.run([str(build_dir/'W4Probe')],input=''.join(f'{p:.17g} {inc:.17g} {note} {corrected}\n' for p,inc,note,corrected in coordinates),text=True,capture_output=True,env=env,check=True)
        actual=np.fromstring(run.stdout,sep='\n');expected=[];poly=[]
        integral=sum((coeff[j]+coeff[16+j])*(KNOTS[j+4]-KNOTS[j])/4 for j in range(16))
        for p,inc,_,corrected in coordinates:
            value=2*p-1
            if corrected:
                value-=inc*integral
                for k in range(-4,5):
                    t=(p-k)/inc
                    if -4<t<0: value+=float(basis(-t)@coeff[:16])
                    elif 0<=t<4: value+=float(basis(t)@coeff[16:])
            expected.append(value)
            q=2*p-1
            if corrected:
                if p<inc: x=p/inc;q-=x+x-x*x-1
                elif p>1-inc: x=(p-1)/inc;q-=x*x+x+x+1
            poly.append(q)
        error=float(np.max(np.abs(actual-expected)))
        nesting=float(np.max(np.abs(actual-poly))) if name=='nested' else None
        # Independent high-order Gaussian integration split at every shifted
        # source knot. This tests continuous-phase DC, not finite-window DC.
        dc=[];nodes,weights=np.polynomial.legendre.leggauss(4)
        for inc in (.039,.125,.15,.25,.45):
            edges={0.,1.}
            for k in range(-2,4):
                for t in set(KNOTS):
                    for sign in (-1,1):
                        x=k+sign*inc*t
                        if 0<x<1: edges.add(x)
            edges=sorted(edges);points=[];quadrature=[]
            for a,b in zip(edges[:-1],edges[1:]):
                points.extend((a+b)/2+(b-a)*nodes/2);quadrature.extend((b-a)*weights/2)
            response=subprocess.run([str(build_dir/'W4Probe')],input=''.join(f'{p:.17g} {inc:.17g} 91 1\n' for p in points),text=True,capture_output=True,env=env,check=True)
            dc.append(float(np.fromstring(response.stdout,sep='\n')@quadrature))
        row=dict(id=name,points=len(coordinates),max_scalar_absolute_error=error,
                 native_polyblep_max_absolute_error=nesting,continuous_phase_means=dc)
        scalar_rows.append(row);dump(out/'source-controls.json',scalar_rows)
        if error>2e-12 or (nesting is not None and nesting>2e-12) or max(abs(x) for x in dc)>2e-12:
            raise ValueError('Independent scalar/nesting/DC source gate failed')
    # Source signal is independently rendered, including all earlier notes,
    # rather than created by multiplying the measured downstream matrix.
    def render(phase):
        return render_source(build_dir,patch_path,midi_path,planted,phase=phase,output_dir=out/f'planted-phase-{phase:.3f}')
    with ThreadPoolExecutor(max_workers=2) as pool: truths=dict(zip((0.,.321),pool.map(render,(0.,.321))))
    backend_rows=[]
    with open_backend(build_dir,patch_path,midi_path,output_dir=out/'backend') as backend:
        for phase in (0.,.321):
            matrix=backend.matrix(phase);offset=backend.offset()
            sr,audio=wavfile.read(truths[phase]);truth=audio[START:END,0].astype(np.float64)
            reconstructed=offset+(matrix-offset[:,None])@np.r_[1.,planted]
            relative_rms=float(np.sqrt(np.mean((truth-reconstructed)**2)/np.mean(truth**2)))
            absolute=float(np.max(np.abs(truth-reconstructed)))
            design=np.column_stack((matrix[:,1:]-offset[:,None],np.ones(END-START)))
            singular=np.linalg.svd(design,compute_uv=False);rank=int(np.linalg.matrix_rank(design));condition=float(singular[0]/singular[-1])
            row=dict(phase=phase,independent_truth=pin(truths[phase]),offset_peak=float(np.max(np.abs(offset))),
                linearity_relative_rms=relative_rms,linearity_max_absolute=absolute,
                coefficient_plus_dc_rank=rank,coefficient_plus_dc_columns=33,coefficient_plus_dc_condition=condition,
                request=backend.requests[-1],independent_render=json.loads(truths[phase].with_name('experiment-render.json').read_text()))
            backend_rows.append(row);dump(out/'backend-controls.json',dict(ready=backend.ready,rows=backend_rows))
            stats=[row['request']['stats'],row['independent_render']['stats'],backend.ready['prewarm_stats']]
            if relative_rms>1e-6 or absolute>2e-6 or rank!=33 or condition>1e6:
                raise ValueError('Full-engine linearity/copy/rank gate failed')
            if any(s['filter_limit_calls'] or s['output_limit_calls'] for s in stats):
                raise ValueError('Full-engine limiter was active during a linearity control')
    proof=dict(status='pass',protocol=pin(out/'protocol-before-controls.json'),source_controls=scalar_rows,
               backend_controls=backend_rows,backend_ready=json.loads((out/'backend/ready.json').read_text()),
               build=pin(build_dir/'manifest.json'),tool=pin(__file__),hardware_read=False)
    dump(out/'control-proof.json',proof);return proof

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='stage',required=True)
    b=sub.add_parser('build');b.add_argument('--output',type=Path,required=True)
    r=sub.add_parser('render');r.add_argument('--build',type=Path,required=True);r.add_argument('--patch',type=Path,required=True);r.add_argument('--midi',type=Path,required=True);r.add_argument('--coefficients',type=Path,required=True);r.add_argument('--output',type=Path,required=True)
    c=sub.add_parser('controls');c.add_argument('--build',type=Path,required=True);c.add_argument('--patch',type=Path,required=True);c.add_argument('--midi',type=Path,required=True);c.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.stage=='build': print(json.dumps(build(a.output),indent=2))
    elif a.stage=='render': print(json.dumps(render_vector(a.build,a.patch,a.midi,json.loads(a.coefficients.read_text()),a.output),indent=2))
    else: print(json.dumps(integration_controls(a.build,a.patch,a.midi,a.output),indent=2))
if __name__=='__main__': main()
