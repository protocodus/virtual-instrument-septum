# Reproduce the zero-resonance benchmark

The [reproduction tool](../../../Tools/reproduce_zero_resonance_benchmark.py)
uses the [tracked bundle](zero-resonance-reproduction-2026-09-15.json) to rebuild
the original experiment from repository history. It does not depend on any
ignored frozen-source directory, generated script or decoded WAV.

## Inputs

- A checkout with Git revision `82e6ae9` available, Python with NumPy and SciPy,
  a C++20 compiler, `patch`, and `ffmpeg`.
- The original official MP3/preset-bank cache used by
  `Tools/compare_hardware.py`, acquired with `Tools/obtain_hardware_references.py`.
- The original deepsonic MIDI, LP12/LP24 Q000 MP3s, and cached
  `filter_comparison.html`. Their required hashes are in the bundle; original
  source URLs are in the [acquisition manifest](deepsonic-acquisition-2026-09-15.json)
  and [source audit](2026-09-15-new-sources.md). Decoded WAVs are not prerequisites.

From the repository root, choose a new output directory:

```sh
python3 -B Tools/reproduce_zero_resonance_benchmark.py \
  --output build-fidelity/hardware-benchmark/reproduction-new \
  --sources build-fidelity/hardware-benchmark/sources \
  --deepsonic-sources build-fidelity/deepsonic
```

To verify and materialize the source/profile/recipe files without compiling or
accessing audio caches, supply only `--output NEW_DIRECTORY --materialize-only`.
The tool refuses an existing output directory. It verifies repository and
embedded file hashes, checks relative paths and declared patch targets, then
verifies the resulting 18 frozen DSP/renderer source hashes.

## Outputs and interpretation

The tool builds both the LFO-only control and superseded quadratic candidate
from one frozen source, renders the same ten official cases, and calculates
first-25%-calibrated metrics plus the baseline-transform sensitivity. It also
builds the final linear profile and renders/assesses Dist Bs 1, the only official
case with an active intermediate raw resonance. Results are under `run-01/`
and `linear-final/`.

Next it decodes the original dry MP3s into private float WAVs under
`source-cache/deepsonic/` and replays both dry slopes using the original MIDI.
`source-cache/decode-manifest.json` records ffmpeg version, binary hash, commands,
and original/decoded file hashes. Different decoder versions can produce
different WAV containers or samples; original MP3 identities remain mandatory,
while each run records its own decoded identities.

The captured `run_dry.py` first reproduces the preliminary envelope-correlation
sensitivity. `refine_onset.py` then creates the final shared-onset comparison in
`dry-end-to-end/onset-calibrated/results.json`. The bundle contains only the
same eight training cutoff targets from the original larger trajectory file;
the larger file's original hash is recorded. The resulting small training JSON
has a different container hash, with identical training facts. No validation
targets are used to select the patch.

The captured preliminary script contains an inaccurate descriptive list that
also calls FF54 metadata omitted. The actual render receipts show **only
FF20=00 omitted** and preserve FF54 as metadata. The
[dry audit](dry-end-to-end-2026-09-15.md) records the correction. Captured project
script bytes remain pinned so the historical experiment can be inspected.

No third-party audio, published preset payload or cached HTML is embedded in
the bundle. Full reconstructed SysEx files are generated privately from the
cached preset container and recorded recipe. The source patch is the measured
LFO change present when the experiment was frozen; the profile tables supply
the old control, quadratic experiment and final linear correction independently
of later shipping-source changes.

The output equivalence gate remains **not_established**. Reproducing numbers or
byte-identical renders verifies the experiment, not equality with hardware.

## Verification on 2026-09-15

A complete run from a new output directory succeeded with Python 3.11. All
three rebuilt renderer binaries and all 37 audio renders were byte-identical to
the captured experiment. All ten official metric sets and all eight final dry
result records were exactly equal. The
[verification manifest](zero-resonance-reproduction-verification-2026-09-15.json)
records the command, tool/bundle/decoder hashes and each matching artifact.
This verification used the same compiler and decoder environment; other
platforms should compare their recorded audio and metrics with that qualification.
