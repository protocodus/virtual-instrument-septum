# RCS A04 hardware association — 20 September 2026

The [author's video](https://www.youtube.com/watch?v=8LKRnrs8DcQ) visibly shows
**PATCH: A04 JUPITER-8 RESO** at player times 0:48 and 0:58. Root inspected
decoded paused fullscreen frames after stepping one frame past each seek.
These are main video frames, not seek previews. The exact fractional times
of those two observations were not recorded, so the conservative accepted
interior is **49–58 seconds**.

An earlier decoded frame at 0:45 still says **A03 JUPITER-8 WIDE**. It cannot
qualify the preceding audio as A04. Additional decoded frames at 47.42192
and 60.04 seconds show no patch caption; their times were read from the
displayed video's DOM currentTime. Neither captionless frame extends the
accepted interval or establishes an exact transition boundary.

The [supplementary catalog](../rcs-a04-reference-catalog.json) pins the existing
author-linked bank and source recording without changing earlier references.
The extracted original A04 SysEx has SHA-256
`2faa981f99e5a992c532ca8398b268be7ffa01be0f3c74d1b3b6db9252d597ee`;
all 22 temporary DT1 blocks, addresses, payloads and checksums match the bank.
Its delay settings, sends and pan exactly match A03. Overdrive is disabled;
filter cutoff/resonance and amplitude envelopes differ. Detailed extraction
verification is in ignored
`build-fidelity/rcs-a04-source-screen-2026-09-20/patch/fixture-verification.json`.

Labels associate the published preset with the demo but do not authenticate
live numeric settings, absence of edits or capture processing. Original
performance MIDI remains unavailable. Hardware-only passage selection and
stereo qualification must precede a software comparison; this association
alone is not a new sound-match result.
