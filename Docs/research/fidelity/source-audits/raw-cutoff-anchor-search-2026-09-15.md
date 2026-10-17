# Independent raw-cutoff anchor search

2026-09-15. **No independent SH-201 raw-cutoff-to-frequency anchor was recovered in this bounded pass.** Sixteen targeted searches covered English, Japanese, German, French and Russian, followed by inspection of two new primary leads. Existing editor/service/filter audits were read first; firmware archives, factory presets and patents were not searched again. No DSP changed.

## New leads and their limits

### Japanese owner's sound-design description

[misutrax's original owner article](https://note.com/microlab/n/nc7898a7ed946), published 13 January 2022, describes making a SuperSaw patch. The author uses modest resonance and LP24, seeking a position that emphasizes roughly 1–4 kHz. This is an approximate sound-design target: the article supplies no raw cutoff value, instrument measurement method, complete patch or frequency plot. It cannot associate a specific control byte with a measured frequency.

Its [linked 23-second video](https://www.youtube.com/watch?v=IipRHyJH7Ds) is titled *Roland SH-201 SUPERSAW 2x*. Public metadata gives uploader Synthwave-jp8k, description `#shorts`, and no captions. Metadata acquisition revealed no patch recipe. Video content was not analyzed or downloaded in this pass, so no visual parameter claim is made.

### Author-published SH-201 controller specification

The [MIDI Mod author's parameter list](https://eokuwwy.blogspot.com/2019/05/device-parameter-mapping-list.html) and [app guide](https://eokuwwy.blogspot.com/2019/07/midi-mod-for-ipad.html) led to an original public JSON specification. The [pinned SH-201 file](https://github.com/eokuwwy/open-midi-rtc-specs/blob/b7080441427d74a50c3dfda0f107f0215bc11c49/specs/0.0.1/json/sh-201.json) defines:

| Parameter | CC | Value range |
|---|---:|---:|
| Upper Filter Cutoff | 74 | 0–127 |
| Lower Filter Cutoff | 102 | 0–127 |
| Audio Filter Cutoff | 2 | 0–127 |

There is no physical-Hz conversion or measured cutoff table in this file. This is primary evidence for the controller author's routing configuration, not manufacturer-authenticated DSP code. The author's app supports MIDI control; its own LFO/time specifications must not be attributed to SH-201.

## Feasibility result

The existing [parameter audit](cutoff-parameter-audit.md) remains unchanged: official editor fields bind cutoff directly to raw 0–127, and the synthesis guide gives knob-position exercises rather than physical calibration. The [service/editor audit](2026-09-15-new-sources.md) and [filter investigation](filter-envelope-conditional-fit.md) already examined service tests without finding a filter-frequency calibration table. The service search again surfaced those same control/audio tests, not a new calibration document.

This search did not yield a new independent endpoint or interior cutoff anchor. Its failure is bounded; it does not prove no public measurement exists. The current audio-derived cutoff estimates therefore remain conditional on their source, patch and filter assumptions. Values from JP-8000, V-Synth, Gaia or another product provide no new SH-201 law here.

[The companion receipt](raw-cutoff-anchor-search-2026-09-15.json) records all 16 queries, exact URLs, retrieval limits and five acquired-file hashes. Cached material is under ignored `build-fidelity/public-waveforms/raw-cutoff-search/`. No accounts, purchases, contact or media downloads were used.
