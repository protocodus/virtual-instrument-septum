#!/usr/bin/env python3
"""Replay frozen W4 dry/preset inputs through an independently built production renderer.

This verifies numerical integration, not hardware equivalence. No build, fit,
normalization, timing correction, cropping, or candidate selection occurs here.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
import numpy as np
from scipy.io import wavfile

ROOT = Path(__file__).resolve().parents[1]
SELECTION_SHA = "3ef847bad8c0cc9990fd01b40a0bd9a8ba09374153a166c1f6b910dea82b6e91"
OFFICIAL_SHA = "db2703598678513b3c0a26618d62605f199d722477d51f5c51bfd3908bbf8505"
DRY_SHA = {"lp12": "0c8a41584d700f6e7545f78d64c80eb349bc595fcbbe604e56d03f215c189b47",
           "lp24": "f29886147ad73e91c6a48203ef2da13a73626d44640192a95aca117fbc0ef5a2"}
LIMITS = dict(max_absolute=2**-23, rms_full_scale=1e-8, relative_rms=1e-6)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pin(path, expected=None):
    path = Path(path).resolve()
    actual = sha(path)
    if expected is not None and actual != expected:
        raise ValueError("Changed pinned input: " + str(path))
    return dict(path=str(path), sha256=actual)


def checked(info):
    return pin(info["path"], info["sha256"])


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")


def current_source():
    names = sorted(str(p.relative_to(ROOT)) for p in (ROOT/"Source/DSP").rglob("*") if p.is_file())
    names += ["Tools/RenderMidi.cpp", "Tools/render_midi.py", "CMakeLists.txt"]
    return dict(git_head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                file_sha256={name: sha(ROOT/name) for name in names},
                qualification="Source and binary pinned before/after replay; compilation provenance belongs to the independent production build receipt")


def prepared_case(cohort, name, experiment_path, selection, byte_control=False, baseline=None):
    experiment = json.loads(Path(experiment_path).read_text())
    for key in ("source_manifest", "coefficients", "native_config", "wav", "render_receipt"):
        checked(experiment[key])
    config = json.loads(Path(experiment["coefficients"]["path"]).read_text())
    if not config["enabled"] or config["ramp"] != 1 or config["phase_cycles_training_note91"] != 0:
        raise ValueError("Changed canonical source configuration")
    if config["negative"] + config["positive"] != selection["candidate_coefficients"]:
        raise ValueError("Coefficient selection drift")
    native = [float(v) for v in Path(experiment["native_config"]["path"]).read_text().split()]
    if native != [1, 1, 0, *selection["candidate_coefficients"]]:
        raise ValueError("Native runtime configuration drift")
    receipt = json.loads(Path(experiment["render_receipt"]["path"]).read_text())
    inputs = {key: checked(receipt["inputs"][key]) for key in ("sysex", "midi")}
    settings = receipt["settings"]
    if settings["sample_rate"] != 44100 or settings["automatic_note_offs_at_end"] or settings["program_bank_policy"] != "reject":
        raise ValueError("Unexpected frozen replay policy")
    if cohort == "dry":
        expected = [dict(tick=0, track=0, order=0, kind="meta", meta_type=32, hex="00", sample=0,
            reason="unsupported routing or sequencer-specific meta event", degrades_replay=True)]
        if receipt["ignored_events"] != expected or settings["unsupported_policy"] != "omit with audit":
            raise ValueError("Dry original-MIDI omitted-event policy changed")
        pin(experiment["wav"]["path"], DRY_SHA[name])
    elif receipt["ignored_events"] or settings["unsupported_policy"] != "reject":
        raise ValueError("Unexpected omitted official events")
    if baseline is not None:
        checked(baseline)
        if byte_control and baseline["sha256"] != experiment["wav"]["sha256"]:
            raise ValueError("Non-Saw frozen control was not byte-identical")
    return dict(cohort=cohort, id=name, candidate=experiment["wav"], candidate_receipt=experiment["render_receipt"],
        candidate_experiment=pin(experiment_path), source_manifest=experiment["source_manifest"],
        coefficient_config=experiment["coefficients"], native_config=experiment["native_config"],
        inputs=inputs, preserved_settings=settings, exact_byte_control=byte_control, pre_w4_baseline=baseline)


def prepare(args):
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    official_pin = pin(args.official_run/"results.json", OFFICIAL_SHA)
    official = json.loads(Path(official_pin["path"]).read_text())
    dry_pin = pin(args.dry_root/"manifest.json")
    dry = json.loads(Path(dry_pin["path"]).read_text())
    selection_pin = checked(dry["selection"])
    if selection_pin["sha256"] != SELECTION_SHA or official["selection"] != selection_pin:
        raise ValueError("Dry/factory selections differ")
    selection = json.loads(Path(selection_pin["path"]).read_text())
    cases = [prepared_case("dry", slope, args.dry_root/slope/"experiment-render.json", selection) for slope in ("lp12", "lp24")]
    for row in official["cases"]:
        cases.append(prepared_case("official", row["id"], Path(row["candidate_render"]["wav"]["path"]).parent/"experiment-render.json",
                    selection, row["required_w4_byte_identity"], row["input"]["current_wav"]))
    if len(cases) != 12 or sum(r["exact_byte_control"] for r in cases) != 5:
        raise ValueError("Unexpected frozen case/control count")
    protocol = dict(status="prepared_before_production_replay", tool=pin(__file__), selection=selection_pin,
        official_run=official_pin, dry_manifest=dry_pin, cases=cases,
        comparison="All unmodified raw float32 stereo frames including the complete tail; unity gain, zero alignment offset, no crop",
        arithmetic_limits=LIMITS,
        numerical_acceptance="WAV/PCM identity preferred. Otherwise all three tight numerical bounds must pass; exact five non-Saw controls may not use tolerance.",
        difference_policy="Retain every failed comparison and full/tail diagnostics; no post-result tolerance adjustment",
        midi_policy="Exact input bytes and full receipt settings/events. Dry file retains its sole FF20 channel-prefix metadata omission; all 124 note-ons/offs remain.",
        hardware_equivalence="not_established")
    save(out/"input-inventory.json", protocol)
    print(out/"input-inventory.json", flush=True)


def difference(actual, reference):
    delta = actual.astype(np.float64) - reference.astype(np.float64)
    rms = float(np.sqrt(np.mean(delta*delta)))
    reference_rms = float(np.sqrt(np.mean(reference.astype(np.float64)**2)))
    changed = np.flatnonzero(np.any(delta != 0, axis=1))
    def ordered_float(audio):
        bits = audio.view(np.uint32).astype(np.int64)
        return np.where(bits & 0x80000000, 0x80000000-(bits & 0x7fffffff), 0x80000000+bits)
    ulp = abs(ordered_float(actual)-ordered_float(reference))
    substantial = abs(reference) >= 1e-6
    return dict(max_absolute=float(abs(delta).max()), rms_full_scale=rms,
        reference_rms=reference_rms, relative_rms=rms/max(reference_rms, 1e-30),
        changed_float_samples=int(np.count_nonzero(delta)), changed_frames=len(changed),
        first_changed_frame=None if not len(changed) else int(changed[0]),
        last_changed_frame=None if not len(changed) else int(changed[-1]),
        max_float32_ulp=int(ulp.max()), max_float32_ulp_reference_above_minus120dbfs=int(ulp[substantial].max()) if substantial.any() else None,
        pcm_identical=bool(np.array_equal(actual, reference)))


def replay(args):
    inventory_pin = pin(args.inventory)
    protocol = json.loads(args.inventory.read_text())
    checked(protocol["tool"])
    for key in ("selection", "official_run", "dry_manifest"):
        checked(protocol[key])
    if protocol["arithmetic_limits"] != LIMITS:
        raise ValueError("Prepared numerical bounds changed")
    renderer = pin(args.renderer)
    wrapper = pin(ROOT/"Tools/render_midi.py")
    source = current_source()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ)
    removed = [key for key in ("SEPTUM_W4_CONFIG", "SEPTUM_W4_STATS") if key in env]
    for key in removed:
        del env[key]
    result = dict(status="production_replay_in_progress", protocol=protocol, inventory=inventory_pin,
        renderer=renderer, wrapper=wrapper, source=source, removed_experimental_environment_keys=removed, results=[])
    jobs = []
    for row in protocol["cases"]:
        for key in ("candidate", "candidate_receipt", "candidate_experiment", "source_manifest", "coefficient_config", "native_config"):
            checked(row[key])
        dst = out/row["cohort"]/row["id"]
        dst.mkdir(parents=True)
        for key, filename in (("sysex", "patch.syx"), ("midi", "performance.mid")):
            checked(row["inputs"][key])
            shutil.copyfile(row["inputs"][key]["path"], dst/filename)
        s = row["preserved_settings"]
        cmd = [sys.executable, wrapper["path"], "--renderer", renderer["path"], "--syx", str(dst/"patch.syx"),
            "--midi", str(dst/"performance.mid"), "--output", str(dst/"production.wav"), "--sample-rate", str(s["sample_rate"]),
            "--tail", str(s["tail_seconds"]), "--master-level", str(s["master_level"]), "--channel", str(s["midi_channel"]),
            "--tempo-policy", s["tempo_policy"]]
        if s["unsupported_policy"] == "omit with audit":
            cmd.append("--allow-unsupported")
        if s["note_semantics"] == "Engine keyboard/arpeggiator replay":
            cmd.append("--keyboard-mode")
        jobs.append((row, dst, cmd))
    result["commands"] = [cmd for _, _, cmd in jobs]
    save(out/"protocol-before-rendering.json", result)
    for row, dst, cmd in jobs:
        start = time.monotonic()
        process = subprocess.run(cmd, env=env, capture_output=True, text=True)
        (dst/"render.log").write_text(process.stdout+process.stderr)
        if process.returncode:
            save(out/"render-failure.json", dict(id=row["id"], command=cmd, returncode=process.returncode))
            raise ValueError("Production replay failed: " + row["id"])
        receipt = json.loads((dst/"production.render.json").read_text())
        original = json.loads(Path(row["candidate_receipt"]["path"]).read_text())
        if receipt["inputs"]["renderer"] != renderer:
            raise ValueError("Production binary identity changed")
        for key in ("settings", "midi", "metadata", "replay_event_counts", "replay_events", "ignored_events", "degraded_replay"):
            if receipt[key] != original[key]:
                raise ValueError("Replay semantics changed: " + row["id"] + "/" + key)
        for key in ("frames", "sample_rate", "latency_samples", "master_level", "initial_patch", "patch_tempo_at_end", "clock_tempo_at_end", "patch_load_warning", "active_voices_at_end"):
            if receipt["output"][key] != original["output"][key]:
                raise ValueError("Output semantics changed: " + row["id"] + "/" + key)
        for key in ("sysex", "midi"):
            if receipt["inputs"][key]["sha256"] != row["inputs"][key]["sha256"]:
                raise ValueError("Input bytes changed")
        sr, actual = wavfile.read(dst/"production.wav")
        cr, candidate = wavfile.read(row["candidate"]["path"])
        if sr != cr or sr != 44100 or actual.shape != candidate.shape or actual.dtype != np.float32 or candidate.dtype != np.float32 or actual.ndim != 2 or actual.shape[1] != 2:
            raise ValueError("Complete raw format/dimensions changed")
        if not np.isfinite(actual).all() or not np.isfinite(candidate).all():
            raise ValueError("Nonfinite output")
        full = difference(actual, candidate)
        tail_start = receipt["midi"]["end_sample"]
        tail = difference(actual[tail_start:], candidate[tail_start:])
        wave = pin(dst/"production.wav")
        byte_identical = wave["sha256"] == row["candidate"]["sha256"]
        numeric_pass = all(full[key] <= value for key, value in LIMITS.items())
        peak = float(abs(actual).max())
        passes = numeric_pass and peak < 1 and receipt["output"]["active_voices_at_end"] == 0
        if row["exact_byte_control"]:
            passes = passes and byte_identical and full["pcm_identical"]
        record = dict(cohort=row["cohort"], id=row["id"], production=wave, production_receipt=pin(dst/"production.render.json"),
            candidate=row["candidate"], frames=len(actual), sample_rate=sr, byte_identical=byte_identical,
            exact_byte_control=row["exact_byte_control"], full_difference=full, tail_difference=tail,
            tail_samples=[tail_start, len(actual)], finite=True, peak=peak,
            samples_at_or_above_full_scale=int(np.count_nonzero(abs(actual) >= 1)), active_voices_at_end=receipt["output"]["active_voices_at_end"],
            final_replayed_event_sample=max(e["sample"] for e in receipt["replay_events"]),
            no_future_queued_midi=all(e["sample"] < len(actual) for e in receipt["replay_events"]),
            event_counts=receipt["replay_event_counts"], numerical_bounds_pass=numeric_pass, integration_pass=passes,
            elapsed_seconds=time.monotonic()-start)
        result["results"].append(record)
        save(out/"results-partial.json", result)
        print(row["cohort"], row["id"], "byte-identical" if byte_identical else f"max={full['max_absolute']:.9g}; rms={full['rms_full_scale']:.9g}; pass={passes}", flush=True)
    if current_source() != source or pin(args.renderer) != renderer or pin(wrapper["path"]) != wrapper:
        raise ValueError("Source/wrapper/binary changed during replay")
    result["status"] = "complete"
    result["summary"] = dict(case_count=len(result["results"]),
        all_byte_identical=all(r["byte_identical"] for r in result["results"]),
        all_integration_pass=all(r["integration_pass"] for r in result["results"]),
        all_five_controls_byte_identical=all(r["byte_identical"] for r in result["results"] if r["exact_byte_control"]),
        maximum_absolute_difference=max(r["full_difference"]["max_absolute"] for r in result["results"]),
        maximum_rms_difference=max(r["full_difference"]["rms_full_scale"] for r in result["results"]),
        total_stereo_frames=sum(r["frames"] for r in result["results"]), hardware_equivalence="not_established")
    save(out/"results.json", result)
    if not result["summary"]["all_integration_pass"]:
        raise SystemExit("Numerical integration mismatch retained; do not infer musical equivalence")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest="stage", required=True)
    q = commands.add_parser("prepare")
    q.add_argument("--dry-root", type=Path, required=True)
    q.add_argument("--official-run", type=Path, required=True)
    q.add_argument("--output", type=Path, required=True)
    q = commands.add_parser("replay")
    q.add_argument("--inventory", type=Path, required=True)
    q.add_argument("--renderer", type=Path, required=True)
    q.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    prepare(args) if args.stage == "prepare" else replay(args)


if __name__ == "__main__":
    main()
