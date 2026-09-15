#!/usr/bin/env python3
"""Exploratory pitch-shared local Saw wrap corrections; never edits engine DSP.

One LP12 MIDI91 +100ms passage trains every coefficient and gain. Later
passages allow phase and DC only. This mathematical source model cannot
separate the oscillator from the high-note filter or unknown capture path.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np
from scipy.interpolate import BSpline
from scipy.io import wavfile
import analyze_deepsonic_saw_aliases as aliases
import fit_high_note_saw_models as fir
from render_midi import parse_smf

ROOT = Path(__file__).resolve().parents[1]
SR, SIZE = 44100, 3528
WIDTHS = (2., 3., 4.)
CONDITION_LIMIT = 1e6


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def spline(width):
    # Double interior knots make C1 cubics. This includes a C1 piecewise
    # quadratic polyBLEP exactly, instead of silently approximating its join.
    knots = np.r_[np.zeros(4), np.repeat(np.arange(.5, width, .5), 2),
                  np.full(4, width)]
    count = len(knots)-4
    # At the clamped right endpoint only the final basis has nonzero value,
    # and only the final two can have nonzero first derivative.
    return knots, BSpline(knots, np.eye(count)[:, :-2], 3, extrapolate=False)


def design(phase, note, width, basis=None):
    increment = aliases.f0(note)/SR
    position = (phase+increment*np.arange(SIZE)) % 1
    naive = 2*position-1
    distance = np.where(position < .5, position, position-1)/increment
    if width == 0:
        return naive[:, None]
    if width == -1:
        magnitude = np.maximum(1-np.abs(distance), 0)**2
        return (naive+np.where(distance >= 0, 1., -1.)*magnitude)[:, None]
    basis = spline(width)[1] if basis is None else basis
    mask = np.abs(distance) < width
    corrections = np.zeros((SIZE, basis.c.shape[1]))
    corrections[mask] = (np.where(distance[mask] >= 0, 1., -1.)[:, None]
                         * basis(np.abs(distance[mask])))
    return np.column_stack((naive, corrections))


def train(x, note, width):
    basis = spline(width)[1] if width > 0 else None
    centered = x-x.mean()
    variance = np.mean(centered**2)
    def solve(phase):
        matrix = np.column_stack((design(phase, note, width, basis), np.ones(SIZE)))
        coefficient, _, rank, singular = np.linalg.lstsq(matrix, centered, rcond=None)
        condition = float(singular[0]/singular[-1])
        if rank != matrix.shape[1] or condition > CONDITION_LIMIT:
            raise ValueError(f"Unidentifiable kernel design: rank {rank}, condition {condition}")
        error = float(np.mean((centered-matrix@coefficient)**2)/variance)
        return error, coefficient, int(rank), condition
    phase = fir.search_phase(lambda p: solve(p)[0])
    error, coefficients, rank, condition = solve(phase)
    return dict(phase=phase, relative_error_power=error,
                coefficients=coefficients[:-1].tolist(), dc_fit=float(coefficients[-1]),
                rank=rank, condition=condition, gain=float(coefficients[0]),
                kernel_coefficients=coefficients[1:-1].tolist())


def evaluate(x, note, width, coefficients):
    basis = spline(width)[1] if width > 0 else None
    centered = x-x.mean()
    variance = np.mean(centered**2)
    def prediction(phase):
        p = design(phase, note, width, basis)@coefficients
        return p-p.mean()
    def loss(phase):
        return float(np.mean((centered-prediction(phase))**2)/variance)
    phase = fir.search_phase(loss)
    p = prediction(phase)
    return dict(phase=phase, relative_error_power=loss(phase),
                rms_ratio=float(np.std(p)/np.std(centered)),
                fitted_gain=False, fitted_phase=True, dc_removed=True)


def compare_harmonics(x, y, note):
    _, inverse, _ = aliases.harmonic_model(note, SIZE)
    def amplitudes(signal):
        coefficients = inverse@signal
        return np.array([np.hypot(coefficients[3+6*h], coefficients[4+6*h])
                         for h in range(8)])
    a, b = amplitudes(x), amplitudes(y)
    hardware = 20*np.log10(a/a[0])
    model = 20*np.log10(np.maximum(b, 1e-20)/b[0])
    difference = model-hardware
    return dict(harmonics=list(range(1, 9)), hardware_relative_h1_db=hardware.tolist(),
                model_relative_h1_db=model.tolist(), model_minus_hardware_db=difference.tolist(),
                h2_to_h8_rms_error_db=float(np.sqrt(np.mean(difference[1:]**2))))


def compare_aliases(hardware, model):
    model_by_key = {(r["rate_hypothesis_hz"], r["parent_harmonic"]): r
                    for r in model["tested_alias_lines"]}
    rows = []
    for reference in hardware["tested_alias_lines"]:
        if reference["rate_hypothesis_hz"] != 44100 or not reference["passes_line_threshold"]:
            continue
        candidate = model_by_key[(44100, reference["parent_harmonic"])]
        rows.append(dict(parent_harmonic=reference["parent_harmonic"],
                         expected_hz=reference["expected_hz"],
                         hardware_dbc=reference["relative_h1_db"],
                         model_dbc=candidate["relative_h1_db"],
                         model_minus_hardware_db=candidate["relative_h1_db"]-reference["relative_h1_db"],
                         hardware_peak_hz=reference["peak_hz"], model_peak_hz=candidate["peak_hz"],
                         model_prominence_db=candidate["local_prominence_db"],
                         model_interior_peak=candidate["genuine_interior_local_peak"],
                         model_passes_line_threshold=candidate["passes_line_threshold"]))
    differences = np.array([r["model_minus_hardware_db"] for r in rows])
    return dict(hardware_eligible_line_count=len(rows), lines=rows,
                rms_error_db=float(np.sqrt(np.mean(differences**2))),
                median_signed_error_db=float(np.median(differences)))


def controls():
    rows = []
    for width in WIDTHS:
        knots, basis = spline(width)
        grid = np.linspace(0, width, 2001)
        target = np.maximum(1-grid, 0)**2
        coefficient, _, rank, singular = np.linalg.lstsq(basis(grid), target, rcond=None)
        max_error = float(np.max(np.abs(basis(grid)@coefficient-target)))
        endpoint = dict(value=float(np.max(np.abs(basis(width)))),
                        derivative=float(np.max(np.abs(basis.derivative()(width)))))
        if max_error > 1e-12 or max(endpoint.values()) > 1e-12:
            raise ValueError("Standard polyBLEP is not exactly nested, or endpoint constraints failed")
        planted = .37*design(.321, 91, -1)[:, 0]+.013
        fitted = train(planted, 91, width)
        held = .37*design(.173, 93, -1)[:, 0]-.008
        held_result = evaluate(held, 93, width, np.array(fitted["coefficients"]))
        if fitted["relative_error_power"] > 1e-10 or held_result["relative_error_power"] > 1e-9:
            raise ValueError("PolyBLEP synthetic train/other-pitch recovery failed")
        # A non-polyBLEP planted kernel checks free-shape coefficient recovery.
        free_coefficients = np.r_[.29, .24*np.cos(np.arange(len(coefficient))*.51)]
        free_signal = design(.247, 91, width)@free_coefficients+.011
        free_fit = train(free_signal, 91, width)
        free_held = design(.137, 93, width)@free_coefficients-.021
        free_evaluation = evaluate(free_held, 93, width, np.array(free_fit["coefficients"]))
        if max(free_fit["relative_error_power"], free_evaluation["relative_error_power"]) > 1e-9:
            raise ValueError("Free-kernel synthetic train/other-pitch recovery failed")
        rows.append(dict(width_samples=width, knots=knots.tolist(),
                         nested_polyblep_coefficients=coefficient.tolist(),
                         nested_max_absolute_error=max_error, endpoint=endpoint,
                         polyblep_training=fitted, polyblep_other_pitch=held_result,
                         free_kernel_training=free_fit, free_kernel_other_pitch=free_evaluation))
    return rows


def plot(result, destination):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.5), constrained_layout=True)
    labels = [f"{p['note']} +{round(p['offset_seconds']*1000)}ms"
              for p in [result["protocol"]["training"]]+result["protocol"]["evaluation"]]
    colors = {"naive": "#969696", "polyblep": "#252525", "wrap-W2": "#1f77b4",
              "wrap-W3": "#d95f02", "wrap-W4": "#238b45"}
    for row in result["models"]:
        scores = row["scores"]
        color = colors[row["id"]]
        style = "--" if row["width_samples"] <= 0 else "-"
        for ax, values in zip(axes.flat, ([100*s["relative_error_power"] for s in scores],
                              [s["harmonics"]["h2_to_h8_rms_error_db"] for s in scores],
                              [s["aliases"]["rms_error_db"] for s in scores])):
            ax.plot(labels, values, style, color=color, marker="o", label=row["id"])
        if row["width_samples"] > 0:
            axes[1, 1].plot(row["kernel"]["positions_samples"],
                            np.array(row["kernel"]["magnitude"])/row["training"]["gain"],
                            color=color, label=row["id"])
    t = np.linspace(0, 4, 500)
    axes[1, 1].plot(t, np.maximum(1-t, 0)**2, "--", color=colors["polyblep"], label="polyblep")
    titles = ("Waveform error power / hardware power (%)", "H2–H8 / H1 magnitude error (RMS dB)",
              "Hardware-qualified alias error (RMS dB)", "Trained correction magnitude / gain")
    for ax, title in zip(axes.flat, titles):
        ax.set_title(title)
        ax.grid(alpha=.2)
    axes[0, 0].set_yscale("log")
    axes[0, 0].legend(fontsize=8, ncol=2)
    axes[1, 1].set_xlabel("Distance from wrap (samples)")
    axes[1, 1].legend(fontsize=8)
    fig.suptitle("One local Saw kernel across pitches: good gross shape, unresolved notches\n"
                 "Train only MIDI91 +100ms; later phase/DC only. No DSP change or equivalence claim.", fontsize=13)
    fig.savefig(destination, dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    catalog = json.loads(fir.CATALOG.read_text())
    def source(name):
        entry = next(a for a in catalog["assets"] if Path(a["path"]).name == name)
        path = args.sources/name
        if sha(path) != entry["sha256"]:
            raise ValueError("Original source hash mismatch")
        return entry, path
    midi_entry, midi = source("deepsonic_-_filter_demo_-_comparsion_sequence.mid")
    active, gates = {}, []
    for event in parse_smf(midi.read_bytes())["events"]:
        if event["kind"] != "midi":
            continue
        message = bytes.fromhex(event["hex"])
        status, note = message[0] & 240, message[1]
        if status == 144 and message[2]:
            active[note] = (event["sample"]/SR, message[2])
        elif status == 128 or (status == 144 and not message[2]):
            on, velocity = active.pop(note)
            gates.append((note, on, event["sample"]/SR, velocity))
    if active or len(gates) != 124:
        raise ValueError("Original MIDI note pairing changed")
    mp3_entry, mp3 = source("roland_sh-201_-_filter_demo_-_lpf12_q000.mp3")
    wav = out/"hardware-lp12.wav"
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(mp3),
               "-c:a", "pcm_f32le", str(wav)]
    subprocess.run(command, check=True)
    rate, audio = wavfile.read(wav)
    if rate != SR or audio.ndim != 1 or not np.isfinite(audio).all():
        raise ValueError("Unexpected source decode")
    passages, signals = [], []
    for note, on, offset, role in fir.PASSAGES:
        match = [g for g in gates if g[0] == note and g[1] == on and g[3] == 127]
        if len(match) != 1 or on+offset+.04 > match[0][2]+.035:
            raise ValueError("Passage violates original MIDI gate or fixed 35ms onset convention")
        start = round((on+offset-.04)*SR)
        x = audio[start:start+SIZE].astype(float)
        if len(x) != SIZE:
            raise ValueError("Passage coverage missing")
        signals.append(x)
        passages.append(dict(note=note, midi_onset_seconds=on, midi_off_seconds=match[0][2],
                             velocity=127, offset_seconds=offset, role=role,
                             start_sample=start, end_sample=start+SIZE,
                             sample_sha256=hashlib.sha256(x.astype("<f8").tobytes()).hexdigest()))
    protocol = dict(status="exploratory_mathematical_diagnostic_not_DSP_validation",
                    training=passages[0], evaluation=passages[1:], sample_rate=SR, window_samples=SIZE,
                    widths_samples=WIDTHS, spline_degree=3, knot_spacing_samples=.5,
                    interior_knot_multiplicity=2, continuity="C1",
                    endpoint_at_width="value and first derivative exactly zero",
                    zero_endpoint="magnitude free; sign at exactly zero is positive",
                    equation="y = gain*(2*phase-1) + sign(t)*sum(kernel_coefficient[j]*B[j](abs(t))); t=nearest signed wrap distance / phase increment",
                    fixed_frequency="Nominal equal-tempered original MIDI, no frequency fitting",
                    phase_search="256 point grid, bounded scalar refinement within one grid spacing",
                    full_rank_guard=dict(required=True, maximum_condition=CONDITION_LIMIT),
                    fitting="Train all coefficients/gain/phase/DC on note91 +100ms; freeze coefficients and gain for all later windows. Later phase/DC only.",
                    selection="Report all W=2/3/4 and naive/polyBLEP controls; no holdout selection or per-pitch changes",
                    harmonics="H2-H8 relative to H1; fixed across hardware/models; hardware invariance audit established eligibility",
                    aliases="Separate unchanged alias helper; only hardware-qualified 44.1k descending-fold lines; no candidate-dependent mask",
                    timing="80ms windows centered at original MIDI onset plus offset; hardware delay about35ms is not removed. No renderer delay because models are generated directly inside each window.",
                    limitations="Prior exploratory inspection informed candidate family. Filter and capture transfer remain unknown, especially lower notes and later note91. A fit cannot identify firmware or place processing blocks.")
    (out/"protocol.json").write_text(json.dumps(protocol, indent=2)+"\n")
    recovery = controls()
    hardware = [aliases.measure(x, .04, p["note"], 0.) for p, x in zip(passages, signals)]
    rows = []
    for label, width in (("naive", 0), ("polyblep", -1), *((f"wrap-W{int(w)}", w) for w in WIDTHS)):
        fitted = train(signals[0], passages[0]["note"], width)
        coefficients = np.array(fitted["coefficients"])
        evaluations = [evaluate(x, p["note"], width, coefficients)
                       for x, p in zip(signals[1:], passages[1:])]
        scores = []
        for p, x, phase_fit, ref in zip(passages, signals, [fitted]+evaluations, hardware):
            y = design(phase_fit["phase"], p["note"], width)@coefficients
            scores.append(dict(passage=p, relative_error_power=phase_fit["relative_error_power"],
                               harmonics=compare_harmonics(x, y, p["note"]),
                               aliases=compare_aliases(ref, aliases.measure(y, .04, p["note"], 0.))))
        row = dict(id=label, width_samples=width, training=fitted, evaluations=evaluations, scores=scores)
        if width > 0:
            grid = np.linspace(0, width, 161)
            row["kernel"] = dict(knots=spline(width)[0].tolist(), positions_samples=grid.tolist(),
                                 magnitude=(spline(width)[1](grid)@coefficients[1:]).tolist(),
                                 residual_jump=float(-2*fitted["gain"]+2*coefficients[1]))
        rows.append(row)
        print(label, "power", [round(s["relative_error_power"], 7) for s in scores],
              "harmonic", [round(s["harmonics"]["h2_to_h8_rms_error_db"], 3) for s in scores],
              "alias", [round(s["aliases"]["rms_error_db"], 3) for s in scores], flush=True)
    result = dict(protocol=protocol, script_sha256=sha(__file__), catalog_sha256=sha(fir.CATALOG),
                  dependency_sha256={Path(p).name: sha(p) for p in (fir.__file__, aliases.__file__, ROOT/"Tools/render_midi.py")},
                  source=mp3_entry, original_midi=midi_entry, decode_command=command,
                  decoded_wav_sha256=sha(wav), controls=recovery, models=rows,
                  equivalence_status="not_established")
    (out/"results.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    plot(result, out/"comparison.png")


if __name__ == "__main__":
    main()
