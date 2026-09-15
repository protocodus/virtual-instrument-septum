# Proposed eight-source-sample interpolation experiment

**Proposal only: 24 model fits and 120 passage predictions, targeting a run of
15 minutes or less. No hardware fits or new numerical controls had been run when this protocol was frozen.**
The complete grid and current dependency/source hashes are in the
[proposal JSON](windowed-sinc-interpolation-proposal-2026-09-15.json).

## Evidence and scope

The coordinated [primary-source audit](roland-integrated-interpolation-patent-2026-09-15.md)
finds a distinct mechanism in Roland's
[US4715257A](https://patents.google.com/patent/US4715257A/en): eight stored source
samples, windowed low-pass interpolation, cumulative coefficients applied to
sample differences, finite fractional-position lookup, and optional
pitch-selected kernels. It supplies neither SH-201 association nor exact
coefficients, table length, root pitch, arithmetic precision or an authenticated
window formula. Its unity-base substitution can differ from exact convolution
when the sampled weights do not sum to one.

The completed [48-model study](high-note-wavetable-models-2026-09-15.md) used
left hold, linear and four-point Lagrange interpolation. The proposed eight-point
low-pass response, finite lookup and explicit nonunit coefficient sum are
different mathematical hypotheses. Failure of the earlier study does not test
these mechanisms. Success here would still not identify patent use in the SH-201.

## Small fixed family

All new models use **N=32** source samples per cycle. This reuses an already
studied size to bound the experiment; it is not a measurement of hardware memory.
At an output rate of 44,100 Hz, the implied root frequency is `Fs/N=1378.125 Hz`.
There is no additional fitted root-pitch parameter.

| Group | Contents | Cutoff policy | Lookup policy | Weight policy | Count |
| --- | --- | --- | --- | --- | ---: |
| Normalized core | Ramp and Fourier saw | Constant and banked | Continuous and 64-bin | Normalized direct | 8 |
| Approximation pairs | Ramp and Fourier saw | Constant and banked | Continuous and 64-bin | Raw direct and raw forced-base | 16 |
| Frozen historical comparators | Naive, polyBLEP, N32 ramp linear/cubic | Existing definitions | Existing definitions | Existing coefficients | 4 references, no new fit |

Every row receives the **same 13 signed output FIR taps**, offsets −6…+6, plus
phase/DC. Gain is included in the taps. No row gets a larger filter or a
post-fit normalization. These are waveform-plus-nuisance-filter comparisons;
they do not constitute oscillator-only or actual-engine renders.

The source tables are exactly `T[n]=2n/N−1` and
`T[n]=−2/pi × sum(h=1…15, sin(2*pi*h*n/N)/h)`. No source coefficient is learned.
The normalized/raw-direct/forced-base factor is crossed with every table, cutoff
and lookup policy, with no omitted pair.

### Kernel and phase convention

For high-precision waveform phase `p`, let `i=floor(N*p)` and `u=N*p−i`.
Read eight periodic source values `Y_j=T[(i+j) mod N]`, `j=−3…4`. Use either
continuous `u` or `u_lookup=floor(64*u)/64`. Only the lookup coordinate is
quantized; the pitch increment remains `f0/Fs` in float64.

Define the declared surrogate:

```text
W(t) = 0.5*(1+cos(pi*t/4)) for |t|<4, otherwise 0
a_j  = 2*q*sinc(2*q*(j-u_lookup))*W(j-u_lookup)
sinc(x) = sin(pi*x)/(pi*x)
```

This continuous Hann window is our unsupported but reproducible choice, not a
recovered patent table. No alternate window, table size, lookup rounding,
coefficient precision or source-waveform parameter may be added after checking
the hardware predictions.

### Separate normalization from the patent-style approximation

Reindex the ordered eight values/weights from 0 through 7 for these equations:

```text
s = sum(a_j)
normalized: y = sum((a_j/s)*Y_j)
raw direct: y = sum(a_j*Y_j)
forced base: y = Y_0 + sum(k=1…7, (Y_k−Y_(k−1))*sum(j=k…7, a_j))
forced base − raw direct = (1−s)*Y_0
```

The raw-direct and forced-base pair uses **identical unnormalized weights**.
Comparing those rows isolates the base substitution. Normalized ramp rows
separately show the effect of normalization. Applying the forced-base formula
to already normalized weights would make it identical to direct convolution
and would not test the approximation.

### Fixed cutoff bank and units

Let `rho=N*f0/Fs` source samples per output sample. Constant policy uses `q=0.5`.
The bank uses `q=0.5` for `rho<=1`, `1/3` for `1<rho<=1.5`, and `0.25` for
`1.5<rho<=2`; reject `rho>2`. No threshold is fitted. The bank is a dimensionless
mechanism probe. Its cutoff before folding is `q*rho*Fs`, not the patent's
illustrative cutoff number reused as an SH-201 frequency.

| Note | rho | Bank q | Cutoff before folding |
| --- | ---: | ---: | ---: |
| 86 | 0.85236 | 0.5 | 18794.5 Hz |
| 88 | 0.95674 | 0.5 | 21096.2 Hz |
| 91 | 1.13776 | 1/3 | 16725.1 Hz |
| 93 | 1.27710 | 1/3 | 18773.3 Hz |

The `q=0.25` branch is not exercised by these hardware passages. Test its indexing
only in synthetic controls. Do not change N to place a bank boundary near a
favorable previously observed notch.

## Numerical gates before any hardware fit

1. **Independent reconstruction:** scalar direct summation versus cumulative
   differences on deterministic arbitrary periodic arrays, constants, ramps and
   Fourier tables. Include every fractional bin and circular-wrap crossing.
   Verify the raw forced-base error identity separately, with absolute error
   below `1e−12` for order-one data. Never replace the wrap difference by zero.
2. **Lookup properties:** verify normalized constant reproduction, continuous
   direct-kernel endpoint continuity and the forced-base jump identity, exact bin-edge conventions and unchanged phase
   increment. Check that all normalization denominators are safely nonzero;
   reject a malformed kernel rather than silently clamping its sum.
3. **Planted waveform recovery:** independently synthesize normalized, raw and
   forced-base cases with known 13-tap filters, train on note91, then carry taps
   to note93/88 and test the lower-cutoff branch synthetically. Require full
   training rank and cross-pitch relative waveform error power below `1e−6`.
   Recovering the waveform does not establish uniqueness of phase/FIR taps.
4. **Phase-search sensitivity:** finite lookup makes the objective nonsmooth.
   Use the same deterministic search for every model: 256 uniform phase points,
   then retain up to16strict cyclic local coarse minima sorted by training loss
   with a global-minimum fallback. Refine every seed through three65-point local
   grids spanning ±the previous spacing; divide spacing by32 per pass. Retain
   the minimum training loss over all evaluated points; do not assume scalar smooth minimization is reliable.
   Before hardware, compare planted recoveries with an independent 4096-point
   coarse search plus the same refinement. Failure stops this proposed run.
   This remains a bounded search, not a proof of a global optimum.
5. **Historical controls:** verify original source/window hashes and reconstruct
   frozen historical predictions exactly. These four comparators retain their earlier coefficients, phases and numerical
   results; they are not refitted or substituted for a new factorial row.

These gates have not yet been executed. If a gate fails, report that failure
before changing this proposal; do not consume hardware check results to repair
or broaden the family.

## Frozen hardware comparison and decision rule

Reuse the catalog-pinned dry LP12 Q0 source and original MIDI. Freshly decode
the original MP3 and require all five 80 ms window hashes to match the earlier
wavetable study. Train only on note91, onset18.75 s +100 ms. Carry every tap and
gain to note91 +160 ms, note93 onset18.25 s +100 ms, note88 onset19.75 s +100 ms,
and note86 onset19.25 s +100 ms; fit only phase/DC there. Matrices must have
rank14 and condition below `1e6`. Retain invalid/rejected rows without replacement.

Use the same centered waveform-power objective, then report H2…H8/H1 errors and
every hardware-qualified alias bin. Include unresolved-bin flags and the
independent joint first-plus-second-fold sensitivity on the same mask. Do not
fit alias-specific weights, a new cutoff, sample rate, waveform or gain on
validation passages.

Report **all 24 rows**; select no winner from check results. The check pitches
are already extensively viewed, and the same-note windows overlap20 ms. Unknown
capture transfer and effective high-note filtering remain confounds. The
proposal therefore supports only a bounded comparison of fixed hypotheses.
It cannot establish hardware equivalence or justify a production change.

## Pre-hardware control amendment

The first control run stopped before loading hardware. Its continuity assertion
incorrectly covered forced-base interpolation, which can jump when the base
sample advances. With new integer source index `k`, that jump is
`(1−sum(a_at0))*(T[k−3]−T[k−4])`. The corrected guard checks this identity for
the forced-base branch and retains continuity for both direct branches. Finite
lookup retains its own bin jumps and is not assumed continuous. The rejected
control and earlier protocol hashes are preserved in the JSON amendment; the
24 model definitions and source/validation choices did not change.

A second source-free run passed the algebra and indexing checks but failed the
Fourier/floor64 planted phase-transfer gate (maximum3.21e−6 relative power,
above1e−6). Its planted signals also reused the fitted design helper. The next
implementation corrects that independence issue by generating every extended
sample with a separate scalar implementation and applying `np.convolve(valid)`
with the known taps. The failed phase search is retained; no hardware results
have been produced and the gate has not been relaxed.

A third amendment replaces one-basin phase refinement with the fixed16-basin
rule above, without changing the24models or1e−6gate. Independent4096-coarse
planted checks use the same rule. Exact bin-edge scalar checks and20frozen
historical prediction-hash reconstructions precede hardware fitting. If recovery
still fails, stop and report numerical non-identification; do not broaden the
search indefinitely or select a basin using check-pitch errors.
