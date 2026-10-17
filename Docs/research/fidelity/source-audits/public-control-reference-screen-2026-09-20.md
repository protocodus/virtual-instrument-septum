# Public control-reference screen — 20 September 2026

No new isolated hardware recording was admitted from this bounded search. The two strongest new leads below require either recovery of the author's files or direct verification of the video's control state. No hardware calibration, waveform replacement or new reconstructed performance follows from their descriptions alone.

## Author-distributed waveform cycles: unavailable

[evilsoft's original SH-201 Sample Pack A post](https://www.dogsonacid.com/threads/sh-201-sample-pack-a.485074/), dated 1 April 2007, describes short recordings of the generated waveforms plus three multisampled leads, and refers readers to `SamplePackA.txt` for details. This is a primary author attribution to SH-201 hardware. It does **not** establish filter bypass, effects status, oscillator balance, normalization, pitch or sample editing. The comment about limited filtering applies to the leads, not necessarily the cycles.

The [author's MediaFire link](https://www.mediafire.com/?2zgmozmielz) redirects to an HTTP 404 page stating “Invalid or Deleted File.” Neither audio nor the README was recovered.

Both pages of the primary thread were inspected, including [page 2](https://www.dogsonacid.com/threads/sh-201-sample-pack-a.485074/page-2), explicitly the final page. No later reply supplies an alternate pack link or attachment. Page 1 resolves a reported playback problem; page 2 promises a future pack without supplying another file.

[Mecha Hate Chimp's subsequent Kontakt instruments](https://www.dogsonacid.com/threads/sh201-kontakt-multi.485260/) explicitly derive from some of those cycles. The revised archive URL shown in that thread, `http://www.aymat.org/temp/samples/-keys%20%26%20synth/SH201-multi.rar`, also returns HTTP 404 HTML. Its original sample contents and any processing remain unknown. Exact filename, README and MediaFire-key searches found no usable copy. Wayback availability/CDX requests returned 429/503, so archival recovery is incomplete, not disproved.

Disposition: potentially useful waveform-shape evidence if the original PCM and README are recovered; currently unavailable and excluded.

A later bounded recovery attempt queried Wayback availability once for each
exact MediaFire, Kontakt RAR and previously audited MaxSynths ZIP URL. The web
tool exposed neither an HTTP response nor a snapshot; all three attempts were
unavailable through that tool. No files were recovered, and archive availability
remains unknown. Exact requests and responses are retained in
`build-fidelity/archive-recovery-2026-09-20/retrieval.json` (SHA-256
`3a68bbfa994555660fc1a9bc17a3d4891c580ad3b628d819cb571413178900e9`).

## Hardware patch-creation video: settings unverified

[Roland sh201 patch creation part 1 (no talking)](https://www.youtube.com/watch?v=zeIHMnVxaQE), published by “something something” on 1 October 2016, is an author-described hardware exploration. The description discusses oscillator, envelope and effects behavior, but supplies no parameter table or patch file establishing a dry, single-oscillator interval. Its title and general description are insufficient to assign exact settings to a recorded sound.

The research agent's browser-control entry point returned no available browser; the web reader could retrieve indexed author metadata but not video frames. The parent task then inspected the opening at 0, 10 and 20 seconds in its functioning in-app browser, including fullscreen. It reported an oblique instrument view, the BALANCE knob near the center at 10/20 seconds, visible LPF selectors but unreadable precise knob values, and effects controls outside the cropped instrument view. No INIT selection or numeric-state capture was observed in those frames. The opening therefore does not establish a dry single oscillator or exact static filter setting. This is a bounded opening inspection, not proof that the entire video lacks useful material. No video was downloaded as a substitute for browser inspection.

The parent task subsequently sampled decoded fullscreen frames at 3:35, 5:59,
9:35 and 10:46. They retain the oblique view; hands obscure controls in several
frames, precise values remain unavailable, and the complete effects state is
outside the crop. These additional observations do not establish an isolated
reference either. They are four sampled later frames, not a continuous review
of all control movements or an assertion that the entire video is unusable.

## Retained acquisition evidence

Ignored local responses and SHA-256 identities are in `build-fidelity/hardware-benchmark/control-source-search-2026-09-20/retrieval.json`. They contain the failed download/archive responses, not audio. Forum text was inspected through the web reader; a direct curl request to the original forum page returned 403, so no local original-post HTML was retained.

This search did not repeat the original-performance-MIDI triplet search, MaxSynths waveform archive, or Trioda phase experiment. No creator was contacted and no benchmark or production DSP changed.
