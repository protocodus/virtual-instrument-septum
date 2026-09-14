# Search for exact SH-201 recording inputs

On 14 September 2026, the follow-up search found **zero verified complete
sets** containing all three of the following:

1. A real SH-201 hardware recording.
2. The original performed MIDI used for that recording, including note timing,
   velocity and controllers.
3. The exact SysEx preset used for that recording, with a source establishing
   their association.

This is the result of the inspected public sources, not proof that such files
do not exist. The existing ten comparisons contain estimated MIDI and remain
excluded from this stricter set. A byte-exact copy of a published preset does
not establish that the recording used that exact revision.

## Different sources checked

| Source | Evidence found | Missing qualification |
| --- | --- | --- |
| [Roland product audio library](https://www.roland.com/global/products/sh-201/) | Parsed public HTML contains 18 MP3 links: 17 patch demos and the Scott Tibbs song | No linked original MIDI or recording-specific preset dumps |
| [Artist collection / Catharsis](https://www.rolandus.com/go/sh-201_patches/) | Demo associated with Jordan Rudess's artist bank | No original performance export found; title matches elsewhere do not establish the same take |
| [Final Bossa creator page](https://www.newgrounds.com/audio/listen/1480881) | Creator says the original Logic project was preserved and identifies SH-201 use | Only the mixed song is public; no project, isolated SH-201 take, MIDI or preset dump supplied |
| [LFOstore Analog Dreams](https://lfo.sellfy.store/p/roland-sh-201-analog-dreams-soundset-32-presets/) | Different soundset advertises SysEx presets and a hardware demo | Original performance MIDI is not advertised; paid archive was not purchased or inspected |
| [ILJah's original recordings](https://freesound.org/people/ILJah/packs/20668/) | Three author-described SH-201 WAVs, including two chord recordings and an arpeggio | No original MIDI or preset data linked; BPM tags are insufficient |
| [Ryuno sample pack](https://audiobombs.com/items/674/sound-design-pack-vol.1-by-ryuno-) | WAV one-shots advertised | No MIDI/SysEx advertised; archive requires an account and was not inspected |
| [Bluezone Altered Zone](https://www.bluezone-corporation.com/packs/altered-zone-dark-ambient-samples) | Processed WAV/AIFF samples sourced from several synths | No exact SH-201 session inputs supplied |
| [SH201Librarian](https://github.com/r-b-g-b/SH201Librarian) and [pdsh201](https://github.com/becks/pdsh201) | Repository trees inspected: backup/control code | No audio, original performance MIDI or paired preset dataset |

Legacy official FX and Synthesizer 101 materials were also checked. The FX
archive contains a librarian bank and patch-list PDF; the course is a
programming guide. Neither provides the required performance files. These
are archive-content checks, not assumptions based on filename extensions.

## Search coverage and limits

The search covered official and legacy product pages, artist/demo titles,
creator DAW projects and sample packs, GitHub repositories, Hugging Face,
Zenodo and search-engine queries restricted to OSF. Queries combined SH-201
and SH201 with MIDI, SysEx, WAV, stems, project files, Ableton, Cubase, Logic,
dataset, corpus, sample pack, demo song and Japanese demo-data terms.

Hugging Face's exact model-name API searches returned no datasets. The
successful exact Zenodo query found only an unrelated taxonomy record.
Follow-up Zenodo queries and the OSF API timed out; those are incomplete
checks, not negative results. The project's own GitHub repository appeared
in search and was excluded as an independent hardware source.

No estimated notes, assumed factory patches, patch-only MIDI containers or
newly synthesized audio were admitted as exact input data. No new exact-input
A/B renders were produced. The most promising next route is obtaining a
creator's original session exports or commissioning a documented hardware
capture. No creator has been contacted.

Detailed search notes and the official HTML/archive inspection are retained
locally in `build-fidelity/hardware-benchmark/exact-source-search-2026-09-14/`.
