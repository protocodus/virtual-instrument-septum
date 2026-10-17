# deep!sonic capture-chain and waveform-control search

**New evidence: an original studio routing table and four same-collection comparator recordings. No session-specific SH-201 capture calibration or independent controlled SH-201 saw/pulse/sine capture was recovered.** This source-only audit does not attribute the measured high-frequency notch to an oscillator, filter, converter, or capture process. No DSP changed, and no comparator spectrum was fitted or used to choose a correction.

## Original routing evidence, with a date mismatch

The creator’s [studio page](https://www.deepsonic.ch/deep/htm/deepsonic_studio.php) links an [audio/MIDI connection PDF](https://www.deepsonic.ch/deep/docs_misc/deepsonic_studio_-_connections_current.pdf#page=3). Its internal heading and print date are **4 January 2020**, although the page labels the link 12 February 2020. Page 3 was rendered and inspected. It lists:

| SH-201 connection | Documented destination/source |
|---|---|
| L/Mono output | MOTU 24 I/O unit 1, input 21 |
| R output | MOTU 24 I/O unit 1, input 22 |
| Filter input L/R | MOTU 24 I/O unit 1, outputs 21/22 |
| MIDI input/output | Emagic AMT8 unit 1, port 7 |

These are explicit analog output connections, not USB audio connections. **They describe that documented setup, not necessarily the filter recordings.** All six previously acquired SH-201 filter MP3s have ID3 year **2010**. The routing PDF gives no recording sample rate, input gain, software channel routing, mono-conversion method, resampler, or loopback response associated with those files. Its SHA-256 is `dadd86c4924ac60d255e94c8ce885db60857f720092245d8ed20fcf4a5874069`.

The author’s [MOTU page](https://www.deepsonic.ch/deep/htm/motu.php) labels 24 I/O photographs from 2007 and 2009, establishing a relevant equipment-history lead. The older [18 January 2007 routing document](https://www.deepsonic.ch/deep/docs_misc/deepsonic_studio_-_connections_2007.txt) instead describes a Soundcraft mixer and M-Audio Delta44 capture paths, with optional master EQ, and contains no SH-201 entry. Neither dates the actual 2010 session. Thus a general statement that the site always used one capture chain would be unsupported.

## Four new comparator recordings from the 2010 collection

The original [filter comparison page](https://www.deepsonic.ch/deep/htm/deepsonic_analytics_filter_comparison.php) links these recordings under its common one-saw, no-effects/modulation recipe and original MIDI procedure. All four files fully decode as **mono 44.1 kHz, 320 kbit/s MP3, 30.0182 seconds container duration**. They share the album tag `filter-demos @ deepsonic.ch`, artist `dr.squ`, and year `2010` with SH-201.

| Comparator | Original download | Purpose of a later comparison |
|---|---|---|
| AAS Tassmann 4 VSTi, LPF2Pole Q000 | [MP3](https://www.deepsonic.ch/deep/audio_filter/aas_tassmann_4_vsti_-_filter_demo_-_lpf2pole_q000.mp3) | Software-source contrast; not an authenticated analog loopback |
| Access Virus C, LPF12 Q000 | [MP3](https://www.deepsonic.ch/deep/audio_filter/access_virus_c_-_filter_demo_-_lpf12_q000.mp3) | Other VA saw through an active filter |
| Clavia Nord Modular KB, LPF12 Q000 | [MP3](https://www.deepsonic.ch/deep/audio_filter/clavia_nord_modular_kb_-_filter_demo_-_lpf12_q000.mp3) | Second VA saw/filter implementation |
| Roland Juno-106, LPF Q000 | [MP3](https://www.deepsonic.ch/deep/audio_filter/roland_juno-106_-_filter_demo_-_lpf_q000.mp3) | Analog-instrument contrast |

These are **procedurally described** saw recordings, not measured ideal saws or byte-authenticated patches. The common MIDI contains the high-note sequence used in the SH-201 analysis, but the procedure permits octave transposition; actual comparator pitch and alignment must be verified before measuring those windows. No same-day/session, identical converter channel, or identical processing history is established by common tags. The 2020 routing table places Virus, Nord and Juno on MOTU unit 2, while SH-201 is on unit 1.

They are useful negative controls for a proposed **collection-wide** coloration: a repeated fixed-frequency notch across unrelated instruments could motivate a shared-path investigation; its absence would argue against applying that notch as a blanket site-capture EQ. Neither outcome alone identifies or excludes a SH-201-specific capture error. Their own oscillator and active-filter responses remain confounds. No notch presence/absence is claimed in this source inventory.

Originals and native float32 WAV decodes are cached in `build-fidelity/public-waveforms/deepsonic-capture-chain-2026-09-15/comparators/`. Complete file hashes and decode commands are in the [receipt](deepsonic-capture-chain-controls-2026-09-15.json).

## Additional SH-201 media and excluded leads

The creator’s [SH-201 page](https://www.deepsonic.ch/deep/htm/roland_sh-201.php) supplies two newly acquired originals:

- [Filterinput](https://www.deepsonic.ch/deep/audio_filter/roland_sh-201_-_filter_demo_-_filterinput.mp3): 220.9457 seconds, stereo 44.1 kHz/320 kbit/s, ID3 year 2012. Its embedded title explicitly identifies an **external loop**. The original dry loop, filter settings, switch transitions and source path are not supplied, so it is not a known-input transfer reference.
- [Impressions](https://www.deepsonic.ch/deep/audio_equipment/roland_sh-201_-_sounds_demo_-_impressions.mp3): 1183.8134 seconds, stereo 44.1 kHz/320 kbit/s, ID3 year 2009. No time-indexed patch, raw dump or performance recipe accompanies it. It remains an unannotated original audition, not an isolated-waveform benchmark.

Both complete files decode without reported errors. This pass inspected source associations and metadata; it did not reconstruct their performances or classify every audio passage. Their hashes identify the acquired originals, not proof of a dry section.

The site’s [waveform page](https://www.deepsonic.ch/deep/htm/deepsonic_analytics_waveform.php) contains generic CD-rate sine illustrations, with no SH-201 capture or downloadable waveform data. Its [Synthesizer Pure collection](https://www.deepsonic.ch/deep/htm/deepsonic_analytics_synthesizer_pure.php) describes musical demonstrations and contains no SH-201 entry. A newly inspected [2007 first-person review](https://recording.de/threads/user-review-roland-sh-201.242424/) has controls/editor photographs, but no isolated waveform measurement or original MIDI/patch benchmark.

## Bounded result and reproduction

Eighteen targeted searches and the linked creator pages added routing history and comparison assets, but **did not recover a same-session known input/output pair, SH-201 USB-versus-analog comparison, raw pulse/sine capture, or calibration sweep**. Previously audited Evilsoft/MaxSynths, Trioda, AMAZONA, editor, firmware and manual leads were not acquired again. The existing SH-201 notch therefore remains an effective recorded response whose physical source is unresolved.

For reproduction, download each exact URL in the receipt to its recorded path, verify SHA-256, and run its retained FFmpeg decode command. MP3s stay at native rate/channels; no resampling, EQ or normalization was applied. The four comparator WAV hashes, six prior SH-201 MP3 metadata records, routing-page render hash, HTTP outcomes and search list are preserved. No original media is added to tracked source.
