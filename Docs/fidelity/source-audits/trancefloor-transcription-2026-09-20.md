# Trancefloor: independent high-cutoff reference

2026-09-20. A 1.22-second passage of the public
[Trancefloor recording](https://www.rolandus.com/go/sh-201_patches/mp3/LEAD/TOP8_Trancefloor.mp3)
provides three separated repeated low notes for a comparison at static
cutoff 121. The [reconstruction](../reconstructions/expanded/trancefloor.json)
was prepared entirely from hardware audio and published patch bytes, before
examining any corresponding Septum render.

The original opening contains continuous pitch motion, making a short
note-only reconstruction unreliable. The selected source interval instead
runs from **13.100 to 14.320 seconds**. It starts after a gap and excludes the
next note near 14.332 seconds.

| Event | Estimated source onset | Estimated source note-off | MIDI |
| --- | ---: | ---: | ---: |
| 1 | 13.150 s | 13.500 s | 39 |
| 2 | 13.554 s | 13.894 s | 39 |
| 3 | 13.954 s | 14.294 s | 39 |

Independent spectral windows show strong low families near 38.9 and 77.8 Hz,
with lower-family odd harmonics near 116.7 Hz. Multiple higher harmonics
support this pitch family; individual strongest peaks shift because both
Super Saws have substantial spread. A one-octave-lower family near 19.4 Hz is
much weaker in all three windows. The published Upper tone has oscillator 1
coarse 0, oscillator 2 WIDE off with signed coarse −36 (physical −12 semitones),
and tone octave 0. Thus MIDI 39 is the supported reconstruction. This is not
captured original MIDI or a measurement of every oscillator's detuned pitch.

The original patch is a single mono tone with two Super Saws, LP24 cutoff 121,
resonance 0, and zero key follow, filter envelope depth, velocity sensitivity
and filter-LFO modulation. LOW FREQ is FLAT and overdrive is off. Those controls
make this an independent check of the high cutoff region without multiple
note-dependent filter corners.

Other uncertainties remain. The two spreads are 107 and 108; oscillator 1 has
pitch-envelope depth −30; portamento is enabled. Published delay and reverb
remain on. The crop begins with a quiet wet tail from the prior phrase, while
software starts with empty effects. Original velocity and controllers are
unavailable, so velocity 100 is a placeholder. Estimated onset precision is
about 3 ms and note-off precision about 15 ms. The unmodified preset is used;
none of these uncertainties is corrected by changing its controls.

The subsequent frozen-render comparison **worsens** broad spectral residual
from **2.892 to 3.358 dB** with the experimental Air Lead cutoff table. The
metric uses whole-excerpt stereo Welch power in 32 geometric bands from
25–12,500 Hz, normalized within that range. This is an independent failure of
the proposed high-control interpolation, supporting its rejection as a global
shipping curve. It does not disprove the separate Air Lead raw 91 mismatch or
establish the incumbent raw 121 value as an exact hardware measurement.

The [audit data](trancefloor-transcription-2026-09-20.json) retain source,
bank, complete-patch and reconstruction hashes, raw parameter interpretation,
spectral peaks, octave-band energies and extraction method. The original
recording is associated with the patch on Roland's
[LEAD bank page](https://www.rolandus.com/go/sh-201_patches/patch_lead.html).
