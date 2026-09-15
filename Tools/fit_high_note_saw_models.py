#!/usr/bin/env python3
"""Exploratory classic-saw/FIR source models; no engine or preset correction.

Fits one LP12 high-note window, carries its entire FIR/gain to other pitches,
and fits only phase/DC in those diagnostic passages. These are not blind
holdouts: the passages and candidate families followed exploratory inspection.
A short FIR can represent the oscillator, filter, or capture chain. Numerical
fit does not identify which of those stages produced the observed waveform.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np
from scipy.io import wavfile
from scipy.optimize import minimize_scalar
from render_midi import parse_smf

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "Docs/fidelity/source-audits/deepsonic-acquisition-2026-09-15.json"
SR = 44100
SIZE = 3528
GRID = np.arange(256) / 256
BLENDS = (.5, .75, .8125, .875, .9375, 1.)
COUNTS = (1, 4, 8, 13)
PASSAGES = ((91, 18.75, .10, "training"), (91, 18.75, .16, "same-note-later"),
            (93, 18.25, .10, "other-pitch"), (88, 19.75, .10, "other-pitch"),
            (86, 19.25, .10, "other-pitch"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def design(phase, note, blend, offsets):
    increment = 440 * 2**((note - 69) / 12) / SR
    positions = (phase + increment * (np.arange(SIZE)[:, None] - offsets[None, :])) % 1
    out = 2 * positions - 1
    low = positions < increment
    u = positions[low] / increment
    out[low] -= blend * (2*u - u*u - 1)
    high = positions > 1 - increment
    u = (positions[high] - 1) / increment
    out[high] -= blend * (u*u + 2*u + 1)
    return out


def search_phase(loss):
    scores = [loss(phase) for phase in GRID]
    index = int(np.argmin(scores))
    result = minimize_scalar(loss, bounds=(GRID[index]-1/256, GRID[index]+1/256),
                             method="bounded", options={"xatol": 1e-10})
    # Never discard the observed grid solution if refinement is worse.
    return float(result.x if result.fun < scores[index] else GRID[index])


def train(x, note, blend, offsets):
    centered = x - x.mean()
    variance = np.mean(centered**2)
    def solve(phase):
        matrix = np.column_stack((design(phase, note, blend, offsets), np.ones(SIZE)))
        coef, _, rank, singular = np.linalg.lstsq(matrix, centered, rcond=None)
        prediction = matrix @ coef
        return (float(np.mean((centered-prediction)**2)/variance), coef,
                int(rank), float(singular[0]/singular[-1]))
    phase = search_phase(lambda p: solve(p)[0])
    error, coef, rank, condition = solve(phase)
    return dict(phase=phase, relative_error_power=error, taps=coef[:-1].tolist(),
                dc_fit=float(coef[-1]), rank=rank, condition=condition,
                tap_sum=float(coef[:-1].sum()))


def evaluate(x, note, blend, offsets, taps):
    centered = x - x.mean()
    variance = np.mean(centered**2)
    def prediction(phase):
        p = design(phase, note, blend, offsets) @ taps
        return p - p.mean()
    def loss(phase):
        return float(np.mean((centered-prediction(phase))**2)/variance)
    phase = search_phase(loss)
    p = prediction(phase)
    return dict(phase=phase, relative_error_power=loss(phase),
                rms_ratio=float(np.std(p)/np.std(centered)),
                fitted_gain=False, fitted_phase=True, dc_removed=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    catalog = json.loads(CATALOG.read_text())
    midi_entry = next(a for a in catalog["assets"] if Path(a["path"]).name ==
                      "deepsonic_-_filter_demo_-_comparsion_sequence.mid")
    midi = args.sources / Path(midi_entry["path"]).name
    if sha(midi) != midi_entry["sha256"]:
        raise ValueError("Original MIDI identity changed")
    held, notes = {}, []
    for event in parse_smf(midi.read_bytes())["events"]:
        if event["kind"] != "midi":
            continue
        message = bytes.fromhex(event["hex"])
        status, note = message[0] & 240, message[1]
        if status == 144 and message[2]:
            held[note] = (event["sample"]/SR, message[2])
        elif status == 128 or (status == 144 and not message[2]):
            on, velocity = held.pop(note)
            notes.append((note, on, event["sample"]/SR, velocity))
    if held or len(notes) != 124:
        raise ValueError("Original MIDI note pairing changed")
    for note, on, offset, _ in PASSAGES:
        matches = [n for n in notes if n[0] == note and n[1] == on and n[3] == 127]
        if len(matches) != 1 or on+offset+.04 > matches[0][2]+.035:
            raise ValueError("Passage no longer fits original gate and fixed 35ms onset convention")
    name = "roland_sh-201_-_filter_demo_-_lpf12_q000.mp3"
    entry = next(a for a in catalog["assets"] if Path(a["path"]).name == name)
    mp3 = args.sources / name
    if sha(mp3) != entry["sha256"]:
        raise ValueError("Hardware source identity changed")
    wav = out / "hardware-lp12.wav"
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
               "-i", str(mp3), "-c:a", "pcm_f32le", str(wav)]
    subprocess.run(command, check=True)
    rate, audio = wavfile.read(wav)
    if rate != SR or audio.ndim != 1 or not np.isfinite(audio).all():
        raise ValueError("Unexpected hardware decode")
    passages = []
    signals = []
    for note, on, offset, role in PASSAGES:
        start = round((on + offset - .04) * SR)
        x = audio[start:start + SIZE].astype(float)
        if len(x) != SIZE:
            raise ValueError("Missing passage coverage")
        signals.append(x)
        passages.append(dict(note=note, midi_onset_seconds=on, offset_seconds=offset,
                             role=role, start_sample=start, end_sample=start+SIZE,
                             sample_sha256=hashlib.sha256(x.astype("<f8").tobytes()).hexdigest()))
    protocol = dict(status="exploratory_system_identification_not_engine_validation",
                    sample_rate=SR, window_samples=SIZE, blends=BLENDS, fir_lengths=COUNTS,
                    phase_grid=256, phase_refinement="bounded scalar within one grid spacing",
                    training=passages[0], evaluation=passages[1:],
                    policy="One FIR and gain trained on MIDI91 +100ms. Later passages fit phase and remove DC only. No per-pitch gain, FIR, frequency or time-warp fit.",
                    limitation="FIR has signed taps and noncausal offsets for identification, not a shipping implementation. Phase origin/delay and FIR coefficients are not uniquely identifiable. Candidate grid follows prior exploratory inspection; no blind validation or hardware-equivalence claim.")
    (out / "protocol.json").write_text(json.dumps(protocol, indent=2)+"\n")
    # Recovery verifies the fitter's predicted waveform, not unique tap identity.
    offsets = np.arange(4)-2
    planted = design(.321, 91, .875, offsets) @ np.array([.1,.3,.4,.2])
    control = train(planted, 91, .875, offsets)
    if control["relative_error_power"] > 1e-10:
        raise ValueError("Synthetic fit recovery failed")
    rows = []
    for count in COUNTS:
        offsets = np.arange(count)-count//2
        for blend in BLENDS:
            fitted = train(signals[0], 91, blend, offsets)
            taps = np.array(fitted["taps"])
            evaluations = [dict(passage=p, **evaluate(x, p["note"], blend, offsets, taps))
                           for p, x in zip(passages[1:], signals[1:])]
            rows.append(dict(fir_length=count, blep_correction=blend,
                             tap_offsets=offsets.tolist(), training=fitted,
                             evaluations=evaluations))
            print(count, blend, fitted["relative_error_power"], flush=True)
    result = dict(protocol=protocol, script_sha256=sha(__file__), catalog_sha256=sha(CATALOG),
                  source=entry, original_midi=midi_entry,
                  decode_command=command, decoded_wav_sha256=sha(wav),
                  control=control, models=rows, equivalence_status="not_established")
    (out / "results.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")


if __name__ == "__main__":
    main()
