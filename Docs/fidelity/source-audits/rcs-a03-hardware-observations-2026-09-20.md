# RCS A03 Jupiter8wide — locked hardware-only excerpt

2026-09-20. A single attack at approximately **36.764 seconds** in the [author-linked demonstration](https://www.youtube.com/watch?v=8LKRnrs8DcQ) provides a usable held-note trajectory. The locked [case](../reconstructions/expanded/rcs-a03-jupiter8wide.json) spans **36.720–36.980 seconds**, with reconstructed MIDI **45**, velocity 100, onset 0.044 seconds and an artificial note-off at the 0.260-second crop boundary. The next attack/pitch change around 37.01 seconds is excluded. No original performance MIDI is available.

The parent task independently inspected actual paused decoded frames showing **A03 JUPITER-8 WIDE at 35 and 40 seconds**. These support a conservative interior, not exact transitions or continuous numeric patch-state identity. A separate [supplementary catalog](../rcs-a03-reference-catalog.json) records these observations without modifying the older catalog or source audit. The [author's page](https://www.rcssound.com/index.php?page=6) links both the recording and [original eight-patch bank](https://www.rcssound.com/download.php?kod=6).

The unchanged A03 upper square is physically −12 semitones, the upper saw is unshifted, and the lower sine is −12 semitones. All have zero fine tune and tone octave; the stored lower second oscillator is muted. Families near 55 and 110 Hz therefore support played MIDI 45, conditional on neutral system transpose/bend. Eight harmonic peaks in source windows 36.805–36.965 and 36.865–36.945 seconds give median harmonic-implied base frequencies **54.863 and 54.867 Hz**. Modulation delay and short windows can shift local peaks; no retuning was fitted.

The pre-attack interval 36.400–36.750 seconds has RMS approximately **72.6 dB below** the settled 36.850–36.950-second interval. Absolute sample amplitude first exceeds 0.01 at 36.763878 seconds, with small codec pre-echo about 2 ms earlier. The abrupt onset supports the chosen attack, but exact original MIDI timing and capture latency remain unknown. The final note-off is solely an export convention while the hardware note continues; it must not be treated as a measured release.

The same predeclared A02 closure mathematics was applied to **hardware only**: power ratio of 1500–12000 Hz to 300–1500 Hz, Hann windows 512/1024/2048 samples, 44-sample hops, left/right/mid channels, ±10 ms onset sensitivity, median early reference at 15–35 ms, sustained 10 ms threshold crossings and a 30 ms guard. The STFT source-grid origin is **35 seconds**. All 27 settings observe each landmark:

| Relative drop | Minimum elapsed | Median elapsed | Maximum elapsed |
| --- | --- | --- | --- |
| 10 dB | 35.71 ms | 43.71 ms | 52.71 ms |
| 20 dB | 41.69 ms | 52.51 ms | 64.14 ms |
| 30 dB | 59.47 ms | 65.12 ms | 79.61 ms |

These are spectral-ratio landmarks, **not filter attack-duration measurements**. The 1024-sample mid trace reaches approximately −43.46 dB relative to its early reference before the guard; neither band hits the numerical power floor. The upper filter is LP24, cutoff 113, depth −15, ADSR 13/127/127/127, resonance 0, keyfollow 0 and cutoff velocity 0, with drive 33. Upper amp ADSR 0/53/60/16 and lower sine amp ADSR 0/64/0/14 change the layer balance, so the observed trajectory does not isolate a filter law.

Upper modulation delay is enabled at send 127, with raw parameters `[0,53,12,3,49]` (time, encoded feedback, HF damping, modulation rate, modulation depth). Lower delay send is zero and reverb is globally off. Delay phase/history, relative oscillator phase, live controls, original velocity, same-take patch revision, recording path and lossy encoding remain uncertain. A03 is another patch in the same author montage as A02, not another hardware unit or recording session.

The case, hardware trajectory and this source audit were fixed before any A03 Septum output was inspected. Subsequent unchanged-preset baseline rendering characterizes the fixed case; after that it is no longer untouched by all model inspection. No modified candidate or attack probe informed this selection.

[The JSON summary](rcs-a03-hardware-observations-2026-09-20.json) retains source, bank, case, script and analysis hashes. Original temporary SysEx SHA-256: `ac6e5f6c901903172b2b24b35c6a7d36b899818200304d7b8759d5dca1c901dc`. Case SHA-256: `3a14622a07fcfac460b24a015d4a7a34492a225e98d97b7a21ccf409a42c3362`. Full hardware-only observations, input crop and visually inspected plots remain in ignored `build-fidelity/rcs-a03-hardware-observations-2026-09-20/`. Existing source/catalog pins remain unchanged.
