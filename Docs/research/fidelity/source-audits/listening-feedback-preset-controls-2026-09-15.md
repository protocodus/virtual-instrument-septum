# Listening feedback: exact preset control context

**Three of the four patches already use resonance raw 0 on every active tone.** Dist Bs 1 differs: Upper resonance is 31, Lower is 0. The user hears less resonance in Septum than in the original Moogie 1 and Cotton Wool recordings. That observation concerns the effective DSP response or another contributor to the sound; increasing stored preset values would stop comparing the same preset. The current investigation preserves the original values.

This is a read-only extraction from the exact benchmark SysEx files. All 22 DT1 packets per patch pass framing, address, seven-bit payload and checksum checks. The filter, AMP, drive, level and send fields independently reproduce the prior native decoder values. No parameter, MIDI, coefficient, gain or audio result was changed.

## Active tone controls

A/D/S/R are the stored integer attack/decay/sustain/release controls, **not milliseconds**. Envelope depth and velocity sensitivity are signed decoded values. Key follow is the decoded percentage. All filters below are low-pass. No active tone has a nonzero stored filter-LFO depth; all four reconstructed performances use velocity 100.

| Patch / active tone | Slope | Cutoff / resonance | Key follow / cutoff velocity | Filter A/D/S/R; depth | AMP A/D/S/R | LF / drive |
|---|---|---|---|---|---|---|
| Vangelead Upper | 12 dB | 58 / 0 | +80% / 0 | 36/33/72/92; +17 | 10/0/127/64 | Flat / off |
| Vangelead Lower | 12 dB | 101 / 0 | 0% / 0 | 0/0/0/0; 0 | 76/127/100/76 | Flat / off |
| Moogie 1 Upper | 24 dB | 30 / 0 | 0% / 0 | 0/49/0/0; +22 | 0/0/127/3 | Boost / off |
| Moogie 1 Lower | 24 dB | 47 / 0 | 0% / 0 | 0/37/0/127; +15 | 0/69/127/3 | Flat / off |
| Dist Bs 1 Upper | 24 dB | 36 / 31 | 0% / 0 | 0/64/0/0; +22 | 0/0/127/0 | Boost / on, 100 |
| Dist Bs 1 Lower | 24 dB | 57 / 0 | 0% / 0 | 0/37/0/127; +15 | 0/69/127/0 | Boost / off |
| Cotton Wool Upper | 24 dB | 0 / 0 | +60% / +18 | 10/58/87/105; +39 | 0/0/127/39 | Flat / off |

## Shared controls and important distinctions

- **Vangelead attack:** the DUAL patch has two distinct amplitude attacks: Upper raw 10 and Lower raw 76. Upper filter attack is also nonzero at 36; Lower filter envelope depth is zero. Upper level is 127 and Lower level 59. The Lower Super Saw is a slow layer beneath Upper classic Saws; active delay sends 56/100 further complicate the apparent onset. “Increase attack” does not yet identify AMP versus filter attack or which layer. Global attack retiming would also affect other presets and the dry reference recipe.
- **Moogie and Dist:** both are DUAL, use 24 dB filters, have zero filter velocity sensitivity, zero filter attack/sustain, and the same Lower filter decay/depth pair 37/+15. Upper filter depth is +22 in both, with differing decay 49 versus 64. Their dry source mixtures differ; Dist additionally enables Upper drive 100 and boosts both tones' low-frequency paths. Moogie boosts only Upper. Delay and reverb are disabled in both. A shared resonance/low-bass discrepancy cannot be attributed to wet effects, and Dist's drive/boost and Upper raw 31 prevent treating it as the same response as Moogie's raw 0.
- **Cotton:** SINGLE Upper uses a Super Saw plus an octave-lower sine, so the classic-Saw W4 change is byte-inactive. Filter envelope depth +39, decay 58 and sustain 87 differ substantially from the dry saw recipe. Short reconstructed gates may enter filter release 105 before completing decay, and AMP release is 39. Filter velocity sensitivity +18 makes the unknown original velocity an important brightness confound; the fixed reconstructed 100 was never estimated from Septum audio. Delay is switched on but send is 0; active reverb send is 35. A “faster filter decay” hypothesis must be separated from note-off/release and velocity uncertainty.

Moogie also has no active classic Saw and was byte-identical before/after W4. These two listening observations therefore describe remaining baseline behavior, rather than a regression introduced by that waveform change. Preset bytes are published originals, but recording-specific revisions, original velocities and exact key gates remain unverified.

## Reproduction

```sh
python3 Tools/inspect_listening_feedback_presets.py \
  --output /tmp/listening-feedback-preset-controls.json
```

The [complete receipt](listening-feedback-preset-controls-2026-09-15.json) contains the exact patch hashes, raw Upper/Lower blocks, active routing, oscillator settings, field offsets, source inventory hashes and decoded values. This note identifies control relationships; it proposes no fitted value or DSP promotion.
