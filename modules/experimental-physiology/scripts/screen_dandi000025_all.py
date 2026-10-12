#!/usr/bin/env python3
"""Quantitatively screen paired original APWaveform voltage/current recordings, DANDI 000025.
No artificial recentering, smoothing, clipping or simulated signal is allowed.
All outputs are provisional and require an independent scientific review.
"""
import hashlib,json,urllib.request,tempfile,csv
from pathlib import Path
import h5py,numpy as np
ID="b1364b47-71e1-4b04-b8e4-13aba7543406"
SHA="1ee4844a99fe60c3603c9474d97e12d864eb19a75f851568ad2926385c770b5b"
URL="https://api.dandiarchive.org/api/assets/"+ID+"/download/"
O=Path("modules/experimental-physiology/research")
def acquisition(path):
    dig=hashlib.sha256()
    with urllib.request.urlopen(URL,timeout=150) as r, path.open("wb") as out:
        while True:
            piece=r.read(1024*1024)
            if not piece:break
            dig.update(piece);out.write(piece)
    if dig.hexdigest()!=SHA:raise ValueError("DANDI asset bytes differ from pinned upstream provenance")
def series_values(series,multiplier):
    d=np.asarray(series["data"],dtype=np.float64).reshape(-1)
    conv=series.get("conversion")
    scale=float(np.asarray(conv[()]).reshape(-1)[0]) if conv is not None else float(series.attrs.get("conversion",1))
    off=series.get("offset")
    offset=float(np.asarray(off[()]).reshape(-1)[0]) if off is not None else float(series.attrs.get("offset",0))
    return (d*scale+offset)*multiplier
def screen(vm,current,rate=50000):
    total=len(vm)
    def window(arr,start,end):
        a=arr[int(start*rate/1000):int(end*rate/1000)]
        return float(np.median(a)),float(np.std(a))
    duration=1000*total/rate
    pre,pre_sd=window(vm,30,100)
    late,late_sd=window(vm,duration-150,duration-50)
    i_pre,_=window(current,30,100)
    i_late,_=window(current,duration-150,duration-50)
    threshold=max(-10,pre+38)
    candidates=np.flatnonzero((vm[:-1]<threshold)&(vm[1:]>=threshold))+1
    events=[]
    for index in candidates:
        if not events or index-events[-1]>int(rate*0.002):
            events.append(int(index))
    p_ms=[round(k*1000/rate,4) for k in events]
    good=bool(len(events)==1 and 100< p_ms[0] < duration-200 and abs(pre-late)<3 and
              pre_sd<2.5 and late_sd<2.5 and abs(i_late-i_pre)<20)
    peak_idx = None
    if events:
        k=events[0];peak_idx=k+int(np.argmax(vm[k:min(len(vm),k+int(.003*rate))]))
    return dict(classification="screen_candidate_requires_expert_review" if good else "screen_rejected",
                pre_mV=round(pre,5),post_mV=round(late,5),
                baseline_change_mV=round(late-pre,5),pre_sd_mV=round(pre_sd,5),
                post_sd_mV=round(late_sd,5),
                pre_current_pA=round(i_pre,5),post_current_pA=round(i_late,5),
                current_change_pA=round(i_late-i_pre,5),
                spike_threshold_mV=round(threshold,4),spike_count=len(events),
                spike_crossings_ms=p_ms[:12],first_peak_ms=(round(peak_idx*1000/rate,4) if peak_idx is not None else None),
                first_peak_mV=(round(float(vm[peak_idx]),4) if peak_idx is not None else None),
                duration_ms=round(duration,4))
def main():
    O.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as t:
        nwb=Path(t)/"source.nwb";acquisition(nwb)
        records=[];candidates=[];near_misses=[]
        with h5py.File(nwb,"r") as f:
            for s in sorted(f["acquisition"]):
                if not s.startswith("ic__"):continue
                stim=s.replace("ic__","ics__",1)
                if stim not in f["stimulus/presentation"]:raise ValueError("Missing matched stimulus series "+s)
                v=f["acquisition"][s];i=f["stimulus/presentation"][stim]
                rate=float(v["starting_time"].attrs["rate"])
                if rate<1000 or float(i["starting_time"].attrs["rate"])!=rate:
                    raise ValueError("APWaveform stimulus sampling mismatch")
                if len(v["data"])!=len(i["data"]):raise ValueError("Stimulus data samples differ")
                vm=series_values(v,1000.0);ci=series_values(i,1e12)
                # Physically plausible numbers, not a pass/fail biological interpretation
                if not (-180<float(np.median(vm))<90):raise ValueError("Suspicious membrane voltage calibration")
                if len(vm)/rate < 0.35:
                    print("Skipping short protocol",s,flush=True)
                    continue
                r=screen(vm,ci,rate);r["voltage_series"]=s;r["current_series"]=stim
                records.append(r)
                print(s,r["classification"],"nspikes",r["spike_count"],"baseline delta",r["baseline_change_mV"],flush=True)
                if r["classification"].startswith("screen_candidate"):
                    candidates.append((r,s,stim,vm,ci,rate))
                elif r["spike_count"]==1 and abs(r["baseline_change_mV"])<=8 and r["post_sd_mV"]<=3.0 and r["pre_sd_mV"]<=3.0:
                    near_misses.append((r,s,stim,vm,ci,rate))
        candidates.sort(key=lambda x:abs(x[0]["baseline_change_mV"])+x[0]["post_sd_mV"])
        near_misses.sort(key=lambda x:abs(x[0]["baseline_change_mV"])+x[0]["post_sd_mV"])
        report=dict(source="DANDI 000025 (DRAFT)",asset_id=ID,original_file_sha256=SHA,
              rights="CC-BY-4.0 as declared by DANDI; draft dataset can change",
              count=len(records),candidate_count=len(candidates),near_miss_count=len(near_misses),records=records,
              interpretation="Automated screening only. No isolated spike certified until expert review.",
              method="threshold crossing plus strict late-pre rest and injected-current checks")
        (O/"DANDI000025_ALL_protocols_screen.json").write_text(json.dumps(report,indent=2)+"\n")
        if candidates or near_misses:
            r,name,stim,vm,ci,rate=(candidates or near_misses)[0]
            k=int(r["spike_crossings_ms"][0]*rate/1000)
            start=max(0,k-int(.1*rate));end=min(len(vm),k+int(.2*rate))
            fpath=O/"DANDI000025_review_only_best_single_spike.csv"
            with fpath.open("w",newline="") as out:
                wr=csv.writer(out,lineterminator="\n")
                wr.writerow(["time_ms","Vm_mV","injected_current_pA"])
                for idx in range(start,end):
                    wr.writerow([f"{idx*1000/rate:.5f}",f"{vm[idx]:.6f}",f"{ci[idx]:.6f}"])
            checksum=hashlib.sha256(fpath.read_bytes()).hexdigest()
            (O/"DANDI000025_review_only_best_manifest.json").write_text(json.dumps(dict(
                 status="NEAR_MISS_OR_CANDIDATE_NOT_EXPERT_ACCEPTED",measured_baseline_change_mV=r["baseline_change_mV"],recorded_from=name,stimulus=stim,
                 original_nwb_sha256=SHA,derived_sha256=checksum,
                 sampling_rate_hz=rate, units=["ms","mV","pA"],source_asset_id=ID,
                 excerpt_start_ms=round(start*1000/rate,5),excerpt_end_ms=round((end-1)*1000/rate,5),
                 source_notes="Unsmoothed raw sample values converted from NWB SI units; reviewer must approve before teaching."),indent=2)+"\n")
            print("CANDIDATE CSV written",str(fpath),flush=True)
        else:print("No single spikes fit even near-miss criteria; do not publish a substitute",flush=True)
if __name__=="__main__":main()
