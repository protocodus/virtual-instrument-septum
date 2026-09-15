#!/usr/bin/env python3
"""Materialize and reproduce the dated filter experiment from tracked evidence.

Requires the repository history, optional audio-analysis dependencies, a C++20
compiler, ffmpeg, and the separately acquired original reference caches. No
third-party audio or preset payload is stored in the reproduction manifest.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "Docs/fidelity/source-audits/zero-resonance-reproduction-2026-09-15.json"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def relative(name):
    path = Path(name)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError(f"Invalid artifact path: {name}")
    return path


def materialize(manifest, output):
    if output.exists() or output.is_symlink():
        raise ValueError("Choose a new output directory")
    output.mkdir(parents=True)
    for item in manifest["git_files"]:
        relative(item["source"])
        data = subprocess.check_output(["git", "show", f"{manifest['source_revision']}:{item['source']}"], cwd=ROOT)
        if digest(data) != item["sha256"]:
            raise ValueError(f"Repository-history hash mismatch: {item['source']}")
        path = output / relative(item["destination"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    patch = manifest["source_patch"]
    if digest(patch.encode()) != manifest["source_patch_sha256"]:
        raise ValueError("Frozen source patch hash mismatch")
    # Only the declared repository paths may occur in the historical patch.
    for line in patch.splitlines():
        if line.startswith(("--- ", "+++ ")):
            name = line[4:].split("\t", 1)[0]
            if name.startswith(("a/", "b/")):
                name = name[2:]
            if str(relative(name)) not in manifest["patched_source_paths"]:
                raise ValueError(f"Unexpected frozen patch target: {name}")
    subprocess.run(["patch", "-p1", "--batch", "--forward"],
                   cwd=output / "frozen-source", input=patch, text=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    for item in manifest["embedded_files"]:
        data = item["text"].encode()
        if digest(data) != item["sha256"]:
            raise ValueError(f"Embedded source hash mismatch: {item['path']}")
        path = output / relative(item["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    for name, expected in manifest["frozen_dsp_input_sha256"].items():
        if digest((output / "frozen-source" / relative(name)).read_bytes()) != expected:
            raise ValueError(f"Frozen DSP identity mismatch after reconstruction: {name}")
    (output / "reproduction-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--sources", type=Path, help="Verified official MP3/bank cache")
    parser.add_argument("--deepsonic-sources", type=Path, help="Hash-pinned original MIDI/MP3 and filter_comparison.html; WAVs are decoded privately")
    parser.add_argument("--materialize-only", action="store_true", help="Verify and reconstruct scripts/sources without building or rendering")
    args = parser.parse_args()
    if not args.materialize_only and (not args.sources or not args.deepsonic_sources):
        parser.error("Full reproduction requires both reference caches")
    try:
        manifest = json.loads(MANIFEST.read_text())
        output = args.output.resolve()
        materialize(manifest, output)
        if args.materialize_only:
            print(f"Verified frozen DSP and materialized reproducible scripts: {output}")
            return
        cache = output / "source-cache"
        decoded_sources = cache / "deepsonic"
        decoded_sources.mkdir(parents=True)
        for item in manifest["external_files"]:
            source = args.deepsonic_sources / relative(item["source"])
            if digest(source.read_bytes()) != item["sha256"]:
                raise ValueError(f"External source hash mismatch: {source}")
            shutil.copyfile(source, decoded_sources / relative(item["source"]))
            if item.get("destination"):
                shutil.copyfile(source, output / relative(item["destination"]))
        decoder = shutil.which("ffmpeg")
        if not decoder:
            raise ValueError("ffmpeg is required to decode the original MP3 recordings")
        decoding = {"decoder": decoder, "decoder_sha256": digest(Path(decoder).read_bytes()),
                    "decoder_version": subprocess.check_output([decoder, "-version"], text=True).splitlines()[0],
                    "files": []}
        for slope in (12, 24):
            mp3 = decoded_sources / f"roland_sh-201_-_filter_demo_-_lpf{slope}_q000.mp3"
            wav = mp3.with_suffix(".wav")
            command = [decoder, "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(mp3), "-c:a", "pcm_f32le", str(wav)]
            subprocess.run(command, check=True)
            decoding["files"].append({"source_sha256": digest(mp3.read_bytes()), "decoded_sha256": digest(wav.read_bytes()), "command": command})
        (cache / "decode-manifest.json").write_text(json.dumps(decoding, indent=2) + "\n")
        subprocess.run([sys.executable, "-B", str(output / "run_experiment.py"),
                        "--sources", str(args.sources.resolve())], check=True)
        subprocess.run([sys.executable, "-B", str(output / "frozen-source/Tools/build_timbre_candidate.py"),
                        "--profile", str(output / "profiles/zero-resonance-linear.json"),
                        "--output", str(output / "linear-final/build")], check=True)
        subprocess.run([sys.executable, "-B", str(output / "frozen-source/Tools/compare_hardware.py"),
                        "--sources", str(args.sources.resolve()), "--renderer", str(output / "linear-final/build/SeptumRenderMidi"),
                        "--output", str(output / "linear-final/comparisons"),
                        "--case", str(output / "frozen-source/Docs/fidelity/cases/dist-bs-1.json")], check=True,
                       stdout=subprocess.DEVNULL)
        subprocess.run([sys.executable, "-B", str(output / "frozen-source/Tools/assess_hardware_equivalence.py"),
                        "--comparison", str(output / "linear-final/comparisons/dist-bs-1/comparison.json"),
                        "--calibration-fraction", "0.25", "--max-lag-seconds", "0.05",
                        "--output", str(output / "linear-final/equivalence-prefix25.json")], check=True,
                       stdout=subprocess.DEVNULL)
        # Original captured scripts retain their exact source bytes. Override
        # only their input-directory variable to use this run's private decode.
        environment = dict(os.environ, OPENBLAS_NUM_THREADS="1", VECLIB_MAXIMUM_THREADS="1")
        setup = "import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); import run_dry; run_dry.ROOT=Path(sys.argv[2]); "
        for call in ("run_dry.main()", "import refine_onset; refine_onset.main()"):
            subprocess.run([sys.executable, "-B", "-c", setup + call,
                            str(output / "dry-end-to-end"), str(cache)], check=True, env=environment)
        print(output / "dry-end-to-end/onset-calibrated/results.json")
    except (OSError, ValueError, subprocess.SubprocessError, KeyError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
