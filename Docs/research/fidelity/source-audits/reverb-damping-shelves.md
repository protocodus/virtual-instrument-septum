# Reverb damping shelves

The reverb now realizes its low- and high-frequency damping as complementary first-order shelves. This fixes a numerical mismatch between the damping gains expressed in decibels and the filters that applied those gains. It changes the frequency balance of decaying reverb; direct sound, delay, reverb HIGH CUT, and the reverb's geometry retain their existing models.

## Evidence and implementation

Roland's SH-201 Owner's Manual, printed p. 63, specifies independent LF DAMP GAIN and HF DAMP GAIN controls spanning −36 to 0 dB. It associates each with a frequency separating the range being damped. The manual does not identify the filter order, coefficients, or transition shape. These documented gain semantics support implementing shelves, but they do not prove an exact hardware transfer function. [1]

The previous implementation mixed dry audio with a recursive low-pass smoother. That low-pass has nonzero gain at Nyquist. Consequently, the HF shelf leaked some undamped treble regardless of its requested attenuation, while the LF shelf attenuated high frequencies that should have returned to unity gain. This also made the effective shelf gains depend strongly on host sample rate.

The replacement uses the first-order shelf prototypes described by Julius O. Smith: `H_L(s) = (s + gain) / (s + 1)` and `H_H(s) = (1 + gain*s) / (1 + s)`. A prewarped bilinear transform places the transition at the specified frequency. A direct-form-I low-pass computes complementary low-pass and high-pass outputs; their shelf mixtures reach the requested gain at one endpoint and unity at the other. [2, 3]

Each per-line section retains its preceding input and low-pass output, with both values covered by reset, panic, and denormal handling. Both sections continue updating at 0 dB, with an exact unity output, so a later gain change sees current history. The extra 16 doubles occupy 128 bytes; no additional delay lines or audio-thread allocations are needed. At host rates whose Nyquist frequency is below a published corner, that corner is capped at 0.499 times the sample rate to keep the transition representable and the pole strictly stable.

Preserving actual input/output history also avoids a live-edit problem found during review. A trapezoidal-integrator implementation can accumulate a large hidden state near Nyquist: at 22.05 kHz, a valid HF corner change from 12,500 to 4,000 Hz exposed a 19.05-unit transient from ±0.1 input, despite a −36 dB shelf setting. The direct-form-I realization keeps the same fixed-frequency response and reduces the corresponding worst-case endpoint-edit error across the regression matrix to below 1.4 × 10⁻¹⁸.

## Numerical findings

The following endpoint measurements are for 44.1 kHz. The new endpoints are mathematical properties of the chosen shelf realization, not measurements of an SH-201.

| Setting | Previous Nyquist gain | Corrected Nyquist gain |
| --- | ---: | ---: |
| HF −36 dB, 4,000 Hz | −10.989 dB | −36.000 dB |
| HF −36 dB, 8,000 Hz | −6.318 dB | −36.000 dB |
| HF −36 dB, 12,500 Hz | −4.154 dB | −36.000 dB |
| LF −36 dB, 4,000 Hz | −2.690 dB | 0.000 dB |
| LF −36 dB, 50 Hz | −0.031 dB | 0.000 dB |

This is also audible below Nyquist. With HF damping at −36 dB / 4,000 Hz, the previous single-pass gain at 18 kHz was −10.679 dB; the replacement is −21.107 dB. Because damping occurs inside the feedback network, differences accumulate over the tail.

An integration probe sends a 50 ms, 12 kHz sinusoidal burst through EXT-IN and the production reverb at 44.1 kHz. It uses TIME 100, SIZE 8, HIGH CUT bypass, and separately enables each damping section with a 4 kHz corner. The table measures tail energy from 0.3 to 0.6 seconds, divided by the same render with both damping gains neutral.

| Setting | Previous energy / neutral | Corrected energy / neutral | Change |
| --- | ---: | ---: | ---: |
| LF −36 dB | 0.030617 | 0.628444 | +13.12 dB |
| HF −6 dB | 0.015525 | 0.003286 | −6.74 dB |

The LF correction preserves substantially more upper-frequency reverberation when damping bass. The HF correction reduces the excessive upper-frequency tail when damping treble. A separate deterministic noise-burst comparison with both gains at 0 dB produced bit-identical complete stereo output before and after the isolated change.

## Verification and limits

`Tests/ReverbDampingTests.cpp` checks every published LF and HF corner at six sample rates, including corners above Nyquist. It measures impulse responses rather than reading coefficients to verify endpoint gains, and compares complex responses with an independently specified continuous prototype. It also checks passive transition gains, exact neutral behavior after nonzero state and frequency changes, every pair of published corner edits with non-neutral damping, complete engine tails, and consistent results across 17- and 256-frame processing blocks.

The suite passes 6,846 checks. Linking its integration probes against the saved preceding engine causes both LF and HF tail checks to fail. The shelf unit checks establish the numerical realization; the failing baseline integration checks establish that the defect existed in the production signal path.

Standalone reproduction from the repository root:

```sh
c++ -std=c++20 -O2 -ISource Tests/ReverbDampingTests.cpp Source/DSP/SeptumEngine.cpp -o /tmp/septum-reverb-damping-tests
/tmp/septum-reverb-damping-tests
```

The selected filter order, transition shape, reverb topology, and relationship between per-loop damping and hardware decay remain unverified. Very low host rates cannot preserve a transition frequency beyond Nyquist; the documented cap is a numerical boundary, not a hardware calibration. Establishing exact SH-201 reverb fidelity still requires isolated wet impulse or burst recordings at known settings.

## Sources

1. Roland Corporation. [SH-201 Owner's Manual](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf), 2006, printed p. 63, “EFFECTS parameters.”
2. Julius O. Smith III. [Low and High Shelving Filters](https://www.dsprelated.com/freebooks/filters/Low_High_Shelving_Filters.html), *Introduction to Digital Filters with Audio Applications*, W3K Publishing, 2007.
3. Julius O. Smith III. [Digitizing Analog Filters with the Bilinear Transformation](https://www.dsprelated.com/freebooks/filters/Digitizing_Analog_Filters_Bilinear.html), *Introduction to Digital Filters with Audio Applications*, W3K Publishing, 2007.
