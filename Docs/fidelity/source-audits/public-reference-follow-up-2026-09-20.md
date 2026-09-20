# Public SH-201 reference follow-up

Research date: 2026-09-20. **No new verified recording + original performance MIDI + same-take preset triplet was found.** The strongest immediately reproducible references remain Roland's named Patch 100 recordings and published banks, replayed with explicitly estimated MIDI. This follow-up supplements the [earlier exact-input search](../exact-reference-search.md); it does not imply that all public sources have been exhausted.

## An additional useful comparison: Class A

[Roland's LEAD page](https://www.rolandus.com/go/sh-201_patches/patch_lead.html) still names **Class A**, associates it with patch 1 in the downloadable bank, and describes attacks that depend on legato playing. The [20.95-second recording](https://www.rolandus.com/go/sh-201_patches/mp3/LEAD/TOP8_ClassA.mp3) and [100-patch bank](https://www.rolandus.com/go/sh-201_patches/shl/SH-201_Patch_LEAD.zip) are already cached. Class A is outside the existing ten-recording A/B set.

The previously decoded [candidate inventory](named-reference-filter-candidates.json) reports one active upper tone, mono mode byte 1 (SOLO+LEGATO), saw oscillators, zero resonance, zero filter velocity sensitivity, zero filter LFO depths and no overdrive. Its nonzero filter attack and decay make attack/retrigger behavior a useful bounded target. Delay and reverb sends are nonzero, so this is not an isolated dry envelope measurement. Actual velocities, gates, controller movements and same-take patch revision remain unknown.

A [new opening-phrase transcription](../reconstructions/expanded/class-a.json) provides ten estimated notes covering 1.2 seconds. It uses adjoining estimated gates. Testing a separately labelled legato-overlap hypothesis remains useful; do not identify an envelope curve from a single fitted performance. No engine comparison was performed in this source/transcription follow-up.

Hardware-only inspection found short pitch ramps between several opening notes despite the published portamento switch being off. A longer rise from approximately G4 to A4 starts around 1.25 seconds and reaches two semitones by 1.9 seconds. The published bend range is two semitones; this is consistent with performance bend, but does not recover the original controller messages. The reconstruction ends before that rise rather than inventing a bend curve.

The ten settled primary harmonic families agree with the proposed notes within 4.7 cents under the selected-window method. OSC1's raw coarse value is +36 with WIDE off, mapped to +12 semitones by the current codec; upper tone octave -1 cancels it. OSC2 is one octave below the played note. Weak sub-octave families support this reading, with greater uncertainty on the first very low note and short windows. The [hardware-only audit](class-a-transcription-2026-09-20.json) records source hashes, patch bytes, window measurements and the later pitch trajectory. These frequency checks support note selection, not sound-matching accuracy.

The existing **Dist Bs 1** excerpt remains the stronger simple gating reference: its published patch has no delay/reverb, and three separated events already have documented onset/gate estimates. It still combines two tones and overdrive and uses estimated velocity. See the [current A/B provenance](../ten-recording-ab.md) and [original benchmark qualification](../hardware-audio-benchmark.md).

## New leads inspected

| Primary source | Evidence and result |
| --- | --- |
| [MaxSynths's original Tone2 forum post](https://www.tone2.org/forum/index.php?topic=1336.0) (2012-12-04) | The author identifies SH-201 hardware waveforms among a free impulse/waveform collection. The linked `MaxSynths_Rayblaster_Impulses01.zip` returns HTTP 200 but only the two bytes `OK`; ZIP validation fails. No actual SH-201 waveform, parameter state or performance MIDI was recovered. This remains an unavailable potential waveform reference, not a usable calibration dataset. |
| [Romekd's Trioda hardware experiment](https://forum-trioda.pl/viewtopic.php?t=39199) (2022) and [public file directory](https://www.rm-projekt.pl/~romek/pliki_wav/) | The author discusses SH-201 phase/amplitude observations and links two WAV versions of a musical example. The post explicitly assigns other parts to a Korg N5EX and Fender guitar; the directory supplies no associated MIDI or preset files. No controlled patch state is established, so these mixed recordings were not admitted or downloaded for calibration. |
| [RCS's original free Analog Basses page](https://www.rcssound.com/index.php?page=6) and [author's SoundCloud demonstration](https://soundcloud.com/user-495684465/roland-sh-201-fresh-analog-basses-free-soundset-2020-demo) | Rechecked to distinguish patch MIDI from performance MIDI. The author explicitly describes the MID files as SysEx settings. The earlier local binary audit found no note events. This is useful named-preset audio but does not improve the original-performance evidence tier. |

The MaxSynths lead was found through general oscillator/sample queries and verified against the author's post, rather than relying on the secondary news report. Its archive failure was checked with both HTTP and HTTPS. The Trioda thread's qualitative observations alone were not promoted into new oscillator or voice-allocation rules.

## Local evidence

The ignored folder `build-fidelity/hardware-benchmark/source-search-2026-09-20/` contains cached Roland BASS/LEAD, MaxSynths and Trioda HTML, the directory index, the two-byte archive response, and `retrieval.json` with URLs, HTTP results, sizes and SHA-256 hashes. Python's default TLS store initially failed verification; ordinary `curl` succeeded without disabling certificate validation. The successful curl results are the retained acquisition evidence.

`class-a.syx` and `class-a.provenance.json` in that folder were generated by the existing `Tools/extract_reference_patch.py` from the cached official bank. All 22 parameter blocks are preserved; no settings were modified. They are a published preset export, not a dump authenticated against the recorded take. The new reconstruction is JSON; no binary performance MIDI was generated during this follow-up.

`build-fidelity/hardware-benchmark/class-a-transcription-2026-09-20/` retains the decoded hardware WAV, analysis JSON and visually checked `hardware-note-evidence.png`. Reproduce into a new output directory with `python3 Tools/analyze_class_a_transcription.py --sources build-fidelity/hardware-benchmark/sources --output NEW_DIRECTORY`. The script verifies pinned source hashes and calls no engine renderer.

Existing source files used for verification are `build-fidelity/hardware-benchmark/sources/TOP8_ClassA.mp3`, `TOP8_DistBs1.mp3`, `TOP8_SexyBack.mp3`, and `SH-201_Patch_LEAD.zip`. The three MP3 hashes match [the source catalog](../hardware-reference-catalog.json); FFprobe identifies all three as stereo 44.1 kHz MP3. No third-party audio or preset payload was added to Git, and no creator was contacted.
