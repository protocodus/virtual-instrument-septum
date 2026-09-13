# AMP envelope and voice processing latency

AMP ENV now reaches the voice output at the same time as the oscillator and filter audio it shapes. The oversampled overdrive path introduces numerical transport even when overdrive is off: its clean path uses a matched delay. Applying the current envelope after that delayed audio consumed part of the attack before the note arrived, and started its release too early relative to the same note.

## Evidence and scope

The [Roland SH-201 Owner's Manual](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf), pp. 27 and 38–39, places AMP and its envelope after the filter and defines the attack and release relative to the played note. It does not document a sample offset between those controls and the voice audio. The issue here is introduced by this implementation's oversampling, rather than evidence for a different Roland envelope curve.

Oversampling and antialiasing add processing latency; see Martin Holters, [Antiderivative Antialiasing for Stateful Systems](https://www.mdpi.com/2076-3417/10/1/20), *Applied Sciences*, 2020, section 2. Septum's existing overdrive already compensates the clean path for its integer resampling delay. That delay is 19 samples at 44.1/48 kHz, 16 at 96 kHz and zero at 192 kHz. The current AMP envelope was previously applied without equivalent transport. With the existing minimum one-millisecond attack, this consumed approximately 43%, 40%, 17% and 0% of the attack before the first source sample arrived at those rates.

The correction delays the existing envelope by the same integer voice transport, preserving its time mappings and curvature. It leaves the nonlinear overdrive before the amplitude multiplication. A fixed 32-sample ring per voice is cleared for a fresh note and on reset; a stolen voice retains its envelope history alongside the retained audio transport. After the envelope reaches idle, the voice drains the queued amplitude samples before being freed. Panic still silences it immediately. No allocation occurs while rendering.

This aligns the model's existing integer transport. It does not identify Roland's envelope tables or remove the small frequency-dependent effect and fractional delay of the antiderivative nonlinear shaper. Those are separate calibration and numerical questions.

## Verification

`Tests/AmpEnvelopeLatencyTests.cpp` compares actual clean-voice output against an independent sine multiplied by the requested attack/release envelope, transported together and passed through the separately tested analog output model. The comparison fits only constant gain. It includes the full transient, so a gain fit cannot conceal an advanced attack or release.

| Sample rate | Relative RMS error before | Relative RMS error after |
|---|---:|---:|
| 44.1 kHz | 0.370679 | 3.85 × 10⁻⁸ |
| 48 kHz | 0.348612 | 3.80 × 10⁻⁸ |
| 96 kHz | 0.165102 | 3.33 × 10⁻⁸ |
| 192 kHz | 2.99 × 10⁻⁸ | 2.99 × 10⁻⁸ |

The same tests cover 1-, 37- and 256-sample blocks, voice release after transport drains, and immediate panic. The preceding engine fails 12 of 40 checks; the correction passes all 40. These results establish numerical articulation consistency, not a measured match to SH-201 audio.
