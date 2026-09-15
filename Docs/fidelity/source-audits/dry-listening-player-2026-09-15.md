# Synchronized dry listening comparison

The [local player](http://127.0.0.1:58512/) presents both original dry filter
recordings alongside the shipping DSP and the frozen exponential-in-Hz
envelope experiment. All use the owner's original performance MIDI; the
hardware's raw preset remains unavailable. This is a listening artifact,
not a new fit or an equivalence result.

The page starts all three sources at one Web Audio timestamp and switches
their gains with a 12 ms crossfade. Filter slope, transport, seeking and
passage buttons allow comparison at the same position. The experimental
model is labeled throughout and remains separate from production.

## Preserved audio adjustments

The builder verifies the existing render/assessment manifest identities,
each candidate WAV and the decoded hardware hash. It uses the existing
−1406-sample alignment and each candidate's one gain from the original
MIDI36 training passage. No timing, phase or level is fitted again.

Hardware starts at sample 1406; candidate audio starts at sample zero.
Both end at the last shared frame. A single common attenuation per slope
sets hardware RMS at most 0.1 and every track peak below 0.98. Six mono
float32 WAVs preserve relative candidate levels. The browser may resample
them to its audio-device rate; the exported files remain 44.1 kHz.

All six exports were independently recomputed from source samples and
frozen gains and match bit-for-bit. They contain 1,323,394 finite samples
each, with peaks 0.518–0.610. HTTP responses match their recorded hashes.
Browser checks verified loading, source switching, slope selection,
passage navigation, play/pause and layout, with no JavaScript errors.
The page's wording was then clarified without changing audio or transport.
These checks verify the artifact's construction and controls, not a
subjective listening judgment.

The [receipt](dry-listening-player-2026-09-15.json) retains all six export
hashes, adjustments, underlying measurements, script/template identities
and verification results. Original media and exported WAVs remain in the
ignored build directory.

## Reproduce

Use the frozen [dry engine replay](dry-envelope-engine-2026-09-15.md) inputs
and choose a new output directory:

```sh
python3 Tools/build_dry_benchmark_player.py \
  --experiment build-fidelity/envelope-hypothesis/dry-v2 \
  --assessment build-fidelity/envelope-hypothesis/dry-v2/evaluation-02 \
  --output build-fidelity/dry-listening/new-run

python3 -m http.server 58512 --bind 127.0.0.1 \
  --directory build-fidelity/dry-listening/new-run
```

The retained run is `build-fidelity/dry-listening/run-03`. Its local server
is available during this session. The original recording chain and
oscillator phase remain uncertain; the earlier preset evaluation gives
mixed results for this envelope experiment. No default changed here.
