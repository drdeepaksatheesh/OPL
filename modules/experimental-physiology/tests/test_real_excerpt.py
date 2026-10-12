"""Check that bundled REAL excerpt bytes match documented PhysioNet-derived hashes.

These tests cannot establish raw original provenance by themselves: original
WFDB checksums are independently validated by the SGAMP acquisition workflow.
"""
import csv
import hashlib
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/'examples'/'real'

class TestVerifiedExcerpt(unittest.TestCase):
    def test_excerpt_hash_timing_units(self):
        m=json.loads((ROOT/'sgamp_a1t18_excerpt_manifest.json').read_text())
        self.assertEqual(m['data_class'],'VERIFIED_EXCERPT_FROM_AUTHENTIC_ORIGINAL')
        self.assertEqual(m['original_master_sha256'],'d74534b5d67d7f582694e597e4d4c86adccfdb1f4597379af45323059cafffb9')
        self.assertEqual(m['excerpt_sample_indices_inclusive'],[124000,128750])
        self.assertEqual(m['source_sampling_frequency_hz'],125000)
        for k,c in m['channels'].items():
            file=ROOT/c['file']; raw=file.read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),c['sha256'])
            with file.open(newline='') as f:
                rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),4751)
            self.assertEqual(float(rows[0]['time_ms']),992.0)
            self.assertEqual(float(rows[-1]['time_ms']),1030.0)
            self.assertAlmostEqual(float(rows[1]['time_ms'])-float(rows[0]['time_ms']),0.008,places=6)
            self.assertTrue(all(float(v['value'])==float(v['value']) for v in rows))
        self.assertEqual(m['channels']['Vmembrane']['unit'],'mV')
        self.assertEqual(m['channels']['Istim']['unit'],'uA/cm^2')

if __name__=='__main__':unittest.main()
