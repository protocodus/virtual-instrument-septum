#!/usr/bin/env python3
"""Inspect The Choir's opening for source isolation; do not infer cutoff/MIDI.

Nearby FFT peaks are descriptive observations, not identified oscillator or
note families. Multiple voices, Super Saw components and wet effects overlap.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np
from scipy import signal
from scipy.io import wavfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", required=True, type=Path)
    parser.add_argument("--renderer", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    catalog_path = ROOT / "Docs/fidelity/hardware-reference-catalog.json"
    catalog = json.loads(catalog_path.read_text())
    ref = next(r for r in catalog["recordings"] if r["id"] == "pad-03")
    bank = next(b for b in catalog["banks"] if b["id"] == ref["bank_id"])
    for item in (ref, bank):
        if sha(args.sources / item["local_filename"]) != item["sha256"]:
            raise ValueError("Official source cache identity changed")
    mp3, zip_path = (args.sources / r["local_filename"] for r in (ref, bank))
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ValueError("ffmpeg required")
    wav, syx = out / "hardware.wav", out / "original-patch.syx"
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(mp3),
               "-c:a", "pcm_f32le", str(wav)]
    subprocess.run(command, check=True)
    subprocess.run([sys.executable, str(ROOT / "Tools/extract_reference_patch.py"),
                    str(zip_path), "--patch", "The Choir", "--output", str(syx)], check=True)
    inspected = subprocess.check_output([str(args.renderer.resolve()), "--inspect-patch", str(syx)], text=True)
    patch = json.loads(inspected)
    sr, audio = wavfile.read(wav)
    if sr != 44100 or audio.ndim != 2 or audio.shape[1] != 2 or not np.isfinite(audio).all():
        raise ValueError("Expected finite stereo44.1kHz original decode")
    y = audio.mean(axis=1)
    observations = []
    for center in (.35, .6, 1., 2., 4.5):
        start, end = round((center-.1)*sr), round((center+.1)*sr)
        x = y[start:end]
        z = abs(np.fft.rfft(x*np.hanning(len(x)), 131072))
        f = np.fft.rfftfreq(131072, 1/sr)
        peaks = signal.find_peaks(z, distance=20)[0]
        peaks = sorted([i for i in peaks if 70 < f[i] < 3000], key=lambda i:z[i], reverse=True)[:15]
        observations.append({"center_seconds": center, "sample_interval": [start,end],
            "peaks": sorted([{"frequency_hz": float(f[i]),
                              "relative_to_window_peak_db": float(20*np.log10(z[i]/max(z)))}
                             for i in peaks], key=lambda r:r["frequency_hz"])})
    result = {"schema_version": 1, "status": "source_isolation_not_established",
        "reference_id": ref["id"], "source_url": ref.get("url", "https://www.rolandus.com/go/sh-201_patches/mp3/PAD/TOP8_The_Choir.mp3"),
        "catalog_sha256": sha(catalog_path), "mp3_sha256": sha(mp3), "bank_sha256": sha(zip_path),
        "wav_sha256": sha(wav), "sysex_sha256": sha(syx), "script_sha256": sha(__file__),
        "decoder": {"command": command, "sha256": sha(ffmpeg),
                    "version": subprocess.check_output([ffmpeg,"-version"],text=True).splitlines()[0]},
        "codec": {"renderer_sha256": sha(args.renderer), "inspection": patch},
        "audio": {"sample_rate": sr,"duration_seconds":len(y)/sr,"peak":float(abs(audio).max())},
        "method": {"window_seconds":.2,"window":"Hann","fft_samples":131072,
                   "zero_padding_does_not_improve_true_resolution":True,"peak_spacing_fft_bins":20,
                   "frequency_interval_hz":[70,3000],"peaks_per_window":15,
                   "stereo_policy":"channel mean; possible wet cancellation retained"},
        "observations": observations,
        "conclusion": "Overlapping narrow components do not identify one isolated source or a played MIDI note. No filter frequency, key-follow anchor, raw control calibration or replacement DSP is inferred.",
        "limits": ["Harmonics, different voices and detuned Super Saw components can coincide.",
                   "Strong approximately880–940Hz components cannot be assumed to be the filter corner.",
                   "Noise-floor extraction is contaminated by tonal leakage and wet effects.",
                   "Native patch octave0 does not recover original notes, system/controller state or exact recorded patch revision."]}
    (out / "results.json").write_text(json.dumps(result, indent=2)+"\n")
    shutil.copyfile(__file__,out / "experiment-script.py")
    print(out / "results.json")


if __name__ == "__main__":
    main()
