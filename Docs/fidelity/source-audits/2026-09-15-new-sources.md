# Fresh SH-201 source audit

2026-09-15. Existing manual, Editor, circuit, patch-bank and waveform audits were read first. This pass found a previously uncatalogued first-party measurement collection by an SH-201 owner. It supports a narrow LFO correction and a better dry-filter experiment. It does **not** establish whole-instrument equivalence.

## 1. Published hardware LFO and envelope measurements

deep!sonic's [measurement page](https://www.deepsonic.ch/deep/htm/deepsonic_analytics_envelope_lfo_speed.php) links its [original one-page PDF](https://www.deepsonic.ch/deep/docs_misc/deepsonic_analytics_-_envelope_lfo_speed.pdf), dated 13 January 2021. The downloaded PDF was rendered and its column grouping inspected visually. Its SH-201 row states:

| Control | Minimum setting | Maximum setting |
| --- | ---: | ---: |
| LFO cycle duration | 20.59 s | 40.22 ms (24.86 Hz rounded) |
| Envelope attack | 0.6 ms | 25.70 s |
| Envelope decay | 14.0 ms | 31.23 s |
| Envelope release | 2.0 ms | 31.18 s |

**Confidence:** medium for the reported physical endpoint periods; high that these numbers appear in the original document. The page does not identify SH-201 firmware, acquisition settings, uncertainty, exact patches, amplitude thresholds, or which envelope was measured. It provides envelope-shape pictures for other instruments but none for SH-201.

**Action:** adopt the two LFO periods in `mapping::lfoRateHz`, replacing the former voiced 0.03–30 Hz endpoints. Retain logarithmic interpolation as provisional. Do not convert the decay/release figures to a −60 dB coefficient or apply the attack values globally without further evidence. Tempo sync uses its separate documented note table.

The original PDF's SHA-256 is `e9f0cbe732f09d363f11aa650716831db20dab84998165e40c242a7aec5e283f`. Local source and rendered inspection: `build-fidelity/deepsonic/envelope-lfo.pdf` and `envelope-lfo.png`.

## 2. Six dry filter recordings and original performance MIDI

The owner's [filter comparison page](https://www.deepsonic.ch/deep/htm/deepsonic_analytics_filter_comparison.php) supplies six SH-201 recordings: LPF12 and LPF24, each at resonance 0%, 50% and 100%. All six downloaded files fully decode: 44.1 kHz mono, 320 kbit/s MP3, 30.0182 s container duration.

The stated common recipe isolates one saw, disables effects, LFO, velocity response and pitch modulation, tracks cutoff by one octave per keyboard octave, and calibrates a three-octave filter-envelope fall to about one second. It supplies the [original MIDI sequence](https://www.deepsonic.ch/deep/audio_midi/deepsonic_-_filter_demo_-_comparsion_sequence.mid). The recording procedure specifies short boundary fades and permits octave transposition.

**Confidence:** high in the owner's explicit association of audio and MIDI; incomplete for exact patch identity. No SH-201 SysEx or raw cutoff/depth/decay values appear in the inspected page. This is original MIDI with a procedural patch description, not an authenticated byte-identical preset benchmark.

**Action:** use the LP12/LP24 recordings as independent dry filter-shape evidence, holding the stated acoustic calibration fixed and testing resonance/topology across both slopes and several notes. Recover MIDI-to-audio alignment and any octave offset before fitting. A recreated native patch must retain that label.

Acquired originals and hashes are pinned in [the acquisition catalog](deepsonic-acquisition-2026-09-15.json). All media remain under ignored `build-fidelity/deepsonic/`; no third-party audio or patch data are added to the repository.

### Independent MIDI inspection

The 925-byte file has SHA-256 `21ea21b9ba3ba14cc205931134fb7a320b09e67821bd3a3c70f97fa2e8b5d99a`. Byte parsing finds SMF format 0, one track, 480 ticks/quarter, and a 500,000 µs/quarter tempo event (120 BPM). There are 124 note starts and 124 velocity-zero note releases on channel 1; note-on velocity is 127. There are no SysEx, program changes, pitch bends or CCs. The final event is at tick 28,260, or 29.4375 s. The first note is MIDI 24, released after 420 ticks. The local complete event audit is `build-fidelity/deepsonic/midi-audit.json`.

## 3. Firmware and schematic scope

The [Roland support listing](https://www.roland.com/us/products/sh-201/support/) exposes editor/driver downloads, but no SH-201 system-program payload appeared in this bounded search. A generic “SH-201 firmware” result belongs to [Alcad's unrelated HDMI streamer](https://www.alcadelectronics.com/en/product/streamer-1-x-hdmi-ip-9150056) and was rejected. A manuals aggregator's generic update instructions do not prove an updater exists.

The original [Roland service notes, printed pp.14–15](https://www.synthxl.com/wp-content/uploads/2020/01/Roland-SH-201-Service-Manual.pdf#page=14) describe a conditional future updater using numbered SMFs. That is a transport procedure, not available firmware. Fresh inspection of printed pp.32–33 (PDF page 28) identifies the WSP mode straps, `SYSCKO=384fs`, a slave sync setting and separate codec/USB audio links. These establish hardware connections, not oscillator code, envelope coefficients or every block's execution rate. No firmware binary was acquired or executed.

The public [SH201Librarian](https://github.com/r-b-g-b/SH201Librarian) and [pdsh201](https://github.com/becks/pdsh201) remain backup/control projects; their inspected repository pages do not provide DSP firmware. Earlier official Editor payload inspections remain documented in [the previous audit](factory-bank-second-pass.md).

## Selected correction and limits

The LFO endpoint change is the strongest immediately implementable new numerical finding. Its audio test renders a square LFO modulating a clean sine and measures successive energy-envelope rises, independently of the mapping helper. Both LFOs, keyed/free-running operation, and 44.1/48/96 kHz are covered; tempo-synchronized quarter notes provide a separate control.

The new endpoints improve correspondence to the published measurement. The interior rate curve, source uncertainty and audible agreement of arbitrary original presets remain open. The dry-filter dataset is a new route to discriminate larger timbre errors, with its missing raw preset data explicitly retained.

### Focused validation

The Release `SeptumLfoRateFidelityTests` executable passes 64 checks. Across the 12 slot/trigger/sample-rate combinations, measured slow periods span **20.589764–20.590022 s** and fast periods span **40.2076–40.2262 ms**. The period estimator uses 1 ms energy windows; its sub-window interpolation is a numerical test, not evidence that the original hardware was measured to this precision. Eight synchronized controls retain their 0.5 s quarter-note period.

As a negative control, a temporary copy of the same engine with only the previous 0.03–30 Hz mapping restored fails all 24 endpoint comparisons while retaining the other 40 checks. No shipping source was changed for that control.

The existing S&H amplitude continuity test used the median sample-to-sample
change of a three-second random-gain take as its reference. The revised LFO
rate changed how long low-gain plateaus occupied that median: raw 70 failed
the old ratio despite unchanged gain smoothing. The test now keeps its
four-times continuity bound but measures the steady maximum slope of the
same sine with modulation disabled, excluding the initial note attack, and
checks raw rates 70, 100 and 127. The reference slope is 0.001411; the three
modulated maxima are 0.002598, 0.003232 and 0.003560. A temporary engine copy
with the AMP dezipper removed gives 0.019118, 0.030931 and 0.034979, failing
all three checks. This is a continuity regression test, not a claim about
the original unit's modulation smoothing.

```sh
cmake -S . -B build-lfo-rate -DCMAKE_BUILD_TYPE=Release \
  -DSEPTUM_BUILD_PLUGIN=OFF -DSEPTUM_BUILD_TOOLS=OFF -DBUILD_TESTING=ON
cmake --build build-lfo-rate --target SeptumLfoRateFidelityTests --parallel
ctest --test-dir build-lfo-rate -R Septum.LfoRateFidelity --output-on-failure
```
