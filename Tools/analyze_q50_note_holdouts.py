#!/usr/bin/env python3
"""Localize Q50 audio errors on the eight previously declared isolated holdouts.

Exploratory follow-up to whole-segment scores; no parameters are fitted here.
Uses each recorded training gain and shared lag with the frozen assessor.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from scipy.io import wavfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output file")
    base = args.experiment_dir.resolve()
    results = json.loads((base / "results.json").read_text())
    recipe = json.loads((base / "q0-recipe-source.json").read_text())
    source = json.loads((base / "source-manifest.json").read_text())
    assessor_path = base / "frozen-source/Tools/assess_hardware_equivalence.py"
    if sha(assessor_path) != source["input_sha256"]["Tools/assess_hardware_equivalence.py"]:
        raise ValueError("Frozen assessor identity changed")
    sys.path.insert(0, str(assessor_path.parent))
    import assess_hardware_equivalence as assessor
    notes = recipe["protocol"]["isolated_validation_notes"]
    decode = json.loads((base / "source-cache/decode-manifest.json").read_text())
    hardware = {}
    for slope in (12, 24):
        path = base / "source-cache" / f"roland_sh-201_-_filter_demo_-_lpf{slope}_q050.wav"
        identity = next(item for item in decode["files"] if Path(item["command"][-1]).name == path.name)
        if sha(path) != identity["decoded_sha256"]:
            raise ValueError("Decoded hardware identity changed")
        sr, audio = wavfile.read(path)
        if sr != 44100 or audio.ndim != 1 or not np.isfinite(audio).all():
            raise ValueError("Unexpected hardware audio format")
        hardware[slope] = audio.astype(float)
    rows = []
    for case in results["results"]:
        family, slope, raw = case["family"], case["slope"], case["raw_resonance"]
        path = base / "renders" / f"{family}-lp{slope}-raw{raw}" / "raw.wav"
        if sha(path) != case["receipt"]["render_sha256"]:
            raise ValueError("Raw render identity changed")
        sr, stereo = wavfile.read(path)
        if sr != 44100:
            raise ValueError("Render sample rate changed")
        h, c, lag = hardware[slope], stereo[:, 0].astype(float), case["lag_samples"]
        for note in notes:
            a, b = max(round(note["on"] * sr), -lag), min(round(note["off"] * sr), len(c) - lag)
            rows.append({"family": family, "slope": slope, "raw_resonance": raw,
                         "note": note, "reference_samples": [a, b], "gain": case["gain"], "lag_samples": lag,
                         "metrics": assessor.measure(h[a:b, None], c[a+lag:b+lag, None] * case["gain"], sr)})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"schema_version": 1, "status": "exploratory_holdout_localization",
          "experiment_results_sha256": sha(base / "results.json"), "script_sha256": sha(Path(__file__)),
          "policy": "No new fitting. Eight original isolated validation notes from the committed Q0 protocol; each note-on to note-off interval measured separately with inherited training gain/lag. Analysis motivated by different before/after-training rankings; not an independent acceptance test.",
          "results": rows}, indent=2, allow_nan=False) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
