#!/usr/bin/env python3
"""Build a local player for the cataloged original SH-201 factory demos.

The original MP3 files must already exist at the cataloged paths. This tool
checks their hashes, renders an HTML page, and copies the catalog beside it.
It does not download audio, invent performance MIDI, or produce software audio.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
from urllib.parse import quote, urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "build-fidelity/hardware-benchmark/factory-bank-research/index.html"


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def source_url(value: str) -> str:
    if urlparse(value).scheme != "https":
        raise ValueError(f"Expected an HTTPS source URL: {value}")
    return escape(value)


def duration(seconds: float) -> str:
    rounded = round(seconds)
    return f"{rounded // 60}:{rounded % 60:02d}"


def build(catalog_path: Path, output: Path) -> dict:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    records = catalog["recordings"]
    if not records or len(records) != catalog["recording_count"]:
        raise ValueError("The catalog recording count does not match its entries")
    cards = []
    total_seconds = 0.0
    for record in records:
        audio = record["audio"]
        preset = record["factory_preset"]
        if (record["midi"]["status"] != "unavailable"
                or record["midi"]["exact_original_performance"]
                or record["midi"]["reconstructed"]
                or record["eligible_for_exact_input_ab"]):
            raise ValueError("This player is for factory references without performance MIDI")
        if record["preset_match"]["recorded_factory_revision_verified"]:
            raise ValueError("Update the player labels before claiming verified recorded patch bytes")
        path = (ROOT / audio["local_path"]).resolve()
        relative = path.relative_to(output.parent.resolve())
        payload = path.read_bytes()
        if len(payload) != audio["bytes"]:
            raise ValueError(f"Size mismatch: {path}")
        if hashlib.sha256(payload).hexdigest() != audio["sha256"]:
            raise ValueError(f"SHA-256 mismatch: {path}")
        total_seconds += audio["duration_seconds"]
        local_url = quote(relative.as_posix(), safe="/")
        title = escape(record["name"])
        slot = escape(preset["slot"])
        cards.append(f'''<article class="recording" id="{escape(record['id'])}">
  <div class="card-top"><span class="slot">PRESET {slot}</span><span class="length">{duration(audio['duration_seconds'])}</span></div>
  <h2>{title}</h2>
  <p class="card-status">Factory name verified <span aria-hidden="true">·</span> MIDI unavailable</p>
  <audio controls preload="none" aria-label="Original SH-201 recording: {title}"><source src="{local_url}" type="audio/mpeg">Your browser does not support audio playback.</audio>
  <div class="card-links"><a href="{source_url(audio['source_url'])}" target="_blank" rel="noopener noreferrer">Roland original ↗</a><a href="{local_url}" download>Download MP3</a></div>
</article>''')
    sources = " · ".join(
        f'<a href="{source_url(source["url"])}" target="_blank" rel="noopener noreferrer">{escape(source["title"])}</a>'
        for source in catalog["sources"]
    )
    document = '''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SH-201 · Factory recordings</title>
  <style>
    :root{color-scheme:dark;--bg:#101615;--panel:#18211f;--line:#35443d;--text:#eff3ea;--muted:#aebcaf;--accent:#d7e89c;--amber:#efc780}
    *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
    main{max-width:1160px;margin:auto;padding:44px 30px 50px}.eyebrow{margin:0 0 8px;letter-spacing:.17em;font-size:12px;font-weight:700;color:var(--accent)}
    h1{font-size:clamp(31px,5vw,50px);line-height:1.12;letter-spacing:-.04em;margin:0 0 14px;font-weight:620}header>p{max-width:780px;color:var(--muted);margin:0 0 20px}
    .facts{display:flex;flex-wrap:wrap;gap:9px;margin:22px 0}.facts span{padding:5px 11px;border:1px solid var(--line);border-radius:20px;font-size:13px}
    .status{border:1px solid #75613c;background:#27261d;padding:18px 21px;border-radius:10px;margin:0 0 30px}.status strong{color:var(--amber);display:block;font-size:17px;margin-bottom:7px}.status p{margin:5px 0;font-size:14px;color:#ded7c4}
    .grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:15px}.recording{padding:19px;border:1px solid var(--line);border-radius:11px;background:var(--panel);min-width:0}.card-top{display:flex;justify-content:space-between;align-items:center;gap:12px}.slot{font-size:12px;letter-spacing:.08em;color:var(--accent);font-weight:650}.length{font:12px ui-monospace,monospace;color:var(--muted)}
    h2{font-size:20px;line-height:1.25;letter-spacing:-.02em;margin:12px 0 8px}.card-status{font-size:11px;color:var(--muted);margin:0 0 16px;white-space:normal}.card-status span{margin:0 3px}audio{display:block;width:100%;height:40px;margin:0 0 18px}.card-links{display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;font-size:12px}a{color:var(--accent);text-underline-offset:3px}a:hover{color:#fff}a:focus-visible{outline:2px solid var(--accent);outline-offset:5px}
    footer{margin:30px 0 0;border-top:1px solid var(--line);padding-top:20px;color:var(--muted);font-size:13px}footer p{margin:8px 0}.sources{font-size:12px}
    @media(max-width:950px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:620px){main{padding:26px 16px 34px}.grid{grid-template-columns:1fr}.status{padding:16px}.recording{padding:18px}}
  </style>
</head>
<body><main>
  <header>
    <p class="eyebrow">ROLAND SH-201 / HARDWARE REFERENCES</p>
    <h1>Factory recordings</h1>
    <p>Original Roland patch demos matched by name to the SH-201 factory PRESET bank. Play the published hardware recordings below.</p>
    <div class="facts"><span>RECORDING_COUNT recordings</span><span>TOTAL_DURATION total</span><span>Factory PRESET bank</span><span>Original stereo MP3s</span></div>
  </header>
  <aside class="status" aria-label="Reference accuracy">
    <strong>Performance MIDI unavailable · No software A/B yet</strong>
    <p><b>Factory name verified.</b> Demo titles match the official factory patch list.</p>
    <p><b>Exact patch bytes used in these recordings are unverified.</b> The recordings may include live control changes, effects or mastering. No original or estimated performance MIDI is included.</p>
  </aside>
  <section class="grid" aria-label="Original factory preset recordings">RECORDING_CARDS</section>
  <footer>
    <p>Every recording here matches a factory PRESET name and slot. The factory USER bank contains different patches.</p>
    <p><b>MIDI bank selection is unverified on hardware.</b> The Owner’s Manual p. 84 lists MSB/LSB 87/64 for PRESET and 87/0 for USER. The MIDI Implementation pp. 1 and 3 instead lists 87/0 for PRESET and 87/20 for USER. Catalog values are explicitly attributed to the Owner’s Manual; the official documents conflict.</p>
    <p><a href="factory-recordings.json" download>Download source and verification catalog</a></p>
    <p class="sources">SOURCE_LINKS</p>
  </footer>
</main>
<script>
  document.querySelectorAll('audio').forEach(player => {
    player.addEventListener('play', () => {
      document.querySelectorAll('audio').forEach(other => { if (other !== player) other.pause(); });
    });
  });
</script>
</body>
</html>
'''
    document = (document.replace("RECORDING_COUNT", str(len(records)))
                .replace("TOTAL_DURATION", duration(total_seconds))
                .replace("RECORDING_CARDS", "\n".join(cards))
                .replace("SOURCE_LINKS", sources))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    (output.parent / "factory-recordings.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"page": str(output), "recordings": len(records), "audio_hashes_verified": len(records),
            "total_duration_seconds": round(total_seconds, 6)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT / "Docs/fidelity/factory-recordings.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="HTML output; cataloged MP3s must be under the same directory")
    args = parser.parse_args()
    print(json.dumps(build(args.catalog.resolve(), args.output.resolve()), indent=2))


if __name__ == "__main__":
    main()
