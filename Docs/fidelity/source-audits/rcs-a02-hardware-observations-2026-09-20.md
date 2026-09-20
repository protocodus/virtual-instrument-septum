# RCS A02 hardware observations — 2026-09-20

The directly recovered [author-linked YouTube audio](https://www.youtube.com/watch?v=8LKRnrs8DcQ) provides a usable short original-patch comparison. A **0.96 s, five-note reconstruction** is saved as [rcs-a02-moogbass-pw.json](../reconstructions/expanded/rcs-a02-moogbass-pw.json). It uses YouTube 21.18–22.14 s, played-note estimates 44/56/44/56/44, unmodified A02 settings and placeholder velocity 100. No software audio was used to select these notes.

The parent independently observed A02 labels at 20, 25 and 30 s. This is a slideshow, so live parameter changes remain unknown. The parent also aligned six passages of the recovered SoundCloud copy with YouTube: SoundCloud time = YouTube time −1.492517 s, correlation 0.9970–0.99835 after mono resampling. That corroborates timing between two lossy copies of one performance; it does not create a second independent hardware reference. **All times below use the direct YouTube source.**

Hardware-only spectrograms and periodicity identify a fast line with bass/octave alternations, rather than long sustained notes. The 20–25 s pitch groups are approximately G, G♯, C, E♭ and G. Thirty selected 60 ms interiors and attack candidates are retained in the [measurement JSON](rcs-a02-hardware-observations-2026-09-20.json), with original/crop hashes and decode commands.

The selected five-note case is especially clear because it starts after a short silence and finishes with a rapid amplitude release around 22.042 s:

| Approximate attack | Window center | Periodic-fit frequency | Sounding-note estimate | Conditional played MIDI |
|---|---|---:|---|---:|
| 21.210 s | 21.275 s | 51.424 Hz | G♯1 | 44 |
| 21.347 s | 21.425 s | 102.799 Hz | G♯2 | 56 |
| 21.484 s | 21.550 s | 51.487 Hz | G♯1 | 44 |
| 21.621 s | 21.725 s | 102.277 Hz | G♯2 | 56 |
| 21.892 s | 21.975 s | 51.271 Hz | G♯1 | 44 |

Played MIDI assumes the published square/sine −12-semitone oscillator offsets and unchanged system transpose. Onsets are uncertain by roughly 10–15 ms. Adjoining gates are a neutral reconstruction convention, not verified key releases or overlap. Gate sensitivity should retain at least ±15 ms. Short-window periodic fits lie about 13–26 cents below A=440; dynamic filter phase and waveform changes can bias them, and some late high-note fits reach the search boundary. No patch retuning or invented pitch-bend events were added.

The longer high note beginning around 21.621 s exposes a useful temporal feature: the low-frequency waveform persists until the next attack, while 1.5–12 kHz power falls by tens of decibels over approximately 0.1–0.15 s. Its band ratio to 300–1500 Hz also collapses, so this is more than a uniform volume fade. Earlier windows have stable pitch but changing harmonic shape; the late settled stage has weak high harmonics.

This passage can test the original patch's **joint oscillator/filter/overdrive/envelope response**. It cannot directly calibrate pulse width: Upper mixes an octave square and pulse through active overdrive, and Lower adds a sine to the fundamental. The original velocities, gate history, relative oscillator phases, controllers, capture processing and precise recorded patch revision remain unverified. The author's `.mid` preset export contains SysEx, not the original played notes. No production DSP or published patch bytes changed.
