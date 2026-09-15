#!/usr/bin/env python3
"""Final bounded asymmetric local Saw kernel diagnostic; no shipping DSP edit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np
from scipy.io import wavfile
import fit_high_note_saw_wrap_kernels as symmetric
import fit_high_note_saw_models as fir
import analyze_deepsonic_saw_aliases as aliases
from render_midi import parse_smf

ROOT, SR, SIZE = symmetric.ROOT, symmetric.SR, symmetric.SIZE
WIDTHS = (4., 8.)
BASELINE = ROOT/"Docs/fidelity/source-audits/deepsonic-saw-wrap-kernels-2026-09-15.json"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def design(phase, note, width, basis=None, periodic_sum=False):
    increment = aliases.f0(note)/SR
    if 2*width >= 1/increment:
        raise ValueError("Correction support overlaps adjacent periods")
    basis = symmetric.spline(width)[1] if basis is None else basis
    count = basis.c.shape[1]
    position = (phase+increment*np.arange(SIZE)) % 1
    correction = np.zeros((SIZE, 2*count))
    distances = ([(position-k)/increment for k in (-1, 0, 1)] if periodic_sum
                 else [np.where(position < .5, position, position-1)/increment])
    for distance in distances:
        negative = (distance < 0) & (distance > -width)
        positive = (distance >= 0) & (distance < width)
        correction[negative, :count] += basis(-distance[negative])
        correction[positive, count:] += basis(distance[positive])
    return np.column_stack((2*position-1, correction))


def train(x, note, width):
    basis = symmetric.spline(width)[1]
    centered = x-x.mean()
    variance = np.mean(centered**2)
    def solve(phase):
        matrix = np.column_stack((design(phase, note, width, basis), np.ones(SIZE)))
        coefficient, _, rank, singular = np.linalg.lstsq(matrix, centered, rcond=None)
        condition = float(singular[0]/singular[-1])
        if rank != matrix.shape[1] or condition > symmetric.CONDITION_LIMIT:
            raise ValueError(f"Unidentifiable design: rank {rank}, condition {condition}")
        return float(np.mean((centered-matrix@coefficient)**2)/variance), coefficient, int(rank), condition
    phase = fir.search_phase(lambda p: solve(p)[0])
    error, coefficient, rank, condition = solve(phase)
    count = basis.c.shape[1]
    return dict(phase=phase, relative_error_power=error, coefficients=coefficient[:-1].tolist(),
                gain=float(coefficient[0]), negative_coefficients=coefficient[1:1+count].tolist(),
                positive_coefficients=coefficient[1+count:-1].tolist(), dc_fit=float(coefficient[-1]),
                rank=rank, condition=condition)


def evaluate(x, note, width, coefficient):
    basis = symmetric.spline(width)[1]
    centered = x-x.mean()
    variance = np.mean(centered**2)
    def prediction(phase):
        y = design(phase, note, width, basis)@coefficient
        return y-y.mean()
    def loss(phase):
        return float(np.mean((centered-prediction(phase))**2)/variance)
    phase = fir.search_phase(loss)
    return dict(phase=phase, relative_error_power=loss(phase),
                rms_ratio=float(np.std(prediction(phase))/np.std(centered)),
                fitted_gain=False, fitted_phase=True, dc_removed=True)


def controls():
    rows = []
    for width in WIDTHS:
        knots, basis = symmetric.spline(width)
        positions = np.linspace(0, width, 4001)
        target = np.maximum(1-positions, 0)**2
        nested = np.linalg.lstsq(basis(positions), target, rcond=None)[0]
        max_error = float(np.max(np.abs(basis(positions)@nested-target)))
        if max_error > 1e-12 or np.any(basis(width)) or np.any(basis.derivative()(width)):
            raise ValueError("PolyBLEP nesting or endpoint constraints failed")
        rows_for_width = []
        for name, coefficient in (
                ("polyblep", np.r_[.37, -.37*nested, .37*nested]),
                ("asymmetric", np.r_[.29, -.21*np.cos(np.arange(len(nested))*.31),
                                      .17*np.cos(.43+np.arange(len(nested))*.47)])):
            x = design(.321, 91, width)@coefficient+.013
            if name == "polyblep":
                nesting_error = max(float(np.max(np.abs(design(phase, note, width)@coefficient
                                         -.37*symmetric.design(phase, note, -1)[:, 0])))
                                    for phase in (0., .137, .321, .999) for note in (86, 88, 91, 93))
                if nesting_error > 1e-12:
                    raise ValueError("Independent ordinary polyBLEP waveform nesting failed")
            else:
                nesting_error = None
            fitted = train(x, 91, width)
            y = design(.173, 93, width)@coefficient-.008
            evaluation = evaluate(y, 93, width, np.array(fitted["coefficients"]))
            if max(fitted["relative_error_power"], evaluation["relative_error_power"]) > 1e-9:
                raise ValueError(f"{name} train/other-pitch recovery failed at W{width}")
            rows_for_width.append(dict(id=name, planted_coefficients=coefficient.tolist(),
                                       independent_polyblep_max_absolute_error=nesting_error,
                                       training=fitted, other_pitch=evaluation))
        periodic_errors = [float(np.max(np.abs(design(p, n, width)-design(p, n, width, periodic_sum=True))))
                           for p in (0., .137, .499, .73, .999) for n in (86, 88, 91, 93)]
        if max(periodic_errors) != 0:
            raise ValueError("Nearest-wrap differs from periodic-sum definition")
        rows.append(dict(width_samples=width, knots=knots.tolist(), nested_polyblep_coefficients=nested.tolist(),
                         nested_max_absolute_error=max_error, endpoint_value=0., endpoint_slope=0.,
                         minimum_tested_period_samples=SR/aliases.f0(93),
                         support_half_period_margin_samples=SR/aliases.f0(93)/2-width,
                         periodic_sum_max_absolute_difference=max(periodic_errors), recovery=rows_for_width))
        print("controls", width, "passed", flush=True)
    return rows


def load_inputs(source_folder, out):
    previous = json.loads(BASELINE.read_text())
    if previous["script_sha256"] != sha(symmetric.__file__) or previous["catalog_sha256"] != sha(fir.CATALOG):
        raise ValueError("Symmetric baseline implementation or source catalog changed")
    for name, expected in previous["dependency_sha256"].items():
        if sha(ROOT/"Tools"/name) != expected:
            raise ValueError("Baseline helper changed")
    catalog = json.loads(fir.CATALOG.read_text())
    for key in ("source", "original_midi"):
        entry = previous[key]
        if entry not in catalog["assets"] or sha(source_folder/Path(entry["path"]).name) != entry["sha256"]:
            raise ValueError("Original source identity changed")
    midi = source_folder/Path(previous["original_midi"]["path"]).name
    active, gates = {}, []
    for event in parse_smf(midi.read_bytes())["events"]:
        if event["kind"] != "midi":
            continue
        message = bytes.fromhex(event["hex"])
        status, note = message[0]&240, message[1]
        if status == 144 and message[2]:
            active[note] = (event["sample"]/SR, message[2])
        elif status == 128 or (status == 144 and not message[2]):
            on, velocity = active.pop(note)
            gates.append((note, on, event["sample"]/SR, velocity))
    if active or len(gates) != 124:
        raise ValueError("Original MIDI note pairing changed")
    mp3 = source_folder/Path(previous["source"]["path"]).name
    wav = out/"hardware-lp12.wav"
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(mp3),
               "-c:a", "pcm_f32le", str(wav)]
    subprocess.run(command, check=True)
    rate, audio = wavfile.read(wav)
    if rate != SR or audio.ndim != 1 or not np.isfinite(audio).all():
        raise ValueError("Unexpected hardware decode")
    passages = [previous["protocol"]["training"]]+previous["protocol"]["evaluation"]
    if len(passages) != len(fir.PASSAGES):
        raise ValueError("Passage count changed")
    signals = []
    for p, expected in zip(passages, fir.PASSAGES):
        if (p["note"], p["midi_onset_seconds"], p["offset_seconds"], p["role"]) != expected:
            raise ValueError("Passage selection changed")
        gate = (p["note"], p["midi_onset_seconds"], p["midi_off_seconds"], p["velocity"])
        if gates.count(gate) != 1 or p["end_sample"]/SR > gate[2]+.035:
            raise ValueError("Original MIDI gate/onset convention changed")
        x = audio[p["start_sample"]:p["end_sample"]].astype(float)
        if len(x) != SIZE or hashlib.sha256(x.astype("<f8").tobytes()).hexdigest() != p["sample_sha256"]:
            raise ValueError("Exact baseline hardware passage changed")
        signals.append(x)
    return previous, passages, signals, command, wav


def plot(result, destination):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.5), constrained_layout=True)
    labels = [f"{p['note']} +{round(p['offset_seconds']*1000)}ms"
              for p in [result["protocol"]["training"]]+result["protocol"]["evaluation"]]
    colors = {"polyblep": "#252525", "wrap-W4": "#238b45", "asymmetric-W4": "#1f77b4", "asymmetric-W8": "#d95f02"}
    for row in result["baseline_models"]+result["models"]:
        scores = row["scores"]
        for ax, values in zip(axes.flat, ([100*s["relative_error_power"] for s in scores],
                              [s["harmonics"]["h2_to_h8_rms_error_db"] for s in scores],
                              [s["aliases"]["rms_error_db"] for s in scores])):
            ax.plot(labels, values, "--" if row["id"] in ("polyblep", "wrap-W4") else "-",
                    color=colors[row["id"]], marker="o", label=row["id"])
        if row["id"].startswith("asymmetric"):
            for side in ("negative", "positive"):
                pos = np.array(row["kernel"]["positions_samples"])
                axes[1, 1].plot(-pos if side == "negative" else pos,
                                np.array(row["kernel"][side])/row["training"]["gain"],
                                color=colors[row["id"]], label=row["id"] if side == "positive" else None)
    for ax, title in zip(axes.flat, ("Waveform error power / hardware power (%)",
                  "H2–H8 / H1 magnitude error (RMS dB)", "Hardware-qualified alias error (RMS dB)",
                  "Trained asymmetric correction / gain")):
        ax.set_title(title)
        ax.grid(alpha=.2)
    axes[0, 0].set_yscale("log")
    axes[0, 0].legend(fontsize=8)
    axes[1, 1].set_xlabel("Signed distance from wrap (samples)")
    axes[1, 1].legend(fontsize=8)
    fig.suptitle("Asymmetric local Saw kernels: one training window, fixed shape across pitches\n"
                 "Later windows fit phase/DC only; source/filter/capture attribution remains unknown.", fontsize=13)
    fig.savefig(destination, dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    previous, passages, signals, command, wav = load_inputs(args.sources, out)
    protocol = dict(previous["protocol"])
    protocol.update(widths_samples=WIDTHS,
                    equation="y=gain*(2*phase-1)+negative_basis(abs(t))*negative_coefficients for t<0 or positive_basis(t)*positive_coefficients for t>=0",
                    continuity="C1 on each side of zero; value and slope at zero independent on both sides; jump allowed",
                    zero_endpoint="Independent negative and positive values and derivatives",
                    selection="All predeclared W=4/8 asymmetric models; no post-hoc width or holdout selection",
                    support="Reject any overlap: 2*W must be less than shortest tested period; explicit nearest-wrap vs periodic-sum recovery check",
                    baseline="Hash-verified prior symmetric W4 and ordinary polyBLEP, same fresh-decoded exact passages")
    (out/"protocol.json").write_text(json.dumps(protocol, indent=2)+"\n")
    recovery = controls()
    hardware = [aliases.measure(x, .04, p["note"], 0.) for x, p in zip(signals, passages)]
    models = []
    for width in WIDTHS:
        fitted = train(signals[0], passages[0]["note"], width)
        coefficient = np.array(fitted["coefficients"])
        evaluations = [evaluate(x, p["note"], width, coefficient) for x, p in zip(signals[1:], passages[1:])]
        scores = []
        for p, x, ref, phase in zip(passages, signals, hardware, [fitted]+evaluations):
            y = design(phase["phase"], p["note"], width)@coefficient
            scores.append(dict(passage=p, relative_error_power=phase["relative_error_power"],
                               harmonics=symmetric.compare_harmonics(x, y, p["note"]),
                               aliases=symmetric.compare_aliases(ref, aliases.measure(y, .04, p["note"], 0.))))
        positions = np.linspace(0, width, 321)
        knots, basis = symmetric.spline(width)
        kernel = dict(knots=knots.tolist(), positions_samples=positions.tolist(),
                      negative=(basis(positions)@np.array(fitted["negative_coefficients"])).tolist(),
                      positive=(basis(positions)@np.array(fitted["positive_coefficients"])).tolist(),
                      residual_jump=float(-2*fitted["gain"]+fitted["positive_coefficients"][0]-fitted["negative_coefficients"][0]))
        models.append(dict(id=f"asymmetric-W{int(width)}", width_samples=width, training=fitted,
                           evaluations=evaluations, scores=scores, kernel=kernel))
        print(width, "power", [round(s["relative_error_power"], 8) for s in scores],
              "harmonic", [round(s["harmonics"]["h2_to_h8_rms_error_db"], 3) for s in scores],
              "alias", [round(s["aliases"]["rms_error_db"], 3) for s in scores], flush=True)
    result = dict(protocol=protocol, script_sha256=sha(__file__), baseline_sha256=sha(BASELINE),
                  catalog_sha256=sha(fir.CATALOG), source=previous["source"], original_midi=previous["original_midi"],
                  dependency_sha256={Path(p).name: sha(p) for p in (symmetric.__file__, fir.__file__, aliases.__file__, ROOT/"Tools/render_midi.py")},
                  decode_command=command, decoded_wav_sha256=sha(wav), controls=recovery, models=models,
                  baseline_models=[r for r in previous["models"] if r["id"] in ("polyblep", "wrap-W4")],
                  equivalence_status="not_established")
    (out/"results.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    plot(result, out/"comparison.png")


if __name__ == "__main__":
    main()
