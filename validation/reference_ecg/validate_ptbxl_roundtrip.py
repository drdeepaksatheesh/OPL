#!/usr/bin/env python3
"""PTB-XL -> OPL physical-unit/time round-trip benchmark.

Purpose
-------
Verify that the OPL reference importer preserves Lead-II samples, timing and
physical units from PTB-XL without relying on morphology or local hardware.

Selection is deterministic and not based on signal appearance: five records
are selected at fixed quantiles of the sorted PTB-XL metadata table.
"""

from __future__ import annotations

import csv
import io
import json
import math
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import numpy as np
import wfdb

ROOT = Path(__file__).resolve().parents[2]
IMPORTER = ROOT / "validation" / "reference_ecg" / "prepare_physionet_reference.py"
PTBXL_VERSION = "1.0.3"
PN_ROOT = f"ptb-xl/{PTBXL_VERSION}"
CSV_URL = f"https://physionet.org/files/ptb-xl/{PTBXL_VERSION}/ptbxl_database.csv"
DOI = "10.13026/kfzx-aw45"
LICENSE = "Creative Commons Attribution 4.0 International"


def fetch_metadata() -> list[dict[str, str]]:
    with urllib.request.urlopen(CSV_URL, timeout=90) as response:
        text = response.read().decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    rows.sort(key=lambda row: int(row["ecg_id"]))
    return rows


def fixed_quantile_rows(rows: list[dict[str, str]], count: int = 5) -> list[dict[str, str]]:
    if len(rows) < count:
        raise RuntimeError("PTB-XL metadata has fewer rows than requested benchmark records.")
    if count == 1:
        return [rows[0]]
    indices = [round(i * (len(rows) - 1) / (count - 1)) for i in range(count)]
    return [rows[index] for index in indices]


def read_imported_csv(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    samples = []
    times = []
    values = []
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            samples.append(int(row["sample"]))
            times.append(float(row["pc_time_s"]))
            values.append(float(row["ch1"]))
    return (
        np.asarray(samples, dtype=int),
        np.asarray(times, dtype=float),
        np.asarray(values, dtype=float),
    )


def evaluate(row: dict[str, str], temp_root: Path) -> dict:
    filename_hr = row["filename_hr"].strip()
    relative = Path(filename_hr)
    record_name = relative.name
    pn_dir = f"{PN_ROOT}/{relative.parent.as_posix()}"

    physical = wfdb.rdrecord(record_name, pn_dir=pn_dir, physical=True)
    digital = wfdb.rdrecord(record_name, pn_dir=pn_dir, physical=False)

    names = list(physical.sig_name or [])
    if "II" not in names:
        raise RuntimeError(f"Lead II missing from PTB-XL record {record_name}")
    lead_index = names.index("II")

    source = np.asarray(physical.p_signal[:, lead_index], dtype=float)
    source_digital = np.asarray(digital.d_signal[:, lead_index], dtype=float)
    fs = float(physical.fs)
    gain = float((digital.adc_gain or [math.nan] * len(names))[lead_index])
    baseline = float((digital.baseline or [math.nan] * len(names))[lead_index])
    unit = str((physical.units or ["unknown"] * len(names))[lead_index])

    expected_physical = (source_digital - baseline) / gain
    header_conversion_error = float(np.max(np.abs(expected_physical - source)))

    output = temp_root / f"ptbxl_{row['ecg_id']}_leadII"
    subprocess.run(
        [
            sys.executable,
            str(IMPORTER),
            "--pn-dir",
            pn_dir,
            "--record",
            record_name,
            "--lead",
            "II",
            "--output",
            str(output),
        ],
        check=True,
    )

    samples, times, imported = read_imported_csv(output / "raw.csv")
    metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))

    expected_samples = np.arange(source.size, dtype=int)
    expected_times = expected_samples / fs

    sample_index_exact = bool(np.array_equal(samples, expected_samples))
    sample_max_abs_error_mV = float(np.max(np.abs(imported - source)))
    time_max_abs_error_s = float(np.max(np.abs(times - expected_times)))

    return {
        "ecg_id": int(row["ecg_id"]),
        "filename_hr": filename_hr,
        "record": record_name,
        "lead": "II",
        "sampling_rate_hz": fs,
        "sample_count": int(source.size),
        "duration_s": float(source.size / fs),
        "lead_count": int(physical.n_sig),
        "source_unit": unit,
        "adc_gain_counts_per_mV": gain,
        "adc_baseline_count": baseline,
        "header_physical_conversion_max_abs_error_mV": header_conversion_error,
        "opl_import_sample_index_exact": sample_index_exact,
        "opl_import_sample_max_abs_error_mV": sample_max_abs_error_mV,
        "opl_import_time_max_abs_error_s": time_max_abs_error_s,
        "opl_metadata_exported_unit": metadata["exported_signal_unit"],
        "opl_metadata_sample_rate_hz": metadata["sample_rate_target_hz"],
        "opl_metadata_sample_count": metadata["sample_count"],
        "pass": bool(
            fs == 500.0
            and source.size == 5000
            and physical.n_sig == 12
            and unit.lower() == "mv"
            and abs(gain - 1000.0) < 1e-12
            and abs(baseline) < 1e-12
            and header_conversion_error <= 1e-12
            and sample_index_exact
            and sample_max_abs_error_mV <= 1e-10
            and time_max_abs_error_s <= 5e-13
            and str(metadata["exported_signal_unit"]).lower() == "mv"
            and float(metadata["sample_rate_target_hz"]) == 500.0
            and int(metadata["sample_count"]) == 5000
        ),
    }


def main() -> None:
    rows = fetch_metadata()
    selected = fixed_quantile_rows(rows, count=5)

    with tempfile.TemporaryDirectory(prefix="opl_ptbxl_") as temp:
        temp_root = Path(temp)
        records = [evaluate(row, temp_root) for row in selected]

    report = {
        "schema": "org.openphysiologylab.ptbxl-roundtrip-validation/v1",
        "dataset": "PTB-XL",
        "dataset_version": PTBXL_VERSION,
        "doi": DOI,
        "license": LICENSE,
        "selection_rule": (
            "Five records at fixed quantiles of the sorted PTB-XL ecg_id table; "
            "selection is independent of waveform appearance or OPL output."
        ),
        "record_count": len(records),
        "lead": "II",
        "expected_sampling_rate_hz": 500,
        "expected_resolution": "16-bit, 1 microvolt/LSB (1000 counts/mV)",
        "records": records,
        "summary": {
            "all_passed": all(record["pass"] for record in records),
            "max_sample_abs_error_mV": max(
                record["opl_import_sample_max_abs_error_mV"] for record in records
            ),
            "max_time_abs_error_s": max(
                record["opl_import_time_max_abs_error_s"] for record in records
            ),
            "max_header_conversion_error_mV": max(
                record["header_physical_conversion_max_abs_error_mV"] for record in records
            ),
        },
        "claim_boundary": [
            "Validates OPL software import/time/unit preservation for these frozen PTB-XL records.",
            "Does not validate ECG diagnosis or morphology interpretation.",
            "Does not calibrate NPG Lite or any analogue acquisition hardware.",
        ],
    }

    output = ROOT / "build" / "reference-validation" / "ptbxl_roundtrip_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report["summary"], indent=2))
    for record in records:
        print(
            f"PTB-XL {record['ecg_id']:05d}: "
            f"sample_error={record['opl_import_sample_max_abs_error_mV']:.3g} mV, "
            f"time_error={record['opl_import_time_max_abs_error_s']:.3g} s, "
            f"pass={record['pass']}"
        )

    if not report["summary"]["all_passed"]:
        raise SystemExit("PTB-XL round-trip validation failed.")


if __name__ == "__main__":
    main()
