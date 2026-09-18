#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="site/reference/ecg-id/data/Person_01_rec_1.json")
    args = parser.parse_args()

    data = json.loads(Path(args.path).read_text(encoding="utf-8"))

    assert data["schema"] == "org.openphysiologylab.reference-record/v1"
    assert data["record_id"] == "ECG-ID/Person_01/rec_1"
    assert data["sampling_rate_hz"] == 500.0
    assert data["sample_count"] == 10000
    assert data["duration_seconds"] == 20.0
    assert data["adc"]["resolution_bits"] == 12
    assert len(data["signals"]["raw"]) == 10000
    assert len(data["signals"]["filtered"]) == 10000
    assert data["signals"]["raw"] != data["signals"]["filtered"]
    assert data["annotation_summary"]["annotated_beats"] == 10
    assert data["annotation_summary"]["annotation_events"] == len(data["annotations"])
    assert len(data["annotations"]) >= 10

    symbols = [item.get("symbol") for item in data["annotations"]]
    assert "N" in symbols
    assert "t" in symbols

    assert data["provenance"]["doi"] == "10.13026/C2J01F"
    assert data["provenance"]["license"] == "Open Data Commons Attribution License v1.0"

    for ext in ("hea", "dat", "atr"):
        source = data["source_files"][ext]
        assert len(source["sha256"]) == 64
        assert source["bytes"] > 0
        assert source["url"].startswith("https://physionet.org/files/ecgiddb/1.0.0/Person_01/")

    print("ECG-ID reference package verification passed")


if __name__ == "__main__":
    main()
