# Ten real SH-201 recordings: published-preset A/B set

Ten official Roland hardware recordings are paired with their named published
presets and freshly rendered through Septum at revision `987237a`. Each case
includes the complete original MP3, an unchanged patch export as SysEx, MIDI
reconstructed from a selected hardware excerpt, the raw software render and
level-matched A/B audio. The four existing current reconstructions are joined
by six new bass/lead reconstructions.

**All ten MIDI files are reconstructed, not original captured performances.**
The user accepted this fallback. Full hardware recordings contain more music
than the short matched excerpts: together the excerpts cover **29.74 seconds**.
No preset parameters or DSP models were fitted to make these examples agree.

## Listen and download

The generated page is `build-fidelity/hardware-benchmark/ten-patch-ab-987237a/index.html`,
served locally at <http://127.0.0.1:8915/>. It switches between hardware and
Septum at the same timeline position. Every case provides its full original
recording, MIDI, SysEx, raw render, sequential A/B, plots and provenance.

`sh201-ten-ab.zip` in the same directory contains the complete portable
listening set, about 69 MB. `dataset-manifest.json` records all included file
hashes, source URLs, renderer/source identity and audio validation results.
Generated media and third-party preset payloads remain outside Git.

| Recording | Original excerpt | Notes | Reconstruction |
| --- | ---: | ---: | --- |
| Moogie 1 | 0–3.70 s | 16 | [Current octave-corrected](reconstructions/current/moogie-1.json) |
| So Juno 1 | 0–1.55 s | 5 | [New opening phrase](reconstructions/expanded/so-juno-1.json) |
| Dist Bs 1 | 1.94–3.20 s | 3 | [Current octave-corrected](reconstructions/current/dist-bs-1.json) |
| Pedal Bs 1 | 0–1.55 s | 3 | [New short phrase](reconstructions/expanded/pedal-bs-1.json) |
| Club Bass | 0–3.25 s | 6 | [New separated bass notes](reconstructions/expanded/club-bass.json) |
| Cotton Wool | 0–5.00 s | 27 | [Current chord estimate](reconstructions/current/cotton-wool.json) |
| Air Lead 1 | 0–3.45 s | 10 | [New opening phrase](reconstructions/expanded/air-lead-1.json) |
| Vangelead | 0–5.15 s | 5 | [New descending phrase](reconstructions/expanded/vangelead.json) |
| SupaJuce 1 | 0–1.80 s | 6 | [Current octave check](reconstructions/current/supa-juce-1.json) |
| Brassy Ld 1 | 0–3.03 s | 11 | [New staccato phrase](reconstructions/expanded/brassy-ld-1.json) |

## What is verified

The real-recording/preset associations come from Roland's
[BASS](https://www.rolandus.com/go/sh-201_patches/patch_bass.html),
[PAD](https://www.rolandus.com/go/sh-201_patches/patch_pad.html) and
[LEAD](https://www.rolandus.com/go/sh-201_patches/patch_lead.html) pages,
rechecked on 14 September 2026. Original MP3 and librarian-bank hashes match
the [reference catalog](hardware-reference-catalog.json). Patch names match
the bank records, and all 22 parameter blocks per preset export unchanged
into checksum-valid Roland DT1 messages. A matching published preset does
not authenticate the exact patch revision used during recording.

New notes were inferred from hardware spectra, harmonic families and attack
timing, accounting for the published WIDE, coarse-tuning and tone-octave
settings. [Bass measurements](source-audits/ten-recording-bass-transcriptions.json)
and [lead measurements](source-audits/ten-recording-lead-transcriptions.json)
retain the source hashes, tuning bytes and pitch evidence. No software render
was used to choose or optimize those notes.

Settled lead fundamentals agree with their assigned equal-tempered notes
within approximately 19 cents for modulated Air Lead, 7 cents for Vangelead
and 3 cents for Brassy. These checks support note selection, not synthesizer
fidelity scores. Pedal Bs has more uncertain attack pitch movement and gates;
Cotton Wool has more uncertain voicing and releases. The case files describe
those limitations individually.

The standard current engine renders at 44.1 kHz, master level 100, MIDI
channel 1 and preserved patch tempo. Experimental timbre profiles are
disabled. The 93-sample output latency is retained. Listening copies apply
constant gain to match whole-excerpt RMS, with shared attenuation if needed
for headroom; no EQ, compression, time warping or post-render alignment is
applied. Sequential A/B files alone add a half-second gap and 5 ms edge fades.

All 20 listening WAVs are finite, nonzero stereo audio with matching paired
frame counts and safe peaks. The renderer reports no degraded replay.
An independent compilation of the current DSP reproduced the initial four
raw renders byte for byte. Published presets, raw renders, source MP3s and
listening copies are kept separately so each transformation is inspectable.
Independent final QA checked all 220 exported parameter blocks and balanced
MIDI events for every case. Chrome decoded all 20 listening WAVs; hardware
playback, position-preserving switching to Septum, Stop and desktop layout
passed without media or console errors. The download includes the detailed
`independent-qa.json` report.

## Original MIDI search and remaining uncertainty

A fresh bounded search found no verified original performance MIDI triplets.
The existing [source audit](hardware-audio-benchmark.md) already distinguishes
patch-only SMFs from performed note data. Newly inspected
[Synthdesign banks](https://www.synthdesign.de/roland.htm) contained preset
files and text only. A [creator's twenty-recording post](https://rmmedia.ru/threads/34446/)
did not provide matching presets or performance MIDI, while
[RCS](https://www.rcssound.com/index.php?page=6) explicitly identifies its
MIDI downloads as SysEx settings. This search result does not establish that
original MIDI is unavailable everywhere.

Velocities are explicitly fixed at 100 as placeholders. Exact gates,
legato overlaps, controller movement, oscillator history, system transpose,
the recorded patch revision and the recording chain remain uncertain.
Several crops end on held notes and use artificial final note-offs. These
are useful listening comparisons of the same published sounds, not waveform
null tests or controlled hardware measurements.

## Reproduce

The existing [source acquisition instructions](hardware-audio-benchmark.md#reproduce-the-comparisons)
recover the cataloged assets. With the optional Python analysis dependencies
and `ffmpeg` installed, render the ten cases into a new directory:

```sh
cmake --build build-fidelity --target SeptumRenderMidi --parallel 6
python3 Tools/compare_hardware.py \
  --sources build-fidelity/hardware-benchmark/sources \
  --renderer build-fidelity/SeptumRenderMidi \
  --output build-fidelity/hardware-benchmark/ten-patch-ab-new \
  --case Docs/fidelity/reconstructions/current/moogie-1.json \
  --case Docs/fidelity/reconstructions/expanded/so-juno-1.json \
  --case Docs/fidelity/reconstructions/current/dist-bs-1.json \
  --case Docs/fidelity/reconstructions/expanded/pedal-bs-1.json \
  --case Docs/fidelity/reconstructions/expanded/club-bass.json \
  --case Docs/fidelity/reconstructions/current/cotton-wool.json \
  --case Docs/fidelity/reconstructions/expanded/air-lead-1.json \
  --case Docs/fidelity/reconstructions/expanded/vangelead.json \
  --case Docs/fidelity/reconstructions/current/supa-juce-1.json \
  --case Docs/fidelity/reconstructions/expanded/brassy-ld-1.json
python3 -m http.server 8915 --bind 127.0.0.1 \
  --directory build-fidelity/hardware-benchmark/ten-patch-ab-new
```

This recreates the comparisons and standard player. The delivered directory
also retains `package_set.py`, which records the local packaging procedure
for the complete MP3 copies, download bundle and compact player layout.
