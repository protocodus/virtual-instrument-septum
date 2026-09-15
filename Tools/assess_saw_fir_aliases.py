#!/usr/bin/env python3
"""Check alias constraints separately from the exploratory saw/FIR power fit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np
from scipy.io import wavfile
import analyze_deepsonic_saw_aliases as aliases
import fit_high_note_saw_models as fitter


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def key(line):
    return line["rate_hypothesis_hz"], line["parent_harmonic"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh output file")
    inputs = args.experiment / "results.json"
    raw = json.loads(inputs.read_text())
    if raw["script_sha256"] != sha(fitter.__file__):
        raise ValueError("Fitted waveform implementation changed")
    wav = args.experiment / "hardware-lp12.wav"
    if sha(wav) != raw["decoded_wav_sha256"]:
        raise ValueError("Hardware decode changed")
    rate, audio = wavfile.read(wav)
    if rate != fitter.SR:
        raise ValueError("Unexpected sample rate")
    passages = [raw["protocol"]["training"], *raw["protocol"]["evaluation"]]
    references = []
    for p in passages:
        x = audio[p["start_sample"]:p["end_sample"]].astype(float)
        if hashlib.sha256(x.astype("<f8").tobytes()).hexdigest() != p["sample_sha256"]:
            raise ValueError("Hardware passage changed")
        observation = aliases.measure(x, .04, p["note"], 0.)
        references.append(dict(passage=p, observation=observation))
    results = []
    for model in raw["models"]:
        offsets = np.array(model["tap_offsets"])
        taps = np.array(model["training"]["taps"])
        phases = [model["training"]["phase"], *[e["phase"] for e in model["evaluations"]]]
        rows = []
        for reference, phase in zip(references, phases):
            p = reference["passage"]
            y = fitter.design(phase, p["note"], model["blep_correction"], offsets) @ taps
            observed = aliases.measure(y, .04, p["note"], 0.)
            by_key = {key(line): line for line in observed["tested_alias_lines"]}
            selected = [line for line in reference["observation"]["tested_alias_lines"]
                        if line["rate_hypothesis_hz"] == 44100 and line["passes_line_threshold"]]
            comparisons = []
            for h in selected:
                c = by_key[key(h)]
                comparisons.append(dict(parent_harmonic=h["parent_harmonic"],
                    expected_hz=h["expected_hz"], hardware_relative_h1_db=h["relative_h1_db"],
                    model_relative_h1_db=c["relative_h1_db"],
                    model_minus_hardware_db=c["relative_h1_db"]-h["relative_h1_db"],
                    model_local_prominence_db=c["local_prominence_db"],
                    model_has_interior_local_peak=c["genuine_interior_local_peak"],
                    model_passes_full_threshold=c["passes_line_threshold"]))
            errors = np.array([c["model_minus_hardware_db"] for c in comparisons])
            rows.append(dict(passage=p, hardware_qualified_lines=len(comparisons),
                             median_difference_db=float(np.median(errors)) if len(errors) else None,
                             fixed_bin_rms_difference_db=float(np.sqrt(np.mean(errors**2))) if len(errors) else None,
                             comparisons=comparisons))
        results.append(dict(fir_length=model["fir_length"], blep_correction=model["blep_correction"], passages=rows))
    output = dict(status="exploratory_fixed_hardware_mask_no_model_selection",
                  waveform_fit_sha256=sha(inputs), source_audio_sha256=sha(wav),
                  script_sha256=sha(__file__), waveform_tool_sha256=sha(fitter.__file__),
                  alias_tool_sha256=sha(aliases.__file__),
                  qualification="Aliasing levels remain separate from main-waveform fit. Hardware-only eligibility; unresolved model peaks are residual-level upper-bound proxies. No new fit, gain, delay, phase or candidate selection in this assessment.",
                  references=references, results=results)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, allow_nan=False)+"\n")


if __name__ == "__main__":
    main()
