#!/usr/bin/env python3
"""Audio tier: render every demo twice and check the takes are complete and deterministic.

Each take must be a non-empty 16-bit stereo WAV, audible, within the -3 dBFS
normalisation ceiling, and byte-identical on a second render, so an
unchanged engine never makes the main build commit new audio.
"""
import argparse
from array import array
import filecmp
from pathlib import Path
import subprocess
import sys
import tempfile
import wave

EXPECTED_DEMOS = 11
# The renderer normalises each take to -3 dBFS on its own peak.
CEILING = round(0.7079457843841379 * 32767) + 1


def check_take(path: Path) -> None:
    with wave.open(str(path), "rb") as take:
        if take.getnchannels() != 2 or take.getsampwidth() != 2 or take.getnframes() == 0:
            raise AssertionError(f"{path.name}: expected a non-empty 16-bit stereo WAV")
        samples = array("h", take.readframes(take.getnframes()))
    peak = max(abs(sample) for sample in samples)
    if peak < 33:
        raise AssertionError(f"{path.name}: silent (peak {peak})")
    if peak > CEILING:
        raise AssertionError(f"{path.name}: peak {peak} exceeds the {CEILING} ceiling")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demos", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="septum-audio-tier-") as folder:
        first, second = Path(folder, "first"), Path(folder, "second")
        for output in (first, second):
            output.mkdir()
            subprocess.run([str(args.demos), "--jobs", "4", str(output)], check=True,
                           stdout=subprocess.DEVNULL, timeout=300)
        takes = sorted(first.glob("[0-9][0-9]-*.wav"))
        if len(takes) != EXPECTED_DEMOS:
            raise AssertionError(f"rendered {len(takes)} demos, expected {EXPECTED_DEMOS}")
        for take in takes:
            check_take(take)
            if not filecmp.cmp(take, second / take.name, shallow=False):
                raise AssertionError(f"{take.name}: a second render is not byte-identical")
    print(f"Septum: {EXPECTED_DEMOS} demos complete, within the ceiling and deterministic")
    return 0


if __name__ == "__main__":
    sys.exit(main())
