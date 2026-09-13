# Feedback oscillator synchronization

The FB OSC source now restarts when OSC2 starts a new cycle in SYNC mode. Previously, selecting SYNC with FB OSC as OSC1 produced exactly the same output as MIX when OSC2 was muted by BALANCE. The change removes that unconditional exclusion while preserving the existing feedback oscillator's waveform, delay, damping, gain and nonlinear processing.

This is a **moderately grounded behavioral inference**, not a recovered SH-201 oscillator algorithm or a match to a hardware recording. Roland documents the general OSC1 restart contract and publishes patches that select this combination. The detailed interaction between synchronization and the hardware feedback loop remains unknown.

## Source evidence

Roland's [English Owner's Manual](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf), p. 32, describes SYNC as restarting OSC1 at the beginning of OSC2's cycles. It does not exclude FB OSC. The [Japanese Owner's Manual](https://static.roland.com/jp/media/pdf/SH-201_j1.pdf), p. 32, gives the same general behavior. Pages 28 and 30 describe FB OSC and its feedback control without adding a SYNC restriction. These are product behavior descriptions, not an internal block diagram for the feedback oscillator.

Roland's public editor resources also expose MIX/SYNC/RING without a waveform-dependent restriction. The editor resource identities and original download links are retained in [the oscillator semantics audit](oscillator-semantics.md). Their absence of a restriction supports applicability but cannot establish what the DSP actually computes.

Two examples from Roland's published Patch 100 banks select FB OSC as OSC1 in an active SYNC tone. The [MIDI Implementation](https://cdn.roland.com/assets/media/pdf/SH-201_MI.pdf), p. 5, provides the tone offsets and enum interpretation; the existing `Tools/extract_reference_patch.py` validates and reads the public librarian container.

| Bank and patch | Tone | OSC1 / OSC2 waveform bytes | MIX/MOD byte | BALANCE byte / signed value |
|---|---|---|---|---|
| [PAD, 27: ReverseMetal](https://www.rolandus.com/go/sh-201_patches/patch_pad.html) | Lower | 6 / 0: FB OSC / saw | 1: SYNC | 1 / −63 |
| [BASS, 100: FB Harmonics](https://www.rolandus.com/go/sh-201_patches/patch_bass2.html) | Upper | 6 / 3: FB OSC / triangle | 1: SYNC | 67 / +3 |

The original archives are [SH-201_Patch_PAD.zip](https://www.rolandus.com/go/sh-201_patches/shl/SH-201_Patch_PAD.zip) and [SH-201_Patch_BASS.zip](https://www.rolandus.com/go/sh-201_patches/shl/SH-201_Patch_BASS.zip). Archive SHA-256 identities are:

| Archive | SHA-256 |
|---|---|
| PAD | `d00b19491c2cec27ee640147e0dfb6d1b8a47bcb70831a93a819a70d21a2a222` |
| BASS | `782e04766bec4dc8b8485e82499a0a7f12fe2408a8a04141a5e1db098c7f36fc` |

Both examples have equal nominal oscillator pitches: ReverseMetal's coarse/fine bytes are 64/64 on both oscillators; FB Harmonics uses 28/64 on both, with WIDE off. Consequently, the stored settings are evidence that Roland exposed and used the combination, **not proof of an audible nontrivial reset in these specific patches**. No isolated recording establishes how their feedback paths respond to synchronization. Neither preset is modified or distributed by this change.

## Implementation and limits

`Engine::renderVoiceTick()` now permits FB OSC through the source-phase reset already used by the classic waveforms. OSC2 supplies its fractional wrap time; the source phase is positioned so the generator's following sample advance lands the correct fraction of a sample after the reset. This preserves timing when the oscillator period is not an integer number of samples.

Only the source phase resets. The comb buffer, its write position and its damping state continue uninterrupted. This is the smallest extension of the current model and retains audible feedback even when the delay tap spans several OSC2 cycles. Clearing that history each cycle would erase the delayed signal in that case. This reasoning selects a useful conservative model; it does not establish Roland's actual reset topology.

Noise and external-input slave handling are unchanged. Restarting a random generator or looping external audio would require additional undocumented mechanisms. FB OSC as OSC2 retains its existing master-cycle behavior. The earlier oscillator audit's unresolved FB slave exclusion is superseded by this implementation; OQ-19's feedback-loop topology uncertainty remains open.

A decisive hardware comparison would record FB OSC as isolated OSC1, effects off and filter bypassed, at zero and several nonzero feedback settings. Compare MIX and SYNC at unequal OSC1/OSC2 pitch ratios, including a slave whose comb period would exceed one master cycle, then inspect period, reset timing and transient evolution. This would distinguish source-only reset from delay reset, phase-offset and alternative feedback topologies.

## Rendered regression evidence

`Tests/FeedbackSyncTests.cpp` uses procedural patches rather than redistributed Roland presets. The tests compare complete engine output, including its normal voice transport and analog output model. For zero feedback and a slave below its master, the independent source reference is `2 × (f1/f2) × frac(t × f2) − 1`. Only overall output gain and the coupling capacitor's decaying startup state are fitted; these cannot conceal an incorrect period or reset position.

| Test | Before | After |
|---|---:|---:|
| Fractional-ramp relative RMS error, 44.1 kHz | 0.986409 | 7.34 × 10⁻⁸ |
| Fractional-ramp relative RMS error, 48 kHz | 0.986209 | 6.86 × 10⁻⁸ |
| Fractional-ramp relative RMS error, 96 kHz | 0.985410 | 5.87 × 10⁻⁸ |
| MIX/SYNC relative audio difference, feedback 0 / 48 / 96 / 127 | 0 / 0 / 0 / 0 | 1.267 / 1.563 / 1.445 / 1.266 |
| Regression checks | 7 failures out of 10 | 10 pass |

The suite additionally verifies that feedback remains audible across master resets, an isolated FB OSC master is unchanged, and changing the host block size does not move the source reset. The before results were produced by compiling the same tests against the pre-change engine. These numerical comparisons validate the selected implementation, not hardware fidelity beyond the cited behavioral evidence.
