#!/usr/bin/env python3
"""Independent, standard-library-only scientific check of PhysioNet SGAMP a1t18.

Reads unaltered original WFDB format-16 bytes, not derived CSV, and reports
explicit-threshold, exploratory events. Not an independently adjudicated answer key.
"""
import argparse
import hashlib
import json
import statistics
import struct
from pathlib import Path

EXPECTED={
 'a1t18.dat':'d74534b5d67d7f582694e597e4d4c86adccfdb1f4597379af45323059cafffb9',
 'a1t18.hea':'9dd10bf0703219b08be82f69444d25ae9e4c81f5f419f998b422c9ab72f66e0c',
}
def read_original(folder):
 folder=Path(folder)
 for name,expected in EXPECTED.items():
  if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=expected:raise ValueError('Original upstream SHA-256 mismatch: '+name)
 h=(folder/'a1t18.hea').read_text('ascii').splitlines();assert h[0]=='a1t18 2 125000 250001',h[0]
 assert len(h)==3
 parsed=[]
 for x in h[1:]:
  p=x.split(); gain=float(p[2].split('(')[0]);baseline=int(p[2].split('(')[1].split(')')[0]);parsed.append((gain,baseline))
 assert h[1].endswith('Vmembrane') and h[2].endswith('Istim')
 data=(folder/'a1t18.dat').read_bytes();assert len(data)==250001*4
 return parsed,data
def analyze(folder):
 g,raw=read_original(folder)
 vm=[];stim=[];t=[]
 for n,(a,b) in enumerate(struct.iter_unpack('<hh',raw)):
  t.append(n*.008);vm.append((a-g[0][1])/g[0][0]*100);stim.append((b-g[1][1])/g[1][0]*5)
 baseline=[i for i,x in enumerate(t) if 990<=x<999]
 rest=[i for i,x in enumerate(t) if 0<=x<900]
 hits={}
 for threshold in (0.5,1.0,2.0,4.0):
  rising=next(i for i,x in enumerate(t) if 999<=x<=1002 and stim[i]>threshold)
  falling=next(i for i in range(rising+1,len(t)) if t[i]<=1003 and stim[i]<=threshold)
  hits[str(threshold)]={'onset_ms':round(t[rising],3),'pulse_end_ms':round(t[falling],3),'pulse_duration_ms':round(t[falling]-t[rising],3)}
 idx=max((i for i,x in enumerate(t) if 1000<=x<=1002),key=lambda i:vm[i]); onset=hits['1.0']['onset_ms']
 assert len(vm)==250001 and abs(t[-1]-2000)<1e-6
 assert 39<vm[idx]<40 and 1001<t[idx]<1001.3
 return {
  'source_doi':'10.13026/C25C73','record':'a1t18','n_samples':len(vm),'rate_hz':125000,
  'master_sha256':EXPECTED,'time_resolution_ms':0.008,
  'pre_stimulation_Vm_median_mV':round(statistics.median(vm[i] for i in baseline),4),
  'prestim_0_900ms_Vm_median_mV':round(statistics.median(vm[i] for i in rest),4),
  'pre_stimulation_current_median_uA_cm2_not_offset_corrected':round(statistics.median(stim[i] for i in baseline),6),
  'stimulus_onset_sensitivity_uA_cm2':hits,
  'first_positive_peak_ms':round(t[idx],3),
  'first_positive_peak_mV':round(vm[idx],4),
  'onset_to_peak_ms_threshold_1uA_cm2':round(t[idx]-onset,3),
  'first_pulse_peak_recorded_current_uA_cm2':round(max(stim[i] for i,x in enumerate(t) if 1000<=x<1002),4),
  'interpretive_status':'descriptive exploratory analysis, not expert-adjudicated action-potential initiation time',
  'limitations':['pulse detector based on uncorrected current channel > selected threshold',
                 'source data are 8 microsecond sampled; biological onset estimation has additional uncertainty',
                 'single isolated-axon trial, no causal inference about all repetitive discharges',
                 'first positive peak is not action-potential initiation',
                 'original instrumentation current-channel DC offset retained']
 }
def main():
 p=argparse.ArgumentParser();p.add_argument('--original',type=Path,required=True);p.add_argument('--output',type=Path);a=p.parse_args()
 report=analyze(a.original)
 if a.output:a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
 else:print(json.dumps(report,indent=2))
if __name__=='__main__':main()
