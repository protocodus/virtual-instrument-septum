#!/usr/bin/env python3
"""Build the distributable JUCE dependency notice bundle.

The license payloads are copied as bytes from the pinned JUCE checkout.  The
metadata surrounding each payload records the source path and detected source
hash without modifying the license text itself.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JUCE = ROOT / "build-ui" / "_deps" / "juce-src"
OUTPUT = ROOT / "ThirdParty" / "JUCE-DEPENDENCY-NOTICES.txt"
JUCE_VERSION = "8.0.14"
JUCE_COMMIT = "2cdfca8feb300fb424002ba2c2751569e5bacb64"


NOTICES = (
    {
        "name": "JUCE Framework",
        "version": "8.0.14",
        "license": "JUCE Framework licence (AGPLv3/commercial dual licence notice)",
        "source": "LICENSE.md",
        "scope": "All JUCE modules linked by Septum",
    },
    {
        "name": "AudioUnitSDK",
        "version": "1.1.0",
        "license": "Apache License 2.0",
        "source": "modules/juce_audio_plugin_client/AU/AudioUnitSDK/LICENSE.txt",
        "scope": "AU plug-in wrapper on macOS",
    },
    {
        "name": "FLAC (libFLAC)",
        "version": "1.4.3",
        "license": "FLAC BSD-style licence and JUCE integration notice",
        "source": "modules/juce_audio_formats/codecs/flac/Flac Licence.txt",
        "scope": "juce_audio_formats codec support on macOS, Linux, and Windows",
    },
    {
        "name": "Ogg container / Vorbis headers",
        "version": "JUCE-bundled source; version not declared in this notice",
        "license": "Ogg-Vorbis BSD-style licence and JUCE integration notice",
        "source": "modules/juce_audio_formats/codecs/oggvorbis/Ogg Vorbis Licence.txt",
        "scope": "juce_audio_formats codec support on macOS, Linux, and Windows",
    },
    {
        "name": "libvorbis",
        "version": "1.3.7",
        "license": "BSD-style licence",
        "source": "modules/juce_audio_formats/codecs/oggvorbis/libvorbis-1.3.7/COPYING",
        "scope": "Bundled libvorbis implementation used by juce_audio_formats",
    },
    {
        "name": "Independent JPEG Group JPEG software",
        "version": "release 9f (14-Jan-2024)",
        "license": "Independent JPEG Group licence",
        "source": "modules/juce_graphics/image_formats/jpglib/README",
        "scope": "Bundled JPEG image codec used by juce_graphics",
    },
    {
        "name": "libpng",
        "version": "1.6.37",
        "license": "PNG Reference Library License",
        "source": "modules/juce_graphics/image_formats/pnglib/LICENSE",
        "scope": "Bundled PNG image codec used by juce_graphics",
    },
    {
        "name": "zlib",
        "version": "1.3.1",
        "license": "zlib licence",
        "source": "modules/juce_core/zip/zlib/LICENSE",
        "scope": "Bundled ZIP/deflate implementation used by juce_core",
    },
    {
        "name": "HarfBuzz",
        "version": "10.1.0",
        "license": "Old MIT licence",
        "source": "modules/juce_graphics/fonts/harfbuzz/COPYING",
        "scope": "Bundled text shaping implementation used by juce_graphics",
    },
    {
        "name": "SheenBidi",
        "version": "2.9.0",
        "license": "Apache License 2.0",
        "source": "modules/juce_graphics/unicode/sheenbidi/LICENSE",
        "scope": "Bundled bidirectional text implementation used by juce_graphics",
    },
    {
        "name": "VST3 SDK",
        "version": "JUCE-bundled SDK; version not declared in this checkout",
        "license": "MIT License",
        "source": "modules/juce_audio_processors_headless/format_types/VST3_SDK/LICENSE.txt",
        "scope": "VST3 plug-in wrapper on macOS, Linux, and Windows",
    },
)


def build_notice(juce_root: Path) -> bytes:
    lines = [
        "Septum — JUCE dependency notices",
        "=================================",
        "",
        f"Pinned JUCE version: {JUCE_VERSION}",
        f"Pinned JUCE commit: {JUCE_COMMIT}",
        "",
        "This file is intended to accompany distributed Septum plug-ins and",
        "standalone applications. It contains the JUCE licence notice and the",
        "licence texts for bundled third-party components used by Septum's",
        "configured JUCE targets.",
        "",
        "The licence payload between each BEGIN/END pair is copied byte-for-byte",
        "from the source path recorded immediately above it. The surrounding",
        "metadata is provided for provenance and packaging; it is not part of",
        "the upstream licence text.",
        "",
        "Configured formats: VST3 and Standalone on macOS, Linux, and Windows;",
        "AU additionally on macOS. System SDKs and host-provided libraries are",
        "not bundled here and remain subject to their respective terms.",
        "",
        "This artifact records source notices only. It does not grant or claim",
        "any JUCE commercial licence or other commercial distribution right.",
        "",
    ]
    output = "\n".join(lines).encode("utf-8")

    for notice in NOTICES:
        source = juce_root / notice["source"]
        if not source.is_file():
            raise FileNotFoundError(f"Missing JUCE notice source: {source}")

        payload = source.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        metadata = (
            f"===== {notice['name']} =====\n"
            f"Version: {notice['version']}\n"
            f"Licence: {notice['license']}\n"
            f"Scope: {notice['scope']}\n"
            f"Source (JUCE-relative): {notice['source']}\n"
            f"Pinned JUCE version: {JUCE_VERSION}\n"
            f"Pinned JUCE commit: {JUCE_COMMIT}\n"
            f"Source SHA-256: {digest}\n"
            "----- BEGIN UPSTREAM LICENCE TEXT -----\n"
        ).encode("utf-8")
        output += metadata + payload
        output += b"----- END UPSTREAM LICENCE TEXT -----\n\n"

    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the checked-in artifact differs from the pinned sources",
    )
    parser.add_argument(
        "--juce-root",
        type=Path,
        default=DEFAULT_JUCE,
        help=f"JUCE source root (default: {DEFAULT_JUCE})",
    )
    args = parser.parse_args()

    notice = build_notice(args.juce_root)
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_bytes() != notice:
            print(f"{OUTPUT} is out of date")
            return 1
        print(f"{OUTPUT} matches the pinned JUCE notice sources")
        return 0

    OUTPUT.write_bytes(notice)
    print(f"Wrote {OUTPUT} ({len(notice)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
