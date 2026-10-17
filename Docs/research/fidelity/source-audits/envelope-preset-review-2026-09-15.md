# Independent preset-holdout protocol review

The completed `preset-holdouts-v1` experiment passes the reviewed mechanics:
production alone selects the lag from the first 25%; every candidate uses
that lag, a single training-only gain, and identical evaluation coverage.
Both timelines remain outside calibration during evaluation. The fixed
production-gain sensitivity is retained. Input and renderer hashes are checked.

All **40 listening WAVs across ten presets** were independently reproduced
bit-for-bit from the recorded sample ranges, lag, training gain and common
listening scalar. Playback therefore uses the same transforms as measurement.

The zero-filter-depth Air Lead 1 and Club Bass controls are **byte-identical**
for production, Hz tau49=0.15 and log tau49=0.27:

| Preset | Shared raw WAV SHA-256 |
| --- | --- |
| Air Lead 1 | `43bca32341c215f6ccfe58291f787a7c286602f8772061e26d59566921c591e3` |
| Club Bass | `d5fab55b6cfccca0cbe60161eb8fdcfbcf24618e2d4d2b7333b7824fde50a61e` |

These complete-audio controls show that the experimental transform leaves
output unchanged when the filter envelope has no depth in these two fixtures.
They strengthen the earlier AMP/pitch source-isolation review, without
establishing behavior for every parameter combination or hardware equivalence.

The [review record](envelope-preset-review-2026-09-15.json) pins the experiment,
tool, control hashes, all sample ranges and listening verification counts.
No consequential protocol defect was found; no experiment code was edited.
