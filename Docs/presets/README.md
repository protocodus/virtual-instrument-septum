# Free SH-201 presets for Septum

The local [preset catalog](http://127.0.0.1:8919/SH-201%20Patch%20100/) contains **400 original Roland Patch 100 definitions**, converted into native Septum presets. These are additional published patches, not the SH-201 factory bank or the approximate demo recreations.

The completed pack is `out/presets/SH-201 Patch 100/`, with a matching ZIP alongside it. In Septum, click **Load** and choose a `.septum` file from a category folder.

| Folder | Presets | Sound-type subfolders |
|---|---:|---:|
| Bass | 100 | 24 |
| Leads | 100 | 20 |
| Pads | 100 | 19 |
| Effects | 100 | 9 |

Subfolders preserve Roland's original librarian labels, such as Analog, Acid, Strings and Sequence. Filenames retain the original one-based bank position; unsafe filename characters are replaced without changing the embedded source name. The matching `SysEx/` tree contains each unmodified 22-block parameter payload in individual `.syx` files. `Sources/` retains the original ZIPs, including their SHL banks and patch-list PDFs.

## Sources and conversion

The four public downloads come directly from Roland: [Bass](https://www.rolandus.com/go/sh-201_patches/patch_bass.html), [Leads](https://www.rolandus.com/go/sh-201_patches/patch_lead.html), [Pads](https://www.rolandus.com/go/sh-201_patches/patch_pad.html) and [Effects](https://www.rolandus.com/go/sh-201_patches/patch_fx.html). The [source catalog](free-sh201-sources.json) pins archive/member hashes and records the source inspection. Individual designers are not credited in these downloads.

Every native file was saved and reloaded through Septum's existing preset APIs. All represented patch settings, all native parameters and the complete arpeggio grid were verified after reload. No shipping DSP or built-in preset programs were changed.

The [validation record](validation.json) records the 400 verified conversions, 803 checked catalog links, archive integrity and converter refusal checks.

The current codec normalizes 43 coarse-tuning bytes in 39 patches to its integer-semitone representation: 2 Bass, 11 Leads, 12 Pads and 14 Effects. `native-conversion-report.json` identifies every affected file and source/native byte difference. All 400 `.syx` files retain the original source bytes. Some patches reference hardware controls or external input; preserving their settings does not reproduce a missing D-Beam sensor or external signal.

These downloads are offered without payment, with instructions for loading the banks. No separate public redistribution grant was found in the inspected files. The generated pack stays local under ignored `out/`; the repository contains the downloader, converter and factual source catalog, rather than third-party sound data. The presets are not relicensed under Septum's code license.

## Rebuild

With a configured plugin build, build the converter and run the downloader:

```sh
cmake --build build-fidelity --target SeptumConvertPresets --parallel 2
python3 Tools/bundle_free_presets.py
```

The converter requires `SEPTUM_BUILD_PLUGIN=ON` and `SEPTUM_BUILD_TOOLS=ON`. Pass `--converter` to use a different build. The Python tool uses only the standard library plus the existing extraction helper and `curl`; it verifies pinned downloads before conversion and refuses to overwrite an existing pack. Use `--output` for a fresh destination and `--cache` to reuse downloaded sources.

To browse the catalog with a working ZIP link, serve the pack's **parent** folder:

```sh
python3 -m http.server 8919 --bind 127.0.0.1 --directory out/presets
```

Then open `/SH-201%20Patch%20100/`. The ZIP contains the whole category tree, source banks, catalog and conversion report.
