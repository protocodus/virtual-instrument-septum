# Effect sends and tone balance: continuous gain changes

| Control | Grounding | Existing plug-in route |
| --- | --- | --- |
| DELAY / REVERB DEPTH | [Roland SH-201 Owner's Manual, p. 63](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf#page=63): independent UPPER/LOWER effect levels, each 0–127 | Per-tone FX DEPTH controls; the existing CC93 delay / CC91 reverb mappings in `PluginProcessor.cpp` |
| TONE BALANCE | [Owner's Manual, p. 64](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf#page=64): balance between LOWER and UPPER, −63 to +63 | The `tone_balance` parameter, labelled PART BAL in the editor |
| Gain dezippering | [JUCE SmoothedValue documentation](https://docs.juce.com/master/classjuce_1_1SmoothedValue.html): smoothing changing values prevents audio glitches | Apply a continuous gain trajectory before dry/send mixing |

The controls and ranges are documented. The linear send law, existing tone
balance law, and exact smoothing duration have not been calibrated against
hardware. CC91/93 above describe the plug-in's existing routing; this change
does not establish additional hardware MIDI mappings.

Before this change, DEPTH and PART BAL were constant multipliers for an
entire render tick. A full controller or automation jump could change the
dry or effect input by the entire current sample amplitude. The resulting
edge can click directly or enter a delay/reverb tail.

Each voice now retains three gain states. The existing normalized send
values and mapped tone balance gains remain the targets. An audio-rate
one-pole transition uses the engine's existing 2.5 ms control time constant
(`mapping::controlSlewSeconds`), independent of host block boundaries.
Smoothing the linear gains preserves their static laws and avoids gain
overshoot. The time constant is an artifact-suppression choice, not a
measured SH-201 control response or a change to effect decay calibration.

Fresh notes initialize at their patch's gains, including exact zero and
maximum values, so smoothing adds no attack fade. Sounding voices retain
their states through SOLO, LEGATO and voice stealing. Patch Remain voices
continue toward the prior program's stored targets. Storage is three fixed
doubles per voice; rendering adds no allocation.

`Tests/EffectSendSmoothingTests.cpp` checks the actual dry and effect-send
buses at 44.1, 48 and 96 kHz. It covers rising/falling full-scale steps on
both tones, settled endpoints, static intermediate values, fresh/reset/panic
initialization, poly/solo/legato reuse, Patch Remain, sample-dense extreme
automation, finite bounds and irregular host block splits.

All **807 checks pass**. Against the pre-change engine and its matching
headers (engine baseline `db9e950`), **42 checks fail**. The largest measured
first-sample send gain step falls from **1 to 0.00902928355**; the dry tone
balance step falls from **1 to 0.00902924755**. The tested automation renders
are bit-identical across the different block partitions. These are synthetic
regression fixtures, not hardware recordings or a hardware-match score.
