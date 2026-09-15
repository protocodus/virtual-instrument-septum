#!/usr/bin/env python3
"""Frozen high-note periodic-table hypotheses with a shared nuisance FIR."""
import argparse
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import subprocess

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np
from scipy.io import wavfile
import analyze_deepsonic_saw_aliases as aliases
import fit_high_note_saw_models as previous
from render_midi import parse_smf

ROOT = Path(__file__).resolve().parents[1]
SR, SIZE = 44100, 3528
TABLE_SIZES = (16, 24, 32, 48, 64, 128, 1024)
INTERPOLATIONS = ("hold", "linear", "cubic_lagrange")
OFFSETS = np.arange(13)-6
sha = previous.sha


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")


@lru_cache(maxsize=128)
def table(size, kind, cap):
    positions = np.arange(size)/size
    if kind == "sampled_ramp":
        return 2*positions-1
    harmonics = np.arange(1, cap+1)
    return -2/np.pi * (np.sin(2*np.pi*positions[:, None]*harmonics)/harmonics).sum(axis=1)


def interpolate(values, phases, method):
    position = (phases % 1)*len(values)
    index = np.floor(position).astype(int)
    u = position-index
    if method == "hold":
        return values[index]
    if method == "linear":
        return values[index]*(1-u)+values[(index+1)%len(values)]*u
    weights = (-u*(u-1)*(u-2)/6, (u+1)*(u-1)*(u-2)/2,
               -(u+1)*u*(u-2)/2, (u+1)*u*(u-1)/6)
    return sum(w*values[(index+offset)%len(values)] for w, offset in zip(weights, (-1, 0, 1, 2)))


def cutoff_count(model, note):
    if model["kind"] == "fourier_output_nyquist":
        return int(np.floor(SR/(2*aliases.f0(note))))
    if model["kind"] == "fourier_output_rate":
        return int(np.floor(SR/aliases.f0(note)))
    return model["table_size"]//2-1


def design(phase, note, model, offsets=OFFSETS):
    if model["kind"] == "polyblep_control":
        return previous.design(phase, note, 1., offsets)
    if model["kind"] == "naive_control":
        return previous.design(phase, note, 0., offsets)
    positions = phase + aliases.f0(note)/SR*(np.arange(SIZE)[:, None]-offsets[None, :])
    values = table(model["table_size"], model["kind"], cutoff_count(model, note))
    return interpolate(values, positions, model["interpolation"])


def train(x, note, model):
    centered = x-x.mean()
    power = np.mean(centered**2)
    def solve(phase):
        matrix = np.column_stack((design(phase, note, model), np.ones(SIZE)))
        coefficient, _, rank, singular = np.linalg.lstsq(matrix, centered, rcond=None)
        y = matrix@coefficient
        return float(np.mean((centered-y)**2)/power), coefficient, int(rank), float(singular[0]/singular[-1])
    phase = previous.search_phase(lambda p:solve(p)[0])
    loss, coefficient, rank, condition = solve(phase)
    return dict(phase_cycles=phase, relative_error_power=loss, taps=coefficient[:-1].tolist(),
                dc=coefficient[-1], rank=rank, condition=condition,
                valid_full_rank=rank == len(OFFSETS)+1 and condition < 1e6)


def evaluate(x, note, model, taps):
    centered = x-x.mean()
    power = np.mean(centered**2)
    def prediction(phase):
        y = design(phase, note, model)@taps
        return y-y.mean()
    def loss(phase):
        return float(np.mean((centered-prediction(phase))**2)/power)
    phase = previous.search_phase(loss)
    return dict(phase_cycles=phase, relative_error_power=loss(phase), gain_refitted=False), prediction(phase)


def harmonic_ratios(x, note):
    _, inverse, _ = aliases.harmonic_model(note, len(x))
    coefficients = inverse@x
    amplitude = np.array([np.hypot(*coefficients[3+6*h:5+6*h]) for h in range(8)])
    return 20*np.log10(np.maximum(amplitude, 1e-20)/max(amplitude[0], 1e-20))


def compare_lines(hardware, prediction, note):
    measured = aliases.measure(prediction, .04, note, 0.)
    by_h = {x["parent_harmonic"]:x for x in measured["tested_alias_lines"] if x["rate_hypothesis_hz"] == SR}
    rows = []
    for line in hardware["tested_alias_lines"]:
        if line["rate_hypothesis_hz"] != SR or not line["passes_line_threshold"]:
            continue
        candidate = by_h[line["parent_harmonic"]]
        rows.append(dict(parent_harmonic=line["parent_harmonic"], expected_hz=line["expected_hz"],
                         hardware_db=line["relative_h1_db"], candidate_db=candidate["relative_h1_db"],
                         error_db=candidate["relative_h1_db"]-line["relative_h1_db"],
                         candidate_has_interior_peak=candidate["genuine_interior_local_peak"],
                         candidate_prominence_db=candidate["local_prominence_db"],
                         candidate_passes_threshold=candidate["passes_line_threshold"]))
    errors = np.array([r["error_db"] for r in rows])
    return dict(lines=rows, count=len(rows), rms_error_db=float(np.sqrt(np.mean(errors**2))),
                maximum_absolute_error_db=float(abs(errors).max()),
                candidate_resolved_lines=sum(r["candidate_has_interior_peak"] and r["candidate_prominence_db"] >= 12 for r in rows),
                other_peak_diagnostics=measured["diagnostic_nonharmonic_peaks"])


def controls():
    # Polynomial reproduction independently checks the four Lagrange weights.
    u = np.linspace(0, 1, 1001)
    weights = np.array([-u*(u-1)*(u-2)/6, (u+1)*(u-1)*(u-2)/2,
                        -(u+1)*u*(u-2)/2, (u+1)*u*(u-1)/6])
    polynomial_error = max(float(abs((np.array([-1., 0., 1., 2.])**degree)@weights-u**degree).max()) for degree in range(4))
    # Continuous Fourier coefficients for periodic ZOH/linear interpolation:
    # DFT(table)[h mod N]/N times sinc(h/N) or sinc(h/N)^2.
    # ZOH additionally delays by half a table interval.
    rows = []
    for size in (16, 32, 128):
        values = table(size, "finite_fourier", size//2-1)
        count = size*2048
        phase = (np.arange(count)+.5)/count
        dft = np.fft.fft(values)/size
        for method in ("hold", "linear"):
            y = interpolate(values, phase, method)
            for h in (1, size//2-1, size-1, size+1, 2*size-1):
                numerical = np.mean(y*np.exp(-2j*np.pi*h*phase))
                expected = dft[h%size]*np.sinc(h/size)**(1 if method == "hold" else 2)
                if method == "hold":expected *= np.exp(-1j*np.pi*h/size)
                rows.append(dict(table_size=size, interpolation=method, harmonic=h,
                                 absolute_complex_error=float(abs(numerical-expected))))
    if polynomial_error > 1e-14 or max(r["absolute_complex_error"] for r in rows) > 1e-7:
        raise ValueError("Interpolation/Fourier control failed")
    recovery = []
    for size, kind, interpolation in ((24, "sampled_ramp", "linear"), (32, "finite_fourier", "cubic_lagrange"),
                                      (1024, "fourier_output_nyquist", "linear")):
        model = dict(table_size=size, kind=kind, interpolation=interpolation)
        taps = np.array([0., 0., 0., 0., -.03, .11, .33, .09, -.01, 0., 0., 0., 0.])
        training = design(.321, 91, model)@taps
        fitted = train(training, 91, model)
        held = design(.217, 93, model)@taps
        checked, _ = evaluate(held, 93, model, np.array(fitted["taps"]))
        recovery.append(dict(model=model, training=fitted, different_pitch=checked))
    return dict(polynomial_maximum_absolute_error=polynomial_error, continuous_fourier_checks=rows,
                cross_pitch_recovery=recovery)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    catalog = json.loads(previous.CATALOG.read_text())
    source_records = []
    def verify(name):
        entry = next(x for x in catalog["assets"] if Path(x["path"]).name == name)
        path = args.sources/name
        if sha(path) != entry["sha256"]:raise ValueError("Original source mismatch")
        source_records.append(entry)
        return path
    midi = verify("deepsonic_-_filter_demo_-_comparsion_sequence.mid")
    held, notes = {}, []
    for event in parse_smf(midi.read_bytes())["events"]:
        if event["kind"] != "midi":continue
        message = bytes.fromhex(event["hex"])
        kind, key = message[0]&240, (message[0]&15, message[1])
        if kind == 144 and message[2]:held[key] = (event["sample"]/SR, message[2])
        elif kind == 128 or kind == 144 and not message[2]:
            on, velocity = held.pop(key)
            notes.append(dict(note=key[1], on=on, off=event["sample"]/SR, velocity=velocity))
    if held or len(notes) != 124:raise ValueError("Original MIDI pairing changed")
    source = verify("roland_sh-201_-_filter_demo_-_lpf12_q000.mp3")
    wav = out/"hardware-lp12.wav"
    decode = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(source), "-c:a", "pcm_f32le", str(wav)]
    subprocess.run(decode, check=True)
    sr, audio = wavfile.read(wav)
    if sr != SR or audio.ndim != 1 or not np.isfinite(audio).all():raise ValueError("Unexpected decode")
    passages, signals = [], []
    for note, on, offset, role in previous.PASSAGES:
        original = next(x for x in notes if x["note"] == note and x["on"] == on)
        if original["velocity"] != 127 or on+offset+.04 > original["off"]+.035:raise ValueError("Original gate changed")
        start = round((on+offset-.04)*SR)
        x = audio[start:start+SIZE].astype(float)
        signals.append(x)
        passages.append(dict(**original, offset_seconds=offset, role=role, start_sample=start, end_sample=start+SIZE,
                             samples_sha256=hashlib.sha256(x.astype("<f8").tobytes()).hexdigest()))
    models = []
    for kind in ("sampled_ramp", "finite_fourier"):
        for size in TABLE_SIZES:
            for method in INTERPOLATIONS:
                models.append(dict(id=f"{kind}-n{size}-{method}", kind=kind, table_size=size, interpolation=method))
    for kind in ("fourier_output_nyquist", "fourier_output_rate"):
        for method in ("linear", "cubic_lagrange"):
            models.append(dict(id=f"{kind}-n1024-{method}", kind=kind, table_size=1024, interpolation=method))
    models.extend(dict(id=k, kind=k) for k in ("naive_control", "polyblep_control"))
    protocol = dict(status="exploratory_finite_wavetable_family_no_source_identification_or_shipping_change", models=models,
                    training=passages[0], validation=passages[1:],
                    model_count=len(models), fir_offsets_samples=OFFSETS.tolist(), phase_grid_size=len(previous.GRID),
                    policy="Each model fits one13tap FIR including gain, phase and DC on91+100ms only; freezes all taps/gain, then only phase/DC on other passages. No model selected from validation. Every declared model and hardware-qualified alias line retained.",
                    table_definition="Sampled ramp table[n]=2n/N-1; finite Fourier table sums -2*sin(2pi*h*n/N)/(pi*h), h1..N/2-1. Pitch-dependent variants use floor(Fs/(2f0)) or floor(Fs/f0) harmonics in a1024point table. Periodic left hold, linear, or four-point cubic Lagrange interpolation; no phase increment quantization.",
                    fir_qualification="Shared13tap signed/noncausal nuisance FIR accommodates known main-spectrum coloration; it is not identified as oscillator/filter/capture or an engine implementation.",
                    metrics="Waveform residual power, H2..H8/H1 magnitude RMSE, original first-descending-branch alias helper with hardware-only mask. Model unresolved bins remain upper-bound proxies; simultaneous/extra-fold estimator audit pending separately.",
                    source_records=source_records, catalog_sha256=sha(previous.CATALOG), decode_command=decode, decoded_wav_sha256=sha(wav),
                    tool_sha256=sha(__file__), helper_sha256={Path(m.__file__).name:sha(m.__file__) for m in (previous, aliases)},
                    limits="These previously examined windows are excluded from coefficient fitting, not blind holdouts. Original raw recipe and capture transfer remain unknown. Same-note windows overlap20ms. This finite family cannot exclude arbitrary wavetables, fractional interpolation methods, table bank switching or frequency-dependent filters.")
    save(out/"protocol-before-fit.json", protocol)
    control = controls()
    save(out/"controls.json", control)
    print("Controls", [(x["training"]["relative_error_power"], x["different_pitch"]["relative_error_power"]) for x in control["cross_pitch_recovery"]], flush=True)
    references = [aliases.measure(x, .04, p["note"], 0.) for x, p in zip(signals, passages)]
    ratios = [harmonic_ratios(x, p["note"]) for x, p in zip(signals, passages)]
    records = []
    for model in models:
        fitted = train(signals[0], passages[0]["note"], model)
        rows = []
        if fitted["valid_full_rank"]:
            taps = np.array(fitted["taps"])
            for i, (x, passage, reference) in enumerate(zip(signals, passages, references)):
                if i == 0:
                    y = design(fitted["phase_cycles"], passage["note"], model)@taps
                    result = dict(phase_cycles=fitted["phase_cycles"], relative_error_power=fitted["relative_error_power"], gain_refitted=True)
                else:
                    result, y = evaluate(x, passage["note"], model, taps)
                error = harmonic_ratios(y, passage["note"])[1:]-ratios[i][1:]
                rows.append(dict(passage=passage, fit=result, harmonic_error_h2_h8_db=error.tolist(),
                                 harmonic_rmse_db=float(np.sqrt(np.mean(error**2))), aliases=compare_lines(reference, y, passage["note"]),
                                 predicted_pcm_float64_sha256=hashlib.sha256(y.astype("<f8").tobytes()).hexdigest()))
        records.append(dict(model=model, training=fitted, passages=rows))
        save(out/"results-partial.json", dict(protocol=protocol, controls=control, references=references, models=records))
        print(model["id"], "rank", fitted["rank"], "power", fitted["relative_error_power"], "alias", [round(r["aliases"]["rms_error_db"], 3) for r in rows], flush=True)
    for module in (previous, aliases):
        if sha(module.__file__) != protocol["helper_sha256"][Path(module.__file__).name]:raise ValueError("Helper changed during experiment")
    save(out/"results.json", dict(protocol=protocol, controls=control, references=references, models=records, selected_model=None, production_dsp_changed=False))


if __name__ == "__main__":
    main()
