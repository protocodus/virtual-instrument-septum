# RCS A01 Moog BASS — hardware-only transcription

2026-09-20. The three separated notes at **9.25–10.07 seconds** in the [author's demonstration](https://www.youtube.com/watch?v=8LKRnrs8DcQ) support a short independent patch comparison. The case and notes were selected using hardware audio only, before rendering Septum. All performance MIDI is reconstructed.

The author provides the [bank publicly](https://www.rcssound.com/download.php?kod=6) from the [RCS sound page](https://www.rcssound.com/index.php?page=6). Its A01 `MoogBass` librarian bytes and `A01 MoogBASS.mid` SysEx bytes agree; the MIDI file contains no played notes. The unchanged temporary patch has SHA-256 `f0dd2c0f662d7e5d466888f01b0b4339ccdd6565bb5441e65dd9efdbedf24a87`. A01 was visibly verified at video times 8 and 15 seconds by the parent task. This brackets the chosen excerpt conservatively but does not prove continuous label or patch-state identity.

The published sound uses one upper tone, saw plus triangle at central balance. Both signed wire coarse values are −36 with WIDE off, which decode to **−12 physical semitones**, with zero fine tune and tone octave. Thus the measured sounding pitches imply played MIDI 60, 63 and 65, conditional on unchanged system tuning and controllers.

| Played MIDI | Sounding pitch | Settled source window | Median harmonic-implied fundamental | Estimated source gate |
| --- | --- | --- | --- | --- |
| 60 | C3 | 9.340–9.440 s | 130.777 Hz | 9.315–9.453 s |
| 63 | E♭3 | 9.620–9.730 s | 155.443 Hz | 9.593–9.735 s |
| 65 | F3 | 9.900–10.000 s | 174.483 Hz | 9.865–10.006 s |

Eight Hann-window FFT harmonic peaks support each pitch. Two-ms RMS at 0.5-ms hops supports the separated gates. Across thresholds of 5–20% of each region's 90th-percentile RMS, start estimates shift by at most 3 ms and end estimates by at most 1 ms. Roughly ±5 ms local event uncertainty remains, in addition to unknown common audio alignment. Zero padding interpolates peaks; it does not improve the short window's intrinsic resolution. The evidence plot was visually checked against the selected notes and boundaries.

The [case](../reconstructions/expanded/rcs-a01-moog-bass.json) uses velocity 100 as an explicit placeholder. Filter velocity +9 and amp velocity +8 make original velocity a timbre/gain confound. Portamento is enabled at raw time 20 in SOLO mode, and the state before the crop is unknown. The settled windows begin 25–33 ms after attacks; onset phase and portamento should not be fitted from this case.

This is useful as an independent **patch-level triangle-candidate guard**, not an isolated triangle measurement. Although delay and reverb are disabled, drive 8 and a resonant LP24 filter remain active: cutoff 39, keyfollow +30%, resonance 10, filter ADSR 8/39/43/47 and depth +32. Actual velocity, possible live controls, same-take patch revision, system settings, recording path and lossy encoding remain unknown. No sound parameters were altered or fitted.

A separate held-note observation at **11.600–11.900 s** has a ~195.986 Hz G3 family (conditionally played MIDI 67). Its measured H2–H6 levels relative to H1 are −13.65, −35.85, −45.24, −53.72 and −64.22 dB. The strong harmonic attenuation is compatible with a changing filter, but the observation cannot uniquely identify filter, envelope, velocity or drive. It is supplemental data, not an additional reconstructed case.

[The JSON summary](rcs-a01-transcription-2026-09-20.json) retains source, case, audit and script hashes plus measured windows and limitations. Full hardware-only analysis, script, plots and original proposal are under the ignored `build-fidelity/rcs-a01-hardware-observations-2026-09-20/` directory. Decoded source WAV SHA-256: `3f55200e611c9f01c3d7cbedba5c089bc021b232e39abd6c2c06a651aee5ecd3`. No software output was inspected for this transcription.
