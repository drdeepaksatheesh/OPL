#!/usr/bin/env python3
"""Verify and convert one authentic PhysioNet SGAMP WFDB 16 two-channel record.

The original bytes must match PhysioNet's published SHA-256. The two physical
channels remain separate; no invented stimulus baseline subtraction is applied.
There is no dependency on external WFDB libraries.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import re
import struct
from pathlib import Path
from urllib.request import urlopen

SOURCE = 'https://physionet.org/files/sgamp/1.0.0/raw/'
DATASET = 'https://physionet.org/content/sgamp/1.0.0/'
# From the upstream SHA256SUMS.txt (PhysioNet dataset release 1.0.0)
APPROVED = {
  'a1t18': {
    'dat_sha256': 'd74534b5d67d7f582694e597e4d4c86adccfdb1f4597379af45323059cafffb9',
    'hea_sha256': '9dd10bf0703219b08be82f69444d25ae9e4c81f5f419f998b422c9ab72f66e0c',
    'condition': 'PULSE',
    'record_notes': 'Irms.txt labels 1.18 PULSE. Stimulus-channel offset must not be interpreted as physical baseline current.'
  },
}

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def check(data: bytes, expected: str, filename: str):
    actual = sha(data)
    if actual != expected:
        raise ValueError(f'{filename} SHA-256 mismatch: expected {expected}, got {actual}')
    return actual

def parse_header(raw: bytes, record_id: str) -> dict:
    try:
        lines = [line.strip() for line in raw.decode('ascii').splitlines() if line.strip() and not line.startswith('#')]
    except UnicodeDecodeError as e:
        raise ValueError('Header must be ASCII') from e
    if len(lines) != 3:
        raise ValueError('Expected a single-segment WFDB record with exactly two signal lines')
    h = lines[0].split()
    if len(h) != 4 or h[0] != record_id or h[1] != '2':
        raise ValueError('Unexpected record ID or channel count')
    rate = float(h[2]); nsamples=int(h[3]);
    if not (rate > 0 and nsamples > 0 and rate == 125000):
        raise ValueError('Unexpected sample rate or sample count')
    signals=[]
    for i, line in enumerate(lines[1:]):
        parts=line.split()
        if len(parts) != 9 or parts[0] != record_id+'.dat' or parts[1] != '16':
            raise ValueError('Unsupported signal layout: only contiguous WFDB format 16 accepted')
        m=re.fullmatch(r'([0-9]+(?:\.[0-9]+)?)\((-?\d+)\)/V', parts[2])
        if not m or float(m.group(1)) <= 0 or parts[3] != '0' or parts[4] != '0' or parts[7] != '0' or parts[8] not in ('Vmembrane','Istim'):
            raise ValueError('Unsupported gain, unit, or layout')
        if i==0 and parts[8]!='Vmembrane' or i==1 and parts[8]!='Istim':
            raise ValueError('Unexpected signal order')
        signals.append({'name':parts[8], 'adc_gain_per_volt':float(m.group(1)),
                        'adc_baseline':int(m.group(2)), 'first_sample':int(parts[5]),
                        'checksum_signed16':int(parts[6])})
    return {'record_id':record_id,'sampling_rate_hz':rate,'sample_count':nsamples,'signals':signals}

def signed16_checksum(total: int)->int:
    return (total+32768)%65536-32768

def ingest(raw_hea: bytes, raw_dat: bytes, record_id: str, output: Path) -> dict:
    if record_id not in APPROVED:
        raise ValueError(f'Unapproved record: {record_id}; do not silently trust unreviewed records')
    reg=APPROVED[record_id]
    hs=check(raw_hea,reg['hea_sha256'],record_id+'.hea')
    ds=check(raw_dat,reg['dat_sha256'],record_id+'.dat')
    hdr=parse_header(raw_hea,record_id)
    n=hdr['sample_count']; sr=hdr['sampling_rate_hz']; ss=hdr['signals']
    if len(raw_dat)!=n*4:
        raise ValueError(f'Invalid data size, expected {n*4} bytes, got {len(raw_dat)}')
    if output.exists() and list(output.iterdir()):
        raise ValueError('Output directory not empty; immutable versioned output required')
    output.mkdir(parents=True,exist_ok=True)
    vm_path=output/(record_id+'_Vmembrane_mV.csv')
    is_path=output/(record_id+'_Istim_uA_cm2.csv')
    sums=[0,0]; first=None; ranges=[[float('inf'),float('-inf')],[float('inf'),float('-inf')]]
    with vm_path.open('w',newline='',encoding='utf-8') as fv, is_path.open('w',newline='',encoding='utf-8') as fi:
        vwrite=csv.writer(fv,lineterminator='\n');iwrite=csv.writer(fi,lineterminator='\n')
        vwrite.writerow(('time_ms','value'));iwrite.writerow(('time_ms','value'))
        for idx,(vraw,iraw) in enumerate(struct.iter_unpack('<hh',raw_dat)):
            if first is None: first=(vraw,iraw)
            sums[0]+=vraw;sums[1]+=iraw
            # Convert WFDB ADC counts -> raw volts -> physical units (PhysioNet instructions).
            vm = ((vraw-ss[0]['adc_baseline']) / ss[0]['adc_gain_per_volt']) * 100.0
            stimulus = ((iraw-ss[1]['adc_baseline']) / ss[1]['adc_gain_per_volt']) * 5.0
            t = 1000*idx/sr
            vwrite.writerow((f'{t:.6f}',f'{vm:.8f}'))
            iwrite.writerow((f'{t:.6f}',f'{stimulus:.8f}'))
            for j,value in enumerate((vm,stimulus)):
                ranges[j][0]=min(ranges[j][0],value)
                ranges[j][1]=max(ranges[j][1],value)
    if tuple(s['first_sample'] for s in ss)!=first:
        raise ValueError('WFDB first-sample metadata mismatch')
    checks=[signed16_checksum(x) for x in sums]
    if checks != [s['checksum_signed16'] for s in ss]:
        raise ValueError('WFDB per-channel 16-bit checksum mismatch')
    # Preserve untouched original upstream bytes only after verification; not necessary to distribute masters in Git.
    (output/(record_id+'.hea')).write_bytes(raw_hea)
    (output/(record_id+'.dat')).write_bytes(raw_dat)
    data={
      'record_id':record_id,'data_class':'RAW_ORIGINAL_VERIFIED_AND_CALIBRATED_DERIVED',
      'source_dataset':DATASET,'source_doi':'10.13026/C25C73',
      'original_study':'Paydarfar D, Forger DB, Clay JR. J Neurophysiol 2006;96:3338–3348.',
      'source_version':'1.0.0','source_license':'ODC-BY-1.0','species':'Doryteuthis pealeii (dataset describes Loligo pealei)',
      'preparation':'isolated squid giant axon','protocol_class':reg['condition'],
      'sampling_rate_hz':sr,'sample_count':n,'duration_ms':(n-1)*1000/sr,
      'original_files':{record_id+'.hea':hs,record_id+'.dat':ds},
      'channels':[{'id':'Vmembrane','unit':'mV','file':vm_path.name,
                   'sha256':sha(vm_path.read_bytes()),'raw_adc_gain':ss[0]['adc_gain_per_volt'],
                   'raw_adc_baseline':ss[0]['adc_baseline'],
                   'conversion':'((ADC - adc_baseline) / adc_gain_per_volt) * 0.1 V * 1000 mV/V',
                   'range':[round(x,6) for x in ranges[0]]},
                  {'id':'Istim','unit':'uA/cm^2','file':is_path.name,
                   'sha256':sha(is_path.read_bytes()),'raw_adc_gain':ss[1]['adc_gain_per_volt'],
                   'raw_adc_baseline':ss[1]['adc_baseline'],
                   'conversion':'((ADC - adc_baseline) / adc_gain_per_volt) * 5 uA/cm^2 per volt; NO DC OFFSET REMOVAL',
                   'range':[round(x,6) for x in ranges[1]]}],
      'integrity_check':{'upstream_sha256':'pass','WFDB_initial_values':'pass','WFDB_checksums':'pass',
                         'file_size':'pass'},
      'review_status':'automated-integrity-and-scale-reviewed; waveform-interpretation-pending',
      'limitations':['Stimulus current recording may have DC offset; do not subtract arbitrarily or interpret as applied baseline.',
                     'Original paper, protocol and trial annotation should be consulted before biological claims.',
                     'CSV decimal rounding to 8 digits in physical units; original WFDB bytes preserved verbatim.']}
    (output/(record_id+'_manifest.json')).write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    return data

def download(url: str) -> bytes:
    with urlopen(url,timeout=60) as f:
        if f.status != 200:
            raise ValueError('HTTP '+str(f.status))
        return f.read()

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--record',default='a1t18', choices=sorted(APPROVED))
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--source-dir',type=Path,help='Read original .hea/.dat from local directory (offline mode)')
    args=p.parse_args(argv)
    if args.source_dir:
        h=(args.source_dir/(args.record+'.hea')).read_bytes()
        d=(args.source_dir/(args.record+'.dat')).read_bytes()
    else:
        h=download(SOURCE+args.record+'.hea')
        d=download(SOURCE+args.record+'.dat')
    result=ingest(h,d,args.record,args.output)
    print(json.dumps({'record_id':result['record_id'],'source_verified':True,
                      'samples':result['sample_count'],'output':str(args.output)},indent=2))

if __name__=='__main__':main()
