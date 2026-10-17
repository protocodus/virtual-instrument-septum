# Evilsoft waveform-pack recovery: second bounded pass

**No SamplePackA.txt, Evilsoft waveform bytes or controlled dry SH-201 sample
was recovered. No DSP change follows from this search.** This extends the
[earlier recovery audit](public-waveform-recovery-2026-09-15.md), without
reacquiring its Trioda or AMAZONA media.

## Exact original links and archive outcomes

The [original author announcement](https://www.dogsonacid.com/threads/sh-201-sample-pack-a.485074/)
links MediaFire key `2zgmozmielz`. Its unmodified query form,
`https://www.mediafire.com/?2zgmozmielz`, now redirects to a MediaFire error
page with HTTP 404. Thus the earlier failure was not merely caused by an
appended equals sign. Page two contains no alternative download.

The [Kontakt conversion thread](https://www.dogsonacid.com/threads/sh201-kontakt-multi.485260/)
has two distinct Aymat paths: the author's original `/temp/samples/SH201-multi.rar`
and the later corrected `/temp/samples/-keys & synth/SH201-multi.rar`.
The shorter original path also returns a current HTML 404.

Direct Wayback replay requests now return explicit missing-archive pages,
rather than the previous temporary-service failures, for these exact spellings:

| Requested replay | Result |
| --- | --- |
| 2007-04-01 / original MediaFire query | HTTP 404; URL not archived |
| 2007-04-02 / original shorter Aymat path | HTTP 404; URL not archived |
| 2008-02-03 / corrected Aymat path | HTTP 404; URL not archived |
| 2012-12-05 / original MaxSynths Impulses01 ZIP | HTTP 404; URL not archived |

This does not exclude captures under other spellings or unknown mirrors.
A single Aymat-prefix CDX index request still returned HTTP 503 and was not
polled again. Exact filename/key, author, GitHub-index and sample-pack searches
found no identifiable public mirror of the missing pack.

## Internet Archive item search and excluded project

The Archive item catalog responds successfully. The broad SH-201 sample/wave
query returned 15 items: music, manuals and the already-known Vacyd soundset.
The pack-name query returned one unrelated-to-the-pack SH-201 composition,
[Naftaasia's *speak*](https://archive.org/details/speak_466). Its original
metadata describes SH-201 with a distortion pedal and a Renoise arrangement.

A bounded HTTP-range inspection recovered the ZIP directory and `Song.xml`
from its original `Naftaasia-Speak.xrns` project. The directory lists FLACs
named `Recorded Sample`, `b2` and `b3`; the XML includes sampled material and
software percussion instruments. It does not identify which embedded sample
is a dry SH-201 waveform or provide a corresponding SH-201 patch recipe.
No full project, embedded audio or executable was downloaded. This is a new
public project lead, excluded from oscillator calibration after inspection.

## Newly located owner testimony

In [evilsoft's March 2007 SH-201 discussion](https://www.dogsonacid.com/threads/man-i-am-loving-this-sh201.483187/),
the owner calls the envelopes “VERY linear” and explains that he means straight
inter-stage trajectories. Although the quoted reply mentions SH-101, he
explicitly corrects that misunderstanding and says he was discussing SH-201.
This is firsthand but **unmeasured** testimony: no trace, patch, timing or
definition of the measured quantity is supplied. It neither identifies a
normalized envelope law nor resolves the distinction between envelope amount,
cutoff in hertz and logarithmic cutoff. Retain it as contrary qualitative
evidence when assessing curved-envelope hypotheses.

## Durable evidence

The [request catalog](evilsoft-recovery-second-pass-2026-09-15.json) records
exact requested/final URLs, HTTP results, response byte counts and SHA-256,
archive-item metadata outcomes, inspected ZIP entries and XML hashes.
Response bodies remain under ignored
`build-fidelity/public-waveforms/evilsoft-recovery-2`. Hashes identify retrieved
error/catalog responses and partial project ranges, **not recovered sample-pack
archives**. No request bypassed a login, and no external message was sent.
