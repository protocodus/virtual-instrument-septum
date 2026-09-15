# synth-love Super Saw chapter: visual feasibility

## Result

The original [SH-201 part-2 video, 9:00 to end](https://www.youtube.com/watch?v=OB3J7AQBla0&t=540s)
shows Super Saw selection and repeated spread-control gestures. **It does not
authenticate a minimum/maximum spread endpoint, or a dry single-oscillator
passage.** Two short late passages warrant separate audio inspection, subject
to note/voice mixture and frequency-resolution checks.

The author's primary description identifies this chapter as Super Saw tests.
It supplies no raw values, patch dump, MIDI notes or dry-signal assertion.
The current uploader remains @909techno; source identity and the earlier
sections are covered by the [original acquisition audit](synth-love-video-acquisition-2026-09-15.md).
This audit inspects only the previously unreviewed final chapter.

## Visible evidence

The [official manual, pp.28 and 30](https://cdn.roland.com/assets/media/pdf/SH-201_OM.pdf)
places Super Saw at the right-middle WAVE indicator, immediately before the
lower-right EXT IN position. With Super Saw selected, **PW/FEEDBACK** changes
the pitch spread of its seven component saws. The separate **DETUNE** knob
shifts their pitches together. These control meanings must not be confused.

The oscillator labels are defocused. The Super Saw identification below is a
positional LED comparison with the manual, with moderate-high confidence;
it does not rely on reading nonexistent detail from the video.

| Nominal source time | Observation and usable constraint |
|---|---|
| 540–542 s | WAVE button operation; the exposed indicator afterward is at the Super Saw position. |
| 542.5–549 s | Hand moves between the three OSC knobs. Multiple oscillator parameters change. |
| 549–556.5 s | Repeated manipulation of the rightmost OSC knob, PW/FEEDBACK. No mechanical stop or raw value is certified. |
| 558.5–564.5 s | WAVE indicator is now on the left side; further PW/FEEDBACK gestures. A different waveform state interrupts the chapter. The exact transition and left-side waveform are unassigned. |
| 565–569.5 s | Repeated WAVE button cycling, ending at the Super Saw position by 570 s. |
| 570.5–586.5 s | Repeated PW/FEEDBACK gestures. Hand occlusion and defocus prevent reliable endpoint readings. |
| 587.5–588.5 s | Another OSC adjustment precedes the late passage. |
| **589.2–591.0 s** | OSC controls untouched; the keyboard hand is partly outside the frame. Candidate for audio stationarity inspection only. |
| 594.5–597.5 s | Operator touches the far-right controls, including the partly obscured FX area. Do not assume unchanged effects across this interval. |
| **598.5–601.3 s** | Second interval with untouched OSC controls and a partly off-frame keyboard hand. Candidate for audio inspection only. |

The final two candidate intervals are **visual search intervals, not measured
note gates**. The frame does not prove a single held key, a particular note,
one contributing oscillator, or dry effects. The selected oscillator index,
mixer balance, other oscillator, modulation and part-layer state also remain
unverified. A physical knob orientation does not supply its stored value;
even after manipulation, these frames do not establish raw0 or raw127.
No numerical detune endpoint or DSP change follows from this visual audit.

## Media and reproducibility

The [companion JSON](synth-love-supersaw-visual-2026-09-15.json) pins 27 assets:
the new chapter, full offered audio, primary metadata, acquisition log,
official manual, panel diagrams, 14 selected full-resolution frames and six
inspection contact sheets. Cached media is under
`build-fidelity/public-waveforms/synth-love/`.

- New `OB3J7AQBla0.540-605.f137.mp4`: 22,856,000 bytes,
  SHA-256 `4dd9738a3a83309a0259ac3ccf33eb99fdbe04472d805f1f351a264f07ed2b89`.
- Reused full `OB3J7AQBla0.f251.webm`: 10,312,197 bytes,
  SHA-256 `6ed77a823dde937f4bf87bf9cf803a7293dd21a97056f36694704355b8b15f4c`.

Public yt-dlp 2026.8.19 retrieved offered format137 and ffmpeg remuxed the
requested 540–605 s chapter without video re-encoding. The resulting presented
duration is 64.937 s at 1920×1080, 30000/1001 fps. The first presented frame is
at local zero; preceding retained keyframe packets have negative timestamps
and discard flags. Use source time approximately `540 + presentation time`,
not the first packet timestamp. Two-frame-per-second overview sampling and
targeted full-resolution frames support observations rounded about 0.5 s;
these are not sample-accurate synchronization measurements.

The receipt includes the exact acquisition command and frame-extraction
method. No cookies, credentials or access-control bypass were used. Both
streams are YouTube transcodes, rather than the owner's uncompressed master.
The full audio timeline remains available for the separate DSP analysis.
