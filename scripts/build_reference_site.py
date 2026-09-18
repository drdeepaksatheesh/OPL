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
DEST = BUILD_ROOT / "opl-site"
ZIP_PATH = BUILD_ROOT / "opl-reference-lab-static.zip"


def main():
    if DEST.exists():
        shutil.rmtree(DEST)
    BUILD_ROOT.mkdir(exist_ok=True)
    shutil.copytree(SOURCE, DEST)

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
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": os.environ.get("GITHUB_SHA", "local"),
        "reference_record": "ECG-ID/Person_01/rec_1",
        "reference_dataset_version": "1.0.0",
    }
    (DEST / "build-info.json").write_text(json.dumps(build_info, indent=2) + "\n", encoding="utf-8")

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
