"""Preserve input raw CSV as bytes and generate a standardized checked copy.

Educational tool only: input units, identity and rights remain the depositor's
responsibility, and are not inferred from magnitudes. Only `time_ms,value` files.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import re
import sys


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ingest(source: Path, outdir: Path, record_id: str, source_id: str,
           unit: str, species: str, license_id: str, citation: str) -> dict:
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,90}', record_id) or record_id in {'.','..'}:
        raise ValueError('Unsafe record-id; use letters, digits, hyphen, underscore or dot')
    if not source.is_file():
        raise ValueError('Input file not found')
    rows = []
    with source.open('r', encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not {'time_ms', 'value'}.issubset(reader.fieldnames):
            raise ValueError('CSV must include exact time_ms,value headers')
        previous = float('-inf')
        for line, row in enumerate(reader, start=2):
            try:
                t = float(row['time_ms'])
                v = float(row['value'])
            except (TypeError, ValueError) as exc:
                raise ValueError(f'Non-numeric row at line {line}') from exc
            if not all(map(__import__('math').isfinite, (t, v))):
                raise ValueError(f'Non-finite number at line {line}')
            if t <= previous:
                raise ValueError(f'time_ms must increase strictly (line {line})')
            previous = t
            rows.append((t, v))
    if len(rows) < 2:
        raise ValueError('At least two rows required')
    if license_id.lower() in {'unknown', 'none', 'pending'}:
        raise ValueError('Do not ingest a dataset with unknown reproduction rights')
    if not all((record_id, source_id, unit, species, citation)):
        raise ValueError('Supply identity, units, species, source and citation')
    outdir.mkdir(parents=True, exist_ok=True)
    original = outdir / f'{record_id}_original{source.suffix.lower()}'
    derived = outdir / f'{record_id}_normalized.csv'
    manifest = outdir / f'{record_id}_manifest.json'
    if any(x.exists() for x in (original, derived, manifest)):
        raise ValueError('Output exists: use a new record identifier; never overwrite master')
    shutil.copyfile(source, original)
    with derived.open('w', encoding='utf-8', newline='') as stream:
        w = csv.writer(stream)
        w.writerow(('time_ms', 'value'))
        w.writerows(rows)
    meta = {
        'record_id': record_id, 'source_id': source_id, 'data_class': 'UNVERIFIED_IMPORT',
        'species': species, 'time_unit': 'ms', 'y_unit': unit, 'source_citation': citation,
        'licence': license_id, 'original_filename': source.name,
        'original_sha256': digest(original), 'derived_sha256': digest(derived),
        'sample_count': len(rows), 'time_interval_ms': [rows[0][0], rows[-1][0]],
        'calibration': 'INPUT UNITS ASSERTED BY DEPOSITOR; independent verification pending',
        'processing': ['parsed CSV floats; copied to normalized text; no filtering or resampling'],
        'review_status': 'unverified-not-for-biological-release',
        'limitations': ['Provenance, licence and physical-unit assertions require human review'],
    }
    manifest.write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')
    return meta


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('--output-dir', type=Path, required=True)
    for name in ('record-id', 'source-id', 'unit', 'species', 'license', 'citation'):
        p.add_argument('--'+name, required=True)
    a = p.parse_args()
    try:
        r = ingest(a.source, a.output_dir, a.record_id, a.source_id,
                   a.unit, a.species, a.license, a.citation)
    except ValueError as exc:
        print('REJECTED:', exc, file=sys.stderr)
        return 2
    print(json.dumps(r, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
