# synth-love: original SH-201 video/audio acquisition

## New evidence recovered

The two original videos are available publicly. Both complete YouTube Opus
audio streams, primary metadata, and three bounded 1080p video excerpts were
acquired for audio and control inspection. This provides analyzable recordings,
but **no complete patch recipe or isolated dry oscillator was identified** in
the inspected sections.

- [Part 1](https://www.youtube.com/watch?v=zeIHMnVxaQE): 11:59 metadata duration,
  titled “Roland sh201 patch creation part 1 (no talking).” Metadata upload date
  is 2016-10-02; the contemporary Matrixsynth article is dated October 1 in its
  displayed timezone. No chapters or captions are supplied.
- [Part 2](https://www.youtube.com/watch?v=OB3J7AQBla0): 10:05 metadata duration
  (the browser player displays 10:04), titled “Roland SH-201 Patch Creation
  Part 2 (no talking),” uploaded 2016-10-07. No captions are supplied.
- The current uploader is **something something / @909techno**, channel
  `UCmVcKfVsgQJuYQRTRx9bqHA`. The original descriptions retain the synth-love
  subscription link; the [contemporary Matrixsynth
  post](https://www.matrixsynth.com/2016/10/roland-sh201-patch-creation-part1.html)
  identifies the uploader as synth-love and embeds these exact video IDs.

Part 2's expanded primary description supplies more sections than the older
Matrixsynth excerpt:

| Time | Author's section topic |
|---|---|
| 0:00–0:50 | Maximum LFO speeds |
| 0:50–3:55 | Drum sounds |
| 3:55–4:51 | FM-like chimes and bells |
| 4:51–7:35 | Portamento |
| 7:35–9:00 | Reverb |
| 9:00–end | Supersaw |

## What the visible controls establish

The camera shows a real SH-201 from an oblique angle. Some labels and indicators
are readable, but the oscillator/left-side region is soft and hands conceal
controls or keys during changes. Physical knob positions do not by themselves
establish the current stored parameter values.

**Maximum-LFO section:** inspected frames at 0, 4, 5, 10, 20, 30, 40 and 49 s.
The DESTINATION1 knob changes orientation between the early frames; a different
LFO shape-indicator position appears by 20 s; the operator manipulates an
oscillator-section knob at 30 s and FILTER ENV sliders at 49 s. RATE appears
unchanged across these sparse snapshots. The section therefore contains
multiple patch states. The title gives an endpoint-test intention; the video
inspection has not established both LFOs' raw rates, routing, sync state or a
single-oscillator dry patch. Analyze local passages and distinguish modulation
from beating/carrier harmonics before using an observed periodicity.

An additional visual check against the [official panel diagram, OM
p.40](https://cdn.roland.com/assets/media/pdf/SH-201_OM.pdf) maps the selected
SHAPE LED at **4 s to sample-and-hold**, the second position from the clockwise
end of the seven-position arc. At 20 s the final, random position is selected.
This is a positional comparison independent of the audio analysis, with
moderate-high confidence; it does not rely on reading the blurred waveform
icon. LFO1 appears selected (moderate confidence). The manual defines S&H as
one value change per LFO cycle, making a validated local step cadence a useful
rate diagnostic. This still does not certify raw127 from the camera.

**Portamento section:** inspected 291, 296, 306 and 319 s. It includes bank/number
button operations and playing, followed by filter-cutoff and FILTER ENV
manipulation. Some number indicators are visible, but the complete held-button
sequence and raw portamento time were not recovered. Roland permits time
changes using PORTAMENTO plus numbered buttons or the EFFECTS TIME knob; that
does not justify assigning a raw time to an isolated LED snapshot.
([Owner's Manual, p.19](https://cdn.roland.com/assets/media/pdf/SH-201_OM.pdf))

**Part 1 opening:** inspected 0, 10, 20 and 39 s of a 0–40 s clip. The first
frame is black; subsequent frames show playing and several illuminated
bank/number controls. No complete initialization or saved-patch identification
was recovered. The author's description discusses aliasing and envelope
behavior qualitatively; it supplies no numeric measurement or preset recipe.

## Assets and reproducibility

All media remains in the ignored local directory
`build-fidelity/public-waveforms/synth-love/`. The durable
`synth-love-video-acquisition-2026-09-15.json` beside this report pins all
35 assets, acquisition logs, metadata, 16 inspected video PNGs, the official
manual/panel-diagram helper, and media probe output.

| Asset | Acquisition |
|---|---|
| `zeIHMnVxaQE.f251.webm` | Full part-1 YouTube Opus audio, 48 kHz stereo |
| `OB3J7AQBla0.f251.webm` | Full part-2 YouTube Opus audio, 48 kHz stereo |
| `OB3J7AQBla0.0-50.audio.wav` | First 50 seconds decoded to float32 PCM |
| `zeIHMnVxaQE.0-40.f137.mp4` | Part-1 opening, H.264 1080p |
| `OB3J7AQBla0.0-50.f137.mp4` | Part-2 maximum-LFO section, H.264 1080p |
| `OB3J7AQBla0.291-320.f137.mp4` | Opening of portamento section, H.264 1080p |

Part-2 full audio SHA-256:
`6ed77a823dde937f4bf87bf9cf803a7293dd21a97056f36694704355b8b15f4c`.
Its decoded 50-second excerpt SHA-256:
`8e2babd5e54375b8b6454dd4271c5a9c95b16e29e634e4219069c5eb19727131`.
These are platform transcodes, not the owner's uncompressed master. Audio was
retained as offered; no player normalization gain, denoising, EQ or sample-rate
conversion was applied. The acquisition log and ffprobe record nominal video
cut timing; use the full audio timeline for quantitative timing.

Acquisition used yt-dlp **2026.8.19**, installed from PyPI into the isolated
`build-fidelity/research-tools/yt-dlp` directory. No cookies, credentials,
CAPTCHA handling or login bypass were used. Chrome independently verified the
primary page, uploader and expanded description; the research tab was closed.
Web text fetches of the YouTube URLs were throttled, while public yt-dlp access
succeeded without changing identity or bypassing an access control.

Representative reproduction commands (choose a new output directory):

```sh
PYTHONPATH=build-fidelity/research-tools/yt-dlp python3 -m yt_dlp \
  --no-playlist --socket-timeout 15 --retries 0 --extractor-retries 0 \
  --skip-download --write-info-json -o 'NEW_DIR/%(id)s.%(ext)s' \
  'https://www.youtube.com/watch?v=OB3J7AQBla0'

PYTHONPATH=build-fidelity/research-tools/yt-dlp python3 -m yt_dlp \
  --no-playlist --socket-timeout 15 --retries 0 --extractor-retries 0 \
  -f 251 -o 'NEW_DIR/%(id)s.f%(format_id)s.%(ext)s' \
  'https://www.youtube.com/watch?v=OB3J7AQBla0'

PYTHONPATH=build-fidelity/research-tools/yt-dlp python3 -m yt_dlp \
  --no-playlist --socket-timeout 15 --retries 0 --fragment-retries 0 \
  --extractor-retries 0 --download-sections '*0-50' \
  --download-sections '*291-320' -f 137 \
  -o 'NEW_DIR/%(id)s.%(section_start)s-%(section_end)s.f%(format_id)s.%(ext)s' \
  'https://www.youtube.com/watch?v=OB3J7AQBla0'
```

The maximum-LFO audio is passed to a separate periodicity audit. These sources
are currently useful for conditional parameter-behavior diagnostics. They do
not supply the same-preset/MIDI hardware benchmark needed to establish output
equivalence, and they justify no shipping DSP change on their own.
