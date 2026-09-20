# RCS named-preset reference screen — 20 September 2026

The published RCS A02 settings provide a promising candidate for a new **named-preset** reference: they have no enabled internal delay/reverb contribution. The parent task verified its label in separately decoded paused video frames at **20, 25 and 30 seconds**. Exact patch-change boundaries remain unverified. These settings do not provide an isolated pulse-wave measurement.

The [author's page](https://www.rcssound.com/index.php?page=6) links both the [eight-patch download](https://www.rcssound.com/download.php?kod=6) and [this demonstration](https://www.youtube.com/watch?v=8LKRnrs8DcQ), and attributes the patches to actual SH-201 hardware. The freshly downloaded archive is byte-identical to the previously audited copy. All eight SHL patches again equal their companion SMF SysEx frames byte for byte; every SMF has zero note events. The archive's patch list alone does not establish playback order. Separate decoded paused browser frames show A01 at 8 and 15 seconds, A02 at 20, 25 and 30 seconds, and A03 at 34 seconds. These were inspected by the parent task; screenshots were emitted in its CUA tool results but not saved as filesystem files. An initial apparent A02 label at 0:02 is excluded because it may have been a stale seek frame. The video is a labelled slideshow, without live panel footage or numeric control states.

The [JSON audit](rcs-reference-screen-2026-09-20.json) pins source, archive, bank, SMF and tool hashes and records the relevant settings for every active part. Parameter interpretation follows Roland's MIDI Implementation p. 5. Coarse pitch is retained as signed wire data plus the WIDE switch; this screen makes no played-note inference.

## Published settings

| Patch | Configured sounding oscillators | Internal spatial sends | Upper overdrive | Upper filter |
| --- | --- | --- | --- | --- |
| A01 MoogBass | Upper saw + triangle | None | On, drive 8 | LPF24, cutoff 39, resonance 10, envelope +32, velocity +9 |
| A02 MoogBass PW | Upper square + pulse; lower sine | None | On, drive 33 | LPF24, cutoff 120, resonance 0, envelope −22, velocity 0 |
| A03 Jupiter8wide | Upper square + saw; lower sine | Delay | On, drive 33 | LPF24, cutoff 113, resonance 0, envelope −15 |
| A04 Jupiter8reso | Upper square + saw; lower sine | Delay | Off | LPF24, cutoff 123, resonance 39, envelope −15 |
| A05 Jupiter8Perc | Upper square + pulse; lower sine | Delay | On, drive 33 | LPF24, cutoff 106, resonance 0, envelope −22 |
| A06 Jupiter8wet | Upper square + pulse; lower sine | Delay | Off | LPF12, cutoff 64, resonance 50, envelope +20, velocity +32 |
| A07 SmoothClicky | Upper square + saw; lower pulse | Delay | Off | LPF12, cutoff 89, resonance 0, envelope −37 |
| A08 HouseBASS | Upper square + saw; lower pulse | Delay and reverb | Off | LPF12, cutoff 90, resonance 0, envelope −36 |

Oscillator counts describe the configured active keyboard parts and balance settings; amplitude envelopes can remove a layer later. All eight upper parts mix both oscillators at balance 0. A01 is single-part; the other seven are dual. None combines a single oscillator with absent spatial effects and overdrive. All upper filters have nonzero envelope depth, although a held note can still reach a static sustain stage.

## What A02 can test

A02 has zero cutoff velocity sensitivity in both parts, zero oscillator pitch-envelope depth and zero LFO depths. Its upper filter sustain is 127, so a sufficiently settled held note can provide a static passage. The global delay switch is on, but both delay sends are zero; reverb is off. External capture processing and live control changes remain unverified.

Its square and pulse waves enter an overdriven upper part, while the lower sine changes the fundamental. Consequently, neither even-harmonic amplitude nor ratios normalized by the fundamental directly identify pulse width. Nonlinear mixing also makes relative oscillator phase consequential. The lower filter is LPF24 with cutoff 64 and resonance 9; the upper pulse-width byte is 56.

The next useful comparison is a stable, visibly labelled A02 note: preserve the source and exact time window, estimate pitch from hardware alone, then check higher-harmonic ratios that exclude the fundamental across declared gate, velocity and relative-phase variations. This would test the combined oscillator/filter/overdrive behavior of a new published patch. It should not promote a global waveform change on its own. The 20–25 second video interval is the current candidate; exact transitions were not timed. The separate SoundCloud copy was subsequently aligned numerically as described below; it does not supply independent hardware evidence.

## Audio acquisition

Both the author-linked YouTube audio and the author's SoundCloud demo were acquired with ordinary public yt-dlp requests, without cookies or authentication. A local certificate-bundle issue was repaired with certifi; no certificate checks or access protections were disabled. The downloader environment, media, complete metadata and logs are ignored under `build-fidelity/hardware-benchmark/rcs-reference-screen-2026-09-20/`.

The YouTube source is 121.901 seconds of stereo Opus at 48 kHz, format 251; SoundCloud supplies 117.368 seconds of stereo MP3 at 44.1 kHz/128 kbps. Their durations differ, so equal timestamps were not assumed. Use the YouTube source directly for the labelled 20–25 second interval. Full-file stereo float WAVs at 44.1 kHz were decoded successfully and checked for finite, nonempty, nonzero samples. Source/WAV hashes, codec details, canonical URLs and reproduction commands are pinned in the JSON audit; direct stream URLs remain in the hashed ignored metadata. These are lossy platform encodes, with external capture processing still unverified.

The parent task subsequently compared six one-second snippets at YouTube times 8, 10, 20, 23, 25 and 29 seconds with the SoundCloud waveform, after mono polyphase downsampling to 4,410 Hz. Every best match used **SoundCloud time = YouTube time − 1.492517 seconds**, with normalized PCM correlations **0.997043–0.998349**. The JSON pins that report and both decoded source hashes. This corroborates two lossy copies of the same sampled performance; it is not a second independent hardware reference. The primary YouTube comparison needs no such alignment.
