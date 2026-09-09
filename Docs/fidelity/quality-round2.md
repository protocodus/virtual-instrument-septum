# Sound-quality improvements, round 2

This round fixes five audible implementation problems in the shipping native-rate
engine. The baseline is `cd71244`. These are numerical and performance-control
corrections; they do not establish an exact SH-201 match without hardware recordings.
The schematic-derived output circuit and existing oscillator/filter mappings remain
the reference for the instrument's voicing.

## 1. Preserve audio between SysEx events

The processor previously consumed consecutive SysEx packets as one batch even when
their timestamps differed. Advancing the render position inside that batch skipped
the audio between packets. Only packets at the same clamped sample position now
share an atomic patch commit. Later packets return to the normal render loop first.

Processor regressions compare a single MIDI buffer with the same timeline split at
each event. They exercise Roland DT1, universal device controls, both mixed orders,
ignored packets and same-time patch batches, and require actual audio between
distinct timestamps.

## 2. Remove stepped volume and expression changes

Master/patch/CC7 gain and per-tone CC11 expression previously advanced to a new gain
once every eight samples. INPUT VOL used a tick-length approximation and linear
segments. All now advance their existing 10 ms one-pole once per sample, using
`a = 1 - exp(-1 / (sampleRate * 0.010))`. The master level of the direct input monitor
uses the same method. This removes gain stairs and makes these control responses
independent of how the host or MIDI events split the audio.

Expression still acts on its selected tone or tones before their effect sends.
The direct input monitor still receives panel volume independently of patch level,
CC7, expression and part pan. This change does not make the native engine's LFO,
envelope and voice-control cadence invariant to every possible block partition.

## 3. Dezipper stereo pan

CC10 previously changed the stereo gains immediately. Pan now slews over the same
10 ms time constant as level controls. Smoothing the pan angle preserves the existing
constant-power law during motion and unity gain at the centre. This short smoothing
time is a plug-in quality choice, not a measured Roland controller response.

## 4. Let bypassed effects age naturally

Delay and reverb previously froze their buffers, modulation and damping states while
OFF, then released old audio when switched back ON. Both networks now continue to
advance while bypassed. Their wet returns and new inputs fade over 5 ms in both
directions, including the delay's contribution to the reverb. Once OFF is settled,
they accept no new input. Fading the send prevents a long delay from playing an
abrupt first echo after its return fade has finished, or replaying an abrupt cutoff
after a quick OFF/ON cycle. Rapid changes retarget the current fade instead of
restarting it from an endpoint.

This prevents a paused echo or reverb tail from returning after an unrelated silent
interval. A recently bypassed long tail can still be present when re-enabled because
it has decayed for the actual elapsed time. The bypass policy and fade length are
explicit plug-in choices; the [Roland manual](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf#page=30)
documents effect controls but does not specify their internal state lifecycle.

## 5. Reduce unintended treble loss in delay repeats

The modulation delay now reconstructs fractional positions with four-point Lagrange
interpolation. Two-point linear interpolation had added a low-pass response inside
the feedback loop even with HF DAMP bypassed. This extra damping depended on the
host sample grid and modulation position. The new kernel preserves DC and exact
integer-delay samples while reducing the fractional-position error. All nonzero
taps are causal, and individual tap validity checks protect the All Sounds Off
boundary.

[Julius O. Smith's delay-line interpolation reference](https://www.dsprelated.com/freebooks/pasp/Delay_Line_Interpolation.html)
explains the gain error of linear interpolation and why feedback loops magnify it.
Lagrange interpolation is a reconstruction choice for this plug-in; Roland's exact
delay interpolation remains undocumented. The change reduces numerical damping,
so fractional-delay repeats can sound brighter than previous Septum versions.

## Measured results

Controller fixtures use settled sine voices or independently generated stereo
input, with identical automation times. Partition comparisons cover 1/3/7/8/31
sample calls at 44.1/48/96/192 kHz. Numbers below are absolute full-scale sample
errors, not a hardware fidelity score.

| Probe | Before | After |
| --- | --- | --- |
| Worst master/patch/CC7 partition difference | 0.002006158 | 0 |
| Worst expression partition difference | 0.002006151 | 0 |
| Worst INPUT VOL partition difference | 0.000117242 | 0 |
| Worst monitored-master partition difference | 0.000618801 | 0 |
| External input/master versus independent exponential and output-circuit reference | Up to 0.000618581 | 0 |
| Pan switch residual, relative to the steady carrier's largest sample step | 147–382× | Below 1× |
| Half-sample delay interpolation loss at 10 kHz / 44.1 kHz | 2.420 dB per echo | 0.739 dB per echo |
| Delay peak after two seconds OFF, then ON without new notes | 0.059818730 | 0.000001721 |
| Reverb peak after two seconds OFF, then ON without new notes | 0.024588890 | 0.000000333 |

The first-echo onset probe, with a held sine and the effect enabled near a signal
peak, initially exposed a second switch discontinuity even after fading the wet
return. Fading the new send reduced the onset jump from 60.0× to 1.11× the normal
wet waveform's largest step for delay, and 24.5× to 1.08× for reverb.
A separate 660 ms delay probe toggles OFF for 20 ms and then ON, checking the
cutoff when it arrives later in the echo. Fading the input on both edges reduces
that delayed jump from 35.22× to 1.00× the steady wet waveform's largest step.

The initial 186-check controller suite rejected the baseline with 144 failures;
the corrected engine passed all 186. The remaining baseline checks already passed,
including expression routing, static pan endpoints and direct-monitor isolation.
Additional dynamic-pan checks require the control to actually reach its requested
endpoints and return to centre, so simply ignoring CC10 cannot pass.

The interpolation sweep checks 101 fractional positions across DC–Nyquist for
frequency gain no greater than unity, plus cubic-polynomial reconstruction and
exact endpoints. Engine tests cover minimum-delay causality, maximum feedback and
modulation, long reverb, and clearing old audio on All Sounds Off at
32/44.1/48/96/192 kHz.

An idle-engine Release benchmark on an Apple M1 Max, macOS 26.5.1, used 44.1 kHz,
256-sample blocks and the best of three ten-second renders. Both effects OFF
increased from 1.048% to 1.499% of one core (about 0.45 percentage points);
both ON changed from 1.422% to 1.490%. These elapsed-time measurements are a local
cost check, not a portable performance guarantee. The continuously running networks
allocate no buffers on the audio thread.

## Validation

- All eight Release DSP/tool suites passed: 198 controller checks, 248 effects
  checks, 4,313 existing engine checks, 2,666 reference-rate checks, circuit,
  reference-patch extraction and rendering checks.
- The JUCE processor suite passed all 3,540 checks, including the SysEx timeline
  regressions and completed part-control UI. A headless UI test now waits for its
  actual timer-updated state instead of assuming one short sleep is sufficient.
- Standalone, VST3 and AU built successfully. Debug controller and effects suites
  also passed.
- The 32-fixture/rate quick comparison produced finite, audible raw renders with
  matching patch/MIDI manifests. All 11 demonstration WAVs were regenerated and
  their peak levels refreshed in the main README.

## Reproduce

```sh
cmake -S . -B build-fidelity -DCMAKE_BUILD_TYPE=Release -DSEPTUM_BUILD_PLUGIN=OFF -DBUILD_TESTING=ON
cmake --build build-fidelity --parallel
ctest --test-dir build-fidelity --output-on-failure
build-fidelity/SeptumControlSmoothingTests
build-fidelity/SeptumEffectsQualityTests
```

Build with `SEPTUM_BUILD_PLUGIN=ON` to include the SysEx processor regressions in
`SeptumPluginProcessorTests`. Tests measure behaviour through the actual render
path; isolated interpolation tests also check DC, frequency response and endpoints.
