# Gain-structure diagnostics — 2026-09-20

**No global change is supported.** Pure gain probes fail cross-preset checks, and the A02 interaction screen fails joint trajectory/harmonic checks. No Roland gain law or full hardware match is established. Production DSP remains unchanged.

## Scope and operating levels

Two fixed probes multiply the current tanh input by **0.5** (`halfInput`) or **0.22** (`headroomInput`) and divide its output by the same factor. Drive law, ADAA, latency and bypass remain. Small-signal gain is preserved; compression changes.

There are **43 actual new renders: 34 original-preset comparisons + six additional A02 interaction renders + three telemetry controls**. The eight A02 diagnostic cells include two reused original-patch/current-attack renders. The predeclared A02 design crosses both factors with current/100 ms attack and original depth −22/temporary depth −32. The temporary patch changes only Upper filter-envelope depth and its checksum.

Buffered taps on incumbent tanh produced byte-identical audio for A01, original A02 and A02 depth −32. Measured Upper shaper inputs:

| Fixed windows | Input min…max | RMS range | Fraction with magnitude >1 |
|---|---:|---:|---:|
| A01, 18 note windows | −2.986…1.305 | 1.030–1.060 | 33.84–35.57% |
| A02, eight late windows | −5.460…5.522 | 3.325–3.478 | 51.66–55.36% |
| A02 depth −32, eight late windows | −2.189…4.733 | 2.334–2.369 | 62.02–63.83% |

These **software measurements** exclude warm-start replay. Native engine-input frames and internal ordinals are retained; the output's 93-sample delay is not subtracted from internal taps. The ninth originally declared telemetry window ending at 21.880 s is separately labelled; primary eight windows end by 21.877 s.

[Source review](rcs-linear-center-results-2026-09-20.md) establishes unity oscillator legs summed without halving at BALANCE 0, unity-DC LP stages below limiting, and drive-33 pregain 2.604642. AMP envelope and voice headroom 0.22 follow overdrive. Quiet output therefore does not imply small shaper input. Moving numerical gain around tanh does not identify the hardware's internal staging.

## Original-preset checks

All 34 renders preserve the 17 original patches, reconstructed MIDI and strict settings. All **20 OD-off controls are byte-identical**; no candidate reaches the final-output 0.9 safety knee.

| Median dry harmonic error, dB | Baseline | Factor 0.5 | Factor 0.22 |
|---|---:|---:|---:|
| A01: H2–H8/H1 | 2.503 | 2.457 | 3.412 |
| A01: H3/H5/H7 relative to H1 | 2.466 | 3.354 | 4.642 |
| Dist Bs 1: H2–H8/H1 | 7.888 | 11.249 | 8.152 |
| Dist Bs 1: H4/H6/H8 relative to H2 | 3.693 | 5.075 | 11.765 |

Factor 0.5 worsens every Dist harmonic group in all 27 sensitivity settings. Factor 0.22 improves Dist's odd group in all 27 but worsens its even group in all 27. A01's even group improves, while odd error worsens in 18/27 and 21/27 settings respectively. Dist's broad spectral score improves for both factors, demonstrating why that secondary score cannot decide fidelity.

A03 has no sustained 10/20/30 dB closure in either probe, versus hardware 27/27 at each threshold. A05 has observed counts 1/0/0 for factor 0.5 and 3/3/3 for 0.22, versus hardware 27/27/26. Its late high band approaches the recording floor. Broad errors also worsen for A02, A03, Club Bass and Sexy Back.

## A02 interaction and provenance

At factor 0.22/depth −32, late H4/H2 is −25.165 dB versus hardware −24.371, but H3/H2 is −9.721 versus −15.719 and H2/H1 is −12.726 versus −7.012. With 100 ms attack, first-note high/low powers change −39.944/−8.140 dB versus −30.713/−2.307; fourth-note closures are only 3/27 at each threshold versus 27/27. No joint fit appears. Original/common guards stay separate; matched tanh/linearized controls are reused, not remeasured.

The [artifact index](rcs-gain-structure-results-2026-09-20.json) pins protocols, sources, results and commands. The 17-case hardware/baseline metrics and 66 A02 hardware harmonic fits reproduce exactly. An initial redundant A02 check stopped at a 4.66×10⁻¹⁰ first-note float32 power difference despite byte-identical PCM and exact harmonic/closure results; its log and superseded runner remain. The unchanged 17-case analysis was completed in a new directory, with A02 delegated separately. Both runners safely handle `--help` and refuse overwrites.

Known preset association does not supply original performance MIDI, phase, capture gain or proof against live edits. RCS video/SoundCloud encode one performance; overlapping windows are sensitivity checks, not independent trials. A02 remains diagnostic training, with no unseen validation or aggregate winner.
