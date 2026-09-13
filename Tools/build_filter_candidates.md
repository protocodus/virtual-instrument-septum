The default `linear-slow` renderer now uses the production filter-envelope decay
implementation unchanged. `exponential-slow` preserves the experimental
exponential comparison. Both timings come from conditional recording fits,
not a measured Roland envelope specification. The builder works in isolated
source copies and never modifies shipping source or published preset bytes.

Build the shipping DSP support archive, then create a fresh candidate directory:

```sh
cmake -S . -B build-filter-support -DSEPTUM_BUILD_PLUGIN=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build-filter-support --target SeptumDSP
python3 Tools/build_filter_candidates.py --dsp-library build-filter-support/libSeptumDSP.a \
  --output build-filter-support/filter-candidates
```

Each profile contains a standalone `SeptumRenderMidi`, copied source, build log,
and `profile.json` with compiler, command, source, support-library and binary
hashes, plus whether the profile uses the production fit or an experimental
override. The builder refuses an existing output directory. Use `--dsp-library`
or `--compiler` to select another built archive or C++20 compiler.

Defaults reproduce the conditional Moogie fits in
`Docs/fidelity/source-audits/filter-envelope-conditional-fit.json`: raw decay 49
uses a **0.4189852819747085 s linear duration** or a
**0.26557632184918367 s exponential time constant**. The linear profile retains
nominal 2 ms/12 s endpoints using the production provisional power curve; the
exponential profile scales the original exponential decay curve. Other control
values are unmeasured. The linear override changes `mapping::filterDecaySeconds`;
the exponential comparison substitutes its coefficient when the filter envelope
is configured. Both use cached envelope configuration, and neither changes
amplifier envelopes, filter attack/release, or per-control-update processing.
Optional `--linear-seconds` and `--exponential-seconds` overrides are marked as
experiments in the profile metadata.

Use either binary with `Tools/render_midi.py`, the same original `.syx`, the
same reconstructed `.mid`, `--tempo-policy preserve-patch --tail 2
--master-level 100`. The render manifest pins those inputs. Compare raw WAV
hashes with prior renders on the same compiler/platform; hashes of rebuilt
executables may differ with build paths or toolchains. The historical profile
names are retained so existing comparison commands continue to work.
