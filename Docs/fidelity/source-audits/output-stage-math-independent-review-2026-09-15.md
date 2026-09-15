# Independent output-stage circuit review

**No circuit-math blocker found.** A separate full-node calculation reproduces both the loaded reconstruction stage and the omitted line-output network in all 144 declared scenarios. This supports the arithmetic of the linear sensitivity study; it does not validate a nonlinear preamp model.

[Receipt](output-stage-math-independent-review-2026-09-15.json), [independent checker](../../../Tools/review_output_stage_math.py), reviewed [calculation](../../../Tools/analyze_output_stage_circuit.py). No hardware audio, optimizer or production Source change was used.

## Independently derived line path

Let `s = j2πf`, `Rp` be the total pot resistance, and `a` the electrical wiper fraction measured from ground. It is not an authenticated physical knob angle. With both line jacks inserted and the mute transistors off:

```
Zw = 1 / [1/(a Rp) + 1/10000 + 1/104700 + s·100pF]
Hw = Zw / [1/(s·22uF) + (1−a)Rp + Zw]

ZL = 1 / [1/Rexternal + s·470pF]
Zb = 100000 || (1010 + ZL)
Hout = Zb / [1/(s·22uF) + Zb] · ZL/(1010 + ZL)

Hline = Hw · 2 · Hout                 (ideal IC20)
```

Here the first 22 µF is C178, the output coupling is C177, and 1010 Ω is R136 + R137. R141 is the 100 kΩ shunt **after** C177. The phones input loads the wiper through R340 4.7 kΩ and R120 100 kΩ; the headphone output/load is behind its own amplifier and is not directly across the wiper. C356 and the additional line feedback/coupling parts marked NIU are absent in this model.

The primary images place C343 100 pF on the CN7 pin-9/L70 **wiper return**, not the pot input. C344 is the corresponding pin-10/L69 return. The equation remains valid at `a=1`; the independent solver aliases the top and wiper node rather than introducing an arbitrary small resistor. Constant nominal gain, resistive pot loading and resistive external-load attenuation are removed exactly as in the reviewed calculation.

### Important jack qualification

The independently traced JK6 right-output normal contact joins the two line-output drivers at the jack side when the R plug is absent. L/MONO operation therefore needs a **two-channel** network, with both drivers feeding through their separate series resistors. The independent-channel calculation here requires **both line jacks inserted**. Capture jack state is not established for every public recording. RF ferrites are treated as wires over the audio band, and the mute transistors as off; these are explicit modeling omissions.

## Finite-amplifier equations

For the illustrative dominant-pole amplifier:

```
1/A(s) = 1/A0 + s/(2π·GBW)
G20(s) = 1 / [1/2 + 1/A(s)]
β25(s) = (1+s·33000·10pF)/(2.5+s·33000·10pF)
K25(s) = 1 / [β25(s) + 1/A(s)]
```

K25 must participate inside the Sallen–Key capacitor-feedback equations; multiplying the ideal reconstruction response by an unrelated low-pass would not represent that topology. The reviewed calculation correctly includes it there and includes C216's loading by the following network.

The independent solver instead stamps each resistor and capacitor into Kirchhoff current equations, includes the op-amp inverting node and feedback resistors explicitly, and adds a dependent voltage-source current with constraint `v+−v−=vout/A`. It retains separate 680 Ω/330 Ω and phones-input nodes. Thus its agreement is not obtained by calling the reviewed closed-loop or impedance-divider functions.

The frozen study uses `A0=100000` with ideal and 3/5/7 MHz one-pole cases. The M5218 table gives typical 110 dB open-loop gain and 7 MHz GBW, with 86 dB minimum gain and 3 V/µs typical slew rate under its stated ±15 V conditions. The study's cases are **illustrative sensitivities**, not guaranteed bounds at the SH-201's nominal ±8 V rails, nor a manufacturer macro-model. No saturation or slew function follows from those values.

## Numerical verification and interpretation

The grid contains 4 pot values × 3 electrical fractions × 3 loads × 4 amplifier cases, each at 801 frequencies from 20 Hz to 20 kHz. Across **230,688 independent network solves**:

- Maximum complex transfer disagreement: **2.332e−15**.
- Maximum discrepancy in the 144 reported magnitude/phase extrema: **3.020e−14** in their respective units.
- The reviewed maximum magnitude change relative to current `AnalogOutput`, after the declared constant gains are removed, is **0.045986 dB**; maximum phase change is **10.1263°**.
- Exact loading at C216 changes the current simplified reference by at most **0.000163844 dB** in this audio band.

For the nominal 10 kΩ pot and 10 kΩ external load with ideal amplifiers, the maximum magnitude changes are 0.01347, 0.01566 and 0.03101 dB at electrical fractions 0.1, 0.5 and 1. Phase can change waveform shape or crest factor; these small linear magnitude changes do not establish the perceived missing “power” or any amplitude-dependent compression.

### Conditional voltage/slew sanity check

The AK4552 table specifies typical DAC output 1.75 Vpp at VA=3.0 V and proportional scaling with VA. At the schematic's nominal 3.3 V this suggests 1.925 Vpp. With ideal passband gains 2.5 and 2, full electrical volume implies approximately **4.8125 V peak before the output series resistance** for a full-scale sine. Scaling the listed 1.94 Vpp maximum similarly gives 5.335 V peak. Both are below ±8 V rail magnitude; this is not proof of clipping margin because actual swing, load, supply tolerance, transients and component variation still matter.

Even a 4.8125 V-peak 20 kHz sine requires only 0.605 V/µs. Comparing this with a typical slew value measured at a different supply is a plausibility check, not a hardware distortion bound. These estimates provide no reason to invent op-amp saturation in production.

## Reproduction

```
OPENBLAS_NUM_THREADS=1 python3 Tools/review_output_stage_math.py \
  --run build-fidelity/output-stage-investigation/circuit-01 \
  --output build-fidelity/output-stage-math-review/replay
```

The checker verifies the frozen calculation's tool hash before importing it. The durable receipt pins the result/protocol, independent checker and visually reviewed schematic/datasheet assets. Reproduction requires the original frozen circuit run or a byte-identical reconstruction of it.
