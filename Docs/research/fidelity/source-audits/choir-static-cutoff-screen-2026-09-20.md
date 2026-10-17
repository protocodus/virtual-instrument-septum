# The Choir: static-cutoff screening

2026-09-20. The public [The Choir recording](https://www.rolandus.com/go/sh-201_patches/mp3/PAD/TOP8_The_Choir.mp3)
does not provide an unambiguous dry monophonic or noise-only interval for
choosing between the incumbent raw 69 cutoff of 864 Hz and the experimental 674 Hz.
No model was fitted and no production change was made.

The original patch has one Upper tone with Super Saw plus noise, LP24,
cutoff 69, resonance 60, key follow +90, zero filter-envelope/velocity depths,
LOW FREQ CUT, delay send 75 and reverb send 100. Each sounding key therefore
contributes its own filter corner. A noise-floor fit would combine several
note-dependent filters, detuned saw partials and wet history rather than expose
one static transfer function.

The entire 43.65-second recording was screened. Pitched lines remain prominent
through the final decay. Examples at 36–37 seconds include approximately 117,
233.5, 290.7, 348 and 466 Hz; at 38–39 seconds they remain near 117, 233, 293, 347
and 463 Hz. These lines are **not** asserted to be individual played notes:
Super Saw detuning and harmonic relationships prevent a unique voicing from
this screening. They do show that the tail has not become isolated noise.

The tail also becomes strongly stereo. Side/mid energy is −5.1 dB at 36–37 s,
**+1.5 dB at 38–39 s**, and −0.7 dB at 40–41 s. This is consistent with substantial
wet signal; it prevents interpreting the late spectrum as a clean mono
amplifier release. The two proposed raw 69 corners differ by about 0.36 octave,
equivalent to about 4.8 MIDI semitones under +90 key follow, so unknown voice
allocation is a material confound.

[Measured windows, source hashes and method](choir-static-cutoff-screen-2026-09-20.json)
retain the check. Measurements use a 44.1 kHz float decode, Welch spectra with
16384-sample Hann windows and 65536-point FFTs, and independent mid/side energy.
The strongest 15 local peaks from 70–2000 Hz are reported for each selected
one-second interval. No Septum render informed note inference.

The next viable high-control reference is **Trancefloor**: a single mono tone
with static cutoff 121, zero key follow/envelope/velocity/filter-LFO modulation,
and no overdrive. Its two Super Saw oscillators and effects remain limitations,
but every played note shares the same filter corner. Moving Str. is less
useful because its published filter LFO is active.
