#!/usr/bin/env python3
"""Independent full-node review of the frozen output-stage calculation; no audio fitting."""
import argparse
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]

def pin(path):
    p=Path(path).resolve()
    return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())

def solve_network(hz, names, connections, drive_cap, amp, gbw, dc_gain):
    """KCL at every physical node, plus the dependent voltage-source current.

    connections: (nodeA,nodeB,conductance,capacitance); None denotes ground.
    drive_cap: capacitance from a unit ideal input voltage to its named node.
    amp: (noninverting,inverting,output). Feedback remains explicit resistors.
    """
    idx={name:i for i,name in enumerate(names)}; n=len(idx); s=2j*np.pi*np.asarray(hz)
    m=np.zeros((len(s),n+1,n+1),complex); b=np.zeros((len(s),n+1),complex)
    for na,nb,g,c in connections:
        y=g+s*c
        if na is not None: m[:,idx[na],idx[na]]+=y
        if nb is not None: m[:,idx[nb],idx[nb]]+=y
        if na is not None and nb is not None:
            m[:,idx[na],idx[nb]]-=y; m[:,idx[nb],idx[na]]-=y
    node,cap=drive_cap; m[:,idx[node],idx[node]]+=s*cap; b[:,idx[node]]=s*cap
    plus,minus,out=map(idx.get,amp)
    m[:,out,n]=1
    # v+ - v- = vout/A; ideal opamp is the A→infinity limiting constraint.
    m[:,n,plus]=1; m[:,n,minus]=-1
    if gbw is not None: m[:,n,out]=-(1/dc_gain+s/(2*np.pi*gbw))
    return np.linalg.solve(m,b[...,None])[...,0],idx

def reconstruction_mna(hz,gbw=None,dc_gain=1e5):
    edges=[('coupled',None,1/22000,0),('coupled','junction',1/4700,0),
           ('junction','plus',1/8200,0),('junction','out',0,270e-12),
           ('plus',None,0,820e-12),('minus',None,1/22000,0),
           ('minus','out',1/33000,10e-12)]
    v,idx=solve_network(hz,['coupled','junction','plus','minus','out'],edges,
                        ('coupled',22e-6),('plus','minus','out'),gbw,dc_gain)
    return v[:,idx['out']]/2.5

def line_mna(hz,pot,a,load,gbw=None,dc_gain=1e5):
    # At full volume the top and wiper are one node, avoiding a fake small R.
    top='wiper' if a==1 else 'top'
    names=list(dict.fromkeys([top,'wiper','phones','minus','amp','coupled','between','jack']))
    edges=[('wiper',None,1/(a*pot)+1/10000,100e-12),
           ('wiper','phones',1/4700,0),('phones',None,1/100000,0),
           ('minus',None,1/22000,0),('minus','amp',1/22000,0),
           ('amp','coupled',0,22e-6),('coupled',None,1/100000,0),
           ('coupled','between',1/680,0),('between','jack',1/330,0),
           ('jack',None,1/load,470e-12)]
    if a!=1: edges.append((top,'wiper',1/((1-a)*pot),0))
    v,idx=solve_network(hz,names,edges,(top,22e-6),('wiper','minus','amp'),gbw,dc_gain)
    # Remove the identical constant reference gains, independent of capacitors.
    wiper_r=1/(1/(a*pot)+1/10000+1/(4700+100000))
    constant=2*wiper_r/((1-a)*pot+wiper_r)*load/(load+680+330)
    return v[:,idx['jack']]/constant

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    original=json.loads((a.run/'results.json').read_text()); protocol=original['protocol']
    tool=Path(protocol['tool']['path']); assert pin(tool)==protocol['tool']
    spec=importlib.util.spec_from_file_location('reviewed_circuit',tool); root=importlib.util.module_from_spec(spec);spec.loader.exec_module(root)
    hz=np.geomspace(20,20000,801); records=[]; max_complex=0.;max_reported=0.
    for amp,pot,wiper,load in itertools.product(protocol['amplifier_models'],protocol['pot_ohms'],protocol['electrical_wiper_fractions'],protocol['external_loads_ohms']):
        gbw,A=amp['gbw_hz'],amp['dc_gain']
        sk=reconstruction_mna(hz,gbw,A);line=line_mna(hz,pot,wiper,load,gbw,A)
        rsk=root.reconstruction(hz,gbw,A);rline=root.omitted_line(hz,pot,wiper,load,gbw,A)
        errors=[float(np.max(np.abs(sk-rsk))),float(np.max(np.abs(line-rline)))];max_complex=max(max_complex,*errors)
        ratio=sk/root.existing_response(hz)*line
        magnitude=float(np.max(np.abs(20*np.log10(np.abs(ratio)))))
        phase=float(np.max(np.abs(np.angle(ratio,deg=True))))
        old=next(r for r in original['scenarios'] if r['amplifier']==amp['id'] and r['pot_ohms']==pot and r['wiper_fraction']==wiper and r['load_ohms']==load)
        delta=max(abs(magnitude-old['maximum_absolute_magnitude_delta_db']),abs(phase-old['maximum_absolute_phase_delta_degrees']));max_reported=max(max_reported,delta)
        records.append(dict(amplifier=amp['id'],pot_ohms=pot,wiper_fraction=wiper,load_ohms=load,maximum_complex_errors=errors,maximum_report_field_difference=delta))
    assert max_complex<1e-11 and max_reported<1e-9
    result=dict(status='passed',scope='Independent node KCL and explicit opamp feedback; no audio or parameter fitting',reviewer=pin(__file__),reviewed_tool=pin(tool),reviewed_result=pin(a.run/'results.json'),reviewed_protocol=pin(a.run/'protocol-before-calculation.json'),frequencies=dict(first=20,last=20000,count=len(hz),spacing='geometric'),scenarios=len(records),independent_network_solves=2*len(records)*len(hz),maximum_complex_difference=max_complex,maximum_reported_magnitude_or_phase_difference=max_reported,records=records,limitations=['Both line jacks inserted; otherwise switched R normal joins output drivers.','Mute transistors off; RF ferrites treated as zero impedance in the audio band.','One-pole finite opamps are sensitivities, not a verified macro-model or guaranteed bounds at ±8 V.','No saturation, slew-rate limiting, output impedance, dielectric or loading nonlinearities inferred.'])
    (a.output/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='records'},indent=2))
if __name__=='__main__':main()
