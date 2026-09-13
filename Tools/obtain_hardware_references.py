#!/usr/bin/env python3
"""Obtain the public Roland reference corpus, checking every pinned SHA-256.

Recordings and preset payloads remain local. This does not obtain performance
MIDI: the catalog records that limitation explicitly.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def verify(path, asset):
    return (path.is_file() and path.stat().st_size == asset['size_bytes']
            and hashlib.sha256(path.read_bytes()).hexdigest() == asset['sha256'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, default=Path(__file__).resolve().parents[1]
                        / 'Docs/fidelity/hardware-reference-catalog.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--recording', action='append', help='catalog id; repeat to select; default all')
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text())
    recordings = catalog['recordings']
    if args.recording:
        unknown = set(args.recording) - {a['id'] for a in recordings}
        if unknown:
            parser.error('unknown recording ids: ' + ', '.join(sorted(unknown)))
        recordings = [a for a in recordings if a['id'] in args.recording]
    bank_ids = {a['bank_id'] for a in recordings}
    assets = [a for a in catalog['banks'] if a['id'] in bank_ids] + recordings
    args.output.mkdir(parents=True, exist_ok=True)
    for asset in assets:
        filename = asset['local_filename']
        if Path(filename).name != filename:
            raise ValueError('catalog filenames must be simple basenames')
        path = args.output / filename
        if verify(path, asset):
            print('Verified cached ' + filename)
            continue
        with tempfile.TemporaryDirectory(dir=args.output) as temporary:
            downloaded = Path(temporary) / filename
            subprocess.run(['curl', '--fail', '--location', '--silent', '--show-error',
                            '--retry', '2', '--connect-timeout', '15', '--max-time', '90',
                            '--output', str(downloaded), asset['url']], check=True)
            if not verify(downloaded, asset):
                raise ValueError(f'{filename}: content changed; review source before updating catalog')
            downloaded.replace(path)
        print('Downloaded and verified ' + filename)
    print(f'{len(assets)} assets verified. No original performance MIDI accompanies this corpus.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f'error: {error}', file=sys.stderr)
        sys.exit(1)
