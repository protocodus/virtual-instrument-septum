#!/usr/bin/env python3
"""Replay non-reverb frozen alignment fits; preserve old studies unchanged."""
import argparse
import json
from pathlib import Path
import subprocess
from scipy.io import wavfile
import audit_reverb_alignment_variance as audit


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fidelity-root", type=Path, required=True)
    p.add_argument("--alignment-run", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    root, run, out = args.fidelity_root.resolve(), args.alignment_run.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    previous = json.loads((run/"results.json").read_text())
    for name, key in (("historical_assessor.py", "historical_assessor_sha256"), ("updated_assessor.py", "updated_assessor_sha256")):
        if audit.sha(run/name) != previous["protocol"][key]:
            raise ValueError("Pinned assessor changed")
    old = audit.load_module(run/"historical_assessor.py", "other_historical_assessor")
    new = audit.load_module(run/"updated_assessor.py", "other_updated_assessor")
    records, no_search = [], []
    files = subprocess.check_output(["rg", "--files", str(root)], text=True).splitlines()
    cli_files = [Path(x) for x in files if x.endswith(".json") and
                 ("equivalence-prefix25" in x or "equivalence-assessment" in x) and not x.endswith("/summary.json")]
    for path in sorted(cli_files):
        data = json.loads(path.read_text())
        if "calibration" not in data:
            continue
        prior = data["calibration"]
        if prior["max_lag_seconds"] == 0:
            no_search.append(dict(path=str(path), sha256=audit.sha(path), reason="max_lag_seconds=0; correlation branch is not executed"))
            continue
        if data["tool_sha256"] != audit.OLD_SHA:
            raise ValueError("Unexpected historical CLI assessor")
        records.append(dict(group="named_presets_cli", source_result_path=str(path), source_result_sha256=audit.sha(path),
                            reference=data["sources"]["reference"], candidate=data["sources"]["candidate"],
                            historical_fit=prior, audio_adapter="float64", sample_slice=None))
    for relative, subfolder, hashes in (("envelope-hypothesis/preset-holdouts-v1", "", "inputs_sha256"),
                                      ("hardware-benchmark/cutoff-taper-candidates/run-01", "cases", "input_sha256")):
        directory = root/relative
        path = directory/"results.json"
        data = json.loads(path.read_text())
        for row in data["cases"]:
            folder = directory/subfolder/row["id"]
            records.append(dict(group=relative, id=row["id"], source_result_path=str(path), source_result_sha256=audit.sha(path),
                                reference=dict(path=str(folder/"hardware-excerpt-raw.wav"), sha256=row[hashes]["hardware-excerpt-raw.wav"]),
                                candidate=dict(path=str(folder/"septum-raw.wav"), sha256=row[hashes]["septum-raw.wav"]),
                                historical_fit=row["calibration"], audio_adapter="float64", sample_slice=None))
    for relative in ("zero-resonance-candidate/dry-end-to-end/run-01",
                     "zero-resonance-candidate/dry-end-to-end/run-01-rejected-bypass-setup",
                     "zero-resonance-reproduction-check/dry-end-to-end/run-01"):
        directory = root/"hardware-benchmark"/relative
        path = directory/"results.json"
        data = json.loads(path.read_text())
        note = data["protocol"]["training_note"]
        for row in data["results"]:
            folder = directory/(row["recipe"]+f"-lp{row['slope']}")
            hardware = root/"deepsonic"/f"roland_sh-201_-_filter_demo_-_lpf{row['slope']}_q000.wav"
            records.append(dict(group=relative, id=f"{row['recipe']}-lp{row['slope']}-{row['family']}",
                                source_result_path=str(path), source_result_sha256=audit.sha(path),
                                reference=dict(path=str(hardware), sha256=row["hardware_decoded_sha256"]),
                                candidate=dict(path=str(folder/(row["family"]+"-raw.wav")), sha256=row["raw_render_sha256"]),
                                historical_fit=row["calibration"], audio_adapter="historical_native_float32_reference_and_float64_candidate_left_channel",
                                sample_slice=[round(note["on"]*44100), round(note["off"]*44100)]))
    protocol = dict(tool_sha256=audit.sha(__file__), helper_sha256=audit.sha(Path(audit.__file__)),
                    input_alignment_run_result_sha256=audit.sha(run/"results.json"),
                    historical_assessor_sha256=previous["protocol"]["historical_assessor_sha256"],
                    updated_assessor_sha256=previous["protocol"]["updated_assessor_sha256"],
                    scope="All discovered historical CLI equivalence-prefix fits, ten envelope-holdout and ten cutoff-taper fits, and all24 initial dry correlation fits including the rejected bypass setup. No candidate rendering or score selection.",
                    records=records, no_search=no_search)
    audit.save(out/"protocol-before-replay.json", protocol)
    results = []
    for item in records:
        for name in ("reference", "candidate"):
            if audit.sha(item[name]["path"]) != item[name]["sha256"]:
                raise ValueError("Historical audio changed: "+item[name]["path"])
        if item["audio_adapter"] == "float64":
            sr, ref = old.read_audio(item["reference"]["path"])
            rate, candidate = old.read_audio(item["candidate"]["path"])
        else:
            sr, ref = wavfile.read(item["reference"]["path"])
            rate, stereo = wavfile.read(item["candidate"]["path"])
            ref, candidate = ref[:, None], stereo[:, :1].astype(float)
        if sr != rate:
            raise ValueError("Rate mismatch")
        if item["sample_slice"] is not None:
            start, end = item["sample_slice"]
            ref, candidate = ref[start:end], candidate[start:end]
        prior = item["historical_fit"]
        fit_args = (sr, prior["calibration_frames"], prior["max_lag_seconds"])
        reproduced = old.fit_transform(ref, candidate, *fit_args)
        if any(prior[k] != v for k, v in reproduced.items()):
            raise ValueError("Historical fit does not reproduce: "+item["source_result_path"])
        changed = new.fit_transform(ref, candidate, *fit_args)
        lags = [prior["candidate_lag_samples"], changed["candidate_lag_samples"]]
        results.append(dict(**item, updated_fit=changed, lag_changed=lags[0] != lags[1],
                            gain_changed=prior["candidate_gain"] != changed["candidate_gain"],
                            direct_statistics=audit.selected_statistics(old, ref, candidate, sr, prior, lags)))
    groups = {name:dict(rows=sum(r["group"] == name for r in results),
                       changed_lags=sum(r["group"] == name and r["lag_changed"] for r in results),
                       changed_gains=sum(r["group"] == name and r["gain_changed"] for r in results)) for name in sorted({r["group"] for r in results})}
    audit.save(out/"results.json", dict(protocol=protocol, comparisons=results, per_group=groups,
                                        all_historical_fits_reproduced=True, no_audio_rerenders=True,
                                        historical_results_unchanged=True))
    print(json.dumps(groups), flush=True)


if __name__ == "__main__":
    main()
