#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "site"
BUILD_ROOT = ROOT / "build"
DEST = BUILD_ROOT / "opl-ecg-reference-lab-paper1"
ZIP_PATH = BUILD_ROOT / "OPL_ECG_Reference_Lab_Paper1.zip"

EXCLUDED = {
    "classroom",
    "classroom_server.ps1",
    "START_OPL_CLASSROOM.cmd",
}


def ignore(path: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        if name in EXCLUDED:
            ignored.add(name)
    return ignored


def main() -> None:
    if DEST.exists():
        shutil.rmtree(DEST)
    BUILD_ROOT.mkdir(exist_ok=True)
    shutil.copytree(SOURCE, DEST, ignore=ignore)

    icons = DEST / "icons"
    icons.mkdir(parents=True, exist_ok=True)
    logo = ROOT / "software" / "OpenPhysiologyLab" / "assets" / "openphysiolab.png"
    if logo.exists():
        with Image.open(logo).convert("RGBA") as source:
            for size in (192, 512):
                resized = source.copy()
                resized.thumbnail((size, size), Image.Resampling.LANCZOS)
                canvas = Image.new("RGBA", (size, size), (23, 59, 87, 255))
                x = (size - resized.width) // 2
                y = (size - resized.height) // 2
                canvas.alpha_composite(resized, (x, y))
                canvas.save(icons / f"icon-{size}.png")

    build_info = {
        "schema": "org.openphysiologylab.paper1-build/v1",
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": os.environ.get("GITHUB_SHA", "local"),
        "release_scope": "Paper 1 ECG Reference Lab",
        "reference_record": "ECG-ID/Person_01/rec_1",
        "reference_dataset_version": "1.0.0",
        "classroom_features_included": False,
        "hardware_acquisition_included": False,
    }
    (DEST / "build-info.json").write_text(json.dumps(build_info, indent=2) + "\n", encoding="utf-8")

    test_note = """OpenPhysiologyLab ECG Reference Lab — Paper 1 test build

PURPOSE
Standalone open-reference ECG visualization, measurement, practice and reproducibility tool.
This build intentionally excludes Classroom Mode and live acquisition.

TEACHING STORY
1. Ideal ECG: notation and known geometry.
2. Clean real LUDB Lead II: physical mV with cardiologist boundaries.
3. Imperfect real ECG-ID: physical mV derived from the source WFDB gain.
4. Machine view: the same ECG-ID signal in source ADC counts, with known ADC↔mV conversion.

PRACTICE LAB
Six bundled LUDB Lead-II exercises are available. Choose an unfamiliar trace, set a baseline,
measure an interval/segment, and reveal the cardiologist annotation only after the attempt.

WINDOWS
1. Extract this ZIP.
2. Double-click START_OPL_REFERENCE_LAB.cmd.
3. The ECG Reference Lab opens in the browser.

PHONE ON SAME WI-FI
1. On the Windows PC double-click START_OPL_PHONE_TEST.cmd.
2. Open the printed LAN URL on the phone.

CHECK
- ECG paper remains square: 40 ms × 0.1 mV in physical-mV modes.
- Caliper time reports both milliseconds and 40-ms small boxes.
- Caliper voltage reports both mV and 0.1-mV vertical boxes.
- Stage 4 reports ADC counts plus equivalent mV/box value when gain is known.
- Practice annotations remain hidden until Reveal expert.
- Provenance, DOI/license and downloadable reproducibility outputs remain visible.

Educational/research prototype; not a diagnostic ECG device.
"""
    (DEST / "PAPER1_TEST_ME_FIRST.txt").write_text(test_note, encoding="utf-8")

    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(DEST.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(DEST.parent))

    print(f"Built {DEST}")
    print(f"Built {ZIP_PATH}")


if __name__ == "__main__":
    main()
