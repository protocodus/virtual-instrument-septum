# Synchronized W4 listening comparison — 2026-09-15

The local player contains **12 comparisons and 36 audio tracks**: dry LP12/LP24 plus all ten frozen named-preset excerpts. Each comparison switches among the public hardware recording, the pre-W4 Septum baseline, and the same frozen W4 candidate. No case was removed based on its result.

- Player: `build-fidelity/saw-w4-listening/run-04/index.html`
- Running local URL: <http://127.0.0.1:8766/run-04/index.html>
- Reproduction tool: `Tools/build_saw_w4_listening.py`
- Template: `Tools/saw_w4_listening.html`
- [Verification receipt and hashes](saw-w4-listening-player-2026-09-15.json)

## Frozen adjustments

The dry tracks use `hardware[t]` against `engine[t − 1406]`. Baseline and W4 share the fixed note-36 scalar for each slope: 4.137125725839024 for LP12 and 3.870462967942607 for LP24. One common **−0.101013 dB** peak-only attenuation applies to all six dry exports. The first 1,406 hardware samples lack paired engine support and are omitted.

Named presets reuse the existing benchmark listening exports byte-for-byte, preserving their saved production-only prefix alignment/gain, shared per-case audition attenuation, stereo, and common coverage. The original-recording clock includes Dist Bs 1's 1.94-second excerpt offset. The five no-Saw controls are labeled, and their baseline/W4 audio exports remain byte-identical: Club Bass, Cotton Wool, Moogie 1, Pedal Bs 1, and Supa Juce 1.

The timeline marks gain-calibration regions and the dry coefficient-training note at 18.75–19.25 seconds. Source switching changes only the playback gains with a 12 ms fade. All sources start on one audio-clock timestamp and offset. Switching dry slopes preserves source time; switching to another preset resets to its original excerpt start.

## Verification

All 36 exported files were checked against their exact declared float32 transformations. Chrome decoded all 36 to the **same sample hashes at 44.1 kHz**, with the expected mono/stereo channel counts. Browser checks covered all 12 synchronized starts, source switching without resetting the timeline, training-note seek/label, slope changes, original excerpt offsets, pause, and end-of-file stopping. No page errors occurred. Desktop and 390-pixel mobile screenshots were reviewed; the mobile page has no horizontal overflow.

The complete browser script, results, screenshots, source receipts, and audio hashes are retained under the player directory. The durable verification receipt also embeds the browser check source. Existing listening players were unchanged.

## Reproduce

```sh
python3 Tools/build_saw_w4_listening.py --official-results build-fidelity/saw-w4-official-comparison/run-01/results.json --output build-fidelity/saw-w4-listening/reproduction
python3 -m http.server 8766 --bind 127.0.0.1 --directory build-fidelity/saw-w4-listening
```

Then open `http://127.0.0.1:8766/reproduction/index.html`. The tool uses the already cached public reference material and frozen render receipts. It does not fit or render new DSP.

This is a listening evaluation, not a hardware-equivalence result. The dry raw preset and original capture chain remain uncertain; the named presets use reconstructed performance MIDI and do not authenticate the exact recorded patch revision. Quantitative outcomes belong to the underlying frozen comparisons, including their contrary results.
