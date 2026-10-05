#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from pathlib import Path

RECORD = Path("site/reference/ecg-id/data/LUDB_clean_LeadII.json")
REPORT = Path("site/reference/ecg-id/data/LUDB_clean_selection.json")


def main() -> None:
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    report = json.loads(REPORT.read_text(encoding="utf-8"))

    assert report["dataset"] == "LUDB"
    assert report["dataset_version"] == "1.0.1"
    assert report["eligible_record_count"] > 0

    metrics = report["selected_metrics"]
    assert report["selected_record_id"] == metrics["record_id"]
    assert math.isfinite(float(metrics["selection_score"]))
    assert math.isfinite(float(metrics["baseline_segment_spread_mV"]))
    assert metrics["isoelectric_segment_count"] > 0

    assert record["record_id"] == f'LUDB/{report["selected_record_id"]}/LeadII'
    assert float(record["sampling_rate_hz"]) == 500.0
    assert int(record["sample_count"]) == 5000
    assert record["units"] == ["mV"]
    assert record["provenance"]["doi"] == "10.13026/eegm-h675"
    assert record["annotation_summary"]["manual_delineation"] is True
    assert len(record["isoelectric_segments"]) == metrics["isoelectric_segment_count"]

    for ext in ("hea", "dat", "ii"):
        digest = record["source_files"][ext]["sha256"]
        assert isinstance(digest, str) and len(digest) == 64

    boundary_waves = {
        ann.get("wave")
        for ann in record["annotations"]
        if ann.get("symbol") in {"(", ")"}
    }
    assert {"P", "QRS", "T"}.issubset(boundary_waves)

    print(
        "LUDB clean real reference verification passed:",
        report["selected_record_id"],
        "score=",
        metrics["selection_score"],
    )


if __name__ == "__main__":
    main()
