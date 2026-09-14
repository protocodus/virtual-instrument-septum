# Factory bank acquisition: second pass

Date: 2026-09-14. Result so far: no authenticated SH-201 factory PRESET parameter bank acquired. This is a record of bounded searches and access limitations, not a claim that no public copy exists.

## Public owner archives and code search

The [RolandClan SH-201 index](https://forums.rolandclan.com/viewforum.php?f=26) and indexed discussions were searched for factory/original patches, backups, dumps, SHL files and preset downloads. Direct index requests returned HTTP 406 or timed out. The indexed [bulk-dump discussion](https://forums.rolandclan.com/viewtopic.php?t=57283) contains request-command guidance and a tutorial link, rather than factory patch bytes. Factory-reset instructions elsewhere likewise do not supply the preset data. The previously examined ACPC and RolandClan library leads are retained in the [first audit](factory-bank-search.json).

Authenticated GitHub code search returned no files for `"SH201" extension:syx` or `SH-201 extension:shl`. Exact `"SilkyStrings"` search returned six results, of which the relevant SH-201 file was the already-known [Audio-Workshops name/program list](https://github.com/hypercube-software/Audio-Workshops/blob/710d1bd8646adcdab706acac6424f8d3d3762445/devices-library/Roland/SH-201-presets.yml). It contains no parameter dump. `"Reso Bass"` returned many unrelated instruments; inspecting the first 50 results found no SH-201 factory payload. Search indexing and page limits constrain these negative results.

An Internet Archive metadata search for `"SH-201"` returned 41 items, including manuals, music and the previously identified Vacyd custom soundset. No result identified a factory bank or original installation-disc image. This was a metadata search, not an inspection of every item's binary contents.

The legacy Google Drive folder linked by Techies Expedition was also checked through a browser. It redirects to Google sign-in and exposes no file inventory without access. No account access or permission bypass was attempted. The surrounding post advertises documents, software and a mixer map; it does not independently establish that factory patches are present.

## Editor and librarian leads

The [AURA JP-80x0 editor](https://auraplugins.com/product/roland-jp-80x0-editor/) advertises SH-201 SHL/SHE import and conversion. Its advertised bundled factory banks are JP-8080 banks. The public Mac demo download returned a No Access page, so archive contents could not be inspected. Import capability alone is not evidence of bundled SH-201 presets.

The [Midi Quest 13 supported instruments](https://squest.com/Products/MidiQuest13/Instruments.html) and [beta modules](https://squest.com/Products/MidiQuest13/InstrumentsBeta.html) have no SH-201 entry. Related SH-01, SH-01A and SH-32 entries do not establish SH-201 support or available factory data.

The earlier official Mac Editor inspection found INIT defaults and editor resources without a complete factory bank; its exact scope and hashes remain in the first audit.

The official [Windows Editor 1.10 download](https://www.roland.com/global/support/by_product/sh-201/updates_drivers/a5c46ba1-90be-419c-ab49-8dc141bafa78/) was successfully retrieved and unpacked. The payload `SH201Editor110_E.EXE` is 9,800,667 bytes, SHA-256 `dbcfe7a754447ccd96a52bd32dd7cd892a96274c506e7d918200cc62936e97e3`. Inspection covered all 26 outer LHA members and 112 inner CAB members. Its sole SHL bank, `Artist_Patch_Lib.shl`, is explicitly documented as 32 additional artist sounds, not the factory PRESET bank. All 25 queried factory names were absent from ASCII and UTF-16 searches of the decompressed members; INIT PATCH was present as a control. This bounded inspection found no authenticated factory data. No downloaded software was executed.

Detailed local evidence for these checks is retained under `build-fidelity/hardware-benchmark/factory-bank-research/second-pass/`, including `roland-clan-forum-audit.md`, `aura-midiquest-audit.md`, `windows-editor-audit.md` and both Windows archive-member hash inventories.

## Remaining actionable input

A complete export of all 32 read-only PRESET slots from an SH-201 owner would supply the missing data without reconstructing the patches by ear. Request the original librarian bank or full SysEx, exact slot order, device/firmware details if known, and confirmation that the source is PRESET A-1 through D-8. Do not ask the owner to factory-reset their USER bank. Patch names alone, program-change commands and edited community variants cannot authenticate those parameters.

No owner or vendor has been contacted. The 17 newly authored software patches remain explicitly approximate and have not been installed as Roland's default factory bank.
