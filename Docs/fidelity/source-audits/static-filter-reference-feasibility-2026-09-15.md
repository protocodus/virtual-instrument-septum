# Additional static-filter references from published presets

## Result

**No independent published-preset cutoff anchor was established.** The 24 named recordings contain ten active tones in nine presets with zero stored filter-envelope depth, filter-LFO depth and filter-velocity sensitivity. Three promising sources were checked or inspected, but each has a material measurement ambiguity. This does not justify changing the cutoff or key-follow law, and it does not authenticate the unchanged recordings as exact reproductions of the downloadable patch revision. These are additional Roland Patch 100 banks, distinct from the read-only factory PRESET bank.

The inventory comes from the original official [BASS bank and demos](https://www.rolandus.com/go/sh-201_patches/patch_bass.html), [PAD bank and demos](https://www.rolandus.com/go/sh-201_patches/patch_pad.html), and [LEAD bank and demos](https://www.rolandus.com/go/sh-201_patches/patch_lead.html). All three ZIPs, their internal librarian banks and all 24 MP3s were checked against the tracked source catalog. The current C++ `decodePatchCommon` and `decodeTonePatch` perform the decode. In particular, WIDE-off raw pitch −36 means **−12 physical semitones**, and tone octave shift is added separately.

The original performance MIDI, controller automation, system state, output processing and exact recording patch revision remain unknown. “Static” below describes stored voice-filter controls. It does not prove a static recorded cutoff.

## Ranked additional candidates

| Rank | Candidate | Stored active controls | Useful source family | Feasibility result |
|---|---|---|---|---|
| 1 | Juicy Fat Upper | LP12; cutoff43, resonance33, KF0; filter depth/LFO/velocity0; no drive; flat low-frequency setting; master delay/reverb off | Single pulse, PW64, physical coarse−12; nominal odd partials | Dry and a useful low raw cutoff, but Lower saw partials nearly coincide. Moving-Lower separation fails conditioning. No cutoff estimate retained. |
| 2 | The Choir Upper | LP24; cutoff69, resonance60, KF90; filter depth/LFO/velocity0; no drive; low-frequency CUT | SuperSaw coarse0 plus Noise; no pitch modulation; tone octave0 | Interharmonic noise might be useful in principle, but early polyphonic/harmonic ambiguity and heavy effects prevent an isolated-source assignment. No verified fundamental or cutoff anchor. |
| 3 | Sequence Bs Lower | LP12; cutoff127, resonance0, KF0; filter depth/LFO/velocity0; no drive; flat low-frequency setting | Sine plus Square at the same physical coarse−12; odd partials above H1 could isolate Square | Opening spectrum is inconsistent with an ordinary unmodulated stored sine-plus-square patch. Reject the opening. Even an authenticated later passage would primarily constrain the high-cutoff endpoint. |

Air Lead 1 remains the existing conditional raw91/KF50 anchor. Its triangle/saw even-harmonic assumption and effects limitations still apply. The entries above do not independently confirm the large Air Lead cutoff residual.

### Juicy Fat: why a simple spectral fit would mislead

The first stable-looking low-frequency peak, in a 120 ms Hann window centered at 0.230 s, is 65.334 Hz. This is a mixture peak, not a precision tuning estimate. It is consistent with approximately sounding C2; with the stored Upper coarse−12 and octave0, that would imply played C3, conditional on system tuning/transpose.

The layers are:

- Upper: Pulse only, coarse−12, fine0, PW64, static LP12 cutoff43/Q33, AMP sustain127.
- Lower OSC1: Saw, coarse−12, fine−4 cents.
- Lower OSC2: Saw, coarse0, fine+5 cents.
- Lower filter: LP24 cutoff12/Q50, KF−30, envelope A21/D52/S40/R38/depth25; low-frequency BOOST. Both tones are active in Dual mode. Both master effects are off despite nonzero stored sends.

Thus the first Lower saw differs from the Upper pulse by only 0.151 Hz at H1, 0.452 Hz at H3 and 0.754 Hz at H5. These are the most relevant low odd partials for the Upper's current modeled cutoff, 209 Hz. The Lower's changing filter moves both amplitude and phase in the same bins.

The joint design includes Upper odd H1–H11, Lower OSC1 H1–H12 and Lower OSC2 H1–H6. This is optimistic: it assumes a perfectly symmetric pulse and exactly known fine tuning, with no Upper even harmonics. Each retained sinusoid has independent cosine/sine coefficients. The moving models additionally allow linear change in those complex coefficients. A condition number over 100 fails the same separation threshold used in the preceding chord study; a large number means small residual or frequency errors can change the individual layer amplitudes greatly.

| Window | All layer amplitudes/phases fixed | Upper fixed, moving Lower | All layers allowed to move |
|---|---:|---:|---:|
| 80 ms | 105 | 46,101 | 4,287,070 |
| 120 ms | 65 | 11,021 | 1,075,649 |
| 200 ms | 37 | 2,261 | 197,395 |

Holding every oscillator amplitude fixed can make the matrix appear usable, but discards the very Lower-envelope behavior that contaminates this measurement. Even the minimal model with a static Upper and moving Lower fails throughout. No individual Upper amplitudes or cutoff fits are reported.

As a mathematical control, changing only the two Lower fine offsets to −50/+50 cents gives conditions 80.5, 33.5 and 13.0 for the Upper-fixed/moving-Lower model. The criterion therefore can accept separated moving families; the failure is tied to this preset's close frequency spacing. This control is a matrix calculation, not a hardware render or a proposed patch modification.

A longer note with a settled Lower envelope, or controlled single-part hardware captures, could change this conclusion. The opening cannot supply that evidence. Merging the near-coincident families would improve numerical stability but would only measure their mixture, not the static Upper filter. A constrained joint transfer-function fit is a possible further experiment, but its result would depend on the assumed Lower envelope, resonance, oscillator phase and waveform; it would not provide an independent Upper measurement by itself.

### Sequence Bs: do not assume the bank controls describe the opening

The unchanged bank uses only Lower, with Sine plus Square at physical coarse−12, fine0, no pitch or filter modulation, LP12 cutoff127/Q0, AMP A0/D0/S127/R0. Arpeggio and delay are on; delay send53 and modulation depth10 are stored. The inactive Upper must not be analyzed as an audible source merely because its block contains different waveforms.

Across 80 ms windows centered at 0.16, 0.25, 0.40, 1.0 and 2.0 s, the recording has **97.98–98.25% of spectral power in 8–16 kHz**, peaks near **11.05–11.12 kHz**, and **less than 0.0016% below 1 kHz**. The dominant band then falls through approximately 3.53 kHz at 3 s and 1.50 kHz at 4 s. At 6 s, 96.93% is below 1 kHz.

These measurements establish a changing recorded spectrum, not its cause. Unknown controller moves, system/audio-filter processing or a different recording patch state are possible. Inferring a raw127 voice-filter cutoff from this opening would silently assume away that discrepancy. No cutoff estimate is retained.

### The Choir: independent opening inspection

The current decoder confirms active SuperSaw coarse0/fine0/spread64 and Noise coarse−12/fine0, mix balance−36, tone octave0; no active pitch-envelope or LFO depths. AMP attack50, delay send75, reverb send100, delay time100 and reverb predelay10 make an immediately dry attack unavailable as an assumption.

The separate root inspection found multiple overlapping early frequency families rather than one identified isolated note. At 0.35 s, reported prominent families include approximately 149, 261, 292, 350, 698, 876–888 and 1747–1768 Hz; at 2 s the mixture remains ambiguous. Neither the high ridge nor the lowest visible family was authenticated as a filter resonance or played-note fundamental. Interharmonic noise extraction is therefore deferred pending a credible polyphonic source model and effects control. No fitted cutoff or key-follow normalization is retained here. The [durable Choir inspection](choir-static-cutoff-feasibility-2026-09-15.json) records source hashes and 200 ms FFT peak lists; `Tools/inspect_choir_reference.py` reproduces it from the pinned original MP3 and native codec.

## All 24 named patches

U/L denote active Upper/Lower tones. A static entry has zero stored filter-envelope, filter-LFO and cutoff-velocity modulation. Full decoded oscillator, envelope, modulation, effects and physical pitch fields are in the accompanying inventory JSON.

| Patch | Active parts | Static filter tones, raw cutoff/KF | Selection limit |
|---|---|---|---|
| Moogie 1 | U+L | — | Both filter envelopes move. |
| So Juno 1 | U+L | L41/−200 | Static Lower is Sine only; moving Upper contaminates. No rich Lower harmonic family. |
| Dist Bs 1 | U+L | — | Both filter envelopes move; Upper drive. |
| Pedal Bs 1 | U | — | Filter envelope and velocity sensitivity. |
| Club Bass | U+L | — | Both route nonzero LFO to cutoff. |
| Sexy Back | U+L | U111/0; L95/0 | Upper SuperSaw pair and driven Lower triangle/saw, delay and high cutoffs; no clean independent low/mid anchor. |
| Juicy Fat | U+L | U43/0 | Ranked1; close detuned moving Lower family. |
| Sequence Bs | L | L127/0 | Ranked3; undocumented changing opening state and high endpoint. |
| Cotton Wool | U | — | Filter envelope and velocity sensitivity. |
| Soundtrack | U+L | — | Upper envelope/LFO; Lower nonzero depth2 at sustain127, so converting its offset requires the unknown depth law. |
| The Choir | U | U69/90 | Ranked2; polyphonic/noise/effects ambiguity. |
| Reso Sweep | U+L, split | — | Both cutoff LFOs active; high resonance. |
| Pulsatron | L | — | Filter envelope and LFO. |
| 201vsJP8000 | U | — | Filter envelope and LFO. |
| Crystalize | U | — | Feedback source, HP filter, envelope/LFO. |
| Moving Str. | U | — | Cutoff LFO. |
| Class A | U | — | Nonzero filter envelope, even if late sustain may settle. |
| Daft Lead | U+L | — | Both filter envelopes and drive. |
| Air Lead 1 | U | U91/50 | Existing conditional even-saw analysis; wet capture and source-shape assumptions. |
| Trancefloor | U | U121/0 | Strongly detuned SuperSaw pair and effects; high cutoff gives weak low/mid mapping sensitivity. |
| Vangelead | U+L | L101/0 | Static Lower SuperSaw with delay100; moving Upper two-saw layer. |
| SupaJuce 1 | U | — | Filter envelope. |
| Ambient SQR | U+L | L101/0 | Static Lower two Sines provide no rich harmonic probe; driven, moving Upper and heavy effects. |
| Brassy Ld 1 | U | — | Filter envelope. |

## Artifacts and reproduction

- `static-filter-reference-inventory-2026-09-15.json`: original-source identities, current-codec identities and complete 24-preset decode.
- `static-filter-reference-openings-2026-09-15.json`: window measurements, all conditioning cases and control matrices.
- `static-filter-reference-openings-2026-09-15.png`: opening spectrograms, inspected after generation.

Use a fresh destination for each run:

```sh
python3 Tools/inventory_static_filter_references.py \
  --sources build-fidelity/hardware-benchmark/sources \
  --output build-fidelity/static-reference-inventory-v1
python3 Tools/audit_static_reference_openings.py \
  --inventory build-fidelity/static-reference-inventory-v1/results.json \
  --output build-fidelity/static-reference-openings-v3
```

The first command compiles the small current-codec helper, verifies catalog-pinned original ZIP/MP3 files and freshly decodes the two inspected MP3s with ffmpeg. The second verifies those WAV hashes before analysis. No preexisting unpinned WAV preparation is required. Numerical results are diagnostics only; no DSP or published preset parameters were changed.
