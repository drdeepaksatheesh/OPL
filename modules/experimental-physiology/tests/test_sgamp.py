"""All test records in this file are SYNTHETIC fixtures, not biological data."""
import importlib.util
import struct
import hashlib
import tempfile
import unittest
from pathlib import Path

SCRIPT=Path(__file__).parents[1]/'scripts'/'ingest_sgamp.py'
spec=importlib.util.spec_from_file_location('ingest_sgamp',SCRIPT)
sg=importlib.util.module_from_spec(spec)
spec.loader.exec_module(sg)

class TestSGAMP(unittest.TestCase):
    def setUp(self):
        frames=[(10,3),(12,7),(-3,-9),(3,5)]
        self.dat=b''.join(struct.pack('<hh',*x) for x in frames)
        s1=sg.signed16_checksum(sum(x[0] for x in frames))
        s2=sg.signed16_checksum(sum(x[1] for x in frames))
        self.hea=(f'fixture 2 125000 4\n'
                  f'fixture.dat 16 100(2)/V 0 0 10 {s1} 0 Vmembrane\n'
                  f'fixture.dat 16 200(-5)/V 0 0 3 {s2} 0 Istim\n').encode('ascii')
        sg.APPROVED['fixture']={'dat_sha256':sg.sha(self.dat), 'hea_sha256':sg.sha(self.hea),
                                'condition':'SYNTHETIC_TEST', 'record_notes':'Not a biological dataset'}
    def tearDown(self):
        sg.APPROVED.pop('fixture',None)
    def test_header(self):
        h=sg.parse_header(self.hea,'fixture')
        self.assertEqual(h['sample_count'],4)
        self.assertEqual(h['signals'][0]['first_sample'],10)
        self.assertEqual(h['signals'][1]['adc_baseline'],-5)
    def test_calibrated_csv_and_master_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'out'
            m=sg.ingest(self.hea,self.dat,'fixture',out)
            self.assertEqual(m['integrity_check']['upstream_sha256'],'pass')
            self.assertEqual((out/'fixture.dat').read_bytes(),self.dat)
            self.assertEqual(m['channels'][0]['range'],[-5.0,10.0])
            self.assertEqual(m['channels'][1]['range'],[-0.1,0.3])
            first=(out/'fixture_Vmembrane_mV.csv').read_text().splitlines()[1]
            self.assertEqual(first,'0.000000,8.00000000')
            firsti=(out/'fixture_Istim_uA_cm2.csv').read_text().splitlines()[1]
            self.assertEqual(firsti,'0.000000,0.20000000')
            last=(out/'fixture_Vmembrane_mV.csv').read_text().splitlines()[-1]
            self.assertTrue(last.startswith('0.024000,'))
            with self.assertRaisesRegex(ValueError,'not empty'):
                sg.ingest(self.hea,self.dat,'fixture',out)
    def test_corruption_rejected_before_file_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'SHA-256 mismatch'):
                sg.ingest(self.hea,self.dat[:-1]+b'x','fixture',Path(tmp)/'out')
            self.assertFalse((Path(tmp)/'out').exists())
    def test_unverified_header_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'SHA-256 mismatch'):
                sg.ingest(self.hea.replace(b'125000',b'100000'),self.dat,'fixture',Path(tmp)/'out')
    def test_unknown_dataset_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'Unapproved record'):
                sg.ingest(self.hea,self.dat,'bogus',Path(tmp)/'out')
    def test_checksum_twos_complement(self):
        self.assertEqual(sg.signed16_checksum(32768),-32768)
        self.assertEqual(sg.signed16_checksum(65535),-1)
        self.assertEqual(sg.signed16_checksum(65536),0)

if __name__=='__main__':unittest.main()
