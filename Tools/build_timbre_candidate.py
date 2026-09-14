#!/usr/bin/env python3
"""Build an isolated, explicitly experimental timbre renderer from a JSON profile.

Example:
  python3 Tools/build_timbre_candidate.py --profile PROFILE.json --output NEW_DIR

This tool never changes shipping DSP sources or contacts MIDI/audio devices.
It compiles a frozen source copy, rather than linking an existing DSP archive.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MAX_PROFILE_BYTES = 256 * 1024


class CandidateError(ValueError):
    """Invalid profile, incompatible sources, or unsuccessful candidate build."""


# name: C++ member, element count (None means scalar), minimum, maximum,
# ordering. "increasing" is strict; the other monotonic laws allow equality.
FIELDS = {
    "filter": {
        "cutoff_hz": ("cutoffHz", 128, 5.0, 40000.0, "nondecreasing"),
        "resonance_damping": ("resonanceDamping", 128, -0.04, 4.0, "nonincreasing"),
        "second_stage_damping": ("secondStageDamping", 128, 0.25, 4.0, "nonincreasing"),
    },
    "envelope": {
        "attack_seconds": ("attackSeconds", 128, 0.00001, 120.0, "nondecreasing"),
        "decay_seconds": ("decaySeconds", 128, 0.00001, 120.0, "nondecreasing"),
        "sustain_level": ("sustainLevel", 128, 0.0, 1.0, "nondecreasing"),
        "release_seconds": ("releaseSeconds", 128, 0.00001, 120.0, "nondecreasing"),
    },
    "waves": {
        "phase_cycles": ("phaseCycles", 5, 0.0, 1.0, None),
        "wave_gain": ("waveGain", 5, -2.0, 2.0, None),
        "pulse_duty": ("pulseDuty", 128, 0.01, 0.99, "nondecreasing"),
    },
    "supersaw": {
        # The incumbent polynomial has a small local decrease at raw 5–6.
        # Preserve it when omitted; bounded diagnostic tables may retain it.
        "detune": ("superDetune", 128, 0.0, 2.0, None),
        "offsets": ("superOffsets", 7, -0.25, 0.25, "increasing"),
        "center_gain": ("superCenterGain", 128, 0.0, 2.0, None),
        "side_gain": ("superSideGain", 128, 0.0, 2.0, None),
        "hpf_ratio": ("superHpfRatio", None, 0.05, 4.0, None),
        "hpf_q": ("superHpfQ", None, 0.25, 2.0, None),
        "normalization": ("superNormalization", None, 0.05, 2.0, None),
    },
}
ENABLED = {"filter": "filterEnabled", "envelope": "envelopeEnabled",
           "waves": "wavesEnabled", "supersaw": "superSawEnabled"}


def _number(value, name, minimum, maximum):
    if type(value) not in (int, float):
        raise CandidateError(f"{name}: expected a finite number, not a boolean or string")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or not minimum <= value <= maximum:
        raise CandidateError(f"{name}: expected a finite value in {minimum}..{maximum}")


def validate_profile(profile):
    """Validate all supplied fields; omitted fields retain engine defaults."""
    if not isinstance(profile, dict):
        raise CandidateError("Profile must be a JSON object")
    unknown = set(profile) - {"version", "id", "evidence", "reference_rate_hz", *FIELDS}
    if unknown:
        raise CandidateError("Unknown profile keys: " + ", ".join(sorted(unknown)))
    if type(profile.get("version")) is not int or profile["version"] != 1:
        raise CandidateError("version must be the integer 1")
    if not isinstance(profile.get("id"), str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", profile["id"]):
        raise CandidateError("id must be 1–80 letters, digits, dots, underscores or hyphens")
    evidence = profile.get("evidence")
    if not isinstance(evidence, str) or not re.search(r"\bexperimental\b", evidence, re.I):
        raise CandidateError("evidence must explicitly describe the profile as experimental")
    if "reference_rate_hz" in profile:
        _number(profile["reference_rate_hz"], "reference_rate_hz", 8000.0, 192000.0)
    for section, fields in FIELDS.items():
        if section not in profile:
            continue
        values = profile[section]
        if not isinstance(values, dict):
            raise CandidateError(f"{section}: expected an object")
        unknown = set(values) - set(fields)
        if unknown:
            raise CandidateError(f"Unknown {section} keys: " + ", ".join(sorted(unknown)))
        for field, value in values.items():
            _, size, minimum, maximum, order = fields[field]
            name = f"{section}.{field}"
            if size is None:
                _number(value, name, minimum, maximum)
                continue
            if not isinstance(value, list) or len(value) != size:
                raise CandidateError(f"{name}: expected an array of exactly {size} numbers")
            for index, item in enumerate(value):
                _number(item, f"{name}[{index}]", minimum, maximum)
            pairs = list(zip(value, value[1:]))
            if (order == "nondecreasing" and any(a > b for a, b in pairs)
                    or order == "nonincreasing" and any(a < b for a, b in pairs)
                    or order == "increasing" and any(a >= b for a, b in pairs)):
                raise CandidateError(f"{name}: values must be {order}")
            if field == "phase_cycles" and any(item >= 1.0 for item in value):
                raise CandidateError(f"{name}: phases must be less than 1 cycle")
            if field == "sustain_level" and (value[0] != 0.0 or value[-1] != 1.0):
                raise CandidateError(f"{name}: endpoints must be exactly 0 and 1")
            if field == "offsets" and value[3] != 0.0:
                raise CandidateError(f"{name}: center element 3 must be exactly zero")
    return profile


def _unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise CandidateError(f"Duplicate JSON key: {name}")
        result[name] = value
    return result


def load_profile(path):
    data = Path(path).read_bytes()
    if len(data) > MAX_PROFILE_BYTES:
        raise CandidateError("Profile exceeds 256 KiB")
    try:
        profile = json.loads(data, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CandidateError(f"Invalid profile JSON: {error}") from error
    validate_profile(profile)
    return profile, data


def candidate_header(profile):
    validate_profile(profile)
    lines = ["// Generated experimental configuration. No hardware-match claim.",
             "#pragma once", '#include "DSP/SeptumEngine.h"', "",
             "inline septum::TimbreCalibration makeCandidateProfile()", "{",
             "    auto profile = septum::Engine::defaultTimbreCalibration();"]
    for section, fields in FIELDS.items():
        if section not in profile:
            continue
        lines.append(f"    profile.{ENABLED[section]} = true;")
        if section == "filter" and "second_stage_damping" in profile[section]:
            lines.append("    profile.secondStageIndependent = true;")
        if section == "supersaw" and "detune" in profile[section]:
            lines.append("    profile.superDetuneTableEnabled = true;")
        for field in fields:
            if field not in profile[section]:
                continue
            member, size, *_ = fields[field]
            value = profile[section][field]
            number = lambda item: format(float(item), ".17g")
            expression = number(value) if size is None else "{ " + ", ".join(map(number, value)) + " }"
            lines.append(f"    profile.{member} = {expression};")
    lines += ["    return profile;", "}", ""]
    return "\n".join(lines)


def _replace_once(text, old, new):
    if text.count(old) != 1:
        raise CandidateError("Renderer integration point changed; expected exactly one: " + old.strip())
    return text.replace(old, new, 1)


def candidate_renderer(source, profile):
    """Adapt only the copied renderer's type/setup, never DSP implementation."""
    reference = profile.get("reference_rate_hz")
    include = '#include "DSP/SeptumEngine.h"'
    extra = '\n#include "CandidateProfile.h"'
    if reference is not None:
        extra += '\n#include "DSP/ReferenceRateEngine.h"'
    source = _replace_once(source, include, include + extra)
    source = _replace_once(source, "using Bytes = std::vector<std::uint8_t>;",
                          "using CandidateEngine = septum::"
                          + ("ReferenceRateEngine;" if reference is not None else "Engine;")
                          + "\nusing Bytes = std::vector<std::uint8_t>;")
    source = _replace_once(source, "void applyMidi (septum::Engine& engine,",
                          "void applyMidi (CandidateEngine& engine,")
    source = _replace_once(source, "auto engine = std::make_unique<septum::Engine>();",
                          "auto engine = std::make_unique<CandidateEngine>();")
    prepare = "engine->prepare (rate, blockSize);"
    call = "engine->prepare (rate, blockSize" + (
        ", " + format(float(reference), ".17g") if reference is not None else "") + ");"
    source = _replace_once(source, prepare,
                          "if (! engine->setTimbreCalibration (makeCandidateProfile()))\n"
                          '            throw std::runtime_error ("Experimental timbre profile rejected by engine");\n'
                          "        " + call)
    return source


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _sources(root):
    result = {}
    dsp = root / "Source/DSP"
    if not dsp.is_dir():
        raise CandidateError("Missing Source/DSP source directory")
    for path in sorted(dsp.rglob("*")):
        if path.is_symlink():
            raise CandidateError("DSP source snapshots cannot contain symlinks: " + str(path))
        if path.is_file():
            result[path.relative_to(root).as_posix()] = path.read_bytes()
    renderer = root / "Tools/RenderMidi.cpp"
    if renderer.is_symlink():
        raise CandidateError("Renderer must be a regular source file")
    result["Tools/RenderMidi.cpp"] = renderer.read_bytes()
    return result


def _git(root, *arguments):
    try:
        result = subprocess.run(["git", *arguments], cwd=root, text=True,
                                capture_output=True, timeout=15, check=True)
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def build_candidate(profile_path, output, *, compiler="c++", source_root=ROOT):
    """Build a new directory. Refuse overwrites and retain logs on build failure."""
    profile, original_profile = load_profile(profile_path)
    root = Path(source_root).resolve()
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise CandidateError("Output already exists; choose a new directory")
    # The output is an artifact, never a destination within shipping sources.
    resolved = output.resolve()
    if any(resolved == parent or parent in resolved.parents
           for parent in (root / "Source", root / "Tools")):
        raise CandidateError("Candidate output must be outside shipping Source and Tools directories")
    executable = shutil.which(str(compiler))
    if not executable:
        raise CandidateError("C++ compiler not found: " + str(compiler))
    # Keep the driver name: clang++ may be a symlink to clang, and invoking
    # its resolved target changes automatic C++ standard-library linkage.
    executable = str(Path(executable).absolute())
    snapshot = _sources(root)
    if "Source/DSP/TimbreCalibration.h" not in snapshot:
        raise CandidateError("This source tree does not provide TimbreCalibration.h")
    transformed = candidate_renderer(snapshot["Tools/RenderMidi.cpp"].decode("utf-8"), profile)
    generated_header = candidate_header(profile).encode("utf-8")
    head = _git(root, "rev-parse", "HEAD")
    dirty = _git(root, "status", "--porcelain", "--", "Source/DSP", "Tools/RenderMidi.cpp")
    if _sources(root) != snapshot:
        raise CandidateError("Source tree changed during snapshot; retry after edits finish")
    try:
        version = subprocess.run([executable, "--version"], capture_output=True,
                                 text=True, timeout=30, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        raise CandidateError("Cannot query C++ compiler: " + str(error)) from error
    try:
        output.mkdir(parents=True, exist_ok=False)
    except FileExistsError as error:
        raise CandidateError("Output already exists; choose a new directory") from error
    files = dict(snapshot)
    files["original/Tools/RenderMidi.cpp"] = snapshot["Tools/RenderMidi.cpp"]
    files["Tools/RenderMidi.cpp"] = transformed.encode("utf-8")
    files["CandidateProfile.h"] = generated_header
    files["profile.original.json"] = original_profile
    files["profile.json"] = (json.dumps(profile, indent=2, allow_nan=False) + "\n").encode()
    for name, data in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    cpp = sorted(name for name in snapshot if name.startswith("Source/DSP/") and name.endswith(".cpp"))
    renderer_name = "SeptumRenderMidi.exe" if sys.platform == "win32" else "SeptumRenderMidi"
    command = [executable, "-std=c++20", "-O2", "-fno-fast-math", "-ISource", "-I.",
               "Tools/RenderMidi.cpp", *cpp, "-o", renderer_name]
    manifest = {
        "version": 1, "status": "building", "id": profile["id"], "evidence": profile["evidence"],
        "experimental": True, "hardware_match_claim": False,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source": {"root": str(root), "head": head, "working_tree_changes": dirty,
                   "input_sha256": {name: _sha(data) for name, data in snapshot.items()}},
        "profile": {"original_path": str(Path(profile_path).resolve()),
                    "original_sha256": _sha(original_profile),
                    "canonical_sha256": _sha(files["profile.json"]),
                    "enabled_sections": [section for section in FIELDS if section in profile],
                    "provided_fields": {section: sorted(profile[section])
                                        for section in FIELDS if section in profile},
                    "reference_rate_hz": profile.get("reference_rate_hz")},
        "compiler": {"path": executable, "resolved_path": str(Path(executable).resolve()),
                     "sha256": _sha(Path(executable).read_bytes()),
                     "version": version, "command": command, "working_directory": str(output)},
        "builder": {"path": str(Path(__file__).resolve()),
                    "sha256": _sha(Path(__file__).read_bytes())},
        "frozen_sha256": {name: _sha(data) for name, data in files.items()},
        "integration": "Copied renderer installs CandidateProfile through the public API before preparation; copied DSP source is unchanged.",
    }
    manifest_path = output / "manifest.json"

    def save_manifest():
        manifest_path.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")

    save_manifest()
    failure = None
    try:
        with (output / "build.log").open("w") as log:
            result = subprocess.run(command, cwd=output, stdout=log, stderr=subprocess.STDOUT, timeout=240)
        if result.returncode:
            failure = f"Compiler failed with status {result.returncode}; see {output / 'build.log'}"
        changed = [name for name, data in files.items()
                   if not (output / name).is_file() or (output / name).read_bytes() != data]
        if changed:
            failure = "Frozen build inputs changed during compilation: " + ", ".join(changed)
        manifest["frozen_inputs_verified"] = not changed
    except (OSError, subprocess.SubprocessError) as error:
        failure = "Candidate compilation failed: " + str(error)
    if failure:
        manifest["status"] = "failed"
        manifest["error"] = failure
        save_manifest()
        raise CandidateError(failure)
    binary = output / renderer_name
    if not binary.is_file():
        manifest["status"] = "failed"
        manifest["error"] = "Compiler reported success but did not produce the renderer"
        save_manifest()
        raise CandidateError(manifest["error"])
    manifest["status"] = "complete"
    manifest["renderer"] = {"path": renderer_name, "sha256": _sha(binary.read_bytes())}
    manifest["build_log_sha256"] = _sha((output / "build.log").read_bytes())
    save_manifest()
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--compiler", default="c++", help="C++20 compiler executable (no shell flags)")
    args = parser.parse_args(argv)
    try:
        result = build_candidate(args.profile, args.output, compiler=args.compiler)
    except (CandidateError, OSError) as error:
        print("Timbre candidate: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps({"id": result["id"], "renderer": str(args.output.resolve() / result["renderer"]["path"]),
                      "manifest": str(args.output.resolve() / "manifest.json"), "experimental": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
