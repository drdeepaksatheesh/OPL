#!/usr/bin/env python3
"""Screen *source-verified* SGAMP pulse records; never silently promote a teaching trace.

Run:
    python scripts/screen_sgamp_isolated.py --prefix a1 --output research/SGAMP_a1_screen.json
Requires: numpy. Does not overwrite or modify original biological samples.
"""
import argparse, hashlib, json, re, time
from pathlib import Path
from urllib.request import urlopen
import numpy as np

ROOT = "https://physionet.org/files/sgamp/1.0.0/"
DOI = "10.13026/C25C73"
def get(relative):
    for attempt in range(3):
        try:
            with urlopen(ROOT+relative, timeout=90) as response:
                return response.read()
        except Exception:
            if attempt == 2: raise
            time.sleep(2*(attempt+1))

def upstream_manifest():
    text = get("SHA256SUMS.txt").decode()
    entries = {}
    for line in text.splitlines():
        m = re.match(r"^([0-9a-f]{64})\s+\*?(\S+)\s*$",line)
        if m: entries[m.group(2)] = m.group(1)
    if len(entries)<100: raise RuntimeError("Unexpected source checksum manifest")
    return entries

def verified_bytes(relative, checksums):
    expected=checksums.get(relative)
    if not expected: raise ValueError("Missing upstream hash for "+relative)
    raw=get(relative)
    measured=hashlib.sha256(raw).hexdigest()
    if measured != expected: raise ValueError("Source SHA256 mismatch for "+relative)
    return raw

def decode(rid, header, data):
    lines=[x.strip() for x in header.decode("ascii").splitlines() if x.strip() and not x.startswith("#")]
    h=lines[0].split()
    if h[0] != rid or int(h[1]) != 2 or float(h[2]) != 125000.0:
        raise ValueError("Unexpected header identity, rate or channel count")
    n=int(h[3])
    if len(data) != n*4: raise ValueError("Wrong raw WFDB length")
    signal=[]
    for name,line in zip(("Vmembrane","Istim"),lines[1:]):
        f=line.split()
        match=re.fullmatch(r"(\d+(?:\.\d+)?)\((-?\d+)\)/V",f[2])
        if f[0]!=rid+".dat" or f[1]!="16" or not match or f[-1]!=name:
            raise ValueError("Unsupported WFDB format or channel identity")
        signal.append({"gain":float(match.group(1)),"zero":int(match.group(2)),
                       "initial":int(f[5]),"checksum":int(f[6])})
    a=np.frombuffer(data,dtype="<i2").reshape((-1,2)).astype(np.int32)
    def checksum(x): return int(((int(np.sum(x,dtype=np.int64))+32768)%65536)-32768)
    for index in range(2):
        if a[0,index] != signal[index]["initial"] or checksum(a[:,index]) != signal[index]["checksum"]:
            raise ValueError("WFDB initial/checksum disagreement")
    # Documentation: recorded volts / 10 -> membrane volts; recorded volts *5 -> current uA/cm2
    v=(a[:,0]-signal[0]["zero"])/signal[0]["gain"]*100.0
    current=(a[:,1]-signal[1]["zero"])/signal[1]["gain"]*5.0
    return v,current

def median_window(a,lo,hi,fs=125000):
    x=a[int(lo*fs/1000):int(hi*fs/1000)]
    return float(np.median(x)),float(np.std(x))

def analyze(v,i):
    fs=125000
    pre,pre_sd=median_window(v,850,950)
    late,late_sd=median_window(v,1230,1450)
    i_pre,_=median_window(i,850,950)
    i_late,_=median_window(i,1230,1450)
    # up-crossing detector; each crossing must be followed by a > 30mV excursion
    threshold=max(0.0,pre+32.0)
    left=int(.95*fs);right=min(len(v),int(1.5*fs))
    inside=v[left:right]
    crossings=np.flatnonzero((inside[:-1]<threshold)&(inside[1:]>=threshold))+left+1
    spike_indices=[]
    for index in crossings:
        # do not re-count fast threshold recrossings inside a spike
        if spike_indices and index-spike_indices[-1]<int(.001*fs):
            continue
        spike_indices.append(int(index))
    first_ms=spike_indices[0]*1000/fs if spike_indices else None
    # recovery is judged *after current offset* and not by arbitrary baseline redrawing
    stimulus_end=int(1.3*fs)
    current_change=abs(i_late-i_pre)
    spike_count=len(spike_indices)
    stable=abs(late-pre)<=3 and late_sd<=2.5 and current_change<=0.5
    is_single=spike_count==1 and first_ms is not None and 995<=first_ms<=1150
    quality="screen_candidate" if (is_single and stable) else "not_qualified"
    return dict(pre_mV=round(pre,5),late_mV=round(late,5),
                delta_baseline_mV=round(late-pre,5),
                pre_sd_mV=round(pre_sd,5),late_sd_mV=round(late_sd,5),
                pre_current_uA_cm2=round(i_pre,5),late_current_uA_cm2=round(i_late,5),
                detected_spikes_950_1500ms=spike_count,first_threshold_crossing_ms=first_ms,
                result=quality,
                caveats=["Automated voltage crossing is not expert-validated AP onset.",
                         "Current-channel DC offsets are retained, not silently corrected.",
                         "Even a screen_candidate requires full trace inspection and independent physiology review."])

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--prefix",default="a1")
    p.add_argument("--limit",type=int,default=30)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    sums=upstream_manifest()
    record_names=[x.strip().split("/")[-1] for x in get("RECORDS").decode().splitlines()]
    chosen=[x.strip() for x in record_names if re.fullmatch(r"a\dt\d+",x.strip()) and x.strip().startswith(args.prefix)][:args.limit]
    if not chosen: raise RuntimeError("No upstream records found")
    reports=[]
    for rid in chosen:
        try:
            hea=verified_bytes(f"raw/{rid}.hea",sums)
            dat=verified_bytes(f"raw/{rid}.dat",sums)
            v,i=decode(rid,hea,dat)
            result=analyze(v,i)
            result.update(record_id=rid,sampling_rate_hz=125000,source_doi=DOI,
                          source_sha256_dat=sums[f"raw/{rid}.dat"],source_sha256_hea=sums[f"raw/{rid}.hea"])
            reports.append(result)
            print(rid,result["result"],"spikes",result["detected_spikes_950_1500ms"],
                  "baseline_diff",result["delta_baseline_mV"],flush=True)
        except Exception as e:
            reports.append({"record_id":rid,"result":"error","error":str(e)})
            print("ERROR",rid,str(e),flush=True)
    out=dict(dataset="PhysioNet SGAMP v1.0.0",source_doi=DOI,screen_method="v0.1.1",
             scanned_count=len(chosen),screen_candidate_count=sum(x["result"]=="screen_candidate" for x in reports),
             scope=f"records with prefix {args.prefix}",acceptance="AUTOMATED SCREEN ONLY — NOT EXPERT VERIFIED",
             records=reports)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    print("screen candidate count:",out["screen_candidate_count"])

if __name__=="__main__": main()
