# SPLIT voice-pool allocation

The [Roland SH-201 Owner's Manual](https://cdn.roland.com/assets/media/pdf/SH-201_OM.pdf)
specifies ten physical voices on p. 74. Page 46 explains that DUAL plays two
tones per key, reducing the simultaneous note count to five. Page 47 describes
SPLIT as selecting UPPER or LOWER according to the key's side of the split.

The old allocator imposed the five-voice per-tone limit in both DUAL and
SPLIT. A six-note chord entirely on one side of a split therefore lost its
oldest voice while five physical voices remained unused. SPLIT now lets
either tone use the shared ten-voice pool; DUAL retains five voices per tone.
Existing released-tail/oldest-note stealing rules handle a full shared pool.

This is an inference from the documented voice budget and one-tone-per-key
SPLIT routing. Roland does not specify a reservation policy or stealing order
for SPLIT, and no isolated hardware allocation measurement is claimed.

`Tests/SplitPolyphonyTests.cpp` checks both single-side ten-note chords, all
unequal two-sided distributions totaling ten notes, cross-part reclamation,
the eleventh-note limit, finite audio, and the unchanged five-plus-five DUAL
allocation at 44.1, 48 and 96 kHz.

Validation: the unchanged baseline fails 42 of 66 focused checks. The corrected
allocator passes all 66. The baseline was compiled with its own original DSP
headers, preventing an ABI mismatch from masquerading as a behavior change.
