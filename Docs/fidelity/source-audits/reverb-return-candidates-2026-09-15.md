# Reverb return width and level: full-engine candidates

**Lowering the entire reverb return improves several named-preset comparisons
more than narrowing it, but does not generalize uniformly.** Half level
improves Cotton, Air Lead, SupaJuce and Brassy in the main spectrum/envelope
metrics. Club Bass's envelope error worsens. Quarter level has further
contrary envelope and stereo results. Neither width nor level is promoted.

The [early stereo audit](official-stereo-feasibility-2026-09-15.md) motivated
this experiment. Its [complete-file tail check](official-reverb-tails-2026-09-15.md)
also matters: late hardware tails are at least as wide as the model control,
despite narrower hardware during earlier mixed passages. That distinction
motivated the separate return-level family.

## Two isolated changes

All builds start from shipping DSP `b0f6c03`, using the same ten published
SysEx files and reconstructed performances. Every copied source, profile,
binary, render and receipt is hashed. The only DSP edit is immediately after
the reverb return's high-cut state is read:

- **Width W=1, .5, .25:** retain wet mid=(L+R)/2 and multiply wet side=(L−R)/2
  by W before recombining. The return's mid is unchanged at this point.
- **Gain G=1, .5, .25:** multiply both wet channels by G. This retains the
  isolated wet signal's stereo ratios while reducing its contribution.

The feedback network, input injection, delay, oscillator/filter/envelope
parameters and preset bytes remain unchanged. A value of one retains the
original arithmetic. These candidates test unmeasured voicing constants;
they do not identify a Roland width parameter or establish a send-control
conversion. Final master pan or limiting can affect mid/side relationships;
the invariance statements above apply at the insertion point.

Cotton is exploratory hypothesis context. The other nine presets provide
comparative checks. They have been inspected previously and are not blind
tests. Production alone supplies a first-quarter alignment fit bounded to
50 ms. Each render gets one gain from that same first quarter, with the
production gain retained as a sensitivity. Evaluation uses the remaining
three quarters with identical sample bounds; no STFT frame crosses the
calibration boundary. No per-note timing, phase, EQ or stereo fit occurs.

## Results

The tables list only the five cases changed by either family. Dist Bs,
Moogie, Pedal Bs, So Juno and Vangelead remain byte-identical for all scales.
Every triple lists **production / half / quarter**. Spectral convergence
(SC) is a normalized spectrum distance, not a fidelity percentage.
The RMS column is the larger P95 envelope error from the existing 10/50 ms
measurements; it is sensitive to phase, gates and low-level tails.

### Narrower return

| Preset | SC | Log-spectrum error dB | RMS-envelope P95 dB |
|---|---|---|---|
| Air Lead | .94653 / .91088 / .90149 | 23.960 / 23.688 / 23.602 | 4.724 / 4.305 / 4.318 |
| Brassy | .60861 / .60878 / .60896 | 12.507 / 12.384 / 12.351 | 10.601 / 10.217 / 10.174 |
| Club Bass | .42396 / .42366 / .42357 | 15.644 / 15.397 / 15.337 | 6.969 / 6.683 / 7.248 |
| Cotton | .80692 / .78449 / .77833 | 13.738 / 13.488 / 13.419 | 11.777 / 11.042 / 10.896 |
| SupaJuce | .53771 / .51218 / .50475 | 8.591 / 8.390 / 8.346 | 10.538 / 9.662 / 9.494 |

Mean SC over the other nine cases falls .54031→.53350/.53164, but the
stereo scores do not select the same direction everywhere. Air's quarter
width is too narrow: side fraction .0264 versus hardware .1102, while
production is .1733. Club Bass already has too little side energy, and
narrowing it worsens that discrepancy. The late-tail evidence is an
additional constraint against promoting a global width reduction.

### Lower return level

| Preset | SC | Log-spectrum error dB | RMS-envelope P95 dB |
|---|---|---|---|
| Air Lead | .94653 / .85225 / .82024 | 23.960 / 22.900 / 22.135 | 4.724 / 4.290 / 4.137 |
| Brassy | .60861 / .60624 / .60619 | 12.507 / 12.120 / 12.331 | 10.601 / 8.992 / 9.276 |
| Club Bass | .42396 / .42446 / .42511 | 15.644 / 14.604 / 14.763 | 6.969 / 10.020 / 15.799 |
| Cotton | .80692 / .70299 / .67812 | 13.738 / 12.326 / 11.955 | 11.777 / 9.114 / 13.455 |
| SupaJuce | .53771 / .45725 / .43663 | 8.591 / 7.837 / 8.333 | 10.538 / 5.335 / 4.284 |

Over the other nine cases, mean SC falls .54031→.52069/.51491 and mean
log-spectrum error falls 13.206→12.846/12.858 dB. The average includes five
unchanged cases; the data also retains the four changed comparative cases
as a separate group. Different objectives favor different scales.

The gains are not responsible for all improvement: with the exact
production gain, half-level SC is .79432 for Air, .68287 for Cotton and
.45470 for SupaJuce. With its own first-quarter gain it is
.85225/.70299/.45725 respectively. Both conventions remain in the receipt.

At half level, SupaJuce's side/mid moves from −9.66 to −13.78 dB against
hardware −13.17 dB; Air moves from −6.79 to −10.06 against −9.07. Cotton
moves from −9.01 to −13.71 against −17.06. These are mixed dry/wet signal
statistics, not an isolated reverberator-level calibration.

Club Bass remains contrary evidence. It is the only changed case with
stored HF damping −36 dB; the other four use neutral damping. That is a
possible interaction to investigate, not grounds to exempt the patch or
install a special rule. Unknown gates and the unverified damping/time
models can also affect its low-level tail. Quarter level additionally
worsens Cotton's P95 envelope error and overshoots Air/SupaJuce stereo.

## Verification and next decision

All 60 renders are finite, unclipped and end with zero active voices.
Both families' ten unchanged controls reproduce the production WAVs
byte-for-byte. Their complete measurements, training gains, alignment
and evaluation boundaries reproduce the previous production results
exactly. Edited source diffs and build manifests remain available for
independent review. The [independent isolation audit](reverb-return-candidate-isolation-2026-09-15.md)
also verifies both source branches, actual output-route controls and
float-level affine relationships in the complete renders. This verifies
the experiment, not hardware agreement.

The [durable data](reverb-return-candidates-2026-09-15.json) retains both
complete result sets, aggregate definitions, raw reverb bytes, damping
values, source hashes and fixed-production-gain sensitivities. The next
useful checks are additional structurally clear preset recordings and
late decay behavior. No global return correction is selected yet.

## Reproduce

Choose new output directories:

```sh
python3 Tools/compare_reverb_width_candidates.py --mode width \
  --comparison-root build-fidelity/hardware-benchmark/final-production-linear-lfo \
  --output build-fidelity/hardware-benchmark/reverb-width-candidates/new-run
python3 Tools/compare_reverb_width_candidates.py --mode gain \
  --comparison-root build-fidelity/hardware-benchmark/final-production-linear-lfo \
  --output build-fidelity/hardware-benchmark/reverb-gain-candidates/new-run
```

The retained runs are `run-01` under each family. Width used the original
tool at commit `d41fc0c`; gain used its explicit-mode extension. Each run
contains its exact copied script, source diff, listening files and HTML
index. The extension leaves the width branch's DSP calculation unchanged.
Original recordings and generated audio remain in ignored build folders.
