# Public waveform recovery follow-up

2026-09-15. **New original-source assets recovered; no isolated oscillator or
long dry-envelope benchmark with known settings recovered.** These sources
support further diagnostics, not an immediate DSP correction.

## New scope captures from a physical SH-201

[Romekd's Trioda post](https://forum-trioda.pl/viewtopic.php?t=39199), published
15 October 2022, describes measurements on a friend's SH-201. Its attachments
remain publicly downloadable: two setup photographs and 17 Rigol scope
screenshots. The setup photographs visibly identify the Roland SH-201 and
Rigol instrument. The scope captures show a 7 February 2022 timestamp.

The author reports disabling keyboard dynamics, without specifying a raw
velocity. He distinguishes two observations: each new keypress produces a
different composite shape; the relative phase also moves while both A440/A880
keys remain held. The December follow-up says it takes roughly a dozen or
severalteen seconds of holding to notice this motion. This concerns two notes
from the SH-201, not phase relative to an external generator. It does not give
the duration of a complete phase cycle.

The first scope image is approximately sinusoidal. The original HTML places
DS1–8 after the octave discussion, DS9–10 after a general waveform paragraph,
DS11–12 after an uncertain ring-modulation attribution, and DS13–16 after the
crest-factor discussion. Exact
oscillator selections, filter settings, effects and raw patch bytes are not
attached to each capture. **Do not interpret these mixtures as isolated
triangle/saw definitions, or infer waveform polarity from them.** No scope
waveform-data export is linked.

### Readable scope measurements and their limits

All 17 original screenshots were visually inspected, including enlarged
measurement strips. The acquisition catalog now includes the complete numeric
transcription, in volts and hertz. These are **display readings**, without a
measurement-accuracy claim or an identified patch. Selected examples:

| Image | RMS (V) | Peak-to-peak (V) | Frequency display (Hz) | Visible shape |
| --- | ---: | ---: | ---: | --- |
| DS0 | 0.67920 | 2.0371 | 439.43 | Smooth, approximately sinusoidal |
| DS1–8 range | 1.0295–1.0662 | 3.3691–3.7609 | 438.93–439.66 | Octave mixtures with different relative phases |
| DS11 | 0.47269 | 1.7373 | 138.84 | Rounded asymmetric shape with a faster component |
| DS12 | 0.47279 | 1.8917 | 175.04 | Asymmetric compound shape |
| DS15 | 0.084777 | 2.3743 | 333.97 | Narrow peaks over a much smaller background |
| DS16 | 0.26248 | 3.8608 | 496.43 | Irregular high peaks |

DS0's counter is about 2.24 cents below 440 Hz. Master tuning, oscillator fine
tuning and the measurement chain are unknown, so this is not evidence for a
pitch correction. On compound signals, the counter does not isolate either
oscillator's frequency. The screenshots have different capture timestamps and
trigger levels: they are not a continuous phase trace from which a beat period
can be recovered. For DS15, the displayed maximum absolute peak divided by RMS
is about 14.57, but the unknown patch and output chain prevent using this as a
gain, saturation or headroom target.

### What this does and does not constrain in Septum

The report is a credible first-person reason to investigate **relative phase
during a held octave** separately from phase on retrigger. It cannot distinguish
voice pitch offsets, multiple detuned oscillators, pitch modulation or chorus.
Retrigger differences alone cannot distinguish oscillator phase retention from
randomized phase, voice allocation or slightly different key timing.

In the current engine, classic oscillator phases survive note-on; `noteToHz`
uses an exact octave ratio when pitch controls match, with no separate voice
drift term. These code properties are relevant hypotheses, not validated or
refuted by this unknown patch. No scope image identifies a dry isolated classic
waveform well enough to compare its polarity, harmonic amplitudes or reset
phase with our oscillator model. **Do not add drift or change waveform shape
from these captures.** A useful discriminating reference would contain a known
single-oscillator patch, effects and pitch modulation off, repeated note-ons
and a long held octave pair, with original MIDI and patch bytes.

The author's linked WAV directory is reachable. The two SH-201-named files
are explicitly a composition also using Korg drums and Fender guitar; the
other low-frequency test waves were generated in Sound Forge. Neither is
an isolated SH-201 measurement, so they were excluded from acquisition.

## New original review recordings

[Thorsten Walter's AMAZONA review](https://www.amazona.de/test-roland-sh-201/),
published 24 July 2006, retains five SH-201 MP3 recordings. All fully decode
as 44.1 kHz stereo. The sixth playlist entry is explicitly a JP-8000 and was
excluded.

| Original title | Container duration |
| --- | ---: |
| Distortion SH-201 | 10.454 s |
| Pad SH-201 | 18.814 s |
| Sequenzer SH-201 | 16.306 s |
| SuperSawSeq SH-201 | 10.689 s |
| Sync SH-201 | 6.797 s |

Source-only spectrogram inspection finds a continuously changing harmonic
pattern over about 0.35–4.7 seconds in the Sync example and several longer
chord passages in Pad. The review discusses oscillator aliasing, but its
audition filenames do not document oscillator, cutoff, modulation or effects
settings. These recordings may support investigations of sync or aliasing;
they cannot identify a replacement envelope law or a specific raw parameter
value. No named preset, SysEx or performed MIDI accompanies them.

## Archive recovery outcome

The [MaxSynths author post](https://www.tone2.org/forum/index.php?topic=1336.0)
still links `MaxSynths_Rayblaster_Impulses01.zip`. The current endpoint returns
HTTP 200 with only the two text bytes `OK`; it is not an archive. Internet
Archive CDX queries for this asset and the Aymat Kontakt conversion returned
503; its availability API returned 429. These failures do not establish
whether archived copies exist. No authorized alternative download was found
in this bounded search.

The [Kontakt conversion author's post](https://www.dogsonacid.com/threads/sh201-kontakt-multi.485260/)
identifies some cycles as coming from evilsoft's already-audited pack. Its
corrected Aymat URL now returns an HTML 404. This extends the earlier failed
MediaFire recovery; it supplies no newly recovered waveform bytes.

## Assets and reproduction

The [acquisition catalog](public-waveform-recovery-2026-09-15.json) pins the
five MP3s, 19 images and two source pages with original URLs, SHA-256 hashes,
sizes and decode results. Download each URL to its catalogued filename under
ignored `build-fidelity/public-waveforms/{amazona,trioda}` and verify its hash
before analysis. No third-party media is committed.

The Trioda images are a new qualitative phase/crest-factor reference; the
AMAZONA examples are new modulation/audio references. Neither closes the
missing isolated-waveform, raw-preset or long known-gate evidence gap.
