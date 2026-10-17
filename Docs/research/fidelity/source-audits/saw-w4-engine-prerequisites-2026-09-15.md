# W4 source through the complete engine: prerequisite controls

**The isolated W4 source and exact-engine backend passed their engineering controls.** Fresh baseline renders and the W4 basis containing ordinary polyBLEP both reproduce the complete retained LP12/LP24 WAVs byte for byte. Independently rendered planted sources agree with the cached forward calculation to about6×10⁻⁸ relative RMS. No hardware fit, candidate selection or shipping source change belongs to this receipt.

This implements the infrastructure in the [bounded proposal](asymmetric-w4-engine-test-proposal-2026-09-15.md), using source revision `545b3d37d9cc1f80bf39bc5d0bf49c0cced1d9f6`. The [complete receipt](saw-w4-engine-prerequisites-2026-09-15.json) pins the builder, generated source, binaries, controls, input MIDI/SysEx, retained failures and independent checks.

## Source and complete downstream path

Only the copied `renderClassicWave` Saw branch changes. It retains the unit ramp and adds independent negative/positive degree3 C1 cubic B-spline curves, with doubled half-sample interior knots and16 retained coefficients per side. The last two basis functions are omitted, making value and slope zero at the four-sample support endpoint. Natural-wrap jump and slope remain free.

For increment `d`, phase `p`, and signed correction `K`, the oscillator uses:

`2p − 1 + Σₖ K((p−k)/d) − d·∫K(t)dt`

The integer sum includes every overlapping support, including increments up to the engine's0.45 limit. Each basis integral is `(knot[j+4]−knot[j])/4`. Mean subtraction is analytic in continuous phase; it does not remove finite sampled-window DC.

The correction sits before the original oscillator mixer, low-frequency shelf, moving voice filter, bypassed-drive oversampling, AMP, master and AnalogOutput. The canonical phase advance and fractional wrap reporting remain unchanged. `corrected=false` still returns the original naive hard-sync-reset sample. Other waveforms are untouched. An optional waveform-only nuisance phase affects the single original MIDI91 event; final comparison renders require phase0.

The original MIDI and physical dry recipe are unchanged. As documented in the [full-engine baseline](production-high-note-saw-2026-09-15.md), this recipe is reconstructed rather than authenticated original SysEx. These controls establish implementation behavior, not Roland's source architecture.

## Exact state caching

The persistent backend independently prewarms34 complete engines: zero source, unit ramp and32 source basis functions. Every earlier original note is processed. It snapshots immediately before the MIDI91 onset at sample826875, then clones each state for a requested nuisance phase.

Only the four meter atomics need a copyable wrapper in the isolated source; their ordinary load/store operations remain unchanged. Engine vectors and DSP state copy deeply. Processing retains the native renderer's256-sample and MIDI-event boundaries, including the complete final process call; the backend crops afterwards to engine samples828115–831643. This corresponds to hardware829521–833049 under the existing−1406 offset. Renderer latency remains93 samples and is not added twice.

## Measured controls

| Control | Result |
|---|---|
| Fresh native LP12/LP24 full original sequence | Both WAV hashes exactly match retained production |
| Exact polyBLEP nested in W4, both full sequences | Both WAV hashes exactly match production again |
| Independent compiled-source/SciPy comparison | Maximum absolute difference2.22×10⁻¹⁶ |
| Analytic continuous-phase DC, including overlaps | Magnitude below5.36×10⁻¹⁷ |
| Planted phase0: full render versus cached basis composition | Relative RMS5.73×10⁻⁸; maximum absolute1.18×10⁻⁸ |
| Planted phase0.321: same comparison | Relative RMS5.89×10⁻⁸; maximum absolute1.33×10⁻⁸ |
| Coefficient-plus-DC matrices | Rank33; conditions8967/8866 |
| Zero-source output | Exactly zero in both controls |
| Filter/output limiting | No calls in basis prehistory, requests or full planted renders |

The planted vector is ordinary polyBLEP plus fixed bounded sine/cosine coefficient perturbations. Truth comes from separate complete MIDI renders, never matrix multiplication. The predeclared gates were relative RMS≤10⁻⁶, maximum absolute error≤2×10⁻⁶ and matrix condition≤10⁶. New coefficients must pass their own complete-render and limiter checks.

The [independent review](asymmetric-w4-engine-independent-review-2026-09-15.md) additionally checked55,488 compiled scalar samples,5,184 calls to the actual oscillator function,2,592 paired canonical-clock/wrap/RNG observations and2,376 unchanged hard-sync/non-Saw outputs. No phase-clock or reset discrepancy was found. The separate evidence files are pinned in the JSON.

Complete baseline renders took about1.26 seconds each while running together. Prewarming took12.15 seconds; the two cached phase requests took0.074/0.095 seconds. These are local runtime observations, not performance guarantees.

Two earlier builds failed before measurements: an exact multiline integration guard, then a missing atomic-reference conversion used by the unchanged meter-decay lambda. Their logs remain pinned. Build03 passed; no model family or numerical tolerance was changed because of either failure.

## Interface and next gate

`Tools/build_saw_w4_experiment.py` exposes:

- `open_backend(build_dir, patch_path, midi_path, output_dir=...)`; `matrix(phase)` returns3528×33 raw-engine columns `[ramp, negative16, positive16]`, and `offset()` returns the separate zero-source output.
- `render_source(build_dir, patch_path, midi_path, coefficients, phase=0, output_dir=...)`;32 coefficients keep the unit ramp, while `None` selects the exact native baseline. It writes full original-input and runtime-configuration receipts.
- `build` and `controls` commands for source reconstruction and source-free gate replay.

The root fitter must still recover an independently planted source with an unknown nuisance phase before reading hardware, then freeze one vector before comparisons. The full-engine scorer must preserve the note91 training exclusion and original-only eligibility masks. Passing this infrastructure gate does not establish a useful hardware improvement or whole-instrument equivalence.
