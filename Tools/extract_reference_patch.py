#!/usr/bin/env python3
"""Extract documented SH-201 parameter blocks from a local Roland librarian bank.

The container layout is observed in Roland's public SH2LibrarianFile0000 banks;
the payload sizes and DT1 framing follow the SH-201 MIDI Implementation v1.00.
This tool downloads nothing and ships no Roland patch data or recordings.
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import zipfile


BLOCK_SIZES = (33, 64, 64, 5, 10, 8) + (66,) * 16
HEADER_SIZE = 160


def read_bank(path):
    """Return bank bytes and archive member identity without extracting files."""
    if path.suffix.lower() != ".zip":
        return path.read_bytes(), None
    with zipfile.ZipFile(path) as archive:
        members = [item for item in archive.infolist()
                   if item.filename.lower().endswith(".shl") and not item.is_dir()]
        if len(members) != 1:
            raise ValueError("expected exactly one .shl member in the archive")
        if members[0].file_size > 16 * 1024 * 1024:
            raise ValueError("librarian bank exceeds the 16 MiB tool limit")
        return archive.read(members[0]), members[0].filename


def parse_bank(data):
    """Validate all records before returning their raw, unmodified blocks."""
    if len(data) < HEADER_SIZE or data[:20] != b"SH2LibrarianFile0000":
        raise ValueError("unsupported librarian header (expected SH2LibrarianFile0000)")
    count = struct.unpack_from(">I", data, 32)[0]
    if not 1 <= count <= 4096:
        raise ValueError("invalid patch count")
    position = HEADER_SIZE
    patches = []
    for index in range(count):
        if position + 4 > len(data):
            raise ValueError(f"truncated record {index + 1}")
        size = struct.unpack_from(">I", data, position)[0]
        position += 4
        end = position + size
        if end > len(data):
            raise ValueError(f"record {index + 1} extends past the bank")
        blocks = []
        for block, expected_size in enumerate(BLOCK_SIZES):
            if position + 4 > end:
                raise ValueError(f"missing block {block} in record {index + 1}")
            block_size = struct.unpack_from(">I", data, position)[0]
            position += 4
            if block_size != expected_size or position + block_size > end:
                raise ValueError(f"invalid block {block} in record {index + 1}")
            payload = data[position:position + block_size]
            if any(value > 127 for value in payload):
                raise ValueError(f"non-MIDI payload in record {index + 1}, block {block}")
            blocks.append(payload)
            position += block_size
        # Remaining bytes are librarian category/comment metadata, not sound
        # parameters. Preserve their identity in the bank hash, never emit them
        # as extra synthesizer bytes.
        position = end
        name = blocks[0][:12].decode("ascii").rstrip(" \0")
        patches.append((name, blocks))
    if position != len(data):
        raise ValueError("unrecognized data after the final patch record")
    return patches


def encode_syx(blocks):
    result = bytearray()
    for index, payload in enumerate(blocks):
        address = bytes((0x10, 0, index, 0))  # Temporary Patch, offset block:00
        checksum = (-sum(address + payload)) & 0x7F
        result.extend(bytes((0xF0, 0x41, 0x10, 0, 0, 0x16, 0x12))
                      + address + payload + bytes((checksum, 0xF7)))
    return bytes(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bank", type=Path, help="local official .shl or single-bank .zip")
    parser.add_argument("--list", action="store_true", help="list one-based patch numbers")
    parser.add_argument("--patch", help="exact patch name or one-based number")
    parser.add_argument("--output", type=Path, help="destination .syx path")
    parser.add_argument("--source-url", default="", help="bank download URL for provenance")
    parser.add_argument("--reference-audio-url", default="", help="paired recording URL")
    args = parser.parse_args()
    try:
        data, member = read_bank(args.bank)
        patches = parse_bank(data)
        if args.list:
            for number, (name, _) in enumerate(patches, 1):
                print(f"{number:3d}  {name}")
        if not args.patch:
            if not args.list:
                parser.error("provide --list or --patch")
            return 0
        if args.output is None:
            parser.error("--patch requires --output")
        if args.patch.isdecimal():
            number = int(args.patch)
            if not 1 <= number <= len(patches):
                raise ValueError("patch number is outside the bank")
        else:
            matches = [i + 1 for i, (name, _) in enumerate(patches)
                       if name.casefold() == args.patch.casefold()]
            if len(matches) != 1:
                raise ValueError("patch name must identify exactly one entry; use --list")
            number = matches[0]
        name, blocks = patches[number - 1]
        syx = encode_syx(blocks)
        manifest = {
            "schema_version": 1,
            "source_file": str(args.bank.resolve()),
            "archive_member": member,
            "bank_sha256": hashlib.sha256(data).hexdigest(),
            "source_url": args.source_url or None,
            "reference_audio_url": args.reference_audio_url or None,
            "patch_number": number,
            "patch_name": name,
            "output_sha256": hashlib.sha256(syx).hexdigest(),
            "parameter_modifications": [],
            "unknowns": ["played MIDI and velocity", "system settings",
                         "recording output path and gain", "mastering and lossy encoding"],
            "container_evidence": "observed Roland SH2LibrarianFile0000 format",
            "payload_evidence": "SH-201 MIDI Implementation v1.00 parameter map and DT1 framing",
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(syx)
        args.output.with_suffix(".provenance.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"Extracted {number}: {name} -> {args.output}")
        return 0
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
