# Reverb PRE DELAY and SIZE transitions

Live changes to PRE DELAY and SIZE previously replaced delay read positions in one sample. Unrelated points in a filled buffer can have very different amplitudes, so moving a control could create a transient unrelated to the intended room change. SIZE changes also abruptly relocated all eight reads inside the feedback network.

Roland documents PRE DELAY as 0–100 ms and SIZE as eight room/hall sizes, with both available from panel controls. [1] These establish the controls and ranges, but do not specify a firmware smoothing algorithm. This change is a DSP quality policy grounded in Julius O. Smith's description of crossfading between fixed read positions for large delay changes. That method shares an existing buffer and avoids the Doppler shift of continuously moving a read head. [2] The 10 ms transition duration is a project choice, not a recovered SH-201 constant.

`ReverbReadHeads.h` retains nonnegative weights for every position currently contributing to the sound. Each sample transfers at most one fade step of total weight to the requested position. A second edit preserves the current mixture, including any older reads still fading out. The gains sum to one; this avoids the feedback gain increase an equal-power crossfade can introduce for correlated reads. Once settled, processing returns directly from one read without scanning the other positions.

The engine precomputes the existing 126 PRE DELAY read lengths and eight sets of SIZE lengths during preparation. The established nonuniform PRE DELAY table, integer sample rounding, room geometry, damping and decay mappings are preserved. During a SIZE transition the feedback coefficients use the new target size's existing decay rule. Every active read checks the panic freshness boundary, so transitioning taps cannot retrieve invalidated audio.

## Verification

`Tests/ReverbGeometryTests.cpp` passes 3,118,014 checks. Coverage includes all 126/8 positions, every-sample retargeting, unity/nonnegative weights, bounded steps between opposite-polarity taps, exact settling, one-read steady operation, maximum-decay tail automation, panic and process-block fragmentation. Six sample rates are covered: 8, 22.05, 44.1, 48, 96 and 192 kHz.

A two-frequency external-input fixture compares an edited render against an unchanged control. The metric below is peak difference during the first millisecond in which the edit reaches the wet output, allowing for output-stage latency and, for PRE DELAY, the first network return:

| 48 kHz edit | Before | After | Reduction |
| --- | ---: | ---: | ---: |
| PRE DELAY 0 → 100 ms | 0.000248287 | 0.0000203205 | 21.7 dB |
| SIZE 1 → 8 | 0.00233030 | 0.000192152 | 21.7 dB |

These are transient measurements for this fixture, not perceptual thresholds or hardware comparisons. The baseline fails both transient limits at all six rates. In an additional stress render, both controls change every eight samples after excitation stops, with maximum decay and neutral damping. The baseline's 22.05 kHz tail gains 5.67 times as much energy between the early and final measurement windows; the crossfaded version falls to 0.00384 times. All six updated tails remain finite and lose energy. This measured stress result does not prove stability for every possible time-varying feedback schedule.

An isolated before/after comparison of 96 settled configurations (all eight sizes, four pre-delays, three rates) produces the same complete-audio hash, `37f04048a39c69ec`. Existing effects-quality tests also pass all 248 checks. During geometry edits, changing host blocks from 256 to 17 samples produces a maximum output difference below 1e-9 after the initial input-monitor settling period.

On an Apple M1 Max with Clang `-O2`, a deliberately dense benchmark activating all 126 PRE DELAY reads plus 8 × 8 SIZE reads takes about 0.044 seconds per four seconds of 48 kHz audio: 1.1% of one core. The complete-engine fixture takes about 2.5% of one core with settled geometry and 3.2% with rapid retargeting. These timings are indicative measurements, not real-time scheduling guarantees; memory and work remain bounded regardless of automation duration.

Reproduce the functional tests and local benchmark with:

```sh
c++ -std=c++20 -O2 -ISource Tests/ReverbGeometryTests.cpp Source/DSP/SeptumEngine.cpp -o /tmp/septum-reverb-geometry-tests
/tmp/septum-reverb-geometry-tests
```

Crossfading can temporarily combine or cancel different portions of a tail. Fast repeated geometry changes can therefore shorten or color it; preserving a single steady impulse response during such changes is not possible with this shared network. Hardware captures are still needed to calibrate the room algorithm and the instrument's own transition behavior.

## Sources

1. Roland Corporation. [SH-201 Owner's Manual](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf#page=63), 2006, printed p. 63, REVERB parameter list.
2. Julius O. Smith III. [Physical Audio Signal Processing: Large Delay Changes](https://dsprelated.com/freebooks/pasp/Large_Delay_Changes.html), author-published DSP text, accessed September 13, 2026.
