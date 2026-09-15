#!/usr/bin/env python3
"""Measure harmonic self-control for the four frozen dry saw phases.

Consumes measure_dry_phase_sensitivity.py output. Same MIDI sample positions,
no delay fit, one RMS gain on note36 only and a fixed-gain-one diagnostic.
This tests finite-window estimator robustness, not hardware equivalence.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import scipy
from scipy.io import wavfile

PHASES = (0., .25, .5, .75)
NOTES = ((0., 24), (.75, 24), (1.5, 36), (2., 29), (4.75, 24),
         (6., 31), (17.25, 57), (18.75, 91), (20.25, 84))
OFFSETS = (.10, .18, .26, .34)
MIDI_SHA = "21ea21b9ba3ba14cc205931134fb7a320b09e67821bd3a3c70f97fa2e8b5d99a"
PRODUCTION_SHA = {
    12: "e960507e6c9404554980eceae90d51e1253347d22fbe7e661f48730dce7484da",
    24: "dd505cd6a020417a5b86c52083a8dd6091b3f18edbad7c28a0de431df2356a33",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(path, expected):
    if sha(path) != expected:
        raise ValueError("Changed input: " + str(path))


def fit_phases(signals, sr, center, width, f0):
    """Same sinusoid/ramp basis as the frozen filter tool, four right sides.

    Every harmonic has cosine, sine and independent linear cosine/sine ramps.
    The reported amplitude is at the window center. Joint here means jointly
    fitting all harmonics; it does not share phase/amplitude across renders.
    """
    a, b = round((center-width/2)*sr), round((center+width/2)*sr)
    if a < 0 or any(b > len(y) for y in signals):
        raise ValueError("Window outside audio")
    x = np.column_stack([y[a:b] for y in signals])
    t = np.arange(a, b)/sr-center
    u = t/(width/2)
    hs = np.arange(1, min(30, int(8000/f0))+1)
    columns = [np.ones(len(t)), u]
    for h in hs:
        c, s = np.cos(2*np.pi*h*f0*t), np.sin(2*np.pi*h*f0*t)
        columns.extend((c, s, u*c, u*s))
    matrix = np.column_stack(columns)
    coeff, _, rank, singular = np.linalg.lstsq(matrix, x, rcond=None)
    amplitude = np.hypot(coeff[2::4], coeff[3::4])
    ratio = 20*np.log10(np.maximum(amplitude, 1e-15)/np.maximum(amplitude[0], 1e-15))
    variance = np.var(x, axis=0)
    residual = np.mean((x-matrix@coeff)**2, axis=0)/np.maximum(variance, 1e-30)
    return dict(harmonics=hs, amplitude=amplitude, ratio=ratio,
                condition=float(singular[0]/singular[-1]), full_rank=rank == len(columns),
                variance=variance, residual=residual, sample_range=[a, b])


def stats(values):
    if not values:
        return {"observations": 0}
    x = np.asarray(values)
    return dict(observations=len(x), rms_db=float(np.sqrt(np.mean(x*x))),
                signed_mean_db=float(np.mean(x)), mean_absolute_db=float(np.mean(abs(x))),
                p95_absolute_db=float(np.percentile(abs(x), 95)),
                maximum_absolute_db=float(np.max(abs(x))))


def summarize(rows, phase_index):
    valid = [r for r in rows if r["common_fit_valid"]]
    answer = dict(requested_windows=len(rows), common_valid_windows=len(valid),
                  rejected_windows=len(rows)-len(valid))
    for label, lo, hi in (("h1", 1, 1), ("h1_h16", 1, 16),
                          ("h2_h8", 2, 8), ("h9_h16", 9, 16)):
        values = {"fixed_gain1_amplitude": [], "training_gain_amplitude": [], "h1_normalized_ratio": []}
        windows = 0
        for row in valid:
            pick = [i for i, h in enumerate(row["harmonics"])
                    if lo <= h <= hi and row["baseline_eligible"][i]]
            if pick:
                windows += 1
            model = row["phases"][phase_index]
            for key in values:
                values[key].extend(model[key+"_difference_db"][i] for i in pick)
        answer[label] = dict(windows_with_eligible_harmonics=windows,
                             **{key: stats(value) for key, value in values.items()})
    return answer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.experiment_dir.resolve()
    manifest_path = root/"renders.json"
    manifest = json.loads(manifest_path.read_text())
    protocol = manifest["protocol"]
    if protocol["source_revision"] != "b0f6c03" or tuple(protocol["phases_cycles"]) != PHASES:
        raise ValueError("Unexpected checkpoint or phase grid")
    verify(root/"source-manifest.json", manifest["source_manifest_sha256"])
    source = json.loads((root/"source-manifest.json").read_text())
    if source["revision"] != "b0f6c03":
        raise ValueError("Unexpected frozen source revision")
    for name, expected in source["input_sha256"].items():
        verify(root/"frozen-source"/name, expected)
    sys.path.insert(0, str(root/"frozen-source/Tools"))
    from render_midi import parse_smf
    estimator_path = root/"frozen-source/Tools/analyze_deepsonic_filter.py"
    spec = importlib.util.spec_from_file_location("frozen_filter_estimator", estimator_path)
    estimator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(estimator)
    midi_path = root/"source-cache/deepsonic_-_filter_demo_-_comparsion_sequence.mid"
    verify(midi_path, MIDI_SHA)
    held, notes = {}, []
    for event in parse_smf(midi_path.read_bytes())["events"]:
        if event["kind"] != "midi":
            continue
        message = bytes.fromhex(event["hex"])
        key = (message[0] & 15, message[1])
        if message[0] & 240 == 144 and message[2]:
            if key in held:
                raise ValueError("Overlapping same-key MIDI")
            held[key] = (event["sample"], message[2])
        elif message[0] & 240 == 128 or message[0] & 240 == 144 and not message[2]:
            onset, velocity = held.pop(key)
            notes.append(dict(on=onset/44100, off=event["sample"]/44100, note=key[1], velocity=velocity))
        else:
            raise ValueError("Unexpected sound-changing MIDI")
    if held or len(notes) != 124:
        raise ValueError("Unexpected original MIDI note count")
    chosen = [next(n for n in notes if (n["on"], n["note"]) == key) for key in NOTES]
    train = next(n for n in chosen if n["on"] == 1.5)
    if protocol["training_note"] != train or protocol["isolated_notes"] != [n for n in chosen if n != train]:
        raise ValueError("Predeclared note selection changed")
    for note in chosen:
        if note["off"] < note["on"]+.38 or any(n != note and n["on"] < note["off"]
                                                  and n["off"] > note["on"] for n in notes):
            raise ValueError("Chosen window no longer belongs to an isolated held note")
    ta, tb = round(train["on"]*44100), round(train["off"]*44100)
    if [ta, tb] != [66150, 85444]:
        raise ValueError("Unexpected training gate")
    audio, inputs, gains = {}, [], {}
    if len(manifest["renders"]) != 8:
        raise ValueError("Expected four phases at two filter slopes")
    for phase in PHASES:
        identity = f"phase-{round(phase*100):02d}"
        build = root/"builds"/identity
        built = json.loads((build/"manifest.json").read_text())
        for name, expected in built["frozen_sha256"].items():
            verify(build/name, expected)
        for name, expected in built["source"]["input_sha256"].items():
            if expected != source["input_sha256"][name]:
                raise ValueError("Candidate input source drift")
        profile = json.loads((build/"profile.json").read_text())
        if profile.get("waves") != {"phase_cycles": [phase, 0., 0., 0., 0.]} or set(profile) != {
                "version", "id", "evidence", "waves"}:
            raise ValueError("Candidate changes something beyond saw phase")
        for slope in (12, 24):
            record = next(r for r in manifest["renders"] if r["phase_cycles"] == phase and r["slope"] == slope)
            path = root/"audio"/identity/f"lp{slope}/candidate.wav"
            verify(path, record["sha256"])
            verify(path.with_suffix(".render.json"), record["render_manifest_sha256"])
            verify(build/"SeptumRenderMidi", record["renderer_sha256"])
            verify(root/f"recipes/lp{slope}.syx", record["patch_sha256"])
            if record["midi_sha256"] != MIDI_SHA or phase == 0 and record["sha256"] != PRODUCTION_SHA[slope]:
                raise ValueError("MIDI or production audio identity changed")
            sr, y = wavfile.read(path)
            if sr != 44100 or y.ndim != 2 or y.shape[1] != 2 or not np.isfinite(y).all():
                raise ValueError("Expected finite stereo 44.1 kHz render")
            channel_difference = float(np.max(abs(y[:, 0]-y[:, 1])))
            if channel_difference > np.finfo(np.float32).eps*np.max(abs(y)):
                raise ValueError("Dry stereo channels differ")
            audio[phase, slope] = y[:, 0].astype(float)
            inputs.append(dict(phase_cycles=phase, slope=slope, wav=str(path), sha256=sha(path),
                               maximum_channel_difference=channel_difference,
                               build_manifest_sha256=sha(build/"manifest.json")))
    for slope in (12, 24):
        for phase in PHASES:
            a, b = audio[0., slope][ta:tb], audio[phase, slope][ta:tb]
            if np.mean(b*b) < 1e-12:
                raise ValueError("Training signal has negligible power")
            gains[phase, slope] = float(np.sqrt(np.mean(a*a)/np.mean(b*b)))
    rows, crosscheck = [], []
    for slope in (12, 24):
        signals = [audio[p, slope] for p in PHASES]
        for note in chosen:
            f0 = 440*2**((note["note"]-69)/12)
            for offset in OFFSETS:
                center = note["on"]+offset
                fit = fit_phases(signals, 44100, center, .08, f0)
                # Cross-check the optimized multi-right-side solve against the
                # exact frozen single-render estimator on the lowest note.
                if note["on"] == 0 and offset == .1:
                    old = estimator.measure(signals[0], 44100, center, .08, f0)
                    maximum = float(np.max(abs(np.asarray(old["amplitude"])-fit["amplitude"][:, 0])))
                    if maximum > 1e-12:
                        raise ValueError("Batched estimator differs from frozen estimator")
                    crosscheck.append(dict(slope=slope, max_amplitude_difference=maximum))
                eligible = (fit["ratio"][:, 0] > -45) & (fit["amplitude"][:, 0] >= 1e-8)
                phases = []
                for i, phase in enumerate(PHASES):
                    failures = []
                    if fit["condition"] > 100 or not fit["full_rank"]:
                        failures.append("condition_or_rank")
                    if fit["variance"][i] < 1e-12 or fit["amplitude"][0, i] < 1e-8:
                        failures.append("negligible_signal_power")
                    if fit["residual"][i] > .01:
                        failures.append("unexplained_power_above_one_percent")
                    raw = 20*np.log10(np.maximum(fit["amplitude"][:, i], 1e-15)/np.maximum(fit["amplitude"][:, 0], 1e-15))
                    phases.append(dict(phase_cycles=phase, fit_valid=not failures, rejection_reasons=failures,
                        fit_residual_power=float(fit["residual"][i]), signal_variance=float(fit["variance"][i]),
                        amplitude=fit["amplitude"][:, i].tolist(), harmonic_ratio_db=fit["ratio"][:, i].tolist(),
                        fixed_gain1_amplitude_difference_db=raw.tolist(),
                        training_gain_amplitude_difference_db=(raw+20*np.log10(gains[phase, slope])).tolist(),
                        h1_normalized_ratio_difference_db=(fit["ratio"][:, i]-fit["ratio"][:, 0]).tolist()))
                rows.append(dict(slope=slope, **note, training=note == train, offset=offset,
                    center_seconds=center, width_seconds=.08, sample_range=fit["sample_range"],
                    fundamental_hz=f0, fundamental_cycles_per_window=f0*.08,
                    harmonics=fit["harmonics"].tolist(), baseline_eligible=eligible.tolist(),
                    condition_number=fit["condition"], common_fit_valid=all(p["fit_valid"] for p in phases), phases=phases))
        print(f"Measured LP{slope}: 36 windows at all four phases", flush=True)
    summaries = []
    for slope in (12, 24):
        for i, phase in enumerate(PHASES):
            for label, select in (("training", lambda r: r["training"]),
                                   ("validation", lambda r: not r["training"]),
                                   ("midi24_validation", lambda r: r["note"] == 24)):
                subset = [r for r in rows if r["slope"] == slope and select(r)]
                summaries.append(dict(slope=slope, phase_cycles=phase, cohort=label, **summarize(subset, i)))
    result = dict(schema_version=1, status="finite_window_phase_self_control_not_hardware_equivalence",
        tool_sha256=sha(__file__), renders_manifest_sha256=sha(manifest_path),
        source_manifest_sha256=sha(root/"source-manifest.json"), source_revision="b0f6c03",
        frozen_estimator_sha256=sha(estimator_path), frozen_estimator_crosscheck=crosscheck,
        numpy_version=np.__version__, scipy_version=scipy.__version__, inputs=inputs,
        protocol=dict(phases_cycles=PHASES, notes=chosen, offsets_seconds=OFFSETS, width_seconds=.08,
            lag_samples=0, common_renderer_latency_retained=True, training_samples=[ta, tb],
            gains=[dict(phase_cycles=p, slope=s, gain=gains[p, s], gain_db=20*np.log10(gains[p, s])) for s in (12, 24) for p in PHASES],
            harmonic_policy="H1 through min(30,floor(8000/f0)); DC/ramp plus independent cosine/sine/ramp per harmonic; no tuning, delay, cutoff or phase fitting",
            mask_policy="Eligibility determined only by phase0: >-45 dB relative to H1 and amplitude >=1e-8. Identical selected harmonics for every phase, no candidate activity mask.",
            validity_policy="Full rank; condition<=100; variance>=1e-12; H1 amplitude>=1e-8; residual/variance<=.01. Summary uses only windows valid for ALL four phases. Every invalid window retained with reasons.",
            qualification="Changing waveform origin also changes finite attack/filter transients. Harmonic quadrature removes constant phase from the estimator, but cannot remove real phase-dependent dynamics or bias from a short moving-signal window. No late chords fitted by this single-fundamental estimator."),
        requested_windows=len(rows), requested_render_windows=len(rows)*4,
        common_valid_windows=sum(r["common_fit_valid"] for r in rows),
        rejected_render_windows=sum(not p["fit_valid"] for r in rows for p in r["phases"]),
        summaries=summaries, windows=rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise ValueError("Refusing to overwrite an existing analysis")
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    for row in summaries:
        if row["cohort"] == "validation":
            print(row["slope"], row["phase_cycles"], row["common_valid_windows"], row["h1_h16"])


if __name__ == "__main__":
    main()
