#!/usr/bin/env python3
"""Bounded E8/E9/E10 cutoff-table experiment against ten unchanged presets.

Air Lead supplies hypothesis context; the other nine cases assess generalization.
No exponent is selected and no shipping source is edited. Requires a previously
generated, hash-verified final-production comparison corpus and Git b0f6c03.
"""
import argparse
import hashlib
import html
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np
from scipy.io import wavfile

ROOT = Path(__file__).resolve().parents[1]
REVISION = "b0f6c03"
EXPONENTS = (10, 8, 9)
HELPER = r'''#include "DSP/SeptumEngine.h"
#include <iomanip>
#include <iostream>
int main() {
    std::cout << std::setprecision(17) << "{";
    for (int e : {8,9,10}) {
        if (e != 8) std::cout << ",";
        std::cout << "\"" << e << "\":[";
        for (int raw=0; raw<128; ++raw) {
            const auto value=20.0*std::exp2(raw*(double(e)/127.0));
            if (e==10 && value!=septum::mapping::cutoffHz(raw)) return 2;
            if (raw) std::cout << ",";
            std::cout << value;
        }
        std::cout << "]";
    }
    std::cout << "}\n";
}
'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False)+"\n")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--comparison-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    frozen = out/"frozen-source"
    names = subprocess.check_output(["git","ls-tree","-r","--name-only",REVISION,"Source/DSP"], cwd=ROOT, text=True).splitlines()
    names += ["Tools/"+n for n in ("RenderMidi.cpp","build_timbre_candidate.py",
              "render_midi.py","assess_hardware_equivalence.py","generate_timbre_capture.py")]
    source_hashes = {}
    for name in names:
        path = frozen/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(subprocess.check_output(["git","show",f"{REVISION}:{name}"], cwd=ROOT))
        source_hashes[name] = sha(path)
    for name in ("compare_cutoff_taper_candidates.py","compare_envelope_preset_holdouts.py"):
        shutil.copyfile(ROOT/"Tools"/name, out/name)
    verification = ROOT/"Docs/fidelity/source-audits/final-production-verification-2026-09-15.json"
    guard = {r["id"]:r for r in json.loads(verification.read_text())["cases"]}
    if len(guard) != 10:
        raise ValueError("Unexpected production identity case count")
    shutil.copyfile(verification, out/"production-verification.json")
    save(out/"source-manifest.json", dict(revision=REVISION, input_sha256=source_hashes,
         experiment_sha256=sha(__file__), production_verification_sha256=sha(verification),
         policy_reference_sha256=sha(out/"compare_envelope_preset_holdouts.py")))
    sys.path.insert(0,str(frozen/"Tools"))
    import build_timbre_candidate as builder
    import assess_hardware_equivalence as assess
    import generate_timbre_capture as capture
    helper = out/"generate-cutoff-tables.cpp"
    helper.write_text(HELPER)
    executable = out/"generate-cutoff-tables"
    command = ["c++","-std=c++20","-O2","-fno-fast-math","-I"+str(frozen/"Source"),str(helper),"-o",str(executable)]
    subprocess.run(command, check=True)
    tables = json.loads(subprocess.check_output([str(executable)], text=True))
    save(out/"cutoff-tables.json", dict(formula="20 * 2^(E * raw / 127)",
         evaluation="C++ 20 * std::exp2(raw * (E / 127.0)); E10 compared exactly with frozen inline mapping",
         helper_sha256=sha(helper), helper_binary_sha256=sha(executable), compile_command=command,
         tables=tables, range_hz={e:[v[0],v[-1]] for e,v in tables.items()},
         qualification="Base cutoff before unchanged key follow, velocity, envelope, LFO and final safety clamp; no bypass shortcut"))
    profiles = out/"profiles"
    profiles.mkdir()
    builds = {}
    for exponent in EXPONENTS:
        name = f"cutoff-e{exponent}"
        path = profiles/(name+".json")
        save(path, dict(version=1, id=name,
             evidence="Experimental fixed taper generalization test; Air Lead context only, no global calibration or equivalence claim.",
             filter=dict(cutoff_hz=tables[str(exponent)])))
        builds[name] = builder.build_candidate(path, out/"builds"/name, source_root=frozen)
        if builds[name]["source"]["input_sha256"] != builds["cutoff-e10"]["source"]["input_sha256"]:
            raise ValueError("Candidate source drift")
        print("Built", name, flush=True)
    comparisons = sorted(args.comparison_root.glob("*/comparison.json"))
    if {q.parent.name for q in comparisons} != set(guard):
        raise ValueError("Expected exactly the ten pinned production cases")
    protocol = dict(status="experimental_no_selection", source_revision=REVISION,
        exponents=list(EXPONENTS), hypothesis_context_case="air-lead-1",
        evaluation_cases=sorted(set(guard)-{"air-lead-1"}),
        alignment="Production only: first-quarter envelope correlation, bounded 50 ms; same lag for every candidate",
        gain="One RMS scalar per complete candidate from first quarter only; exact production scalar as sensitivity",
        coverage="Remaining three quarters with common sample bounds; no STFT frame crosses calibration/evaluation boundary",
        signal_policy="Same named preset bytes, reconstructed MIDI, all envelope times/depths, damping, oscillator and effect parameters unchanged",
        qualification="No exact recorded patch revision or original performance MIDI; no exponent selection from other nine results; no global curve promotion")
    save(out/"protocol-before-rendering.json",protocol)
    cases = []
    sections = []
    for comparison in comparisons:
        meta = json.loads(comparison.read_text())
        case_id = meta["case"]["id"]
        directory = out/"cases"/case_id
        directory.mkdir(parents=True)
        source = comparison.parent
        files = ("hardware-excerpt-raw.wav","septum-raw.wav","original-patch.syx","reconstructed-performance.mid")
        for name in files:
            if sha(source/name) != meta["files"][name]:
                raise ValueError("Changed comparison input: "+str(source/name))
            shutil.copyfile(source/name,directory/name)
        pinned = guard[case_id]
        for filename, key in (("septum-raw.wav","production_sha256"),
                              ("original-patch.syx","patch_sha256"),
                              ("reconstructed-performance.mid","midi_sha256")):
            if sha(directory/filename) != pinned[key]:
                raise ValueError("Production checkpoint input identity failed")
        sr,h = assess.read_audio(directory/"hardware-excerpt-raw.wav")
        bs,base_full = assess.read_audio(directory/"septum-raw.wav")
        n = meta["comparison_frames"]
        if sr != 44100 or bs != sr or len(h) != n or len(base_full) < n:
            raise ValueError("Invalid baseline dimensions")
        base = base_full[:n]
        cal = round(n*.25)
        transform = assess.fit_transform(h,base,sr,cal,.05)
        lag = transform["candidate_lag_samples"]
        start,end = max(cal,cal-lag),min(n,n-lag)
        ca,cb = max(0,-lag),min(cal,cal-lag)
        blocks = capture.decode_syx((directory/"original-patch.syx").read_bytes())
        tones = []
        for label,raw in zip(("upper","lower"),blocks[1:3]):
            tones.append(dict(tone=label, raw_hex=bytes(raw).hex(), filter_type_wire=raw[0x11],
                slope_wire=raw[0x12], cutoff_raw=raw[0x13], key_follow_raw=raw[0x14],
                resonance_raw=raw[0x16], filter_adsr_raw=list(raw[0x17:0x1b]),
                filter_depth_raw=raw[0x1b], predicted_base_cutoff_hz={e:v[raw[0x13]] for e,v in tables.items()}))
        record = dict(id=case_id, role="hypothesis_context" if case_id=="air-lead-1" else "evaluation",
            case=meta["case"], comparison_sha256=sha(comparison),
            input_sha256={name:sha(directory/name) for name in files},
            raw_common_hex=bytes(blocks[0]).hex(), tones=tones,
            calibration=transform, calibration_reference_samples=[ca,cb],
            calibration_candidate_samples=[ca+lag,cb+lag], evaluation_samples=[start,end],
            qualification=meta["comparison_limits"], models={})
        sounds = {"production":base}
        for exponent in EXPONENTS:
            name = f"cutoff-e{exponent}"
            wav = directory/(name+".wav")
            renderer = out/"builds"/name/"SeptumRenderMidi"
            command = [sys.executable,str(frozen/"Tools/render_midi.py"),"--renderer",str(renderer),
                       "--midi",str(directory/"reconstructed-performance.mid"),
                       "--syx",str(directory/"original-patch.syx"),"--output",str(wav),
                       "--tempo-policy","preserve-patch"]
            subprocess.run(command,check=True,stdout=subprocess.DEVNULL)
            cs,c = assess.read_audio(wav)
            receipt = json.loads(wav.with_suffix(".render.json").read_text())
            if cs!=sr or c.shape[1]!=h.shape[1] or len(c)<n or receipt["ignored_events"] or receipt["output"]["active_voices_at_end"]:
                raise ValueError("Replay format, MIDI or ended-voice guard failed")
            identical = sha(wav)==pinned["production_sha256"]
            if exponent==10 and not identical:
                raise ValueError("E10 identity guard failed for "+case_id)
            sounds[name] = c[:n]
            record["models"][name] = dict(raw_sha256=sha(wav), renderer_sha256=sha(renderer),
                receipt_sha256=sha(wav.with_suffix(".render.json")), peak=float(abs(c).max()),
                finite=True, samples_at_or_above_full_scale=int(np.count_nonzero(abs(c)>=1)),
                active_voices_at_end=0, identical_to_production=identical, command=command,
                production_max_pcm_difference=float(np.max(abs(c-base_full))) if c.shape==base_full.shape else None)
        listening = {"hardware":h[start:end]}
        for name,c in sounds.items():
            gain = assess.rms(h[ca:cb])/assess.rms(c[ca+lag:cb+lag])
            row = record["models"].setdefault(name,{})
            row.update(training_gain=gain,training_gain_db=20*math.log10(gain),
                measurements=assess.measure(h[start:end],c[start+lag:end+lag]*gain,sr),
                fixed_production_gain=assess.measure(h[start:end],c[start+lag:end+lag]*transform["candidate_gain"],sr))
            listening[name] = c[start+lag:end+lag]*gain
        scale = min(.1/assess.rms(listening["hardware"]),.98/max(float(abs(y).max()) for y in listening.values()))
        for name,y in listening.items():
            wavfile.write(directory/(name+"-listen.wav"),sr,(y*scale).astype(np.float32))
        record["listening"] = dict(common_gain=scale,segment="Evaluation only; fixed training gain and shared lag")
        save(directory/"result.json",record)
        cases.append(record)
        players = "".join(f'<p>{html.escape(name)}<br><audio controls preload="none" src="cases/{case_id}/{name}-listen.wav"></audio></p>' for name in listening)
        sections.append(f'<section><h2>{html.escape(case_id)} ({record["role"]})</h2>{players}</section>')
        print(case_id, " ".join(f'{k}={v["measurements"]["summary"]["spectral_convergence_mean"]:.5f}' for k,v in record["models"].items()),flush=True)
    save(out/"results.json",dict(protocol=protocol,source_manifest_sha256=sha(out/"source-manifest.json"),
         cutoff_tables_sha256=sha(out/"cutoff-tables.json"),
         build_manifest_sha256={name:sha(out/"builds"/name/"manifest.json") for name in builds},
         all_ten_e10_byte_identical=True,cases=cases))
    (out/"index.html").write_text('<!doctype html><meta charset="utf-8"><title>Cutoff taper experiment</title>'
        '<style>body{font:16px system-ui;max-width:900px;margin:40px auto;padding:20px}section{border-top:1px solid #bbb;margin-top:32px}audio{width:100%}</style>'
        '<h1>Experimental cutoff taper comparison</h1><p>Air Lead provides hypothesis context; nine other presets assess generalization. '
        'Unchanged published presets with reconstructed MIDI; timing comes only from production. One gain per candidate comes from the first quarter. '
        'These players contain the remaining interval. No exponent or global curve is selected; hardware equivalence is not established.</p>'+''.join(sections))
    print(out/"results.json")


if __name__=="__main__":
    main()
