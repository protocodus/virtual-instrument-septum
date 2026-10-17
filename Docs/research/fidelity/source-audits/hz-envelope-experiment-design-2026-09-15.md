# Predeclared Hz-envelope experiment: timing and targets

This is an independent design check against commit `b0f6c03`, written before
candidate preset scores. It specifies a small experiment; it does not modify
DSP or establish the missing Roland parameter tables.

## Keep decay age separate from recording delay

The frozen dry trajectory, in seconds `s` after **original MIDI** note-on, is

```text
r(s) = A + B exp(-s/tau)
A = 0.9318832715
B = 8.4984344071
tau = 0.2140763348 seconds
```

For the proposed interpolation, a zero-sustain exponential envelope gives

```text
r(s) = F [1 + (2^depth - 1) exp(-(s-L)/tau)]
F = base cutoff / note frequency
L = effective MIDI-to-decay-start offset
```

Consequently `F=A`, but `B=A(2^depth−1) exp(L/tau)`. The physical peak is
`P=A+B exp(−L/tau)`, **not `A+B` unless L is zero**. Delay and peak coefficient
trade exactly after attack; fitting them together to the same decay windows
cannot identify both. Delay leaves `tau` and the asymptotic floor unchanged.

`L` includes capture/synthesis latency and the filter attack before decay.
For corresponding envelope ages, compare candidate sample offset
`s_candidate = s_hardware + L_candidate − L_hardware`. Equivalently, delay
candidate audio by `L_hardware − L_candidate`. Include the renderer's known
93-sample latency only once, and distinguish it from its finite filter attack.

An independent audio-edge diagnostic on the original Q0 decodes measures
the high note at 17.25 s and high chords at 22/24/28 s. Centered 45-sample RMS
crosses 10% of local steady energy at **34.58–37.60 ms** after original MIDI.
Thresholds from 1% through 50% span approximately 34.44–38.75 ms. These are
energy edges, not exact filter-decay starts: phase, MP3 pre-echo, amplitude
attack and filter group delay remain. Use **35 ms as a fixed convention**,
with 30/40 ms sensitivity, rather than optimizing a delay per note.

Do not transfer this delay to **Moogie**. Its reconstructed MIDI onsets were
transcribed directly on the decoded hardware-audio timeline: the three long
low notes begin at 0.029, 0.939 and 1.901 s. They already contain the recording's
onset delay. Adding another 35 ms double-counts it. Compensate the candidate's
known rendering latency once, retain the existing onset uncertainty, and
report a ±20 ms sensitivity without selecting the best shift on holdouts.

## Dry physical targets

For an exponential amount envelope whose table value is the duration for a
60 dB amplitude fall,

```text
coefficient = exp(-ln(1000) / (sample_rate * T60))
T60 = tau * ln(1000) = 1.4787869318 seconds
```

The reported `tau=0.214076 s` must not be passed as `T60`. Likewise, the
owner's approximate “one-second” audible fall is not a measurement of `T60`.
At 35 ms effective delay, use these physical fixture targets:

| Quantity | Target |
| --- | ---: |
| Base cutoff / f0 | 0.9318833 |
| Base cutoff at MIDI 60 | 243.8045 Hz |
| Peak cutoff / f0 | 8.1485190 |
| Peak/base ratio | 8.7441413 |
| Depth | 3.1283167 octaves |
| Decay `T60` | 1.4787869 s |

For 30/35/40 ms delay, corresponding depths are 3.15820/3.12832/3.09851
octaves. These three compensated targets represent the same fitted
post-attack curve. They are timing sensitivity cases, not three independent
depth candidates from which to select a winner.

The current mapping translates the physical base to fractional cutoff
45.8172 and the 35 ms depth to fractional depth 16.4237. Hardware raw values
remain unknown. If the fixture requires integer controls, either use an
explicit calibration override to realize the physical targets or label
rounding as an additional approximation. The earlier dry control's cutoff
34/depth21 gave base 0.489×f0 and peak 7.823×f0; it is not the correct floor
for this new hypothesis.

An exactly eight-times-f0 peak would imply `L=39.45 ms` under this fit. That
is consistent with the rough recipe, but it is a conditional calculation,
not independent confirmation of recording latency or a recovered raw depth.

## Small Moogie grid

After the isolated dry integration check, compare unchanged production with
five candidates. Select only the raw49 time-scale anchor using the first
Moogie low note; freeze it before scoring the other long notes or presets.

| Candidate tau at raw49 | Candidate T60 at raw49 |
| ---: | ---: |
| 0.080 s | 0.552620 s |
| 0.110 s | 0.759853 s |
| 0.150 s | 1.036163 s |
| 0.200 s | 1.381551 s |
| 0.270 s | 1.865094 s |

This five-point grid brackets the historical conditional Hz-exponential
estimates near 0.124–0.135 s and the slower envelope alternatives. Those
historical estimates used earlier depth/filter assumptions, so they are
scale guidance, not accepted new targets. Do not add cutoff, depth, delay,
waveform gain or taper parameters to rescue the fit.

Freeze a single interpolation convention before rendering. A defensible
isolation choice is `T60(v)=T60(49) g(v)/g(49)`, where `g` is the committed
filter-decay table. This retains its relative shape while the candidate
changes its time convention and cutoff interpolation. The ratios at raw
37/58/63/64 are 0.37425/1.80881/2.41982/2.55778. These are explicitly
provisional extrapolations. Do not additionally fit those values to held-out
presets. Scaling the old amplifier exponential table instead makes raw127
209 times raw49 and imports a very different extreme extrapolation.

Use hardware-only harmonic eligibility and fixed window selection. A simple
common late-safe set for the three long lows is 80 ms windows centered
100/180/260 ms after each reconstructed onset. Even-harmonic trajectories
can select upper-tone D49 only under the documented symmetric-lower-waveform
assumption; report full and odd-harmonic holdout effects too, since the lower
tone's raw37 timing also changes under a shared table. If the winning anchor
is at a grid endpoint, treat it as an unresolved bound rather than quietly
expanding the search on validation results.

## Guard the new mathematical consequences

The new interpolation preserves peak and zero-sustain cutoff, but changes
other segments. At depth +3 octaves and sustain 0.5, the proposed cutoff is
4.5×base; the old geometric interpolation gives 2.828×base. A linear amount
attack also becomes linear in Hz, and release/negative-depth trajectories
change. They remain experimental even if positive, zero-sustain decay wins.

Existing envelope termination thresholds need a **filter-only** check. Decay
settles at amount error `1e-4`; release ends at `1e-5`. At +12 octaves, additive
Hz interpolation magnifies these to cutoff jumps of about **594 cents** and
**69.5 cents**, respectively. The dry recipe hides this because its depth is
much smaller. A depth-aware cutoff-relative stopping criterion is preferable;
an amount threshold at most `1e-7` bounds the +12-octave zero-sustain jump below
one cent. Keep amplifier and pitch-envelope thresholds unchanged. `T60`
describes an exponential coefficient, not the instant to snap to sustain.

For a one-cent bound at sustain `S`, a depth-aware test can use
`abs(E−S) abs(2^depth−1) / [1+(2^depth−1)S] < 2^(1/1200)−1`.
This also accounts for negative depths and nonzero sustain rather than
assuming that a small normalized amount always means a small cutoff change.

The current exponential decay branch also ignores the calibration decay
table when constructing its coefficient. The isolated filter candidate must
explicitly use its filter `T60` table while leaving amplifier behavior intact.

Published endpoint envelope durations do not identify their envelope type
or amplitude threshold; they cannot safely be interpreted as `T60`. The raw
dry patch, floor, peak and full decay/depth mapping remain unmeasured.
Only an experimental profile is warranted until independent notes/presets,
onset sensitivity and extreme-depth continuity pass.

The [numerical design record](hz-envelope-experiment-design-2026-09-15.json)
retains committed input hashes, all edge thresholds, timing targets, the
predeclared grid and threshold calculations. No candidate score informed
this grid and no DSP or root experiment file was edited.
