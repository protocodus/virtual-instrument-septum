# Causal, configurable synthesis-clock experiment

The comparison renderer now accepts an explicit internal synthesis rate from
8–192 kHz. Invalid/nonfinite rates throw before changing its current setup.
The default remains the prototype's 44.1 kHz. This is a selectable hypothesis,
not a recovered SH-201 clock: the documented USB stream does not establish
the clock of every synthesis block.

The former scheduler rendered a pending core frame after receiving a later
host-boundary control. That could apply notes or pitch changes too early at
fractional rate ratios, including 48 kHz host / 44.1 kHz core. The renderer
now finishes each open host interval with its existing controls. A control
at host frame H first reaches core frame `ceil(H * coreRate / hostRate)`.
Input conversion still reads only audio already supplied by the host.

The independent reference tests compare actual note/bend/release audio
against a manually quantized core timeline. Reinstating the old scheduler
fails four of five distinguishing cases (peak errors 0.00372–0.01996); the
integer-ratio positive control remains unchanged. Eight static Super Saw
and EXT-IN fixtures are byte-identical before/after the scheduling fix.

The focused suite passes 5,267 checks. It covers selected core rates,
converter rejection, reset, arbitrary block partitions, zero render
allocations, invalid rates, event causality and measured external-input
impulse timing. A current A6 Super Saw fixture at 44.1 kHz core has its
15,940 Hz component at approximately −32.278 dBc across 44.1, 48, 88.2, 96
and 192 kHz hosts. This demonstrates consistent chosen-model behavior,
not a measured SH-201 spectrum.

The renderer still evaluates core controls once per internal sample and
has an additional input-converter delay for external audio. These remain
explicit integration limits. At 48 kHz host / 44.1 kHz core, reported fixed
transport is 171 host samples for MIDI-generated sound and 241 for external
audio; control quantization adds less than one core sample separately.

Best-of-three local benchmarks with ten voices, two Super Saws and effects
gave native/reference costs of 4.0%/12.1% of one core at 44.1 kHz and
4.3%/12.3% at 48 kHz. At a 48 kHz host, selected 32/48/96 kHz core rates
cost 9.3%/13.1%/26.1%. These measurements came from an isolated source copy
before the new table APIs and are workload/machine-specific, not a plug-in
performance guarantee. Latency alignment and CPU cost still need work
before considering default plug-in integration.
