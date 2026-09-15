# SH-201 output stage: primary circuit and component audit

**Finding:** the omitted line stages justify a loaded, linear circuit calculation. The documents do not establish an audible saturation curve for normal line-output operation. Phones and L/MONO operation are separate cases. This audit makes no DSP change and does not explain the user's listening impression by assumption.

## Observed hardware

The [Roland Service Notes, May 2006, 17058418E0](https://www.synthxl.com/wp-content/uploads/2020/01/Roland-SH-201-Service-Manual.pdf#page=30), PDF pp.30/37 (printed pp.36–37/48–49), were inspected as rendered schematics. NIU means an unpopulated component (p.2).

| Path | Populated components |
| --- | --- |
| DAC | IC22 AK4552VT; VA from A+3.3 through R172=0; VD through R171=2.2 ohms. IC21 and R294 are NIU. |
| Reconstruction | C216/R179, IC25B Sallen–Key and feedback values already modeled; right duplicate IC25A. |
| Master volume | C178/C192=22 uF into PANEL-L VR2A/B; grounded bottoms, wipers return through CN7/L69/L70. C343/C344=100 pF shunt the returns. |
| Line | IC20A/B, feedback 22k/22k; input shunts R142/R161=10k; C177/C191=22 uF; R141/R160=100k; 680+330 ohms series; C180/C196=470 pF; ferrite beads L43/L44. |
| Phones | R340/R341=4.7k, R120/R127=100k; IC16A/B feedback 10k/22k; C157/C163=100 uF; 100k shunts; 47+47 ohms series; 470 pF shunts. |
| Amplifiers | IC16/20/25: M5218AFP, with KIA4559F alternative; rails A+8/A−8. Muting transistors shunt the paths. |

The R jack's normally closed contact connects its tip to L/MONO. With R unplugged, the two drivers feed the common output through their separate series resistors. Independent stereo-channel calculations require **both line jacks inserted**. The complete jack drawing was inspected, including the return wire that a tight crop can miss.

## Volume component and loading

Roland specifies EVJY15F02B14 for both panel pots. The [original Panasonic EVJC/EVJY family sheet](https://www.mouser.com/catalog/specsheets/panasonic_02222018_EVJC,EVJY.pdf), dated October/December 2005, identifies EVJY15 as a dual volume-control component and specifies ±20% total-resistance tolerance and up to ±3 dB tracking error over −40 to 0 dB. It does not provide a measured SH-201 knob law. The [exact-part authorised-distributor listing](https://lv.mouser.com/en/ProductDetail/Panasonic-Industry/EVJ-Y15F02B14?qs=WwqriLBepZulX6QrHnqNpg%3D%3D) corroborates **10k per gang**; the schematic itself omits the numeric resistance. The cached family PDF is the same dated manufacturer publication from another mirror because Mouser's direct download failed locally.

For a nominal 10k pot, the wiper's resistive load is approximately `10k || (4.7k + 100k) = 9.128k`, before finite amplifier input impedance. The second branch is present even with headphones unplugged. Thus an unloaded half-resistance position gives about 0.3925 of the input, rather than 0.5. This is a **level/control-loading deduction**, not compression: its ratio is independent of signal amplitude. A rotation-to-resistance law should not be inferred from this calculation.

At full volume, the resistance following C178 is approximately `10k || 9.128k = 4.772k`; its isolated corner is about 1.52 Hz. At a fixed setting, coupling and RF networks mostly change the small-signal response, phase and overall level. Root and the DSP reviewer are solving the complete loaded line network separately; these approximate figures are not a substitute for that calculation.

## Voltage scale, headroom and amplifier evidence

The [original AKM AK4552 sheet, MS0055-E-01, pp.4–5](https://www.micro-semiconductor.com/datasheet/61-AK4552VT.pdf#page=4) specifies DAC output as `0.583 × VA` Vpp. At nominal 3.3V this gives **1.9239 Vpp** for a full-scale sine. Its 44.1kHz, 1kHz, VA=VD=3V characterization gives 88dB typical signal/(noise+distortion) at 0dB, and 100dB typical A-weighted S/N. These are component specifications, not measured distortion of the unit or a harmonic transfer law. The DAC's internal digital filter and analog filter remain distinct from IC25; the ADC's 3.4Hz high-pass does not belong on synth output.

With ideal amplifiers, full pot, low frequency and negligible output loading:

| Node | Gain from DAC AC voltage | Full-scale sine peak |
| --- | ---: | ---: |
| IC25 output | 2.5 | 2.4049 V |
| IC20 line driver | 5 | 4.8098 V |
| IC16 phones driver | `2.5 × 3.2 × 100/104.7` | 7.3501 V |

The phone input divider matters. These values precede the output series-resistor/load division and exclude reconstruction-filter frequency dependence. The line estimate is 3.19V below an 8V rail; the phones estimate is only 0.65V below it. Neither margin is a guaranteed clipping threshold. Headphone impedance, actual chip, rails, signal and knob setting are not known for the benchmark captures.

The [original Mitsubishi M5218AL/P/FP datasheet](https://datasheet4u.com/pdf/721082/M5218P.pdf), pp.1–3, gives typical slew rate 3V/us and gain-bandwidth 7MHz. The [original KEC KIA4559P/S/F sheet, 27 May 1994](https://datasheet4u.com/pdf/936427/KIA4559P.pdf), pp.3–4, gives 2V/us and 5MHz. Their electrical tables use **±15V**, and slew-rate tests use a 2k load. Both give typical output swing ±14V into 10k and ±13V into 2k at those supply rails. These numbers must not be transplanted into an exact ±8V clipping model. The typical supply/load plots confirm finite headroom but do not specify an SH-201 knee or recovery law.

For scale, a 4.8098V-peak, 20kHz sine requires 0.6044V/us, before the reconstruction network's high-frequency attenuation. This is below both published typical slew rates. It argues against assuming ordinary line playback is systematically slew limited; it does not prove absence of all transient distortion or supply/load effects. Mitsubishi's headline 0.0015% typical distortion and example-circuit plots likewise do not support adding percent-level saturation to this unit.

## Service tests and interpretation

[Service p.18](https://www.synthxl.com/wp-content/uploads/2020/01/Roland-SH-201-Service-Manual.pdf#page=18) specifies separate full-volume tests: line L/R 220/440Hz at 5Vpp, phones L/R 110/220Hz at 12Vpp. The internal digital sine amplitudes and measuring loads are not given. Their ratio therefore cannot calibrate a common DAC full-scale value. Its 1kHz/20kHz analog-input loop-through test is not an isolated synth-output frequency response. The p.22 DIN-Audio residual-noise check (−72dB or lower) is an acceptance check, not a noise spectrum or a reason to synthesize hiss.

**Actionable order:** finish the loaded linear stereo line path; keep physical gain/DAC-voltage calibration separate from plug-in normalization; retain L/MONO and phones as conditional routing/load cases. A nonlinear trial would need an explicit, bounded operating-level hypothesis and level-matched evaluation. Current public recordings do not authenticate output jack choice, master position, ADC gain, or overdrive of the analog stage. A constant hardware gain is not evidence of greater dynamics once playback is level matched.

The current software gain/limiter audit is [reported separately](output-path-code-audit-2026-09-15.md). Source URLs, PDF/image hashes, component facts, arithmetic and retrieval limitations are retained in the [companion receipt](output-stage-primary-sources-2026-09-15.json). Proprietary source PDFs and rendered schematics remain in the ignored build directory.

## Follow-up: DAC mode and reconstruction filter

**De-emphasis is off.** The enlarged service p.30 wiring shows IC22 pin 6 (DEM0) connected to A+3.3 and pin 7 (DEM1) connected to analog ground. Their wires cross without a junction dot. [AKM p.10, Table 3](https://www.micro-semiconductor.com/datasheet/61-AK4552VT.pdf#page=10) maps `(DEM1, DEM0) = (0, 1)` to OFF. The optional 50/15 us de-emphasis curve therefore should not be added.

AKM p.1 shows an 8× interpolator, delta-sigma modulator and on-chip low-pass filter, described as using switched-capacitor filter techniques. These precede the external IC25 network. [AKM p.5](https://www.micro-semiconductor.com/datasheet/61-AK4552VT.pdf#page=5), under 44.1kHz and de-emphasis-off conditions, supplies these constraints:

| DAC property | Specification |
| --- | --- |
| Digital passband | 0–20kHz within ±0.1dB |
| Digital passband ripple | ±0.06dB |
| Nyquist response | −6dB at 22.05kHz |
| Stopband | Starts 24.1kHz; attenuation at least 43dB |
| Digital filter group delay | 15.4 sample periods; group-delay distortion 0 us |
| Digital plus on-chip analog response | Within ±0.5dB through 20kHz |

Note 7 defines the DAC delay from loading its 24-bit input registers to analog output. At an **assumed 44.1kHz codec rate**, 15.4 sample periods equal about 0.3492ms. The sheet supplies no separate analog phase curve, exact interpolation coefficients, switched-capacitor pole values, or plotted response. This is not a reason to add the documented delay blindly to the plug-in's existing numerical-conversion latency or change a frozen benchmark lag.

Pages 8–9 document alternative clock-ratio/decimation modes. The SH-201 circuit labels MCK/LRCK/BCK but the inspected output page does not give their frequencies. The documented 44.1kHz USB stream supports a conditional 44.1kHz comparison; it does not establish every WSP clock. Likewise, the DAC's 24-bit, LSB-justified serial interface (pp.1/10/13) does not prove 24-bit arithmetic throughout synthesis.

The omitted DAC reconstruction stage is real. The source only constrains a family of responses; it does not recover one exact filter. Under the specified normal-rate conditions, its sub-20kHz bounds are incompatible with assigning a many-decibel 10–11kHz notch to the DAC alone. Any future approximation should satisfy these bounds and remain an explicit hypothesis, with level and transport held fixed during evaluation.
