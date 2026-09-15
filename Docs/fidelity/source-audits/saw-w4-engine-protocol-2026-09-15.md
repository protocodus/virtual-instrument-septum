# Full-engine W4 comparison protocol and baseline control

**The comparison tool is ready, and its production-only controls pass. No fitted W4 output has been evaluated.** The protocol follows the [composed-engine proposal](asymmetric-w4-engine-test-proposal-2026-09-15.md), using authoritative shipping source `545b3d37d9cc1f80bf39bc5d0bf49c0cced1d9f6`. It selects no waveform coefficients or new model family.

## Frozen dry comparison

The [protocol JSON](saw-w4-engine-protocol-2026-09-15.json) was written before scoring any candidate. Both slopes use the original124-note Deepsonic MIDI and unchanged physical-recipe SysEx. The baseline audio is the verified full production LP12/LP24 pair from the [high-note baseline](production-high-note-saw-2026-09-15.md). All shipping DSP files are identical to `545b3d3`; the old render's only source difference is the inactive reverb return correction. The builder independently checks fresh current-source baseline identity before fitting.

- Compare original mono with complete engine left channel, requiring the dry stereo channels to agree within float32 precision. No downmix or waveform-phase alignment is fitted.
- The fixed lag is−1406samples:93 renderer samples +44.1 nominal1ms filter attack −1543.5samples for the existing35ms hardware decay-start convention, rounded once.
- Primary gains are4.137125725839024/3.870462967942607 for LP12/LP24, verified from original note36. Baseline and candidate share them. One candidate gain measured on that same complete note36 is a separately labeled sensitivity, never a per-note adjustment.
- Original training samples are66150–85444; paired engine samples64744–84038. No hardware EQ, resampling, time warp, additional delay or local frequency/phase search is allowed.
- **Exclude the entire coefficient-training note91 interval[18.75,19.25) from every primary aggregate.** This is samples[826875,848925) in hardware time. Candidate support uses the same fixed lag.

Primary aggregate supports are:

| Group | Hardware sample ranges, half-open |
|---|---|
| Before note36 calibration | [1406,63945) |
| After calibration, training note91 excluded | [88200,826875), [848925,1324800) |
| All primary coverage | The three ranges above |

The first range starts at1406 because the candidate's negative lag otherwise leaves no paired samples. End1324800 comes from the complete decoded source. All seven retained isolated-note gates are reported separately, together with seven chord gates and their existing late[on+.41,on+.67) supports. Note36 has harmonic calibration diagnostics only. The removed note91 is absent from primary isolated/harmonic validation.

STFT windows are512/1024/2048/8192samples, periodic Hann and quarter-window hop, without padding or boundary extension. Each interval starts a new transform; audio from opposite sides of an exclusion is never concatenated before analysis. Aggregates combine the resulting magnitudes and preserve each interval's first/last frame bounds. RMS windows are10/50ms with220-sample hop, also restarted independently. Reference-only activity masks at−60dB and a−80dB floor are primary; pair-union masks remain a separate sensitivity to candidate-only artifacts. Every resolution, coverage count, log error and RMS result is retained. Raw waveform residual is explicitly phase-sensitive and is not an audibility percentage.

## Harmonic and high-note checks

The existing80ms quadrature/linear-ramp estimator measures isolated notes at+.10/.18/.26/.34s and chord targets at+.46/.54/.62s. It uses nominal original MIDI pitches, up to30 harmonics below8kHz; therefore high notes do not always have every H2–H16 available. A separate unchanged high-note estimator covers the prior five exploratory windows below20kHz.

Original-only eligibility requires fit residual≤1%, condition≤100 and, for H2–H16, magnitude>−45dBc. Chord partials must also be isolated by the existing cluster estimator and have≥20dB noise-proxy SNR. H1 absolute error and H2–H8/H9–H16/H2–H16 ratios and absolute errors are reported independently. An engine fit failure or weak harmonic **cannot remove an original-eligible bin**. Finite estimates from failed fits are marked as proxies; missing candidate estimates prevent a complete-mask statistic and remain counted. Quiet-line and short-window phase sensitivities remain qualifications.

The five prior note91/91/93/88/86 windows retain all original LP12 alias masks9/9/8/11/13, with those same IDs also observed in LP24. They remain exploratory context. The two note91 windows overlap by20ms; neither is counted as independent validation. No earlier oscillator-only polyBLEP score is substituted for this complete engine baseline.

## Production-only control result

| Post-calibration metric | LP12 | LP24 |
|---|---:|---:|
| Spectral convergence,512samples | 0.50054 | 0.49868 |
| 1024samples | 0.36614 | 0.36913 |
| 2048samples | 0.22010 | 0.22561 |
| 8192samples | 0.14190 | 0.16938 |
| Valid isolated harmonic windows | 28/28 | 28/28 |
| Original-eligible isolated H2–H16 bins | 319 | 203 |
| Isolated H1 amplitude RMS error, fixed gain | 0.151dB | 0.132dB |
| Isolated H2–H16 ratio RMS error | 0.729dB | 0.947dB |
| Valid chord windows | 21/21 | 21/21 |
| Original-eligible chord H2–H8 bins | 70 | 33 |
| Chord H2–H8 ratio RMS error | 3.640dB | 7.037dB |

These numbers use the newly declared exclusion/coverage and are not replacements for differently scoped prior metrics. Baseline fits pass the chosen hardware windows, while weak engine bins remain visible: one isolated bin per slope, eight LP12 chord bins and one LP24 chord bin.

Controls pass for both slopes:

- Production versus itself gives exactly zero STFT and waveform error.
- Adding an amplitude100 corruption only inside the excluded training interval leaves all validation metrics unchanged, both at zero lag and at the paired−1406sample lag.
- A single-sample change just outside the exclusion is detected at all four STFT resolutions and by waveform error.
- Marking an otherwise measured candidate fit invalid and every harmonic weak leaves original masks and denominators unchanged.
- Removing candidate estimates leaves their required-bin count intact and suppresses the complete-mask summary.

## Ten current official preset inputs

The [verified input inventory](saw-w4-official-inputs-2026-09-15.json) contains exact WAV, original SysEx, reconstructed MIDI, hardware excerpt and render-receipt paths/hashes for all ten named cases. Current shipping WAVs live at:

`build-fidelity/hardware-benchmark/reverb-return-integration/run-01/renders/legacy/{case}/shipping.wav`

That directory also contains `shipping.render.json`, `original-patch.syx` and `reconstructed-performance.mid`. The inventory preserves every original source/case qualification and render setting.

Factory timing and evaluated sample ranges are inherited from the production-only first-quarter policy in `reverb-gain-candidates/run-01/results.json`. The **current-half-return** prefix scalar is copied from the saved `gain-0.5` row and independently reproduced from the current shipping WAV, within1e−12. Both baseline and W4 will share it; a W4 prefix gain is sensitivity only. The older pre-return scalar remains recorded for optional sensitivity. No candidate influenced these choices.

Active classic Saw: Air Lead1, Brassy Ld1, Dist Bs1, So Juno1, Vangelead. Club Bass, Cotton Wool, Moogie1, Pedal Bs1 and Supa Juce1 are unchanged-waveform byte-identity controls. Exact recorded patch revisions and original performance MIDI remain unverified for this separate public-demo corpus.

## Interface and receipt

Tool: `Tools/assess_saw_w4_engine.py`. A candidate directory contains `manifest.json` and `lp12/`, `lp24/`, each with the builder's `candidate.wav`, `candidate.render.json`, `patch.syx`, `performance.mid`, `experiment-render.json`, coefficient JSON and native configuration. The root manifest must contain `selection: {path, sha256}` pointing to the frozen fitter `candidate.json`.

The scorer verifies the per-render experiment receipt because runtime coefficient configuration is not captured by the ordinary WAV sidecar alone. It checks the authoritative source revision and original/frozen source hashes, renderer, exact input events/settings, output hashes,32 selected coefficients, unit ramp, canonical phase0 and native configuration. Candidate-specific provenance checks will be exercised when the actual fitted bundle exists; this receipt covers the baseline/control path only.

```sh
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 python3 Tools/assess_saw_w4_engine.py \
  --sources build-fidelity/deepsonic \
  --output build-fidelity/saw-w4-engine-assessment/new-baseline-control

# After the separate fit and its engineering gates are frozen:
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 python3 Tools/assess_saw_w4_engine.py \
  --sources build-fidelity/deepsonic \
  --candidate-root w4=/absolute/path/to/frozen-candidate-root \
  --output build-fidelity/saw-w4-engine-assessment/new-candidate-comparison
```

Baseline run: `build-fidelity/saw-w4-engine-assessment/baseline-control-03` (approximately one minute, single BLAS thread). The [complete compact receipt](saw-w4-engine-baseline-control-2026-09-15.json) preserves every parsed result; JSON data were checked equal to the full run. SHA-256:

- Tool: `72fe13d7412913b99b4f96c9d19ce987a3d39c8e04827ad9853bde9d26371350`.
- Protocol: `f3c4341fee46f8e43ebe71e4937d23bc1748f44adcface88db54e6811be97f90`.
- Compact baseline receipt: `e6387967e77ba51c24d1fbfacd7f90f7829cda4e411e33e0a247a2925817a4be`.
- Full run results: `5f865b1cd08a8f5580d80108c41b3f2715308936b87f53f8165eac7f6eff3c72`.
- Official input inventory: `9bf636d72ff15b00135258f5924798af9c2ecd81556534d485a0a0e4a700402e`.

No Source edits, new synthesis, candidate fitting, staging or commits were performed by this scorer task. Hardware equivalence remains unestablished.
