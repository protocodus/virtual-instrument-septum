# A02 cutoff/depth mechanism experiment — predeclaration

The parent confirmed **seven temporary patch states × four existing attack models**, with no rendering performed by this independent audit. The four original-patch cells may be reused after identity checks; the remaining 24 require new renders. The complete [design and expected SysEx hashes](rcs-a02-mechanism-design-2026-09-20.json) are copied byte-for-byte to `build-fidelity/rcs-endpoint-grid-2026-09-20/design.json`, SHA-256 `6ee2b87a95f211572d52c58e9d1a47feb9d1373bac33cfd74b68073dbc7d5c3f`.

These are **counterfactual preset edits**, not unchanged-preset benchmarks, recovered hardware settings or a calibrated law. They must remain outside the source catalogs and reports that claim unmodified published parameters. Production DSP, Lower part, performance MIDI and all other patch fields stay fixed.

| Upper cutoff | Signed depth | Stored depth byte | Full Upper DT1 checksum | Current model endpoint Hz |
| --- | --- | --- | --- | --- |
| 120 | −22 | 42 | `52` | 765.5 |
| 120 | −32 | 32 | `5C` | 204.4 |
| 120 | −42 | 22 | `66` | 54.6 |
| 120 | −52 | 12 | `70` | 14.6 |
| 120 | −63 | 1 | `7B` | 5.0, clamped |
| 100 | −22 | 42 | `66` | 257.0 |
| 80 | −22 | 42 | `7A` | 86.3 |

Checksums are hexadecimal; endpoint predictions are analytical values from the current engine, not hardware measurements. Each state crosses baseline attack at raw24 ≈5 ms and the existing 50/100/150 ms probes.

Roland's MIDI Implementation p. 5 assigns Upper cutoff to `10 00 01 13` and envelope depth to `10 00 01 1B`; signed depth is stored as depth +64. In the verified original 22-frame SysEx, the full Upper frame starts at byte46. Only absolute bytes76,84 and121—cutoff, depth and checksum—may change. Recompute the checksum as `(-sum(address + payload)) & 0x7f`. Every other byte, including the entire Lower part and other 21 frames, must remain identical. The JSON pins each expected complete-file hash and explicitly lists its parameter modifications.

The first note lasts137 ms. Before an attack finishes, the current model follows `log2(fc) = log2(fc0) + (12 × depth/63) × t/T`. It therefore identifies a **depth/duration slope combination**, not depth and duration separately; the 150 ms attack never settles during this note. Call the late statistic a *late-in-note level*, not an endpoint or floor. The deepest cells can remove the Upper part and leave predominantly Lower sine. Upper overdrive can also regenerate harmonics after filtering.

The primary first-note screen uses the existing300–1500/1500–12000 Hz ratio, 1024-sample Hann windows, hop44, mid channel,93-sample engine latency and ±10 ms onset checks. Early15–35 ms and late75–95 ms windows report their absolute ratios and raw powers, plus both late bands referenced to the same early low-band power. Separate high- and low-band changes, broadband RMS and25–200 Hz power expose layer suppression. Preserve the existing sustained-drop landmarks and their censoring. Longer analysis windows require an explicit common support mask where altered gates would intrude. No candidate-dependent alignment, late-window gain fitting or darkness-only selection is allowed.

Report competing cutoff, depth and duration explanations rather than a unique winning law. Freeze any candidate before checking notes2–5, especially the longer fourth note and declared gap/overlap variants. Those notes were already inspected: this is within-performance validation, not an untouched holdout. The parent's separate declaration may add independently measured late harmonic guards to reject a nearly pure Lower-sine result.
