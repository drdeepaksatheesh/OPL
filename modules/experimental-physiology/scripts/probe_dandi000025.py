#!/usr/bin/env python3
"""Exploratory probe of original rat intracellular NWB file, DANDI 000025.
Only reports measured metadata and flags candidates; no authorizes teaching promotion.
"""
import hashlib,json,tempfile,urllib.request
from pathlib import Path
import h5py,numpy as np
API="https://api.dandiarchive.org/api/dandisets/000025/versions/draft/assets/"
def get_json(url):
    with urllib.request.urlopen(url,timeout=60) as r:return json.load(r)
def strval(v):
    return v.decode(errors="replace") if isinstance(v,bytes) else str(v)
def series_info(label,name,g):
    data=g.get("data")
    if data is None:return None
    if len(data.shape)!=1:return None
    unit=strval(g.attrs.get("unit",data.attrs.get("unit","unknown")))
    conversion=float(np.asarray(g.get("conversion",data.attrs.get("conversion",1))).reshape(-1)[0])
    offset=float(np.asarray(g.get("offset",0)).reshape(-1)[0])
    n=len(data)
    if n<100 or n>10000000:return None
    st=g.get("starting_time")
    rate=float(st.attrs.get("rate",0)) if st is not None else 0
    t0=float(st[()]) if st is not None else None
    sweep=g.get("sweep_number")
    sweep=int(sweep[()]) if sweep is not None else None
    if sweep is None:sweep=int(g.attrs.get("sweep_number",-1))
    return dict(location=label,path=g.name,series_type=strval(g.attrs.get("neurodata_type","")),
                name=name,unit=unit,conversion=conversion,offset=offset,n=n,rate=rate,t0=t0,sweep=sweep)
def main():
    res=get_json(API)
    assets=res.get("results",[])
    if len(assets)!=1:raise ValueError("Expected one source asset in Dandiset 000025")
    asset=assets[0];meta=asset.get("metadata",{});asset_id=asset["asset_id"] if "asset_id" in asset else asset["identifier"]
    size=asset.get("size",0)
    if not (1000000<size<100000000):raise ValueError("Unexpected asset size")
    url="https://api.dandiarchive.org/api/assets/"+asset_id+"/download/"
    with tempfile.TemporaryDirectory() as td:
        target=Path(td)/"verified-download.nwb"
        dig=hashlib.sha256()
        with urllib.request.urlopen(url,timeout=120) as r,target.open("wb") as f:
            while True:
                chunk=r.read(1048576)
                if not chunk:break
                f.write(chunk);dig.update(chunk)
        if target.stat().st_size!=size:raise ValueError("Asset size mismatch")
        details=[]
        with h5py.File(target,"r") as h:
            def callback(n,obj):
                if isinstance(obj,h5py.Group) and "data" in obj:
                    if "/acquisition/" in "/"+n or "/stimulus/" in "/"+n:
                        out=series_info("acquisition" if n.startswith("acquisition/") else "stimulus",n.split("/")[-1],obj)
                        if out and len(details)<800:details.append(out)
            h.visititems(callback)
            report=dict(dandiset="000025",status="DRAFT / EXPLORATORY; asset may change",
                asset_id=asset_id,asset_path=asset.get("path"),asset_size_bytes=size,
                retrieved_sha256=dig.hexdigest(),source_digest=meta.get("digest"),
                licence="CC-BY-4.0 reported by DANDI",groups=len(details),
                series=details,notes=["Raw NWB asset bytes were downloaded from official DANDI API.",
                "Full sweeps are not released in this report; numeric characterization and same-sweep current pairing still required.",
                "A draft dataset is not an immutable published version; pin asset ID and local hash before using."])
        out=Path("modules/experimental-physiology/research/DANDI000025_provenance_probe.json")
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(report,indent=2,default=str)+"\n")
        print("NWB verified bytes SHA256",dig.hexdigest(),"series",len(details))
        print("current-clamp voltage groups",len([x for x in details if "CurrentClampSeries" in x["series_type"]]))
if __name__=="__main__":main()
