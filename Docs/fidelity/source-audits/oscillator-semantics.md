# SH-201 oscillator semantics audit

Audited 2026-09-13; coarse-tuning interpretation corrected after the recording audit. The initial inspection was read-only. The follow-up Super Saw SYNC correction described below changes engine behavior; preset bytes, reconstructed velocities, and EQ are unchanged by that correction.

**Corrected result:** the inspected Roland resources establish Cotton Wool's waveform IDs, mixer bytes and displayed coarse values. They do **not** establish that those displayed values are physical semitones independently of WIDE. The [Cotton/Pedal recording audit](cotton-tuning-audit.md) supports a one-octave oscillator interval with WIDE off, where the earlier literal conversion produced three octaves. This explains much of the excess sub-bass previously attributed to unresolved oscillator levels or recording processing. Triangle harmonic content and nonclassic oscillator sync remain measurement questions.

## Public sources and retained originals

Research files are outside the repository at `/tmp/septum-hw-benchmark/research-official/`, abbreviated `research/` below. These local paths are evidence retained for this session, not required build inputs.

| Original source | Local original | SHA-256 |
|---|---|---|
| [Roland Editor 1.10 Mac disk image](https://static.roland.com/assets/media/dmg/SH201_Editor110_osx.dmg), linked by [Roland support](https://www.roland.com/global/support/by_product/sh-201/updates_drivers/abf3343d-8110-4f36-8175-7511fb58dd71/) | `research/SH201_Editor110_osx.dmg` | `4552fd6d51c184b876fb1522108cee95abce604c90ca0299b4f55fc01a555e86` |
| [English Owner's Manual](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf) | `/tmp/septum-hardware-fidelity/owners.pdf` | `b4a2968d429c7f3e907a6243723d5e803ae2e0014e8e9107c85bd966deea8e79` |
| [Japanese Owner's Manual](https://static.roland.com/jp/media/pdf/SH-201_j1.pdf), linked by [Roland Japan](https://www.roland.com/jp/support/by_product/sh-201/owners_manuals/8ce14ef7-cdb3-4b40-8ee8-1e2c0cfbe851/) | `research/SH-201_j1.pdf` | `e1d9fbe7aec8fd082308e8ce8313a534882a06470a319f0dc5d7e18a6a59a965` |
| [MIDI Implementation](https://static.roland.com/assets/media/pdf/SH-201_MI.pdf) | `research/SH-201_MI.pdf` | `71a8fe00a8d232c494a5aba6885756d99e6650fc14671115260d9446c3009546` |
| [Patch 100 PAD bank](https://www.rolandus.com/go/sh-201_patches/shl/SH-201_Patch_PAD.zip), linked by [PAD page](https://www.rolandus.com/go/sh-201_patches/patch_pad.html) | `research/SH-201_Patch_PAD.zip`; member `SH-201_Patch_PAD/100_PAD.shl` | `d00b19491c2cec27ee640147e0dfb6d1b8a47bcb70831a93a819a70d21a2a222` |

The editor image was mounted read-only, its `SH2Script.pax.gz` inspected, and then detached; no installer was executed. Original XML resources copied from `Roland/SH-201 Editor/Script/` are under `research/editor-resources/`:

| Resource | SHA-256 of original bytes | Relevant reading-copy location |
|---|---|---|
| `BufferModel.xml` | `e8b51e54b397eb1715a05a2efa52e984e1d7cd4929e071ded58d30b022c313d5` | `BufferModel.xml.utf8.txt`, lines 498–635 |
| `PatchOsc.xml` | `d7fd3106d0f1d3bd612185ef52c369cfd5d8dac3882fb98700cd4bf35483e164` | `PatchOsc.xml.utf8.txt`, lines 141–169, 189–339 |
| `Resource.xml` | `e609e52d8006023946754668c5a313168e0d69e07154dcd0a19d40c13ef84840` | `Resource.xml.utf8.txt`, lines 522–523, 910–912 |

Reading copies normalize encoding and line endings; hashes above identify the untouched originals. These are public editor resources, not DSP firmware or leaked ROM code.

## Cotton Wool byte interpretation

PAD record 1 is `Cotton Wool`, single Upper. Offsets below are hexadecimal within its Upper tone block. The editor model supplies the wire ranges; the editor controls supply displayed offsets and waveform IDs. MIDI Implementation p. 5 independently lists these tone fields.

| Field / offset | Published raw value | Interpretation and evidence |
|---|---:|---|
| OSC1 waveform / `00` | 7 | Super Saw, waveform table/button ID 7 |
| OSC1 coarse/fine / `02–03` | 64 / 64 | Coarse display 0, fine 0 cents; displayed values subtract 64 |
| OSC1 PW / `04` | 41 | Super Saw spread input; precise spread curve is undocumented |
| OSC2 waveform / `06` | 4 | Sine, waveform table/button ID 4 |
| OSC2 WIDE/coarse/fine / `07–09` | 0 / 28 / 57 | WIDE off, signed coarse display −36, fine −7 cents; recording evidence supports −12 physical semitones for this coarse endpoint |
| OSC2 PW / `0A` | 64 | No sine-wave effect |
| MIX type / `0E` | 0 | MIX |
| BALANCE / `0F` | 64 | Center; displayed value subtracts 64 |
| LOW FREQ / `10` | 0 | FLAT; editor table `1,0,2` changes visual ordering, not wire meaning |

Owner's Manual pp. 29–30 describes the normal one-octave and WIDE three-octave PITCH-knob ranges; p. 60 identifies its parameter table as Editor display values. The editor's coarse range is 28–100 and its displayed value is raw minus 64. The XML describes that display binding, not the DSP conversion from coarse plus WIDE to physical pitch. PW affects pulse, feedback, and Super Saw; p. 33 describes mixer endpoints and LOW FREQ choices. None supplies a numeric center-mix or relative waveform-gain law.

The earlier assertion that dividing the signed coarse value by three with WIDE off would contradict the Editor resources was incorrect. Agreement between the importer and renderer only proved that both used the same literal interpretation. Cotton Wool and Pedal Bs 1 support signed endpoint −36 corresponding to physical −12 semitones in normal mode; the independent [SupaJuce 1 recording](https://www.rolandus.com/go/sh-201_patches/mp3/LEAD/TOP8_SupaJuce1.mp3), with two square oscillators, supports a one-octave interval for its WIDE-off +36 endpoint. Combined with the documented knob ranges, this supports WIDE-dependent pitch conversion. It does not determine every interior control step or authenticate the original performance MIDI. The waveform-ID and LOW FREQ interpretations remain supported: ID 4 is sine, and LOW FREQ 0 is FLAT.

**Historical measurement, using the old literal-coarse mapping:** at the then-reconstructed MIDI notes 51, 53 and 57, the renderer predicted sine frequencies 19.367, 21.739 and 27.389 Hz; its first-five-second Welch spectrum had peaks near 19.51, 21.87 and 27.42 Hz. Those numbers correctly describe that render, not the hardware's tuning law. The later [recording audit](cotton-tuning-audit.md) identifies a low sine and Super Saw approximately one octave apart and also revises the reconstructed Cotton note octave. Correcting those two assumptions removes most of the excess sub-bass without changing oscillator balance or adding EQ. Remaining waveform levels, filter response, velocities and capture processing are still uncalibrated.

## Triangle wording

English manual p. 28 assigns even harmonics to triangle. Japanese p. 28 also uses `偶数倍` (even multiples); the rendered page was checked, so this is not an English-only translation or extraction error. A mathematically symmetric triangle has odd harmonics. Neither manual provides a measured SH-201 triangle spectrum. **Do not change the triangle generator to implement this inconsistent prose.** A dry single-oscillator recording with filter bypass and effects off would settle the actual waveform.

## SYNC waveform restrictions

Both manuals' p. 32 describe OSC1 restarting with OSC2's period and state no waveform exclusions. `PatchOsc.xml` also provides no waveform-dependent condition on the MIX/SYNC/RING control. Before this correction, `Engine::renderVoiceTick()` excluded Super Saw, FB OSC, noise and external input as OSC1 sync targets, while accepting them on OSC2. This asymmetry is not established by the inspected Roland text.

An independent bank scan using `Tools/extract_reference_patch.py` found 50 active-tone SYNC configurations across the four Patch 100 banks and 32-patch Artist bank (432 patches). It counts the selected tone in Single mode and both tones in Dual/Split. Of these configurations, 22 have nonclassic OSC1 and 19 have nonclassic OSC2. Examples:

| Bank / record / name | Active configuration |
|---|---|
| LEAD / 20 / `Super Sync` | Both tones: Super Saw → Super Saw; balances 0 and −13 |
| PAD / 27 / `ReverseMetal` | Lower: FB OSC → saw; balance −63 |
| FX / 54 / `Head Spinner` | Upper: noise → FB OSC; balance +40 |
| BASS / 37 / `UKDub` | Lower: sine → external input; balance −63 |

Here arrows denote OSC1 → OSC2 assignments, not signal direction. Patch 100 URLs/hashes are in [the source catalog](../hardware-reference-catalog.json). The [Artist bank](https://www.rolandus.com/go/sh-201_patches/shl/SH-201_Artist_Patch.zip) is linked by [Roland's patch page](https://www.rolandus.com/go/sh-201_patches/) and has SHA-256 `628b8fd3751c1fbfa59701ffd186c00a143312651ac21b5c8da1fa9b7e8fae74`. Scan results remain at `research/published-sync-configurations.json`, SHA-256 `fa3424ff85bf999937cb944df611672ebcf57c8e1264cd07ea51d44bd4c7de9d`.

A [Roland Clan owner's post](https://forums.rolandclan.com/viewtopic.php?f=67&p=342087&t=69787) explicitly reports Super Saw oscillator sync working on their SH-201. This was observed in the search-index excerpt; direct page retrieval returned HTTP 429. The post provides no patch, recording, oscillator assignment, or reset topology, and is only a supporting research lead.

Stored settings show that these combinations are used in published presets; they do not prove that hardware audibly applies every selected combination. The owner's report also does not distinguish Super Saw as OSC1 from OSC2.

### Implemented correction and remaining uncertainty

The combined evidence favors restoring an audible OSC1 Super Saw SYNC path over the unconditional bypass. `Super Sync` is especially suggestive: its Upper oscillator coarse fields have signed raw/display values +26 and −36, with PW 64 on both. These are not physical semitone claims; physical pitch also depends on WIDE and its conversion. This is a functional-support inference; an exact Roland seven-phase reset algorithm has not been established.

Resetting only the center saw and resetting all seven are materially different choices. With Septum's current gains, the center accounts for approximately 13.9% of an incoherent stack's power before the common high-pass. A center-only reset leaves most of that stack freely detuned. Resetting all seven makes the complete stack repeat on the master's period under constant controls. Neither the source material nor a preset name determines which topology hardware uses.

The correction resets all seven phases to a shared cycle origin, preserves each saw's detuned increment, and preserves the downstream HPF state. It compensates for the sub-sample master wrap before the existing oscillator advance: `phase[i] = frac((wrapOffset - 1) * detunedIncrement[i])`. This reset topology is **voiced / pending hardware measurement**, alongside the already modeled center-saw master trigger. Feedback, noise, and external-input behavior is unchanged.

`HardwareVoiceFidelityTests.cpp` checks SYNC versus MIX with classic and Super Saw masters, three noninteger pitch ratios, two spread settings, and three sample rates. Irregular process blocks preserve the settled output and all output stays finite. A closed-form ramp identity checks fractional wrap timing and HPF-state continuity when every detuned slave runs below its master. These are implementation contracts, not hardware waveform snapshots. A hardware A/B of MIX and SYNC with one isolated Super Saw, fixed note/velocity and effects off remains the decisive validation.

Validation: 285 voice-fidelity checks pass and the existing `Septum.Engine` suite passes. Isolated scratch builds reintroducing the bypass fail 39 checks; rounding the reset to a whole sample fails the fractional-timing check at 44.1 and 48 kHz. Neither mutation touched shipping sources.
