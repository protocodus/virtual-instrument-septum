# Executed dry-envelope integration guard

All seven frozen `dry-v2` models pass a compiled control-target check:
production plus Hz/log candidates at the predeclared 30/35/40 ms conventions.
The [reproduction tool](../../../Tools/verify_dry_envelope_integration.py)
extracts the exact built renderer's envelope methods, default calibration,
cutoff expression, header mappings and generated `CandidateProfile.h`.
All frozen input hashes are verified before extraction. Only private access
changes in a separate header copy; original sources and renderers stay intact.

The C++ probe advances the actual envelope in eight-sample ticks and evaluates
cutoff for MIDI 24/36/57 at hardware ages 40/100/180/260/340 ms and 1/2.5/4/20 s.
The last two synthetic held-note ages expose termination beyond the original
MIDI gates. Targets come from the previously frozen fitted curves; no new
parameter is fitted.

| Model family | Maximum cutoff error through 2.5 s | Maximum including late termination |
| --- | ---: | ---: |
| Production linear amount | 1.23e−9 cents | 1.23e−9 cents |
| Exponential amount, Hz interpolation | 1.46e−10 cents | 0.00012119 cents |
| Exponential amount, log interpolation | 4.26e−9 cents | 0.000001927 cents |

These are numerical integration errors, not hardware accuracy estimates.
Hz first reaches the Sustain stage at the observed tick at 3.944490 s;
log reaches it at 16.725986 s. The small late errors reflect the declared
`1e-8` amount termination. No premature truncation affects the early targets.

The actual attack takes **45 samples** at 44.1 kHz, versus nominal 44.1:
20.408 microseconds longer. Each target is compared at its actual tick age;
requested evaluation times round forward by at most 158.731 microseconds.
The predeclared audio lags remain unchanged. Including their integer rounding,
they differ from an exact 45-sample attack alignment by −1 sample at 30/40 ms
and −0.5 sample at 35 ms. This is recorded, not used to optimize delay.

The guard validates control-target endpoints. It does not execute the full
audio path, within-tick filter-coefficient interpolation, arbitrary sustain or
negative depth. The independent full-audio comparisons remain necessary.

```sh
python3 Tools/verify_dry_envelope_integration.py \
  --experiment-dir build-fidelity/envelope-hypothesis/dry-v2 \
  --output build-fidelity/envelope-hypothesis/dry-v2/new-integration-check
```

The [durable numerical record](dry-envelope-integration-2026-09-15.json)
contains all measurements, source/profile/probe hashes, compiler identity,
alignment accounting and explicit numerical bounds.
