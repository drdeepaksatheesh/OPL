#!/usr/bin/env python3
"""Convert a WFDB/PhysioNet ECG record into an OPL canonical recording folder.

The default mode preserves physical signal values exactly as returned by WFDB
(e.g. mV for ECG records whose headers declare mV).

Example: PTB-XL Lead II
    python prepare_physionet_reference.py \
        --pn-dir ptb-xl/1.0.3/records500/00000 \
        --record 00001_hr \
        --lead II \
        --output out/ptbxl_00001_leadII

Optional virtual-ADC mode is provided to test OPL's conversion logic without
claiming that the chosen transform represents NPG Lite hardware.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

try:
    import wfdb
except ImportError as exc:
    raise SystemExit(
        "wfdb is required. Install validation/reference_ecg/requirements.txt"
    ) from exc


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--pn-dir", required=True, help="PhysioNet WFDB directory, e.g. ptb-xl/1.0.3/records500/00000")
    p.add_argument("--record", required=True, help="WFDB record name without extension")
    p.add_argument("--lead", required=True, help="Signal/lead name, e.g. II or MLII")
    p.add_argument("--output", required=True, help="Output OPL recording folder")
    p.add_argument("--virtual-adc-counts-per-mv", type=float, default=None)
    p.add_argument("--virtual-adc-zero", type=float, default=2048.0)
    return p.parse_args()


def main():
    args = parse_args()

    rec = wfdb.rdrecord(args.record, pn_dir=args.pn_dir, physical=True)

    if rec.p_signal is None:
        raise RuntimeError("WFDB did not return physical signal values.")

    names = list(rec.sig_name or [])
    try:
        lead_index = names.index(args.lead)
    except ValueError as exc:
        raise SystemExit(
            f"Lead {args.lead!r} not found. Available: {', '.join(names)}"
        ) from exc

    signal = np.asarray(rec.p_signal[:, lead_index], dtype=float)
    fs = float(rec.fs)
    unit = (rec.units or ["unknown"] * len(names))[lead_index]

    output_mode = "physical"
    exported = signal.copy()

    if args.virtual_adc_counts_per_mv is not None:
        if str(unit).lower() != "mv":
            raise SystemExit(
                f"Virtual ADC mode expects an mV source; WFDB reports {unit!r}."
            )
        exported = (
            signal * float(args.virtual_adc_counts_per_mv)
            + float(args.virtual_adc_zero)
        )
        output_mode = "virtual_adc"

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    raw_path = out / "raw.csv"
    with raw_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "sample", "pc_time_s", "segment_id",
            "ch1", "ch2", "ch3", "ch4", "ch5", "ch6"
        ])
        for i, value in enumerate(exported):
            writer.writerow([
                i,
                f"{i / fs:.12f}",
                0,
                f"{value:.12g}",
                "", "", "", "", ""
            ])

    metadata = {
        "recording_mode": "ECG_REFERENCE",
        "reference_source": "PhysioNet/WFDB",
        "reference_pn_dir": args.pn_dir,
        "reference_record": args.record,
        "reference_lead": args.lead,
        "source_signal_unit": unit,
        "exported_signal_unit": unit if output_mode == "physical" else "virtual_ADC_count",
        "reference_output_mode": output_mode,
        "sample_rate_target_hz": fs,
        "sample_count": int(signal.size),
        "duration_s": float(signal.size / fs),
        "physical_min": float(np.nanmin(signal)),
        "physical_max": float(np.nanmax(signal)),
        "physical_peak_to_peak": float(np.nanmax(signal) - np.nanmin(signal)),
        "validation_only": True,
        "diagnostic_use": False,
    }

    if output_mode == "virtual_adc":
        metadata["virtual_adc_counts_per_mV"] = float(args.virtual_adc_counts_per_mv)
        metadata["virtual_adc_zero"] = float(args.virtual_adc_zero)
        metadata["virtual_adc_note"] = (
            "Synthetic transform for software testing only; "
            "not an NPG Lite hardware calibration."
        )

    with (out / "metadata.json").open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print(f"Wrote {raw_path}")
    print(f"Lead: {args.lead} | fs: {fs:g} Hz | source unit: {unit}")
    print(
        "Physical range: "
        f"{metadata['physical_min']:.6g} to {metadata['physical_max']:.6g} {unit}"
    )


if __name__ == "__main__":
    main()
