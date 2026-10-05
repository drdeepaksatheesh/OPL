#!/usr/bin/env python3
"""Build a small, fully attributed LUDB Lead-II practice bank for OPL.

The practice records are downloaded from PhysioNet with wfdb.  The learner view
can hide the cardiologist delineations; the reference annotations remain inside
the local package so the app can reveal/counter-check them after an attempt.
"""

from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import wfdb

PN_DIR="ludb/1.0.1/data"
VERSION="1.0.1"
DOI="10.13026/eegm-h675"
LICENSE="Open Data Commons Attribution License v1.0"
RECORDS=["119","58","166","149","194","152"]

def annotations_with_wave(ann):
    out=[]
    pending_onsets=[]
    current_wave=None
    map_peak={"p":"P","N":"QRS","t":"T"}
    for sample,symbol,num in zip(ann.sample,ann.symbol,ann.num):
        item={"sample":int(sample),"symbol":str(symbol),"num":int(num),
              "source":"LUDB cardiologist manual delineation"}
        if symbol=="(":
            pending_onsets.append(item)
            continue
        if symbol in map_peak:
            current_wave=map_peak[symbol]
            if pending_onsets:
                onset=pending_onsets.pop(0)
                onset["wave"]=current_wave
                out.append(onset)
            item["wave"]=current_wave
            out.append(item)
            continue
        if symbol==")":
            if current_wave:
                item["wave"]=current_wave
            out.append(item)
            current_wave=None
            continue
        out.append(item)
    out.extend(pending_onsets)
    return sorted(out,key=lambda x:x["sample"])

def wave_triplets(annotations):
    grouped=[]
    current=None
    for a in annotations:
        if a["symbol"]=="(":
            current={"wave":a.get("wave"),"onset":a["sample"],"peak":None,"end":None}
        elif current and a["symbol"] in ("p","N","t"):
            current["peak"]=a["sample"]
            current["wave"]=a.get("wave") or current["wave"]
        elif current and a["symbol"]==")":
            current["end"]=a["sample"]
            if current["wave"] and current["peak"] is not None:
                grouped.append(current)
            current=None
    return grouped

def isoelectric_segments(triplets):
    p=[x for x in triplets if x["wave"]=="P"]
    q=[x for x in triplets if x["wave"]=="QRS"]
    t=[x for x in triplets if x["wave"]=="T"]
    segments=[]
    for pw in p:
        nxt=min((x for x in q if x["onset"]>pw["end"]), key=lambda x:x["onset"], default=None)
        if nxt and nxt["onset"]>pw["end"]:
            segments.append({"type":"PR","start_sample":pw["end"],"end_sample":nxt["onset"]})
    for tw in t:
        nxt=min((x for x in p if x["onset"]>tw["end"]), key=lambda x:x["onset"], default=None)
        if nxt and nxt["onset"]>tw["end"]:
            segments.append({"type":"TP","start_sample":tw["end"],"end_sample":nxt["onset"]})
    return segments

def robust_mad(x):
    x=np.asarray(x,float)
    if not x.size:return float("nan")
    med=np.median(x)
    return float(np.median(np.abs(x-med)))

def comments_to_metadata(comments):
    result={}
    for line in comments or []:
        if ":" in line:
            k,v=line.split(":",1)
            result[k.strip().lower().replace(" ","_")]=v.strip()
    return result

def build_record(record_id):
    rec=wfdb.rdrecord(record_id,pn_dir=PN_DIR,physical=True)
    names=[str(x).lower() for x in rec.sig_name]
    lead_index=names.index("ii")
    signal=np.asarray(rec.p_signal[:,lead_index],float)
    ann=wfdb.rdann(record_id,"ii",pn_dir=PN_DIR)
    annotations=annotations_with_wave(ann)
    triplets=wave_triplets(annotations)
    iso=isoelectric_segments(triplets)
    iso_values=[]
    segment_medians=[]
    for seg in iso:
        values=signal[seg["start_sample"]:seg["end_sample"]]
        if values.size:
            iso_values.extend(values.tolist())
            segment_medians.append(float(np.median(values)))
    baseline=float(np.median(iso_values)) if iso_values else float(np.median(signal))
    spread=float(np.ptp(segment_medians)) if segment_medians else 0.0
    robust_range=float(np.percentile(signal,99)-np.percentile(signal,1))
    diff=signal-np.convolve(signal,np.ones(11)/11,mode="same")
    noise=robust_mad(diff)
    score=(spread/max(robust_range,1e-9)) + 2*(noise/max(robust_range,1e-9))
    meta=comments_to_metadata(rec.comments)
    return {
      "schema":"org.openphysiologylab.reference-record/v1",
      "record_id":f"LUDB/{record_id}/LeadII",
      "sampling_rate_hz":float(rec.fs),
      "duration_seconds":float(len(signal)/rec.fs),
      "sample_count":int(len(signal)),
      "units":["mV","mV"],
      "signal_names":["LUDB Lead II","LUDB Lead II"],
      "signals":{"raw":signal.tolist(),"filtered":signal.tolist()},
      "signal_semantics":{"raw":"Source physical Lead-II waveform","filtered":"Same source waveform; no OPL filter"},
      "recommended_baseline_mV":baseline,
      "isoelectric_segments":iso,
      "annotations":annotations,
      "annotation_summary":{
        "annotation_events":len(annotations),
        "P":sum(a.get("wave")=="P" and a["symbol"]=="p" for a in annotations),
        "QRS":sum(a.get("wave")=="QRS" and a["symbol"]=="N" for a in annotations),
        "T":sum(a.get("wave")=="T" and a["symbol"]=="t" for a in annotations),
      },
      "practice_metrics":{
        "baseline_segment_spread_mV":spread,
        "high_frequency_noise_mad_mV":noise,
        "robust_ecg_range_mV":robust_range,
        "difficulty_score":score,
      },
      "source_files":{
        "record":f"https://physionet.org/files/ludb/{VERSION}/data/{record_id}.dat",
        "header":f"https://physionet.org/files/ludb/{VERSION}/data/{record_id}.hea",
        "lead_ii_annotations":f"https://physionet.org/files/ludb/{VERSION}/data/{record_id}.ii",
      },
      "provenance":{
        "dataset":"Lobachevsky University Electrocardiography Database (LUDB)",
        "dataset_version":VERSION,
        "repository":"PhysioNet",
        "doi":DOI,
        "license":LICENSE,
        "record":record_id,
        "lead":"II",
        "sampling_rate_hz":float(rec.fs),
        "known_preprocessing":"No OPL filtering applied; physical waveform read from source WFDB record.",
        "annotation_status":"P/T/QRS peaks and boundaries manually annotated by cardiologists in LUDB.",
        "practice_role":"Unknown real ECG for baseline and interval practice; expert annotations hidden until learner review.",
        "metadata":meta,
      }
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",default="build/ecg-practice-pack")
    args=ap.parse_args()
    out=Path(args.output)
    records_dir=out/"records"
    records_dir.mkdir(parents=True,exist_ok=True)
    built=[build_record(r) for r in RECORDS]
    ranked=sorted(built,key=lambda r:r["practice_metrics"]["difficulty_score"])
    difficulty={}
    for i,r in enumerate(ranked):
        frac=i/max(1,len(ranked)-1)
        difficulty[r["record_id"]]="easier" if frac<.34 else "moderate" if frac<.67 else "challenge"
    manifest={
      "schema":"org.openphysiologylab.ecg-practice-manifest/v1",
      "title":"OPL real-ECG practice bank",
      "dataset":"Lobachevsky University Electrocardiography Database (LUDB)",
      "dataset_version":VERSION,
      "doi":DOI,
      "license":LICENSE,
      "teaching_note":"Records are shown without cardiologist annotations until review. Source identity and attribution remain available at all times.",
      "records":[]
    }
    for idx,r in enumerate(built):
        rid=r["provenance"]["record"]
        filename=f"LUDB_{rid}_LeadII.json"
        (records_dir/filename).write_text(json.dumps(r,separators=(",",":")),encoding="utf-8")
        manifest["records"].append({
          "id":r["record_id"],
          "label":f"Practice ECG {chr(65+idx)}",
          "file":"records/"+filename,
          "difficulty":difficulty[r["record_id"]],
          "sampling_rate_hz":r["sampling_rate_hz"],
          "duration_seconds":r["duration_seconds"],
          "lead":"II",
          "units":"mV",
          "source_dataset":"LUDB",
          "source_record":rid,
          "difficulty_score":r["practice_metrics"]["difficulty_score"]
        })
    (out/"practice_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(manifest,indent=2))

if __name__=="__main__":
    main()
