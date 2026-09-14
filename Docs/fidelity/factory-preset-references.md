# SH-201 factory preset references

Research date: 2026-09-14.

**17 official factory-name recordings are available locally. The authentic factory default bank is not implemented: no complete, verifiable factory patch dump was obtained.** Septum's existing 32 original sounds and 32 initialized USER slots remain unchanged. They are not Roland factory presets.

The [listening page](http://127.0.0.1:8916/) contains 7m28s of original Roland MP3s. The [source catalog](factory-recordings.json) records each URL, SHA-256 hash, duration, factory slot, and MIDI/preset provenance. Audio lives under `build-fidelity/hardware-benchmark/factory-bank-research/recordings/` and is not committed.

## What is verified

All 17 demo titles in [Roland's SH-201 audio library](https://www.roland.com/global/products/sh-201/) match PRESET entries in the [Owner's Manual, p.84](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf). This is a different collection from the additional Patch 100 sounds used in the [previous ten-recording A/B set](ten-recording-ab.md).

| PRESET slot | Recording |
|---|---|
| A-1 | Reso Bass |
| A-2 | Fat Saw Lead |
| A-3 | SilkyStrings |
| A-5 | OSC SyncLead |
| A-6 | SuperSawBrs |
| A-7 | Electro Seq |
| B-1 | Fat Bass |
| B-4 | SuperSawKey |
| B-5 | FB OSC Lead |
| B-6 | Poly Synth |
| B-7 | Sweep Arp |
| C-4 | SH-201 EP |
| C-5 | Sweep Up |
| C-6 | Trancy 201 |
| C-7 | Sliced Pd/Bs |
| D-5 | JP-8SweepPad |
| D-7 | S&H FX 2 |

**Performance MIDI: unavailable for all 17. Exact MIDI: 0. Estimated MIDI files: 0.** No software render is presented as a matched A/B. The published names establish the intended factory sound, but do not verify the actual patch bytes, live control changes, effects, or mastering used in a recording. These are lossy stereo MP3 references, not confirmed dry captures.

## Why the default bank is still missing

The official Editor 1.10 distribution and public patch archives were inspected. Additional designer banks are available, but none of the acquired files establishes the complete, untouched PRESET A-1 through D-8 bank.

- Roland's downloadable Artist and Patch 100 collections contain additional sounds. They are not the built-in factory bank.
- The [Roland Clan library](https://www.rolandclan.com/library/sh-201/) supplies Lello, Synthdesign, Roland additional collections, and a Nutrient collection. Nutrient has 123 SHE files, including 26 files whose embedded names match 15 factory names. Several same-name files have different parameter payloads. Two `JP-8 SoftPAD` variants differ in 44 parameter bytes; `Sweep Arp` variants differ in 265. A matching name cannot identify which version, if any, is untouched factory data.
- The official [Mac Editor 1.10 archive](https://static.roland.com/assets/media/dmg/SH201_Editor110_osx.dmg) provides INIT parameter defaults and editor resources. The inspected archive inventory contains no complete factory bank. A scan for representative factory names in its resources and executables found no bank data; this is a bounded inspection, not a proof that all possible encodings were exhausted. No installer or downloaded executable was run.
- A creator's legacy SH-201 Drive archive now requires sign-in. The other checked legacy paths were unavailable or contained additional sounds. Public editor repositories yielded control code or patch-name lists, not factory parameter dumps.

The [source audit](source-audits/factory-bank-search.json) retains archive hashes, candidate-name collisions, unavailable leads, and the scope of the inspection. All downloaded candidate files remain in the ignored research folder, outside the software's default bank.

## Bank selection discrepancy

Roland's publications disagree: the Owner's Manual p.84 lists PRESET as MSB87/LSB64 and USER as MSB87/LSB0; the [MIDI Implementation](https://static.roland.com/assets/media/pdf/SH-201_MI.pdf), pp.1 and 3, lists PRESET87/0 and USER87/20. The catalog records the Owner's Manual values with their source and this limitation. No hardware capture resolves the conflict, and this task does not change Septum's existing MIDI bank behavior. See the [bank-selection audit](source-audits/factory-midi-bank-select.md).

## Completing the software bank

The missing input is a complete factory PRESET export with credible provenance: an official bank file, or an owner export of all 32 read-only PRESET slots without editing. Each patch needs its full parameter and arpeggio data, not only a name or MIDI program change. Factory USER contains a separate set of 32 sounds and must not be substituted for PRESET.

Once acquired, validate complete block coverage and Roland checksums, retain the source bytes and hashes, and check all slot names. Append the 32 presets after the existing 64 host program IDs to preserve old sessions, present the Roland bank first in the menu, and select its first sound for new instances. Program loading must preserve each imported arpeggio grid. The original demo performances would still require separately recovered or explicitly estimated MIDI; acquiring a factory bank alone would not make their performance MIDI exact.

## Rebuild and validation

With the cataloged MP3s present, run:

```sh
python3 Tools/build_factory_reference_page.py
python3 -m http.server 8916 --bind 127.0.0.1 --directory build-fidelity/hardware-benchmark/factory-bank-research
```

The builder verifies every source file's size and SHA-256 before writing the page. All 17 MP3s were fully decoded successfully with FFmpeg. All 18 local audio/catalog links resolved; browser playback and page layout were checked. Detailed local results are in `build-fidelity/hardware-benchmark/factory-bank-research/player-validation.json`.
