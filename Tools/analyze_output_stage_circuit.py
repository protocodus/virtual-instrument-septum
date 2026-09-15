#!/usr/bin/env python3
"""Bound the omitted SH-201 line circuitry without fitting hardware audio.

An offline small-signal circuit calculation, not an op-amp saturation model.
The original normalized reconstruction stage is compared with a loaded volume
pot, the line amplifier, output coupling and an explicit external load.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
SERVICE_SHA = "b66d0e976d69860d542620ff2248e6c95f77157a6f1cb2037ff07fe0e582b76b"


def pin(path):
    path = Path(path).resolve()
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def save(path, data):
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False)+"\n")


def existing_response(hz):
    s = 2j*np.pi*np.asarray(hz)
    tau = 33000*10e-12
    t1 = 820e-12*(4700+8200)+270e-12*4700*(1-2.5)
    t2 = 4700*8200*270e-12*820e-12
    d1, d2, d3 = t1+tau, t2+tau*820e-12*(4700+8200), tau*t2
    coupling = s*(22e-6*22000)/(1+s*(22e-6*22000))
    return coupling*(1+s*tau/2.5)/(1+d1*s+d2*s*s+d3*s*s*s)


def opamp_gain(s, feedback_fraction, gbw_hz=None, dc_gain=1e5):
    if gbw_hz is None:
        return 1/feedback_fraction
    # One dominant pole is a sensitivity model, not a manufacturer's macro-model.
    inverse_open_loop = 1/dc_gain+s/(2*np.pi*gbw_hz)
    return 1/(feedback_fraction+inverse_open_loop)


def reconstruction(hz, gbw_hz=None, dc_gain=1e5):
    s = 2j*np.pi*np.asarray(hz)
    feedback_impedance = 33000/(1+s*33000*10e-12)
    k = opamp_gain(s, 22000/(22000+feedback_impedance), gbw_hz, dc_gain)
    # Nodes after C216, after R175, and the non-inverting input after R176.
    # The controlled op-amp output is K(s)*node[2]. Include the input loading.
    m = np.zeros((len(s), 3, 3), dtype=complex)
    m[:, 0, 0] = s*22e-6+1/22000+1/4700
    m[:, 0, 1] = -1/4700
    m[:, 1, 0] = -1/4700
    m[:, 1, 1] = 1/4700+1/8200+s*270e-12
    m[:, 1, 2] = -1/8200-s*270e-12*k
    m[:, 2, 1] = -1/8200
    m[:, 2, 2] = 1/8200+s*820e-12
    rhs = np.zeros((len(s), 3), dtype=complex)
    rhs[:, 0] = s*22e-6
    nodes = np.linalg.solve(m, rhs[..., None])[..., 0]
    return nodes[:, 2]*k/2.5


def omitted_line(hz, pot_ohms, wiper_fraction, load_ohms,
                 gbw_hz=None, dc_gain=1e5):
    s = 2j*np.pi*np.asarray(hz)
    top = (1-wiper_fraction)*pot_ohms
    bottom = wiper_fraction*pot_ohms
    # C343 sits on the return wiper. The unmuted phones input loads the same
    # wiper through R340+R120; its gain/output load is behind its own amplifier.
    wiper_conductance = 1/bottom+1/10000+1/(4700+100000)
    zwiper = 1/(wiper_conductance+s*100e-12)
    pot = zwiper/(1/(s*22e-6)+top+zwiper)
    resistive_pot_gain = 1/(1+top*wiper_conductance)
    line_amplifier = opamp_gain(s, .5, gbw_hz, dc_gain)/2
    zjack = 1/(1/load_ohms+s*470e-12)
    zoutput_node = 1/(1/100000+1/(680+330+zjack))
    output = zoutput_node/(1/(s*22e-6)+zoutput_node)*zjack/(680+330+zjack)
    resistive_output_gain = load_ohms/(load_ohms+1010)
    return pot/resistive_pot_gain*line_amplifier*output/resistive_output_gain


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--service", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    service = pin(a.service)
    if service["sha256"] != SERVICE_SHA:
        raise ValueError("Unexpected original service document")
    a.output.mkdir(parents=True, exist_ok=False)
    # Electrical fractions are not knob positions or a fitted volume taper.
    # 20k..100k pots and the finite-amplifier poles are explicit sensitivities.
    protocol = dict(tool=pin(__file__), service=service,
        existing_header=pin(ROOT/"Source/DSP/AnalogOutput.h"),
        component_source="Service printed36-37, panel-L PDF37 and original parts list",
        pot_ohms=[10000, 20000, 50000, 100000],
        electrical_wiper_fractions=[.1, .5, 1.0], external_loads_ohms=[10000, 20000, 100000],
        amplifier_models=[dict(id="ideal", gbw_hz=None, dc_gain=1e5),
            dict(id="one_pole_3MHz", gbw_hz=3e6, dc_gain=1e5),
            dict(id="one_pole_5MHz", gbw_hz=5e6, dc_gain=1e5),
            dict(id="one_pole_7MHz", gbw_hz=7e6, dc_gain=1e5)],
        scope="Normal unmuted stereo line output; ideal source/output impedance inside each amplifier; RF ferrites ideal wires in audio band",
        normalization="Remove only constant nominal amplifier, resistive pot and external-load attenuation; no fitted gain or EQ",
        omissions=["op-amp saturation and higher poles", "muting transistor leakage/nonlinearity", "capacitor dielectric effects", "DAC digital reconstruction", "headphone output loading", "exact recording-chain load"],
        constraints="No hardware audio loaded, no synthesis preset or DSP parameter fitted; finite-amplifier cases are sensitivities",
        hardware_equivalence="not_established")
    save(a.output/"protocol-before-calculation.json", protocol)
    hz = np.geomspace(20, 20000, 801)
    baseline = existing_response(hz)
    loaded = reconstruction(hz)
    controls = dict(loaded_input_vs_existing_max_magnitude_db=float(np.max(np.abs(20*np.log10(abs(loaded/baseline))))),
                    loaded_input_vs_existing_max_phase_degrees=float(np.max(np.abs(np.angle(loaded/baseline, deg=True)))))
    if controls["loaded_input_vs_existing_max_magnitude_db"] >= .0003:
        raise ValueError("Existing independently audited loaded-input control does not reproduce")
    selected_frequencies = np.array([20, 50, 100, 1000, 5000, 10000, 20000])
    records, curves = [], []
    for amp, pot, fraction, load in itertools.product(protocol["amplifier_models"], protocol["pot_ohms"],
            protocol["electrical_wiper_fractions"], protocol["external_loads_ohms"]):
        def ratio(f):
            return reconstruction(f, amp["gbw_hz"], amp["dc_gain"])/existing_response(f)*omitted_line(
                f, pot, fraction, load, amp["gbw_hz"], amp["dc_gain"])
        h = ratio(hz)
        db, phase = 20*np.log10(abs(h)), np.angle(h, deg=True)
        spots = ratio(selected_frequencies)
        row = dict(amplifier=amp["id"], pot_ohms=pot, wiper_fraction=fraction, load_ohms=load,
                   magnitude_delta_db=dict(zip(map(str, selected_frequencies), map(float, 20*np.log10(abs(spots))))),
                   phase_delta_degrees=dict(zip(map(str, selected_frequencies), map(float, np.angle(spots, deg=True)))),
                   maximum_absolute_magnitude_delta_db=float(max(abs(db))),
                   maximum_absolute_phase_delta_degrees=float(max(abs(phase))))
        records.append(row)
        if pot == 10000 and load == 10000:
            curves.append((amp["id"], fraction, db, phase))
    fig, axes = plt.subplots(2, 1, figsize=(9, 7), sharex=True, constrained_layout=True)
    styles = {"ideal":"-", "one_pole_3MHz":":", "one_pole_5MHz":"--", "one_pole_7MHz":"-."}
    for model, fraction, db, phase in curves:
        color = { .1:"#4f69a8", .5:"#138879", 1.:"#b66536" }[fraction]
        label=f"{model.replace('_',' ')}; electrical wiper {fraction:g}"
        axes[0].semilogx(hz, db, styles[model], color=color, label=label, linewidth=1)
        axes[1].semilogx(hz, phase, styles[model], color=color, linewidth=1)
    axes[0].set_ylabel("Magnitude change (dB)"); axes[1].set_ylabel("Phase change (degrees)")
    axes[1].set_xlabel("Frequency (Hz)")
    for ax in axes: ax.grid(alpha=.2); ax.axhline(0, color="gray", linewidth=.5)
    axes[0].legend(fontsize=7, ncol=2)
    fig.suptitle("Omitted line circuitry relative to current output model\n10 kΩ pot and external load; constant gains removed; no audio fitting")
    fig.savefig(a.output/"output-stage-transfer.png", dpi=150); plt.close(fig)
    result=dict(protocol=protocol, controls=controls, scenarios=records, scenario_count=len(records),
                all_scenario_maximum_magnitude_delta_db=max(r["maximum_absolute_magnitude_delta_db"] for r in records),
                all_scenario_maximum_phase_delta_degrees=max(r["maximum_absolute_phase_delta_degrees"] for r in records),
                plot=pin(a.output/"output-stage-transfer.png"))
    save(a.output/"results.json", result)
    print(json.dumps({k:v for k,v in result.items() if k not in ("protocol","scenarios","plot")}, indent=2))


if __name__ == "__main__":
    main()
