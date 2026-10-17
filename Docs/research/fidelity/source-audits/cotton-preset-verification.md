# Cotton Wool preset verification

The current comparison uses **the same published Cotton Wool preset** as patch 1 of Roland’s official PAD bank. All 22 blocks and 1,240 parameter bytes match. A freshly compiled native decoder returns the same values for the published and benchmark files, and native export reproduces the entire original SysEx exactly.

This does **not** prove that the MP3 used precisely this edit revision, nor that the reconstruction reproduces the original note lengths, velocities, controller movements, or system settings. Roland associates the audio and downloadable preset by name; original performance MIDI and an authenticated recorded patch dump are unavailable.

Official [PAD page](https://www.rolandus.com/go/sh-201_patches/patch_pad.html), [bank download](https://www.rolandus.com/go/sh-201_patches/shl/SH-201_Patch_PAD.zip), [Cotton Wool recording](https://www.rolandus.com/go/sh-201_patches/mp3/PAD/TOP8_Cotton_Wool.mp3). Parameter addresses and enum values follow the [Roland MIDI Implementation](https://static.roland.com/assets/media/pdf/SH-201_MI.pdf), pp. 3–5.

## Identity and method

The audit independently reads the first SHL record, validates every block size, constructs DT1 frames, checks the benchmark framing/checksums, and compares their payloads. It does not import the benchmark’s extraction module. Its native utility compiles `SeptumSysEx.cpp` and `SeptumPresets.cpp` directly from the current source; no previously built DSP archive is used. Source, utility, input, and output hashes are recorded in the companion JSON.

| Object | SHA-256 |
|---|---|
| Official PAD ZIP | `d00b19491c2cec27ee640147e0dfb6d1b8a47bcb70831a93a819a70d21a2a222` |
| Official 100_PAD.shl | `78a518f63fe6ce2c15042a8f6258b4b6d6d3519727c7b0befc1f99d097c8a3ea` |
| Independent extraction = benchmark = native export | `e7f23e39445895f2158482037b37a19dfe413e536869c0e6f78352de6e49fbef` |
| Concatenated 22 block payloads, in address order | `23106382cb9794ad6903b46b91e8ba5d5b963f6cbb55cd54103f63246ad3dc6d` |
| Native parameter JSON, sorted compact encoding | `862c6d3821b71ac30a6a3c163aa7b9d070e9931e4872689cfb0057e0f6fa9df8` |

Benchmark: `build-fidelity/hardware-benchmark/brightness-investigation/production-after/cotton-wool`. The recorded render manifest’s SysEx hash also matches. The manifest’s initial patch summary is checked against native fields; all 42 available entries agree.

## Active path and envelope implications

SINGLE / UPPER is selected. The lower tone is stored and verified but does not sound in this replay. Upper OSC1 is Super Saw, spread 41; OSC2 is sine, fine −7 cents; their balance is 0. OSC2’s received coarse byte is 28 (signed −36), with WIDE off; the current decoder interprets it as **−12 physical semitones**. The original byte remains unchanged. The one-octave endpoint interpretation is corroborated by the recording; interior WIDE-off rounding remains an empirical model choice.

Upper FILTER is LPF, 24 dB/oct, cutoff 0, resonance 0, key follow +60%, cutoff velocity sensitivity +18, envelope A/D/S/R = **10/58/87/105**, depth **+39**. AMP A/D/S/R = **0/0/127/39**; its level is **70**, and amp velocity sensitivity is **0**. Both effects switches are on, but the active tone’s delay send is **0**; its reverb send is **35**. All four upper LFO modulation depths are **0**. The envelopes and reverb can produce an overlapping tail; the reconstruction’s note-off times affect filter and amp release. Raw ADSR values are controller units, not milliseconds, and do not validate the modeled time or depth curves.

The replay uses velocity 100 throughout and no controller events. That is a declared reconstruction choice, not a measured hardware velocity. Because filter velocity sensitivity is +18, equal raw preset values do not imply equal cutoff trajectories if the original velocities differed. The note gates are also reconstructed; matching their original values is especially important with filter release 105.

## Complete common, tone, effect, and arpeggio-common values

Every row matches the official SHL and benchmark. `Raw` means received decimal wire bytes, before signed or enum conversion. `Native` is printed by the newly compiled shipping decoder. Table indexes are retained as indexes, not represented as a measured physical response. Sixteen inactive arpeggio pattern blocks are checked byte-for-byte and hashed separately in the JSON; they are omitted from this readable table.

### Common

| Parameter | Address | Raw | Native | Conversion |
|---|---|---|---|---|
| `name` | `10 00 00 00` | 67, 111, 116, 116, 111, 110, 32, 87, 111, 111, 108, 32 | Cotton Wool | ASCII, trailing spaces removed |
| `patchLevel` | `10 00 00 0C` | 127 | 127 | identity |
| `toneBalance` | `10 00 00 0D` | 64 | 0 | raw - 64 |
| `tempo` | `10 00 00 0E` | 0, 7, 8 | 120 | three big-endian nibbles, BPM |
| `keyboardMode` | `10 00 00 11` | 0 | 0 (SINGLE) | enum |
| `keyboardPart` | `10 00 00 12` | 0 | 0 (UPPER) | enum |
| `splitPoint` | `10 00 00 13` | 53 | 53 | MIDI note number |
| `arpeggio.splitArpeggio` | `10 00 00 14` | 2 | 2 (BOTH) | enum |
| `modulationDestination` | `10 00 00 15` | 2 | 2 (BOTH) | enum |
| `dBeamDestination` | `10 00 00 16` | 2 | 2 (BOTH) | enum |
| `pitchBendDestination` | `10 00 00 17` | 2 | 2 (BOTH) | enum |
| `expressionDestination` | `10 00 00 18` | 2 | 2 (BOTH) | enum |
| `activeExpression` | `10 00 00 19` | 0 | 0 (OFF) | boolean |
| `arpeggio.on` | `10 00 00 1A` | 0 | 0 (OFF) | boolean |
| `arpeggio.hold` | `10 00 00 1B` | 0 | 0 (OFF) | boolean |
| `delayOn` | `10 00 00 1C` | 1 | 1 (ON) | boolean |
| `reverbOn` | `10 00 00 1D` | 1 | 1 (ON) | boolean |
| `modulationAssign` | `10 00 00 1E` | 0 | 0 (OSC1+2) | enum |
| `dBeamAssign` | `10 00 00 1F` | 7 | 7 | enum; stored, D Beam not modeled |
| `dBeamPolarity` | `10 00 00 20` | 1 | 1 (MINUS) | enum |

### Upper — active

| Parameter | Address | Raw | Native | Conversion |
|---|---|---|---|---|
| `upper.osc1.wave` | `10 00 01 00` | 7 | 7 (SUPER SAW) | enum |
| `upper.osc1.pitchWide` | `10 00 01 01` | 0 | 0 (OFF) | boolean |
| `upper.osc1.coarse` | `10 00 01 02` | 64 | 0 | WIDE off: round((raw-64)/3); WIDE on: raw-64 semitones |
| `upper.osc1.fine` | `10 00 01 03` | 64 | 0 | raw - 64 cents |
| `upper.osc1.pulseWidth` | `10 00 01 04` | 41 | 41 | PW / feedback / Super Saw spread, by waveform |
| `upper.osc1.pitchEnvDepth` | `10 00 01 05` | 64 | 0 | raw - 64 |
| `upper.osc2.wave` | `10 00 01 06` | 4 | 4 (SINE) | enum |
| `upper.osc2.pitchWide` | `10 00 01 07` | 0 | 0 (OFF) | boolean |
| `upper.osc2.coarse` | `10 00 01 08` | 28 | -12 | WIDE off: round((raw-64)/3); WIDE on: raw-64 semitones |
| `upper.osc2.fine` | `10 00 01 09` | 57 | -7 | raw - 64 cents |
| `upper.osc2.pulseWidth` | `10 00 01 0A` | 64 | 64 | PW / feedback / Super Saw spread, by waveform |
| `upper.osc2.pitchEnvDepth` | `10 00 01 0B` | 64 | 0 | raw - 64 |
| `upper.pitchEnvAttack` | `10 00 01 0C` | 0 | 0 | identity |
| `upper.pitchEnvDecay` | `10 00 01 0D` | 0 | 0 | identity |
| `upper.mixType` | `10 00 01 0E` | 0 | 0 (MIX) | enum |
| `upper.balance` | `10 00 01 0F` | 64 | 0 | raw - 64 |
| `upper.lowFreq` | `10 00 01 10` | 0 | 0 (FLAT) | enum |
| `upper.filterType` | `10 00 01 11` | 1 | 1 (LPF) | enum |
| `upper.filterSlope` | `10 00 01 12` | 1 | 1 (24 dB/oct) | enum |
| `upper.cutoff` | `10 00 01 13` | 0 | 0 | identity |
| `upper.keyFollow` | `10 00 01 14` | 70 | 60 | (raw - 64) × 10 percent |
| `upper.cutoffVelocitySens` | `10 00 01 15` | 82 | 18 | raw - 64 |
| `upper.resonance` | `10 00 01 16` | 0 | 0 | identity |
| `upper.filterEnvAttack` | `10 00 01 17` | 10 | 10 | identity |
| `upper.filterEnvDecay` | `10 00 01 18` | 58 | 58 | identity |
| `upper.filterEnvSustain` | `10 00 01 19` | 87 | 87 | identity |
| `upper.filterEnvRelease` | `10 00 01 1A` | 105 | 105 | identity |
| `upper.filterEnvDepth` | `10 00 01 1B` | 103 | 39 | raw - 64 |
| `upper.overdrive` | `10 00 01 1C` | 0 | 0 (OFF) | enum |
| `upper.drive` | `10 00 01 1D` | 50 | 50 | identity |
| `upper.level` | `10 00 01 1E` | 70 | 70 | identity |
| `upper.levelVelocitySens` | `10 00 01 1F` | 64 | 0 | raw - 64 |
| `upper.pan` | `10 00 01 20` | 64 | 0 | raw - 64 |
| `upper.ampEnvAttack` | `10 00 01 21` | 0 | 0 | identity |
| `upper.ampEnvDecay` | `10 00 01 22` | 0 | 0 | identity |
| `upper.ampEnvSustain` | `10 00 01 23` | 127 | 127 | identity |
| `upper.ampEnvRelease` | `10 00 01 24` | 39 | 39 | identity |
| `upper.delayDepth` | `10 00 01 25` | 0 | 0 | identity |
| `upper.reverbDepth` | `10 00 01 26` | 35 | 35 | identity |
| `upper.bendRange` | `10 00 01 3B` | 2 | 2 | identity |
| `upper.octaveShift` | `10 00 01 3C` | 64 | 0 | raw - 64 |
| `upper.portamento` | `10 00 01 3D` | 0 | 0 (OFF) | enum |
| `upper.portamentoTime` | `10 00 01 3E` | 20 | 20 | identity |
| `upper.mono` | `10 00 01 3F` | 0 | 0 (POLY) | enum |
| `upper.lfo1.shape` | `10 00 01 27` | 0 | 0 (TRIANGLE) | enum |
| `upper.lfo1.rate` | `10 00 01 28` | 92 | 92 | identity / documented table index |
| `upper.lfo1.tempoSync` | `10 00 01 29` | 0 | 0 (OFF) | enum |
| `upper.lfo1.tempoSyncNote` | `10 00 01 2A` | 17 | 17 | identity / documented table index |
| `upper.lfo1.fadeTime` | `10 00 01 2B` | 0 | 0 | identity / documented table index |
| `upper.lfo1.keyTrigger` | `10 00 01 2C` | 0 | 0 (OFF) | enum |
| `upper.lfo1.destination1` | `10 00 01 2D` | 2 | 2 (FILTER) | enum |
| `upper.lfo1.depth1` | `10 00 01 2E` | 64 | 0 | raw - 64 |
| `upper.lfo1.destination2` | `10 00 01 2F` | 2 | 2 (AMP) | enum |
| `upper.lfo1.depth2` | `10 00 01 30` | 64 | 0 | raw - 64 |
| `upper.lfo2.shape` | `10 00 01 31` | 0 | 0 (TRIANGLE) | enum |
| `upper.lfo2.rate` | `10 00 01 32` | 92 | 92 | identity / documented table index |
| `upper.lfo2.tempoSync` | `10 00 01 33` | 0 | 0 (OFF) | enum |
| `upper.lfo2.tempoSyncNote` | `10 00 01 34` | 17 | 17 | identity / documented table index |
| `upper.lfo2.fadeTime` | `10 00 01 35` | 0 | 0 | identity / documented table index |
| `upper.lfo2.keyTrigger` | `10 00 01 36` | 0 | 0 (OFF) | enum |
| `upper.lfo2.destination1` | `10 00 01 37` | 2 | 2 (FILTER) | enum |
| `upper.lfo2.depth1` | `10 00 01 38` | 64 | 0 | raw - 64 |
| `upper.lfo2.destination2` | `10 00 01 39` | 2 | 2 (AMP) | enum |
| `upper.lfo2.depth2` | `10 00 01 3A` | 64 | 0 | raw - 64 |

### Lower — stored, inactive

| Parameter | Address | Raw | Native | Conversion |
|---|---|---|---|---|
| `lower.osc1.wave` | `10 00 02 00` | 0 | 0 (SAW) | enum |
| `lower.osc1.pitchWide` | `10 00 02 01` | 0 | 0 (OFF) | boolean |
| `lower.osc1.coarse` | `10 00 02 02` | 64 | 0 | WIDE off: round((raw-64)/3); WIDE on: raw-64 semitones |
| `lower.osc1.fine` | `10 00 02 03` | 64 | 0 | raw - 64 cents |
| `lower.osc1.pulseWidth` | `10 00 02 04` | 64 | 64 | PW / feedback / Super Saw spread, by waveform |
| `lower.osc1.pitchEnvDepth` | `10 00 02 05` | 64 | 0 | raw - 64 |
| `lower.osc2.wave` | `10 00 02 06` | 1 | 1 (SQUARE) | enum |
| `lower.osc2.pitchWide` | `10 00 02 07` | 0 | 0 (OFF) | boolean |
| `lower.osc2.coarse` | `10 00 02 08` | 64 | 0 | WIDE off: round((raw-64)/3); WIDE on: raw-64 semitones |
| `lower.osc2.fine` | `10 00 02 09` | 64 | 0 | raw - 64 cents |
| `lower.osc2.pulseWidth` | `10 00 02 0A` | 64 | 64 | PW / feedback / Super Saw spread, by waveform |
| `lower.osc2.pitchEnvDepth` | `10 00 02 0B` | 64 | 0 | raw - 64 |
| `lower.pitchEnvAttack` | `10 00 02 0C` | 0 | 0 | identity |
| `lower.pitchEnvDecay` | `10 00 02 0D` | 0 | 0 | identity |
| `lower.mixType` | `10 00 02 0E` | 0 | 0 (MIX) | enum |
| `lower.balance` | `10 00 02 0F` | 1 | -63 | raw - 64 |
| `lower.lowFreq` | `10 00 02 10` | 0 | 0 (FLAT) | enum |
| `lower.filterType` | `10 00 02 11` | 1 | 1 (LPF) | enum |
| `lower.filterSlope` | `10 00 02 12` | 0 | 0 (12 dB/oct) | enum |
| `lower.cutoff` | `10 00 02 13` | 127 | 127 | identity |
| `lower.keyFollow` | `10 00 02 14` | 64 | 0 | (raw - 64) × 10 percent |
| `lower.cutoffVelocitySens` | `10 00 02 15` | 64 | 0 | raw - 64 |
| `lower.resonance` | `10 00 02 16` | 0 | 0 | identity |
| `lower.filterEnvAttack` | `10 00 02 17` | 0 | 0 | identity |
| `lower.filterEnvDecay` | `10 00 02 18` | 0 | 0 | identity |
| `lower.filterEnvSustain` | `10 00 02 19` | 127 | 127 | identity |
| `lower.filterEnvRelease` | `10 00 02 1A` | 0 | 0 | identity |
| `lower.filterEnvDepth` | `10 00 02 1B` | 64 | 0 | raw - 64 |
| `lower.overdrive` | `10 00 02 1C` | 0 | 0 (OFF) | enum |
| `lower.drive` | `10 00 02 1D` | 100 | 100 | identity |
| `lower.level` | `10 00 02 1E` | 127 | 127 | identity |
| `lower.levelVelocitySens` | `10 00 02 1F` | 72 | 8 | raw - 64 |
| `lower.pan` | `10 00 02 20` | 64 | 0 | raw - 64 |
| `lower.ampEnvAttack` | `10 00 02 21` | 0 | 0 | identity |
| `lower.ampEnvDecay` | `10 00 02 22` | 0 | 0 | identity |
| `lower.ampEnvSustain` | `10 00 02 23` | 127 | 127 | identity |
| `lower.ampEnvRelease` | `10 00 02 24` | 0 | 0 | identity |
| `lower.delayDepth` | `10 00 02 25` | 20 | 20 | identity |
| `lower.reverbDepth` | `10 00 02 26` | 20 | 20 | identity |
| `lower.bendRange` | `10 00 02 3B` | 2 | 2 | identity |
| `lower.octaveShift` | `10 00 02 3C` | 64 | 0 | raw - 64 |
| `lower.portamento` | `10 00 02 3D` | 0 | 0 (OFF) | enum |
| `lower.portamentoTime` | `10 00 02 3E` | 20 | 20 | identity |
| `lower.mono` | `10 00 02 3F` | 0 | 0 (POLY) | enum |
| `lower.lfo1.shape` | `10 00 02 27` | 0 | 0 (TRIANGLE) | enum |
| `lower.lfo1.rate` | `10 00 02 28` | 92 | 92 | identity / documented table index |
| `lower.lfo1.tempoSync` | `10 00 02 29` | 0 | 0 (OFF) | enum |
| `lower.lfo1.tempoSyncNote` | `10 00 02 2A` | 17 | 17 | identity / documented table index |
| `lower.lfo1.fadeTime` | `10 00 02 2B` | 0 | 0 | identity / documented table index |
| `lower.lfo1.keyTrigger` | `10 00 02 2C` | 0 | 0 (OFF) | enum |
| `lower.lfo1.destination1` | `10 00 02 2D` | 2 | 2 (FILTER) | enum |
| `lower.lfo1.depth1` | `10 00 02 2E` | 64 | 0 | raw - 64 |
| `lower.lfo1.destination2` | `10 00 02 2F` | 2 | 2 (AMP) | enum |
| `lower.lfo1.depth2` | `10 00 02 30` | 64 | 0 | raw - 64 |
| `lower.lfo2.shape` | `10 00 02 31` | 0 | 0 (TRIANGLE) | enum |
| `lower.lfo2.rate` | `10 00 02 32` | 92 | 92 | identity / documented table index |
| `lower.lfo2.tempoSync` | `10 00 02 33` | 0 | 0 (OFF) | enum |
| `lower.lfo2.tempoSyncNote` | `10 00 02 34` | 17 | 17 | identity / documented table index |
| `lower.lfo2.fadeTime` | `10 00 02 35` | 0 | 0 | identity / documented table index |
| `lower.lfo2.keyTrigger` | `10 00 02 36` | 0 | 0 (OFF) | enum |
| `lower.lfo2.destination1` | `10 00 02 37` | 2 | 2 (FILTER) | enum |
| `lower.lfo2.depth1` | `10 00 02 38` | 64 | 0 | raw - 64 |
| `lower.lfo2.destination2` | `10 00 02 39` | 2 | 2 (AMP) | enum |
| `lower.lfo2.depth2` | `10 00 02 3A` | 64 | 0 | raw - 64 |

### Delay and reverb

| Parameter | Address | Raw | Native | Conversion |
|---|---|---|---|---|
| `delay.time` | `10 00 03 00` | 70 | 70 | identity |
| `delay.feedback` | `10 00 03 01` | 66 | 34 | (raw - 49) × 2 percent |
| `delay.hfDamp` | `10 00 03 02` | 8 | 8 | documented frequency index |
| `delay.modulationRate` | `10 00 03 03` | 5 | 5 | identity |
| `delay.modulationDepth` | `10 00 03 04` | 10 | 10 | identity |
| `reverb.time` | `10 00 04 00` | 104 | 104 | identity |
| `reverb.preDelay` | `10 00 04 01` | 125 | 125 | documented table index |
| `reverb.size` | `10 00 04 02` | 7 | 7 | displayed as native + 1 |
| `reverb.highCut` | `10 00 04 03` | 19 | 19 | documented table index |
| `reverb.density` | `10 00 04 04` | 127 | 127 | identity |
| `reverb.diffusion` | `10 00 04 05` | 127 | 127 | identity |
| `reverb.lfDampFrequency` | `10 00 04 06` | 19 | 19 | documented table index |
| `reverb.lfDampGain` | `10 00 04 07` | 36 | 0 | raw - 36 dB |
| `reverb.hfDampFrequency` | `10 00 04 08` | 0 | 0 | documented table index |
| `reverb.hfDampGain` | `10 00 04 09` | 36 | 0 | raw - 36 dB |

### Arpeggio — off

| Parameter | Address | Raw | Native | Conversion |
|---|---|---|---|---|
| `arpeggio.grid` | `10 00 05 00` | 5 | 5 | identity / documented enum |
| `arpeggio.duration` | `10 00 05 01` | 5 | 5 | identity / documented enum |
| `arpeggio.motif` | `10 00 05 02` | 11 | 11 | identity / documented enum |
| `arpeggio.octaveRange` | `10 00 05 03` | 64 | 0 | raw - 64 |
| `arpeggio.accent` | `10 00 05 04` | 100 | 100 | identity / documented enum |
| `arpeggio.velocity` | `10 00 05 05` | 0 | 0 | identity / documented enum |
| `arpeggio.style.endStep` | `10 00 05 06` | 0, 8 | 8 | two big-endian nibbles |

## What this resolves

There is no detected wrong-bank selection, altered Cotton Wool preset byte, dropped tone/effect block, cutoff sign error, or manifest/native decode disagreement in the current comparison. WIDE coarse conversion is deliberate and canonical export is byte-identical for this patch. This audit verifies data identity and current interpretation; it does not establish that Septum’s filter, envelopes, oscillators, or effects reproduce the SH-201 DSP.

MASTER level, global tuning/transpose, output path, and live controllers are not carried in these 22 patch blocks. The renderer’s master level is 100; the hardware recording’s corresponding setting is unknown. The full MIDI provenance and replay settings are retained in the companion JSON.

Reproduce locally with the already downloaded official ZIP:

```sh
python3 Tools/audit_cotton_preset.py \
  --bank /tmp/septum-hw-benchmark/research-official/SH-201_Patch_PAD.zip \
  --benchmark build-fidelity/hardware-benchmark/brightness-investigation/production-after/cotton-wool
```
