# SH-201 high-note Saw: source feasibility

2026-09-15. **No primary source found in this bounded pass identifies the classic-Saw antialias algorithm or the measured high-note notch.** The recordings support experiments on an effective response, with its location in the signal path unresolved. No DSP changed. Source receipts and queries are in [the companion JSON](sh201-high-note-source-feasibility-2026-09-15.json).

## Concrete source constraints

- The [official owner's manual](https://cdn.roland.com/assets/media/pdf/SH-201_OM.pdf), printed pp.34–36 and 61, documents a separate FILTER TYPE=BYPASS selection. Turning CUTOFF right raises cutoff. It does not specify automatic bypass at the maximum setting or when key follow/envelope reaches a limit. Thus equal LP12/LP24 high-note spectra do not, by themselves, establish an explicit bypass implementation.
- The [original deep!sonic recipe](https://www.deepsonic.ch/deep/htm/deepsonic_analytics_filter_comparison.php) excludes thru/bypass configurations, requests one saw, and disables pitch/LFO/velocity modulation and effects including EQ. These are procedural instructions, not a captured SH-201 parameter dump. The page prescribes short boundary fades and mono 44.1 kHz/320 kbit/s MP3. Its 96 kHz/24-bit original is an example recommendation. The particular SH-201 audio interface, analog versus USB path, resampler and mono conversion remain unspecified.
- [Pinned original ALSA driver code](https://android.googlesource.com/kernel/tegra/+/275f165fa970174f8a98205529750e8abb6c0a33/sound/usb/usbquirks.h) identifies SH-201 USB ID `0582:00ad`, two standard audio interfaces and a MIDI endpoint. It supplies no oscillator implementation, coefficients or device-specific sample-rate value. This new device-specific code lead cannot establish DSP rate or explain a notch.
- The original [AMAZONA reviewer](https://www.amazona.de/test-roland-sh-201/) reports audible aliasing and uneven waveform timbre across the keyboard. The comparison with another Roland product is a listening analogy, not evidence that SH-201 shares its algorithm. The review supplies no numerical transfer curve or complete raw patch for that observation.

The earlier [service/editor audit](2026-09-15-new-sources.md) and [oscillator semantics audit](oscillator-semantics.md) remain applicable: editor/controller code describes controls, service notes describe hardware and an update procedure, and no DSP firmware payload was recovered. The [Trioda scope audit](public-waveform-recovery-2026-09-15.md) contains unknown-patch sine/mixed-wave images, with no controlled high-note classic saw or numerical sample export.

## Implication for the next experiment

The independent [alias audit](deepsonic-saw-aliases-2026-09-15.md) finds a 44.1 kHz fold family, but the deep minimum in that family changes baseband position with pitch. Its controls rule out the detector or tested MP3 encoding inventing those fold lines; they do not certify every main-harmonic amplitude of the original capture.

Fit any oscillator-smoothing or capture-response candidate against **both main harmonics and aliases on held-out pitches**, preserving both slopes and fixed windows. A fixed notch, short delay sum, moving average, cutoff saturation or an internal oscillator response remains a hypothesis until it makes those predictions. Similar LP12/LP24 output can also mean the active filter is nearly transparent there. No current source warrants selecting a particular JP-8000 algorithm or calling an effective notch correction the original SH-201 implementation.
