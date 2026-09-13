#!/usr/bin/env python3
"""Build and measure isolated resonance candidates; never edit shipping DSP."""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError(f"Expected exactly one source anchor: {old!r}")
    return source.replace(old, new, 1)


def summarize(path):
    rows = list(csv.DictReader(path.open()))
    groups = {}
    for row in rows:
        groups.setdefault((row["type"], row["slope"], row["input_amplitude"]), []).append(row)
    trends = []
    for key, values in groups.items():
        differences = []
        for before, after in zip(values, values[1:]):
            db = 20 * math.log10(max(float(after["rms"]), 1e-30)
                                / max(float(before["rms"]), 1e-30))
            differences.append((db, int(after["resonance"])))
        lowest = min(differences)
        highest = max(differences)
        trends.append({"type": key[0], "slope": int(key[1]), "input_amplitude": float(key[2]),
                       "worst_downward_step_db": lowest[0], "downward_step_raw": lowest[1],
                       "largest_upward_step_db": highest[0], "upward_step_raw": highest[1],
                       "stage1_first_limited_raw": next((int(r["resonance"]) for r in values
                                                           if int(r["stage1_limit_hits"]) > 0), None),
                       "stage2_first_limited_raw": next((int(r["resonance"]) for r in values
                                                           if int(r["stage2_limit_hits"]) > 0), None)})
    return {"renders": len(rows), "all_finite": all(row["finite"] == "1" for row in rows),
            "maximum_output_peak": max(float(row["output_peak"]) for row in rows),
            "trends": trends}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New output directory (must not exist)")
    parser.add_argument("--archive", type=Path, default=Path("build-fidelity/libSeptumDSP.a"))
    parser.add_argument("--source", type=Path, help="Source directory containing DSP; defaults to current shipping Source")
    parser.add_argument("--compiler", default="c++")
    parser.add_argument("--profiles", nargs="+", choices=("baseline", "first-stage-2.7", "two-stage-1.6"),
                        default=["baseline", "first-stage-2.7", "two-stage-1.6"])
    parser.add_argument("--modes", nargs="+", choices=("transfer", "sweep"), default=["transfer", "sweep"])
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source_root = (args.source or root / "Source").resolve()
    archive = args.archive.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(archive, output / "libSeptumDSP.a")
    # Capture once: simultaneous work on the shared production source must not
    # make two candidate builds use different baseline headers or Engine.cpp.
    captured = output / "production-source/DSP"
    captured.mkdir(parents=True)
    for path in [*sorted((source_root / "DSP").glob("*.h")), source_root / "DSP/SeptumEngine.cpp"]:
        shutil.copy2(path, captured / path.name)
    original = (captured / "SeptumEngine.cpp").read_text()
    all_results = {}
    for profile in args.profiles:
        directory = output / profile
        dsp = directory / "Source/DSP"
        dsp.mkdir(parents=True)
        for header in captured.glob("*.h"):
            shutil.copy2(header, dsp / header.name)
        source = original
        expression = "mapping::resonanceDamping (tone.resonance)"
        # Reconstruct the historical fixed-stage baseline even after production
        # adopts a separate, calibrated voice damping helper. The old mapping is
        # retained for AUDIO FILTER; never redirect that path here.
        resonance_anchors = re.findall(r"const double resonanceTarget = [^;\n]+;", source)
        stage_anchors = re.findall(r"const double k2 = [^;\n]+;", source)
        if len(resonance_anchors) != 1 or len(stage_anchors) != 1:
            raise ValueError("Voice resonance source layout changed; review anchors before building")
        source = replace_once(source, resonance_anchors[0], "const double resonanceTarget = " + expression + ";")
        source = replace_once(source, stage_anchors[0], "const double k2 = 1.2;")
        if profile != "baseline":
            exponent = 2.7 if profile == "first-stage-2.7" else 1.6
            source = replace_once(source, "const double resonanceTarget = " + expression + ";",
                                  "const double originalResonance = " + expression + ";\n"
                                  "    const double resonanceTarget = originalResonance > 0.0\n"
                                  f"        ? 2.0 * std::pow (originalResonance / 2.0, {exponent})\n"
                                  "        : originalResonance;")
        if profile == "two-stage-1.6":
            source = replace_once(source, "const double k2 = 1.2;",
                                  "const double k2 = std::min (1.2, k);")
        # Observe both voice stages before their unchanged limiter. The AUDIO
        # FILTER has separate state variables and remains completely unchanged.
        source = "extern unsigned long long septumAuditLimitHits[2];\nextern double septumAuditLargestState[2];\n" + source
        anchor = "                stage.ic1eq = limitState (stage.ic1eq);\n                stage.ic2eq = limitState (stage.ic2eq);"
        source = replace_once(source, anchor,
            "                const int auditStage = &stage == &voice.filter1 ? 0 : 1;\n"
            "                for (double auditValue : { stage.ic1eq, stage.ic2eq })\n"
            "                {\n"
            "                    septumAuditLargestState[auditStage] = std::max (\n"
            "                        septumAuditLargestState[auditStage], std::abs (auditValue));\n"
            "                    if (std::abs (auditValue) > mapping::filterStateLimit)\n"
            "                        ++septumAuditLimitHits[auditStage];\n"
            "                }\n" + anchor)
        engine = dsp / "SeptumEngine.cpp"
        engine.write_text(source)
        probe = directory / "AnalyzeResonance.cpp"
        shutil.copy2(root / "Tools/AnalyzeResonance.cpp", probe)
        binary = directory / "AnalyzeResonance"
        command = [args.compiler, "-std=c++20", "-O3", "-I", str(directory / "Source"),
                   str(probe), str(engine), str(output / "libSeptumDSP.a"), "-o", str(binary)]
        subprocess.run(command, check=True)
        executed_modes = [m for m in args.modes if m != "transfer" or profile == "baseline"]
        for mode in executed_modes:
            with (directory / f"{mode}.csv").open("w") as handle:
                subprocess.run([str(binary), "--" + mode], stdout=handle, check=True)
        summary = summarize(directory / "sweep.csv") if (directory / "sweep.csv").exists() else {}
        metadata = {"schema_version": 1, "status": "historical fixed-stage baseline" if profile == "baseline" else "experimental; not hardware validated",
                    "profile": profile, "sample_rate": 48000, "seconds_per_render": 2,
                    "measurement_window_seconds": [1, 2], "executed_modes": executed_modes,
                    "stimulus": "EXT-IN sine; executed modes and CSV rows specify frequency ratios and parameter coverage",
                    "input_amplitudes": [0.001, 1.0], "post_filter_tone_level": 25,
                    "cutoff": 64, "audio_filter_on": False,
                    "cautions": ["Finite-duration sweep; high-Q cases may still be building, so RMS is not steady-state Q.",
                                 "Adjacent settings use independent reset renders, not a live automation transition.",
                                 "Output peak includes the initial EXT-IN direct-monitor handover; RMS and projection use seconds1..2.",
                                 "State2 runs even on slope12; its limiter counts need not affect selected output.",
                                 "These are implementation diagnostics, not measurements of Roland hardware."],
                    "original_engine_cpp_sha256": sha256(captured / "SeptumEngine.cpp"),
                    "original_engine_h_sha256": sha256(captured / "SeptumEngine.h"),
                    "compiler_command": command,
                    "files": {str(p.relative_to(directory)): sha256(p) for p in sorted(directory.rglob("*")) if p.is_file()},
                    "archive_sha256": sha256(output / "libSeptumDSP.a"), "summary": summary}
        (directory / "profile.json").write_text(json.dumps(metadata, indent=2) + "\n")
        all_results[profile] = summary
        print(json.dumps({"profile": profile, "sweep_renders": summary.get("renders", 0),
                          "all_finite": summary.get("all_finite"),
                          "maximum_output_peak": summary.get("maximum_output_peak")}), flush=True)
    (output / "summary.json").write_text(json.dumps(all_results, indent=2) + "\n")


if __name__ == "__main__":
    main()
