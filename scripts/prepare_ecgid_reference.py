#!/usr/bin/env python3
"""Fetch one frozen ECG-ID reference record and convert it to OPL JSON.

The source files remain attributable to the ECG-ID Database on PhysioNet.
This script deliberately records exact source URLs and SHA-256 hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import urllib.request
from pathlib import Path

import wfdb

DATASET = {
    "dataset": "ECG-ID Database",
    "dataset_version": "1.0.0",
    "repository": "PhysioNet",
    "doi": "10.13026/C2J01F",
    "license": "Open Data Commons Attribution License v1.0",
    "contributor": "Tatiana Lugovaya",
    "source_page": "https://physionet.org/content/ecgiddb/1.0.0/",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "OpenPhysiologyLab-reference-builder/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def scalar_list(value):
    if value is None:
        return None
    if hasattr(value, "tolist"):
        return value.tolist()
    return list(value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--person", default="Person_01")
    parser.add_argument("--record", default="rec_1")
    parser.add_argument("--output", default="site/reference/ecg-id/data/Person_01_rec_1.json")
    args = parser.parse_args()

    base = f"https://physionet.org/files/ecgiddb/1.0.0/{args.person}/"
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    source_files = {}
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        for ext in ("hea", "dat", "atr"):
            name = f"{args.record}.{ext}"
            url = base + name
            payload = download(url)
            (tmpdir / name).write_bytes(payload)
            source_files[ext] = {
                "url": url,
                "sha256": sha256(payload),
                "bytes": len(payload),
            }

        stem = str(tmpdir / args.record)
        record = wfdb.rdrecord(stem, physical=False)
        annotation = wfdb.rdann(stem, "atr")

    if record.n_sig < 2:
        raise RuntimeError("ECG-ID reference record does not contain both expected channels")

    raw = record.d_signal[:, 0].astype(int).tolist()
    filtered = record.d_signal[:, 1].astype(int).tolist()

    annotations = []
    for i, sample in enumerate(annotation.sample.tolist()):
        item = {
            "sample": int(sample),
            "symbol": str(annotation.symbol[i]) if i < len(annotation.symbol) else "",
        }
        if getattr(annotation, "subtype", None) is not None:
            item["subtype"] = int(annotation.subtype[i])
        if getattr(annotation, "chan", None) is not None:
            item["channel"] = int(annotation.chan[i])
        if getattr(annotation, "num", None) is not None:
            item["num"] = int(annotation.num[i])
        if getattr(annotation, "aux_note", None) is not None and i < len(annotation.aux_note):
            note = annotation.aux_note[i]
            if note:
                item["aux_note"] = str(note)
        annotations.append(item)

    fs = float(record.fs)
    payload = {
        "schema": "org.openphysiologylab.reference-record/v1",
        "record_id": f"ECG-ID/{args.person}/{args.record}",
        "sampling_rate_hz": fs,
        "duration_seconds": record.sig_len / fs,
        "sample_count": int(record.sig_len),
        "units": scalar_list(record.units),
        "signal_names": scalar_list(record.sig_name),
        "adc": {
            "storage_format": scalar_list(record.fmt),
            "gain_counts_per_unit": scalar_list(record.adc_gain),
            "baseline": scalar_list(record.baseline),
            "zero": scalar_list(record.adc_zero),
            "resolution_bits": int(record.adc_res[0]),
            "dataset_nominal_input_range_mV": "±10",
        },
        "signals": {
            "raw": raw,
            "filtered": filtered,
        },
        "annotations": annotations,
        "source_comments": scalar_list(record.comments) or [],
        "source_files": source_files,
        "provenance": {
            **DATASET,
            "person": args.person,
            "record": args.record,
            "source_signal_0": "ECG I (raw signal)",
            "source_signal_1": "ECG I filtered (source-provided filtered signal)",
            "known_preprocessing": "Signal 1 is the filtered version supplied by the ECG-ID dataset; OPL does not claim this as OPL filtering.",
            "annotation_status": "Automated R/T peak annotations supplied by source; unaudited.",
            "opl_transformations": ["WFDB digital samples converted losslessly to JSON integer arrays for browser visualization"],
        },
    }

    output.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {output} ({output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
