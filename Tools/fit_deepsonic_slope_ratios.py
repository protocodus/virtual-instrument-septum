#!/usr/bin/env python3
"""Conditional extra-section fits of paired Q0 harmonic ratios; no DSP edits."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import numpy as np
from scipy.optimize import least_squares, minimize_scalar

ROOT=Path(__file__).resolve().parents[1]
SR=44100
FC_BOUNDS=(5.,22000.)
K_BOUNDS=(.05,4.)
TOLERANCES=(.10,.25,.50)
GRID=np.geomspace(*FC_BOUNDS,1201)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def rms(x):return float(np.sqrt(np.mean(np.asarray(x)**2)))


def response(base,hs,fc,k):
    frequencies=np.array([base]+[h*base for h in hs])
    ratio=np.tan(np.pi*frequencies/SR)/np.tan(np.pi*fc/SR)
    db=-10*np.log10((1-ratio*ratio)**2+(k*ratio)**2)
    return db[1:]-db[0]


def fit(base,hs,target,free,profiles=True):
    target=np.asarray(target)
    if free:
        def residual(v):return response(base,hs,np.exp(v[0]),v[1])-target
        solutions=[least_squares(residual,[np.log(fc),k],bounds=([np.log(FC_BOUNDS[0]),K_BOUNDS[0]],
                    [np.log(FC_BOUNDS[1]),K_BOUNDS[1]]),xtol=1e-11,ftol=1e-11,gtol=1e-11)
                   for fc in (500,2500,7000,14000,21999) for k in (.3,1.2,3.)]
        best=min(solutions,key=lambda r:rms(r.fun));fc,k=float(np.exp(best.x[0])),float(best.x[1])
    else:
        loss=lambda logfc:rms(response(base,hs,np.exp(logfc),1.2)-target)
        scores=np.array([loss(np.log(fc)) for fc in GRID]);i=int(np.argmin(scores))
        bounds=(np.log(GRID[max(0,i-1)]),np.log(GRID[min(len(GRID)-1,i+1)]))
        found=minimize_scalar(loss,bounds=bounds,method='bounded',options={'xatol':1e-12})
        fc=float(np.exp(found.x)) if found.fun<scores[i] else float(GRID[i]);k=1.2
    prediction=response(base,hs,fc,k);error=rms(prediction-target)
    row=dict(cutoff_hz=fc,damping=k,rmse_db=error,max_abs_error_db=float(np.max(abs(prediction-target))),
             prediction_db=prediction.tolist(),residual_db=(prediction-target).tolist(),
             cutoff_at_upper_bound=fc>21999.,damping_at_bound=k<K_BOUNDS[0]+1e-5 or k>K_BOUNDS[1]-1e-5)
    if profiles:
        if free:
            def profile(fc):
                loss=lambda k:rms(response(base,hs,fc,k)-target)
                # Uniform bounded scalar profiles plus endpoints. Multiple
                # starts above independently check the final two-dimensional fit.
                found=minimize_scalar(loss,bounds=K_BOUNDS,method='bounded')
                return min(found.fun,loss(K_BOUNDS[0]),loss(K_BOUNDS[1]))
            scores=np.array([profile(fc) for fc in GRID])
        else:scores=np.array([rms(response(base,hs,fc,1.2)-target) for fc in GRID])
        ranges=[]
        for tolerance in TOLERANCES:
            accepted=np.flatnonzero(scores<=error+tolerance)
            if not len(accepted):raise ValueError('Profile lost fitted solution')
            low=int(accepted[0]);high=int(accepted[-1])
            ranges.append(dict(extra_rmse_tolerance_db=tolerance,
                lower_cutoff_bracket_hz=[float(GRID[max(0,low-1)]),float(GRID[low])],
                upper_cutoff_bracket_hz=[float(GRID[high]),float(GRID[min(len(GRID)-1,high+1)])],
                includes_22000_hz=bool(high==len(GRID)-1),
                connected_grid_runs=int(1+np.count_nonzero(np.diff(accepted)>1))))
        row['profile_tolerance_ranges']=ranges
    return row


def fixed_svf_controls(out):
    engine=ROOT/'Source/DSP/SeptumEngine.cpp';source=engine.read_text()
    first=source.index('const double v3 = input - stage.ic2eq;')
    last=source.index('// Stage limiter:',first)
    recurrence=source[first:last].strip()
    if recurrence.count('stage.ic1eq =')!=1 or recurrence.count('stage.ic2eq =')!=1:
        raise ValueError('SVF extraction changed')
    cpp='''#include <array>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <algorithm>
struct Stage { double ic1eq=0,ic2eq=0; };
int main(int argc,char**argv) {
  const double base=440*std::exp2((std::atoi(argv[1])-69)/12.0);
  const double fc=std::atof(argv[2]), k=std::atof(argv[3]);
  const double pi=std::acos(-1.0), g=std::tan(pi*fc/44100.0);
  const double stageA1=1/(1+g*(g+k)), stageA2=g*stageA1;
  double maximum=0;
  auto pass=[&](Stage&stage,double input) {
    RECURRENCE
    maximum=std::max(maximum,std::max(std::abs(stage.ic1eq),std::abs(stage.ic2eq)));
    return v2;
  };
  Stage first,second;std::array<double,4> l{},r{};
  for(int i=0;i<44100;++i) {
    double x=0;
    for(int h=1;h<=8;++h) {
      double a=.002*(1+.3*std::sin(1.7*h))/(1+.12*h);
      if(h==5)a*=.15; if(h==6)a*=.05;
      x+=a*std::cos(2*pi*h*base*i/44100.0+.173*h*h);
    }
    const double low=pass(first,x), high=pass(second,low);
    for(int j=3;j>0;--j){l[j]=l[j-1];r[j]=r[j-1];}
    l[0]=low;r[0]=high;
    const double a=.5*l[0]-.15*l[1]+.35*l[2]+.2*l[3];
    const double b=.83*(.5*r[0]-.15*r[1]+.35*r[2]+.2*r[3]);
    if(i>=44100-1764){std::fwrite(&a,8,1,stdout);std::fwrite(&b,8,1,stdout);}
  }
  if(maximum>=.1)return 2; // far below the shipping nonlinear state limiter
  return 0;
}
'''.replace('RECURRENCE',recurrence)
    fixture=out/'fixed-svf-control.cpp';fixture.write_text(cpp)
    binary=out/'fixed-svf-control'
    command=['c++','-O2','-std=c++17',str(fixture),'-o',str(binary)]
    subprocess.run(command,check=True)
    rows=[]
    for note in (69,84,86,88,91,93):
        base=440*2**((note-69)/12);t=np.arange(1764)/SR
        matrix=np.column_stack([np.ones(len(t))]+[v for h in range(1,9)
                               for v in (np.cos(2*np.pi*h*base*t),np.sin(2*np.pi*h*base*t))])
        for fc in (2500.,7000.,18000.):
            for k in (.8,1.2,2.):
                data=subprocess.check_output([str(binary),str(note),str(fc),str(k)])
                audio=np.frombuffer(data,dtype=np.float64).reshape(-1,2)
                coef=np.linalg.lstsq(matrix,audio,rcond=None)[0]
                amps=np.hypot(coef[1::2],coef[2::2])
                target=20*np.log10(amps[1:,1]/amps[0,1])-20*np.log10(amps[1:,0]/amps[0,0])
                model=fit(base,list(range(2,9)),target,True,False)
                analytic_error=rms(response(base,list(range(2,9)),fc,k)-target)
                if analytic_error>1e-7 or abs(model['cutoff_hz']/fc-1)>1e-5 or abs(model['damping']-k)>1e-5:
                    raise ValueError('Actual SVF ratio recovery failed')
                rows.append(dict(note=note,true_cutoff_hz=fc,true_damping=k,
                    measured_ratio_db=target.tolist(),analytic_rmse_db=analytic_error,
                    fit=model,output_sha256=hashlib.sha256(data).hexdigest()))
    return dict(engine_path=str(engine),engine_sha256=sha(engine),recurrence=recurrence,
                fixture_sha256=sha(fixture),binary_sha256=sha(binary),compile_command=command,
                method='Actual extracted scalar TPT state recurrence; fixed cutoff/damping, warmed1second, last40ms. Shared arbitrary eight-harmonic source with deep H5/H6 notches, common signed FIR and independent0.83 LP24 gain. State maximum below0.1; inactive nonlinear limiter omitted. No1/h assumption.',
                cases=rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    original=json.loads(args.input.read_text())
    helper=ROOT/'Tools/analyze_deepsonic_high_note_invariance.py'
    if sha(helper)!=original['tool_sha256']:raise ValueError('Invariance helper changed')
    for s in original['sources']:
        if sha(ROOT/s['path'])!=s['sha256']:raise ValueError('Original source changed')
    protocol=dict(status='exploratory_conditional_extra_TPT_section_not_raw_law_or_engine_candidate',
        input_sha256=sha(args.input),invariance_helper_sha256=sha(helper),source_receipts=original['sources'],
        frequency_policies=['nominal','frozen_refined'],width_seconds=.04,
        cutoff_bounds_hz=FC_BOUNDS,damping_bounds=K_BOUNDS,fixed_damping=1.2,
        groups=['paired_common_H2_H8','fixed_H2_H4'],
        eligibility='Both slopes and both frequency policies must exceed-55dB/H1 and20dB coefficient-SNR proxy, per time/harmonic. Minimum3 harmonics. Candidate-independent.',
        ratio='20log10(Ah_LP24/A1_LP24)-20log10(Ah_LP12/A1_LP12)',
        model='One extra section H(f)=1/[1-r²+j*k*r], r=tan(pi*f/SR)/tan(pi*fc/SR); normalize magnitude to H(f0).',
        assumptions='Identical oscillator/capture frequency response and identical first filter section/cutoff in the paired recordings. The procedural recipe does not authenticate these equalities or identical raw patches. A40ms window may contain moving filter behavior.',
        profiles='1201 logarithmic cutoff samples, nuisance k profiled if free; best RMSE+0.10/0.25/0.50dB tolerance ranges are sensitivity bounds, not statistical confidence intervals.',
        frozen_curve=original['frozen_cutoff_extrapolation'])
    (out/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    controls=fixed_svf_controls(out)
    windows=[r for r in original['hardware']['windows'] if r['purpose']=='cutoff_divergence' and r['width_seconds']==.04]
    rows=[]
    for note in sorted({r['note'] for r in windows}):
        for offset in sorted({r['offset_seconds'] for r in windows if r['note']==note}):
            common=[r for r in windows if r['note']==note and r['offset_seconds']==offset]
            if len(common)!=4:raise ValueError('Missing paired frequency-policy window')
            eligible=[h for h in range(2,9) if all(r['relative_h1_db'][h-1]>-55 and
                      r['coefficient_snr_proxy_db'][h-1]>=20 for r in common)]
            for group,hs in [('paired_common_H2_H8',eligible),('fixed_H2_H4',[2,3,4])]:
                valid=len(hs)>=3 and all(h in eligible for h in hs)
                for policy in ('nominal','frozen_refined'):
                    pair=[r for r in common if r['frequency_policy']==policy]
                    low=next(r for r in pair if r['slope']==12);high=next(r for r in pair if r['slope']==24)
                    record=dict(note=note,offset_seconds=offset,frequency_policy=policy,group=group,
                        harmonics=hs,eligible=valid,frequency_hz=low['frequency_hz'],
                        source_residual_power=[low['residual_power_fraction'],high['residual_power_fraction']])
                    if valid:
                        target=np.array(high['relative_h1_db'])[np.array(hs)-1]-np.array(low['relative_h1_db'])[np.array(hs)-1]
                        fc=low['frozen_low_note_cutoff_extrapolation_hz'];base=low['frequency_hz']
                        at_curve=response(base,hs,fc,1.2)
                        kfit=minimize_scalar(lambda k:rms(response(base,hs,fc,k)-target),bounds=K_BOUNDS,method='bounded')
                        record.update(observed_ratio_db=target.tolist(),ratio_rms_db=rms(target),
                            fixed_k=fit(base,hs,target,False),free_k=fit(base,hs,target,True),
                            frozen_curve=dict(cutoff_hz=fc,fixed_k_prediction_db=at_curve.tolist(),fixed_k_rmse_db=rms(at_curve-target),
                                              best_bounded_k=float(kfit.x),free_k_rmse_db=float(kfit.fun)))
                    rows.append(record)
    result=dict(protocol=protocol,script_sha256=sha(__file__),input_path=str(args.input.resolve()),
                controls=controls,rows=rows,conclusion='Conditional diagnostic only; inspect tolerances and model residuals before interpreting a fitted cutoff.')
    (out/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print('controls',len(controls['cases']),'paired fits',sum(r['eligible'] for r in rows),flush=True)


if __name__=='__main__':main()
