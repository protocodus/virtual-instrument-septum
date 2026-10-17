# Integrated interpolation patent: mechanism audit

## Decision

**A distinct, bounded interpolation experiment is feasible. There is no evidence that the SH-201 implements this patent.** No renderer, production DSP, or measured model was changed. This extends the earlier [patent scope screen](patent-scope-screen-2026-09-15.md); it is a mathematical hypothesis, not an instrument identification.

## Verified primary source

[US4715257A](https://patents.google.com/patent/US4715257A/en), Roland, published 1987-12-29: the example convolves eight waveform samples with a windowed low-pass response. First differences are stored; cumulative filter coefficients avoid reconstructing every sample. Four fractional divisions illustrate the method; “64 points” is a further example. No exact window coefficients or modern implementation are supplied. The printed window name is “humming.”

The 30 kHz waveform-sampling example uses 15/10/7.5 kHz kernels; pitch selection uses lower cutoffs when transposing upward, up to factors 1.5/2. Another example selects kernels by key strength. The base coefficient is approximated as unity even when the lower-cutoff coefficient sum differs. [Original PDF](https://patentimages.storage.googleapis.com/14/6b/54/9d7e5c83b72512/US4715257.pdf)

| PDF page (one-based) | Verified location |
|---|---|
| 3 | Fig. 3: integrated coefficients |
| 4 | Figs. 4–5: impulse response, differences |
| 5 | Figs. 6–7: frequency responses |
| 6–7 | Equations (1)–(4) |
| 8 | General coefficient formula, unity approximation |
| 10 | Pitch-selected kernels; claims |

Mathematical transcription, with the indexing used in the document:

```text
P4 = sum(j=0..7, Y_j * f_(1+4j))                          (1)
d_j = Y_j - Y_(j-1)
P4 = Y0 * sum(j=0..7, f_(1+4j))
     + sum(k=1..7, d_k * sum(j=k..7, f_(1+4j)))           (2–3)
P4 = Y0 + g5*d1 + g9*d2 + g13*d3 + g17*d4
        + g21*d5 + g25*d6 + g29*d7                       (4)
g_(i+mj) = sum(k=j..n-1, f_(i+mk))
i = 0..m-1; j = 1..n-1
```

Equations (2–3) above compress the expanded printed sums without changing their terms. The original images and text are retained in the hash receipt.

## Mathematical implications and distinctions

For arbitrary weights `w_j`, direct convolution equals

```text
sum(w_j * Y_j) = Y0 * sum(w_j)
                + sum(k=1..7, (Y_k-Y_(k-1)) * sum(j=k..7, w_j)).
```

Thus, with exact arithmetic and identical weights, storing differences does not create a new audible response. Replacing the leading coefficient by one adds precisely `Y0 * (1-sum(w))`. That error can vary with fractional position. It must not accidentally be conflated with ordinary normalized convolution.

The [completed wavetable experiment](high-note-wavetable-models-2026-09-15.md) tested hold, linear, and four-point Lagrange interpolation. An eight-point low-pass kernel has a different interpolation response; a lookup grid can add position-dependent error. A pitch-dependent kernel can change that response across notes. These remain untested mechanisms, despite the poor results of the earlier families.

Cutoff units matter. A kernel cutoff `q` cycles per source sample, read at `rho` source samples per output sample, maps to `q*rho*Fs_out` before folding. Consequently the patent's numerical cutoff examples do **not** locate the observed SH-201 notch near 10–11 kHz. Likewise, a finite fractional lookup grid does not identify the pitch accumulator precision. The figures are schematic and cannot supply calibrated taps, an SH-201 oscillator sample rate, or a stored waveform length.

## Proposed small experiment — not run

Use eight declared hypotheses: the existing 32-sample ramp and finite-Fourier saw tables, each with two kernel policies and two fractional-position policies. Selecting this already-studied table length is an exploratory scope choice; it is not an independent inference about hardware memory. Do not expand the grid after examining alias errors.

1. **Kernel:** eight source samples with a normalized windowed sinc. To make the experiment reproducible, choose a continuous Hann window `W(t)=0.5*(1+cos(pi*t/4))` for `|t|<4`, zero outside. This is our specified surrogate, not a recovered patent coefficient table. For fractional position `u`, offsets `j=-3..4`, set `a_j=2*q*sinc(2*q*(j-u))*W(j-u)` and `w_j=a_j/sum(a)`.
2. **Cutoff:** compare constant `q=0.5` with the fixed bank `q=0.5` for `rho<=1`, `q=1/3` for `1<rho<=1.5`, and `q=0.25` for `1.5<rho<=2`; declare unsupported `rho>2`. Here `rho=N*f0/Fs_out`. This is a dimensionless mechanism probe, not an SH-201 control law.
3. **Fractional position:** compare continuous `u` with `floor(64*u)/64`. Keep the same high-precision phase trajectory and nominal fundamental; quantize only the lookup coordinate. Do not quantize the pitch increment or optimize rounding policy.
4. **Controls before hardware:** direct convolution versus cumulative-difference evaluation; arbitrary constants and periodic signals; correct circular wrap differences; continuous-kernel continuity; pitch equality; planted alias recovery. Retain the existing equal-13-tap naïve/polyBLEP and 32-sample linear/cubic controls. Preserve signed tap gain rather than normalizing it after fitting.
5. **Frozen comparison:** reuse the exact source/hash/mask and five-window protocol. Fit the same 13 output taps and gain only on note 91 at +100 ms; later passages get phase/DC only. Report every model's waveform power, main-harmonic error and first/second-fold alias error, including weak-bin limits. The overlapping same-note passage is a consistency check; different pitches carry the stronger test. The output FIR remains an unresolved capture/source nuisance.

The unity-coefficient approximation, coefficient bit depths, alternate windows, and additional table lengths should remain outside this first probe. A successful numerical fit could motivate a separate predeclared control; it could not establish patent use or justify a shipping change. A failure would reject only these eight declared surrogates. No additional citation search is needed to execute this bounded comparison.

## Receipt

PDF SHA-256: `ef733e3073f597b7dd00d7908baf04d543468aa68c3b4a4b9519750d2b8e95f4` (902,967 bytes, 10 pages). The [companion JSON](roland-integrated-interpolation-patent-2026-09-15.json) records URLs, hashes, extraction commands and inspected page renders. Cached originals are under `build-fidelity/public-waveforms/roland-interpolation-patent-2026-09-15/`. They are research inputs, not bundled instrument assets.
