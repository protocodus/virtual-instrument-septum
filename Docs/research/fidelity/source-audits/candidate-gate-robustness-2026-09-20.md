# Candidate ranking under estimated note-gate uncertainty

2026-09-20. The triangle gain **-1.5** candidate retains its whole-excerpt
improvement across the tested Sexy Back, Club Bass and Air Lead gate variants.
That robustness does not make every note closer. Sexy Back's second note shows
a local spectral regression, despite the better aggregate score. The separate
oscillator-balance candidate similarly retains a small aggregate improvement
for Class A while worsening one local note window.

These are bounded paired replay experiments. Both models receive the same
perturbed MIDI and unchanged published preset in each pair. None of the
perturbations replaces the authoritative reconstructed MIDI. The
[summary JSON](candidate-gate-robustness-2026-09-20.json) contains frozen model
identities, exact MIDI hashes, every local regression and a path/hash for the
full locally retained measurement report with all audio and per-window values.

| Case / candidate | Gate variants, including nominal | Whole-excerpt candidate minus baseline | Local window result |
| --- | ---: | ---: | --- |
| Sexy Back / triangle -1.5 | 5 | -0.446 to -0.174 dB | Note 2 worsens in 4/5 variants; nominal +0.698 dB, maximum +0.967 dB |
| Club Bass / triangle -1.5 | 8 | -0.875 to -0.714 dB | All 48 note-window comparisons improve |
| Air Lead 1 / triangle -1.5 | 5 | -1.356 to -0.957 dB | 47/50 windows improve; three first-note residuals increase by only 0.017 dB |
| Class A / oscillator balance | 4 | -0.166 to -0.137 dB | Note 6 worsens by approximately 0.29 dB in all variants |

Negative differences mean lower broad spectral residual. They are not
percentage accuracy, perceptual ratings or a test of identical original MIDI.

Sexy Back shifts the full sequence by +/-10 ms and independently changes
note-offs by +/-10 ms. Club Bass shifts by +/-20 ms, changes note-offs by
+/-20 ms, and separately probes a 10 ms gap or 10/20 ms overlap at its uncertain
F-to-D transition. Air Lead shifts onsets by +/-10 ms or changes nonfinal
note-offs by +/-20 ms. Its artificial final crop release is preserved.
Class A adds 2, 10 or 25 ms overlaps to its adjoining gates, exercising its
SOLO+LEGATO ambiguity. The [input audit](benchmark-input-audit-2026-09-20.md)
explains those uncertainties.

Whole excerpts use the existing 32-band, 25-12,500 Hz normalized Welch-power
metric. Local windows are fixed from the nominal note's onset +30 ms to
note-off -20 ms, shortened before the next note; windows shorter than 30 ms
are omitted. Software measurement windows add its reported 93-sample latency,
without fitting alignment. Short windows have poorer frequency resolution
and some contain effects or pitch motion. Their residuals are diagnostic
checks, not isolated oscillator harmonic estimates. In particular, Sexy Back's
brief second note cannot resolve its sub-25 Hz triangle fundamental precisely.

The 44 complete raw renders report no degraded replay, retain 93-sample
latency, and leave no active voices after the tail. All PCM is finite. Raw
audio, MIDI, replay manifests and the saved `run_audit.py` remain under
`build-fidelity/candidate-gate-robustness-2026-09-20/`. The triangle baseline and
candidate have identical original source-input hash maps; their explicit
triangle calibration profile differs. The balance renderer records its
separate oscillator-only source experiment in its frozen provenance.

To rerun the paired render/score experiment while preserving these results,
copy the saved script into a fresh sibling directory and run it there:

```sh
mkdir build-fidelity/candidate-gate-robustness-reproduction
cp build-fidelity/candidate-gate-robustness-2026-09-20/run_audit.py build-fidelity/candidate-gate-robustness-reproduction/run_audit.py
python3 build-fidelity/candidate-gate-robustness-reproduction/run_audit.py
```

The script requires the original frozen renderers and source comparison
directories retained in this workspace. It refuses to reuse its render output
directory. Its hash and the full report hash are pinned in the summary JSON.

This check supports stability of the aggregate rankings under these specific
gate alternatives. It does not resolve waveform phase, gain, filter response,
unknown performance controllers or recording processing. A global waveform
promotion still requires the independent harmonic checks: consistent local
regressions must not be hidden by a better whole-excerpt average.
