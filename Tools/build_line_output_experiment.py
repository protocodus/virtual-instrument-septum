#!/usr/bin/env python3
"""Frozen isolated ideal line-output trial. No shipping Source edits or audio fitting."""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import warnings
import numpy as np
from scipy.io import wavfile
ROOT=Path(__file__).resolve().parents[1]
REV='4b9f1bfc609910154066708d2cf03e119c7d7b71'
FRACTIONS=[.1,.5,1.]
HEADER=r'''#pragma once
// Isolated, normalized ideal LINE-stage experiment; both stereo plugs inserted.
#include <array>
#include <cmath>
#include <cstdlib>
#include <stdexcept>
namespace septum {
struct LineOutputSection {
    double b0=1,b1=0,b2=0,a1=0,a2=0,z0=0,z1=0;
    void prepare(double d0,double d1,double d2,double n1,double c) noexcept {
        if(d2==0) { // Remove the cancelled z=-1 pole at electrical volume1.
            const double d=d0+d1*c;
            b0=n1*c/d;b1=-b0;b2=0;a1=(d0-d1*c)/d;a2=0;
        } else {
            const double d=d0+d1*c+d2*c*c;
            b0=n1*c/d;b1=0;b2=-b0;
            a1=(2*d0-2*d2*c*c)/d;a2=(d0-d1*c+d2*c*c)/d;
        }
        reset();
    }
    void reset() noexcept {z0=z1=0;}
    double process(double x) noexcept {
        const double y=b0*x+z0;
        z0=b1*x-a1*y+z1;z1=b2*x-a2*y;return y;
    }
};
struct LineOutputExperiment {
    bool enabled=false;
    std::array<LineOutputSection,2> section{};
    void prepare(double fs,double a) {
        if(a!=.1 && a!=.5 && a!=1.)throw std::runtime_error("Unfrozen LINE fraction");
        enabled=true;
        const double ci=22e-6,cw=100e-12,rp=10000,rs=1010,co=470e-12;
        const double g=1/(a*rp)+1/10000.+1/104700., r=(1-a)*rp;
        const double gl=1/10000.,gb=1/100000.,c=16*fs;
        section[0].prepare(g,ci*(1+r*g)+cw,ci*r*cw,ci*(1+r*g),c);
        section[1].prepare(gb*(1+rs*gl)+gl,ci*(1+rs*gl)+co*(1+gb*rs),ci*rs*co,ci*(1+rs*gl),c);
    }
    void prepare(double fs) {
        enabled=false;
        if(const char* p=std::getenv("SEPTUM_LINE_FRACTION")) {
            char* end=nullptr;const double a=std::strtod(p,&end);
            if(end==p || *end!='\0')throw std::runtime_error("Invalid LINE fraction");
            prepare(fs,a);
        }
        reset();
    }
    void reset() noexcept {for(auto& s:section)s.reset();}
    double process(double x) noexcept {
        if(!enabled)return x;
        return section[1].process(section[0].process(x));
    }
};
} // namespace septum
'''
PROBE=r'''#include "Source/DSP/LineOutputExperiment.h"
#include <complex>
#include <iomanip>
#include <iostream>
int main(){
  constexpr double pi=3.14159265358979323846,fs=44100,internal=8*fs;
  std::cout<<std::setprecision(17)<<"{\"rows\":[";bool first=true;
  for(double a:{.1,.5,1.})for(double hz:{20.,50.,100.,1000.,5000.,10000.,20000.}){
    septum::LineOutputExperiment p;p.prepare(fs,a);std::complex<double> sum{};
    const int settle=static_cast<int>(6*internal),count=static_cast<int>(internal);
    const double angle=2*pi*hz/internal,cs=std::cos(angle),sn=std::sin(angle);
    double co=1,si=0;
    for(int n=0;n<settle+count;++n){
      double y=p.process(co);if(n>=settle)sum+=y*std::complex<double>(co,-si);
      double next=co*cs-si*sn;si=si*cs+co*sn;co=next;
    }
    sum*=2./count;if(!first)std::cout<<',';first=false;
    std::cout<<"{\"fraction\":"<<a<<",\"hz\":"<<hz<<",\"response\":["<<sum.real()<<','<<sum.imag()<<"],\"sections\":[";
    for(int j=0;j<2;++j){if(j)std::cout<<',';auto& s=p.section[j];std::cout<<'['<<s.b0<<','<<s.b1<<','<<s.b2<<','<<s.a1<<','<<s.a2<<']';}
    std::cout<<"]}";
  }
  std::cout<<"]}\n";
}
'''
def pin(path):
    p=Path(path).resolve();return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def verify(item):
    assert pin(item['path'])==item,item
    return Path(item['path'])
def save(path,data):Path(path).write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
def call(command,cwd,log,env=None):
    t=time.monotonic();r=subprocess.run(command,cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    Path(log).write_text(r.stdout)
    row=dict(command=list(map(str,command)),cwd=str(cwd),returncode=r.returncode,seconds=time.monotonic()-t,log=pin(log))
    if r.returncode:raise RuntimeError(row)
    return row

def build(out,baseline):
    source=out/'build/source';source.mkdir(parents=True)
    paths=subprocess.check_output(['git','ls-tree','-r','--name-only',REV,'Source','Tools/RenderMidi.cpp','Tools/render_midi.py'],cwd=ROOT,text=True).splitlines()
    originals={}
    for path in paths:
        data=subprocess.check_output(['git','show',REV+':'+path],cwd=ROOT)
        p=source/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);originals[path]=hashlib.sha256(data).hexdigest()
    header=source/'Source/DSP/AnalogOutput.h';s=header.read_text()
    replacements=[('#include <cstddef>','#include <cstddef>\n#include "LineOutputExperiment.h"'),
        ('        hpGain_ = 0.5 * (1.0 + hpPole_);','        hpGain_ = 0.5 * (1.0 + hpPole_);\n        lineOutput_.prepare (sampleRate);'),
        ('        z_.fill (0.0);','        z_.fill (0.0);\n        lineOutput_.reset();'),
        ('            z_[2] = b_[3] * hp - a_[2] * y;\n            return y;','            z_[2] = b_[3] * hp - a_[2] * y;\n            return lineOutput_.process (y);'),
        ('    analog_output_detail::Oversampling8 oversampling_ {};','    analog_output_detail::Oversampling8 oversampling_ {};\n    LineOutputExperiment lineOutput_ {};')]
    for before,after in replacements:
        assert s.count(before)==1,before;s=s.replace(before,after)
    header.write_text(s);(source/'Source/DSP/LineOutputExperiment.h').write_text(HEADER);(source/'LineProbe.cpp').write_text(PROBE)
    commands=[]
    renderer=out/'build/SeptumRenderMidi';probe=out/'build/LineProbe'
    for name,sources,target in [('renderer',['Tools/RenderMidi.cpp','Source/DSP/ReferenceRateEngine.cpp','Source/DSP/SeptumEngine.cpp','Source/DSP/SeptumPresets.cpp','Source/DSP/SeptumSysEx.cpp'],renderer),('probe',['LineProbe.cpp'],probe)]:
        command=['c++','-std=c++20','-O2','-fno-fast-math','-ISource','-I.',*sources,'-o',str(target)]
        commands.append(call(command,source,out/'build'/f'{name}.log'))
    result=dict(source_revision=REV,original_file_sha256=originals,modified_files=[pin(header),pin(source/'Source/DSP/LineOutputExperiment.h')],source_root=str(source),renderer=pin(renderer),probe=pin(probe),probe_source=pin(source/'LineProbe.cpp'),compiler=subprocess.check_output(['c++','--version'],text=True),commands=commands,builder=pin(__file__))
    save(out/'build/manifest.json',result);return result

def controls(out,b):
    commands=call([str(verify(b['probe']))],ROOT,out/'build/probe-output.json')
    measured=json.loads((out/'build/probe-output.json').read_text())
    spec=importlib.util.spec_from_file_location('mna',ROOT/'Tools/review_output_stage_math.py');mna=importlib.util.module_from_spec(spec);spec.loader.exec_module(mna)
    rows=[]
    for row in measured['rows']:
        hz=row['hz'];target=mna.line_mna(np.array([hz]),10000,row['fraction'],10000)[0]
        actual=complex(*row['response']);ratio=actual/target
        mag=abs(20*np.log10(abs(ratio)));phase=abs(np.angle(ratio,deg=True))
        z=np.exp(-2j*np.pi*hz/(8*44100));direct=1+0j
        stable=True
        for b0,b1,b2,a1,a2 in row['sections']:
            direct*=(b0+b1*z+b2*z*z)/(1+a1*z+a2*z*z)
            stable &= bool(np.all(np.abs(np.roots([1,a1,a2]))<1))
        rows.append(dict(fraction=row['fraction'],hz=hz,magnitude_error_db=float(mag),phase_error_degrees=float(phase),processor_vs_coefficients_abs=float(abs(actual-direct)),stable_poles=stable,sections=row['sections']))
    result=dict(status='passed',command=commands,independent_mna=pin(ROOT/'Tools/review_output_stage_math.py'),rows=rows,maximum_magnitude_error_db=max(r['magnitude_error_db'] for r in rows),maximum_phase_error_degrees=max(r['phase_error_degrees'] for r in rows),maximum_processor_vs_coefficients_abs=max(r['processor_vs_coefficients_abs'] for r in rows))
    save(out/'controls.json',result)
    if result['maximum_magnitude_error_db']>.002 or result['maximum_phase_error_degrees']>.1 or result['maximum_processor_vs_coefficients_abs']>1e-7 or not all(r['stable_poles'] for r in rows):
        result['status']='failed';save(out/'controls.json',result);raise ValueError('LINE implementation controls failed')
    return result

def read_audio(path):
    with warnings.catch_warnings():warnings.simplefilter('ignore');sr,x=wavfile.read(path)
    assert sr==44100 and x.dtype==np.float32 and x.ndim==2 and x.shape[1]==2
    assert np.all(np.isfinite(x));return x.astype(np.float64)

def raw_metrics(x,y):
    def stat(z):
        peak=float(np.max(np.abs(z)));rms=float(np.sqrt(np.mean(z*z)))
        return dict(peak=peak,rms=rms,power=float(np.mean(z*z)),crest_db=20*math.log10(peak/rms),per_channel_crest_db=[20*math.log10(float(np.max(np.abs(z[:,i])))/float(np.sqrt(np.mean(z[:,i]**2)))) for i in (0,1)])
    sx,sy=stat(x),stat(y);e=x-y
    return dict(baseline=sx,candidate=sy,crest_delta_db=sy['crest_db']-sx['crest_db'],power_delta_db=10*math.log10(sy['power']/sx['power']),peak_delta_db=20*math.log10(sy['peak']/sx['peak']),residual_rms=float(np.sqrt(np.mean(e*e))),relative_residual_rms=float(np.sqrt(np.mean(e*e)/np.mean(x*x))),maximum_abs_residual=float(np.max(np.abs(e))),candidate_below_output_knee=sy['peak']<.9)

def render_all(out,b,reference):
    env={k:v for k,v in os.environ.items() if not k.startswith('SEPTUM_')}
    source=Path(b['source_root']);renderer=verify(b['renderer']);rows=[];commands=[]
    for variant,a in [('baseline',None)]+[(f'a-{a:g}',a) for a in FRACTIONS]:
        for old in reference['results']:
            directory=out/variant/old['cohort']/old['id'];directory.mkdir(parents=True)
            oldwav=verify(old['production']);receipt=json.loads(verify(old['production_receipt']).read_text());settings=receipt['settings']
            for key,name in [('sysex','patch.syx'),('midi','performance.mid')]:shutil.copyfile(verify(receipt['inputs'][key]),directory/name)
            wav=directory/'candidate.wav'
            command=[sys.executable,str(source/'Tools/render_midi.py'),'--renderer',str(renderer),'--midi',str(directory/'performance.mid'),'--syx',str(directory/'patch.syx'),'--output',str(wav),'--sample-rate',str(settings['sample_rate']),'--tail',str(settings['tail_seconds']),'--master-level',str(settings['master_level']),'--channel',str(settings['midi_channel']),'--tempo-policy',settings['tempo_policy']]
            if settings['unsupported_policy']=='omit with audit':command.append('--allow-unsupported')
            e=env.copy()
            if a is not None:e['SEPTUM_LINE_FRACTION']=str(a)
            commands.append(call(command,ROOT,directory/'render.log',e))
            fresh=json.loads(wav.with_suffix('.render.json').read_text())
            assert fresh['settings']==settings,(fresh['settings'],settings)
            assert fresh['midi']==receipt['midi']
            assert fresh['output']['latency_samples']==receipt['output']['latency_samples']
            x,y=read_audio(oldwav),read_audio(wav);assert x.shape==y.shape
            identity=pin(wav)['sha256']==pin(oldwav)['sha256']
            row=dict(id=old['id'],cohort=old['cohort'],variant=variant,electrical_fraction=a,production=pin(wav),production_receipt=pin(wav.with_suffix('.render.json')),inputs={k:pin(directory/n) for k,n in [('sysex','patch.syx'),('midi','performance.mid')]},baseline_pin=pin(oldwav),frames=len(y),latency_samples=fresh['output']['latency_samples'],byte_identical_to_baseline=identity,metrics_vs_baseline=raw_metrics(x,y))
            rows.append(row);save(out/'partial-results.json',dict(cases=rows,commands=commands))
            print(variant,old['id'],'identity',identity,flush=True)
            if a is None and not identity:raise ValueError('Baseline byte identity failed')
    result=dict(status='complete',source_revision=REV,protocol=pin(out/'protocol-before-build.json'),build_manifest=pin(out/'build/manifest.json'),controls=pin(out/'controls.json'),baseline_receipt=pin(ROOT/'build-fidelity/saw-w4-production-integration/run-02/results.json'),cases=rows,commands=commands)
    save(out/'manifest.json',result)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    path=ROOT/'build-fidelity/saw-w4-production-integration/run-02/results.json';reference=json.loads(path.read_text())
    protocol=dict(status='frozen before build, controls and renders',source_revision=REV,builder=pin(__file__),baseline=pin(path),fractions=FRACTIONS,pot_ohms=10000,external_load_ohms=10000,scope='Ideal omitted LINE network only, after existing SK y inside the existing8x lambda; both stereo plugs inserted; muteoff; ferrites ideal wires',normalization='Only constant resistive pot/load and idealIC20gain2 removed as in independentMNA; no scalar fitting',sample_rate=44100,latency='Unchanged existing transport; no extraoversampler',controls=dict(maximum_magnitude_error_db=.002,maximum_phase_error_degrees=.1,maximum_processor_vs_coefficients_abs=1e-7,baseline_all12_byte_identity=True),render_count=48,candidate_count=36,selection='None: preserve all three cases, no fitting or selection by results',metrics='All-frame stereo/eachchannel crest, power, peak and baseline residual; original-scoring uses separately frozen gates/gains; no new lag/gain fit',exclusions=['No Source edits','No finite-A, distortion, saturation, noise, slew or DAC digitalfilter model','ExistingSKcoupling approximation retained'])
    save(out/'protocol-before-build.json',protocol)
    b=build(out,reference);controls(out,b);render_all(out,b,reference)
if __name__=='__main__':main()
