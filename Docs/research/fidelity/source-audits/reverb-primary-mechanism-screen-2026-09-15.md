# Reverb mechanism screen: no recovered SH-201 network

A bounded primary-source search did not identify the SH-201's reverb network,
delay lengths, shelf coefficients or time mapping. The new
[bus decomposition](reverb-tail-bus-decomposition-2026-09-15.md) therefore
remains a diagnostic of the current model, not a reconstruction of a published
Roland algorithm.

The [SH-201 Owner's Manual](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf),
printed page 63, documents separate high-cut, density, diffusion, LF/HF damping
and time controls. It does not specify a feedback matrix or filter equation.
The [MIDI implementation](https://cdn.roland.com/assets/media/pdf/SH-201_MI.pdf)
maps the damping gains' stored values 0–36 to −36–0 dB; this does not establish
how the coefficients enter a network.

Roland's [COSM Effects List](https://cdn.roland.com/assets/media/pdf/COSM_EffectsList_E_.pdf)
describes low/high damping as filtering sound fed back into an effect, with a
separate post high-cut. This supports feedback damping as a Roland design
convention. Its controls and ranges differ from the SH-201, so it cannot identify
this instrument's implementation or justify copying a decay law.

The patent search was likewise inconclusive:

| Document | Scope and consequence |
| --- | --- |
| [US5543579A, Roland](https://patents.google.com/patent/US5543579A/en) | Divides effect output into mono low frequencies and stereo high frequencies for a speaker system. It does not reveal the effect generator's internal reverb algorithm. |
| [JPH0749694A, Roland](https://patents.google.com/patent/JPH0749694A/en) | Describes a virtual-wall reflection model. The search result supplies no SH-201 product link. No implementation is inferred. |
| [US4955057A, Dynavector](https://patents.google.com/patent/US4955057A/en) | All-pass dispersion in a feedback reverb; a different assignee. |
| [JPH05216489A, Denso Ten](https://patents.google.com/patent/JPH05216489A/en) | Randomized feedback taps/amplitudes in a reverberator; a different assignee. |

Queries combined Roland/“Roland Corporation,” reverberation, digital, feedback,
filter, density and diffusion, plus the exact SH-201 damping-control names.
The two non-Roland documents were excluded after checking their assignees;
sharing a search result is not evidence of product lineage. No coefficient or
topology change follows from this screen.
