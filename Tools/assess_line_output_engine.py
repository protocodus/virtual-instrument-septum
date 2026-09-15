#!/usr/bin/env python3
"""Measure the three frozen LINE-circuit hypotheses against existing original matrices.

No build, rendering, parameter/phase/timing fit, candidate gain rematch or selection.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
import numpy as np
from scipy import signal

import characterize_output_stage_references as base

ROOT=Path(__file__).resolve().parents[1]
BASELINE_SHA="761b5d4004e7ba62fdefd57af28badbe154f1acd9a7f65ea0c8177a24479bad7"
VARIANTS={"a-0.1":.1,"a-0.5":.5,"a-1":1.}


def pin(path,expected=None):
    return base.pin(path,expected)


def save(path,value):
    base.save(path,value)


def prepare(args):
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    source=pin(args.baseline,BASELINE_SHA);prior=json.loads(args.baseline.read_text())
    base.checked(prior["protocol"]["tool"])
    if len(prior["cases"])!=12:
        raise ValueError("Expected all twelve existing cases")
    for c in prior["cases"]:
        for key in ("reference","production","native_receipt"):
            base.checked(c["source"][key])
    protocol=dict(status="frozen_before_LINE_candidate_outputs_or_statistics",script=pin(__file__),helper=pin(base.__file__),
        baseline_measurements=source,variant_fractions=VARIANTS,case_ids=[c["id"] for c in prior["cases"]],
        candidate_count=3,selection="No variant selected from these recordings",
        electrical_hypothesis="Both stereo jacks; pot10kOhm, external load10kOhm, electrical fraction0.1/0.5/1.0. Root-owned isolated builder inserts normalized linear sections after existing SK inside8x output processing. Fixed normalized constant gain; no new oscillator/filter/FX/patch/MIDI control.",
        primary="Exact saved production gain/lag/reference segments. All raw input bytes and full render metadata must match existing native output; baseline-disabled must match its WAV bytes.",
        original_matrices="Reuse existing original K-block starts/gates, source rise landmarks, original-only spectral counts/hashes and RMS masks/values. Recomputed originals must match exactly.",
        level_sensitivity="The existing production K-match scalar is shared by every candidate for each case. No candidate gain rematching. Candidate K-level changes remain measured under the primary fixed gain.",
        floors="Primary RMS floor remains original-fixed. Shared-scalar envelope sensitivity is recomputed from scaled samples with the same original floor, avoiding the earlier dry floored-log caveat. No model failure deletes an original bin or landmark.",
        comparison="All three alternatives retained, including every regression and insufficient original band. No hardware equivalence or shipping decision follows.")
    save(out/"protocol.json",protocol);print(out/"protocol.json",flush=True)


def verify_render(row,prior):
    wave=base.checked(row["production"]);receipt_pin=base.checked(row["production_receipt"])
    receipt=json.loads(Path(receipt_pin["path"]).read_text())
    original=json.loads(Path(prior["source"]["native_receipt"]["path"]).read_text())
    for key in ("settings","midi","metadata","replay_events","replay_event_counts","ignored_events","degraded_replay"):
        if receipt[key]!=original[key]:
            raise ValueError("LINE replay semantics changed: "+row["id"]+"/"+key)
    for key in ("sysex","midi"):
        if receipt["inputs"][key]["sha256"]!=original["inputs"][key]["sha256"]:
            raise ValueError("LINE original patch/MIDI bytes changed")
    for key in ("frames","sample_rate","latency_samples","master_level","initial_patch","patch_tempo_at_end","clock_tempo_at_end","patch_load_warning","active_voices_at_end"):
        if receipt["output"][key]!=original["output"][key]:
            raise ValueError("LINE output settings changed: "+row["id"]+"/"+key)
    if receipt["output"]["active_voices_at_end"]!=0:
        raise ValueError("Unexpected remaining voices")
    return wave,receipt_pin


def assert_originals(metrics,prior):
    for a,b in zip(metrics["envelopes"],prior["envelopes"]):
        for key in ("window_samples","hop_samples","starts","original_active","original_rms_db","original_active_count","original_dynamic_range_p95_p10_db","original_quartile_bounds_db"):
            if a[key]!=b[key]:
                raise ValueError("Frozen original RMS matrix changed: "+key)
    fresh=metrics["transient_rises"];old=prior["transient_rises"]
    if len(fresh["landmarks"])!=len(old["landmarks"]):
        raise ValueError("Original landmark count changed")
    for a,b in zip(fresh["landmarks"],old["landmarks"]):
        for key in ("reference_landmark_sample","source_rise_db","source_rms_db","source_segment","windows","accepted","rejection_reason"):
            if a[key]!=b[key]:
                raise ValueError("Original transient landmark changed")
        if a["accepted"] and a["models"]["original"]!=b["models"]["original"]:
            raise ValueError("Original transient statistics changed")
    for a,b in zip(metrics["spectral_bands"],prior["spectral_bands"]):
        for key in ("window_samples","hop_samples","coverage","original_active_bins","original_mask_sha256"):
            if a[key]!=b[key]:
                raise ValueError("Original spectral matrix changed")
        for ba,bb in zip(a["bands"],b["bands"]):
            for name,pa in ba["policies"].items():
                for key in ("original_power","original_band_fraction_of_full_original_power","original_band_relative_power_db","bins","status"):
                    if pa[key]!=bb["policies"][name][key]:
                        raise ValueError("Original band support changed")


def measure_model(prior,wave):
    source=prior["source"];mono=source["cohort"]=="dry"
    h=base.read(source["reference"],mono);c=base.read(wave,mono)*source["fixed_gain"]
    segments,lag=source["reference_segments"],source["lag_samples"]
    if any(a+lag<0 or b+lag>len(c) for a,b in segments):
        raise ValueError("Invalid frozen candidate support")
    used=np.concatenate([c[a+lag:b+lag] for a,b in segments])
    stats=base.sample_stats(used)
    env=base.envelopes(h,c,segments,lag)
    spectra=base.spectral_bands(h,c,segments,lag,source["inherited_spectral_controls"])
    rises=base.transient_rises(h,c,segments,lag)
    # Reuse the stored original block coordinates and selection verbatim.
    old=prior["loudness"];starts=np.asarray(old["starts"],dtype=int);active=np.asarray(old["original_selected"],dtype=bool)
    filtered=signal.sosfilt(base.k_sections(base.SR),c,axis=0)
    powers=base.frame_power(filtered,starts+lag,old["window_samples"])*c.shape[1]
    k_level=float(base.db(float(np.mean(powers[active])))-.691)
    scalar=old["matched_sensitivity_scalar"]
    sensitivity=base.envelopes(h,c*scalar,segments,lag)
    for a,b in zip(sensitivity,env):
        for key in ("starts","original_active","original_rms_db"):
            if a[key]!=b[key]:
                raise ValueError("Scalar sensitivity changed original mask")
    for s in spectra:
        for b in s["bands"]:
            for p in b["policies"].values():
                value=p["production_minus_original_db"]
                p["shared_production_K_scalar_error_db"]=None if value is None else value+old["matched_sensitivity_adjustment_db"]
    metrics=dict(sample_statistics=stats,loudness=dict(original_level=old["original_k_level"],candidate_level=k_level,
        candidate_minus_original_db=k_level-old["original_k_level"],candidate_block_levels=(base.db(powers)-.691).tolist(),
        original_selected_block_count=int(active.sum()),source_blocks="Verbatim existing baseline receipt",
        shared_production_K_scalar=scalar,shared_scalar_adjustment_db=old["matched_sensitivity_adjustment_db"]),
        envelopes=env,shared_production_K_scalar_sample_statistics=base.sample_stats(used*scalar),
        shared_production_K_scalar_envelopes=sensitivity,transient_rises=rises,spectral_bands=spectra)
    assert_originals(metrics,prior)
    original=prior["sample_statistics"]["original"];before=prior["sample_statistics"]["production_fixed"]
    metrics["summary"]=dict(
        rms_error_before_db=before["rms_dbfs"]-original["rms_dbfs"],rms_error_after_db=stats["rms_dbfs"]-original["rms_dbfs"],
        k_error_before_db=old["production_minus_original_db"],k_error_after_db=k_level-old["original_k_level"],
        crest_error_before_db=before["crest_db"]-original["crest_db"],crest_error_after_db=stats["crest_db"]-original["crest_db"],
        crest_change_from_baseline_db=stats["crest_db"]-before["crest_db"],
        rms_change_from_baseline_db=stats["rms_dbfs"]-before["rms_dbfs"],
        envelope50_range_before_db=prior["envelopes"][1]["production_dynamic_range_p95_p10_db"],
        envelope50_range_after_db=env[1]["production_dynamic_range_p95_p10_db"],
        envelope50_original_range_db=env[1]["original_dynamic_range_p95_p10_db"],
        envelope50_correlation_before=prior["envelopes"][1]["log_envelope_correlation"],
        envelope50_correlation_after=env[1]["log_envelope_correlation"])
    return metrics


def compare(args):
    protocol_pin=pin(args.protocol);protocol=json.loads(args.protocol.read_text())
    for key in ("script","helper","baseline_measurements"):
        base.checked(protocol[key])
    prior=json.loads(Path(protocol["baseline_measurements"]["path"]).read_text())
    manifest_pin=pin(args.manifest);manifest=json.loads(args.manifest.read_text())
    rows=manifest["cases"]
    variants={"baseline",*VARIANTS}
    expected={(c["id"],c["cohort"],variant) for c in prior["cases"] for variant in variants}
    actual={(c["id"],c["cohort"],c["variant"]) for c in rows}
    if actual!=expected or len(rows)!=48:
        raise ValueError("Incomplete or duplicate LINE variant/case coverage")
    for row in rows:
        if row["variant"]!="baseline" and row["electrical_fraction"]!=VARIANTS[row["variant"]]:
            raise ValueError("Frozen electrical fraction changed")
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    result=dict(status="all_three_frozen_LINE_variants_no_selection",protocol=protocol,protocol_file=protocol_pin,
        renders_manifest=manifest_pin,render_provenance=manifest,baseline_controls=[],cases=[],hardware_equivalence="not_established")
    # Verify all disabled controls, then measure candidates without new fitting.
    for p in prior["cases"]:
        row=next(c for c in rows if c["id"]==p["id"] and c["variant"]=="baseline")
        wave,receipt=verify_render(row,p)
        if wave["sha256"]!=p["source"]["production"]["sha256"]:
            raise ValueError("Disabled LINE control is not byte-identical")
        fresh=measure_model(p,wave)
        for key,previous in (("sample_statistics",p["sample_statistics"]["production_fixed"]),("transient_rises",p["transient_rises"])):
            if fresh[key]!=previous:
                raise ValueError("Baseline metric did not reproduce: "+key)
        for a,b in zip(fresh["envelopes"],p["envelopes"]):
            for key,value in a.items():
                if value!=b[key]:
                    raise ValueError("Baseline envelope did not reproduce")
        if abs(fresh["loudness"]["candidate_level"]-p["loudness"]["production_k_level"])>1e-12:
            raise ValueError("Baseline K weighting did not reproduce")
        result["baseline_controls"].append(dict(id=p["id"],wave=wave,receipt=receipt,byte_identical=True,original_matrices_and_baseline_metrics_reproduced=True))
        print(p["id"]+": baseline byte/metric control passed",flush=True)
    for p in prior["cases"]:
        item=dict(id=p["id"],cohort=p["cohort"],variants={})
        for variant in VARIANTS:
            row=next(c for c in rows if c["id"]==p["id"] and c["variant"]==variant)
            wave,receipt=verify_render(row,p)
            metrics=measure_model(p,wave)
            item["variants"][variant]=dict(wave=wave,receipt=receipt,electrical_fraction=VARIANTS[variant],metrics=metrics)
            print(p["id"],variant,metrics["summary"],flush=True)
        result["cases"].append(item);save(out/"results-partial.json",result)
    if pin(args.manifest)!=manifest_pin:
        raise ValueError("Renderer manifest changed during measurement")
    result["all12_disabled_controls_passed"]=True
    save(out/"results.json",result);print(out/"results.json",flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest="stage",required=True)
    p=sub.add_parser("prepare");p.add_argument("--baseline",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    p=sub.add_parser("compare");p.add_argument("--protocol",type=Path,required=True);p.add_argument("--manifest",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();prepare(args) if args.stage=="prepare" else compare(args)


if __name__=="__main__":
    main()
