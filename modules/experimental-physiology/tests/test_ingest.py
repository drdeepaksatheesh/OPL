import importlib.util
from pathlib import Path
import tempfile
import unittest
import csv
import json
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('ingest_csv',ROOT/'scripts/ingest_csv.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)


class IngestTests(unittest.TestCase):
    def test_synthetic_is_marked_synthetic(self):
        f=json.loads((ROOT/'examples/demo_SYNTHETIC_muscle_twitch.manifest.json').read_text())
        self.assertEqual(f['data_class'],'SYNTHETIC')

    def test_ingest_valid_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);s=d/'test.csv';s.write_bytes(b'time_ms,value\n0,1\n1,2\n2,3\n')
            result=mod.ingest(s,d/'out','abc','source','mV','squid','CC-BY-4.0','Author, title, 2026')
            self.assertEqual(result['sample_count'],3)
            self.assertEqual((d/'out/abc_original.csv').read_bytes(),s.read_bytes())
            self.assertEqual(mod.digest(d/'out/abc_original.csv'),result['original_sha256'])
            self.assertEqual(result['review_status'],'unverified-not-for-biological-release')
            self.assertEqual(result['data_class'],'UNVERIFIED_IMPORT')

    def test_incomplete_metadata_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);s=d/'test.csv';s.write_text('time_ms,value\n0,1\n1,2\n')
            with self.assertRaises(ValueError):
                mod.ingest(s,d/'out','abc','source','mV','squid','unknown','Citation')

    def test_unsafe_identifier_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);s=d/'test.csv';s.write_text('time_ms,value\n0,1\n1,2\n')
            with self.assertRaises(ValueError):
                mod.ingest(s,d/'out','../escape','source','mV','squid','CC-BY-4.0','Citation')

    def test_time_regression_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);s=d/'test.csv';s.write_text('time_ms,value\n0,1\n0,2\n')
            with self.assertRaises(ValueError):
                mod.ingest(s,d/'out','abc','source','mV','squid','CC-BY-4.0','Citation')

if __name__=='__main__':unittest.main()
