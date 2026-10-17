# Factory-bank MIDI selection: conflicting sources

Reviewed 2026-09-14. Roland's two published tables disagree. The factory-recording catalogue uses the Owner's Manual's PRESET names and slots; it does not establish which incoming bank-select bytes a hardware unit accepts.

| Source | PRESET bank, decimal MSB / LSB | USER bank, decimal MSB / LSB |
|---|---:|---:|
| [SH-201 MIDI Implementation v1.00, March 1, 2006](https://cdn.roland.com/assets/media/pdf/SH-201_MI.pdf), p. 1 | 87 / 0 | 87 / 20 |
| [SH-201 Owner's Manual](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf), patch list, p. 84 | 87 / 64 | 87 / 0 |

Both sources list 32 programs per bank. Their printed program numbers 1–32 correspond to MIDI program bytes 0–31. This disagreement is not resolved by interpreting the MIDI Implementation's `020` as hexadecimal: neither decimal 20 nor decimal 32 matches the Owner's Manual's USER value 0.

An independent [Audio-Workshops device definition](https://github.com/hypercube-software/Audio-Workshops/blob/710d1bd8646adcdab706acac6424f8d3d3762445/devices-library/Roland/SH-201-presets.yml), inspected at commit `710d1bd8646adcdab706acac6424f8d3d3762445`, agrees with the Owner's Manual. Its PRESET identifiers run from hexadecimal `574000` to `57401F`, and its USER identifiers from `570000` to `57001F`. It contains names and selection identifiers, not patch parameters or a captured hardware transaction. Its USER list names the separately released Artist Patch Collection, so it is not an original factory USER-bank dump. This is useful corroboration, but it does not prove how the identifiers were verified.

## Current behavior and unresolved decision

Septum's `MidiBankSelect` currently follows the MIDI Implementation: explicit 87/0 selects its authored programs 0–31, and 87/20 selects its initialized user slots 32–63. Bare Program Change messages retain the flat 0–63 compatibility map. That runtime behavior remains unchanged in this task. The earlier [bank-selection audit](midi-bank-selection.md) describes that implementation but did not account for the conflicting Owner's Manual table.

Before changing the mapping, obtain a hardware MIDI trace or a verified editor/controller transaction demonstrating both PRESET and USER selection. In particular, LSB 0 cannot support both interpretations simultaneously. Adding aliases would not resolve that conflict.

## Factory-library integration once verified data is available

Authentic patch bytes are still required; patch names and recordings do not supply the parameter bank. A compatible implementation can append the 32 PRESET patches at host indices 64–95, show them first in the menu, and select index 64 for new instances. Existing program indices 0–63 and INIT parameter defaults can remain stable. Explicit bank routing must wait for the mapping decision above.

Every imported factory patch must pass checksum and complete 22-block coverage checks. Program loading must preserve its exact arpeggio grid using the existing guarded grid-publication path: the current program writers discard imported grids, and subsequent snapshots reconstruct Septum's original template from the selector. Replacing the global template list would also change legacy sounds and saved sessions.

The bank should initialize before audio processing. The current seven-bit staged program encoding accommodates 96 programs, but not 128. Finally, processor snapshots currently use the name `INIT PATCH` for SysEx export; the bank's own patch objects preserve their names, but claiming byte-identical plug-in exports also requires preserving patch-name state through selection, edits and session restoration.
