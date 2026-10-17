# Alternate cached reference audit — 20 September 2026

No new calibration passage was admitted from this bounded local inspection outside the 32 named Patch 100 recordings. The two strongest cached collections below lack independently established recorded settings. This does not claim that no suitable public recording exists. No network search, new transcription, audio-based patch identification or production change was made.

The [machine-readable audit](alternate-reference-cache-audit-2026-09-20.json) retains source URLs, archive/member hashes, metadata results and reproduction methods. Referenced source files remain in the ignored local cache.

## Reviewer collection: numbered recordings without a preset map

[Pier Calderan's SH-201 review download](https://www.calderan.info/downloads.asp?id=44) is catalogued as 32 preset demonstrations with arpeggios. The cached ZIP was opened again: it contains exactly 32 MP3 files, `sh-201-000.mp3` through `sh-201-031.mp3`, and no settings, MIDI or explanatory document. All member hashes match the existing catalog. The ZIP and every member have empty comments; `ffprobe` finds no format or stream tags in any recording.

The archive therefore adds no independent per-file preset association. In particular, numbering alone cannot establish that file 031 is PRESET D-8/INIT or a dry oscillator. Finding a similar-sounding factory recreation would not establish that identity either. A primary-source file-to-preset map plus authenticated settings is the next useful evidence; detailed spectral work before that would still fit an unknown patch.

## Official Fat Bass demo: a known name, conflicting candidate settings

The cached [Roland product page](https://www.roland.com/global/products/sh-201/) explicitly labels its [Fat Bass recording](https://static.roland.com/assets/media/mp3/sh_201_fat_bass.mp3). Its title matches PRESET B-1 in the Owner's Manual. The product HTML, manual and MP3 hashes were checked against the existing factory catalog.

The cached [Nutrient community collection](https://www.rolandclan.com/media/20/Nutrient_collection.zip) contains 123 SHE files and no other non-directory files. Three files embed the name `Fat Bass`. Two share the same apparent 1,240-byte patch region; the third differs in 35 bytes. This freshly reproduces the earlier name-collision finding. It does not certify the SHE layout or which, if either, contains original factory settings.

Nothing in the archive connects those bytes to Roland's recording. Exact recorded revision, live controls, original performance MIDI and dry output remain unverified. Selecting whichever community variant fits the MP3 best would be patch fitting, not independent DSP calibration. An authenticated PRESET B-1 dump would improve the patch hypothesis, but evidence linking that state to the recorded take would still be needed. A documented new capture with the dump and performance MIDI would supply a stronger reference.

## Other local leads

The existing [RCS byte audit](rcs-shl-smf-byte-audit.json) has the strongest external patch provenance: eight author-paired SHL/SMF patches. All SMFs contain zero note events; they transfer settings. No source-labelled recording passage was available in the inspected local cache. The useful next step is to inspect the author's demo for an explicit patch-to-passage association, then label any reconstructed notes as estimates.

Roland's cached Synthesizer 101 course explicitly selects PRESET D-8 and describes its OSC 1 saw wave. That is a documented exercise, but no associated cached recording supplies a measured dry waveform. The course cannot substitute for recorded hardware.
