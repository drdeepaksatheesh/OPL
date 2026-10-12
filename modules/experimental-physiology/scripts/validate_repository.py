"""Validate source catalogue and experiment references (stdlib only)."""
from pathlib import Path
import json
import sys
ROOT = Path(__file__).resolve().parents[1]


def validate(root=ROOT):
    errors=[]
    obj=json.loads((root/'data/sources.json').read_text())
    sources=obj.get('sources', [])
    known=set()
    for s in sources:
        sid=s.get('id','')
        if not sid or sid in known: errors.append('missing or duplicate ID '+sid)
        known.add(sid)
        for field in ('title','species','preparation','experiment_id','signal_class','access_status','licence','reuse_review','source_url','attribution','caveats'):
            if not str(s.get(field,'')).strip(): errors.append(f'{sid}: missing {field}')
        if s.get('signal_class') not in {'RAW','SCAN','FIGURE','SYNTHETIC','LEAD'}:
            errors.append(sid+': invalid evidence class')
        if s.get('record_in_repository') is not False:
            errors.append(sid+': claims bundled external data unexpectedly')
        if not str(s.get('source_url','')).startswith('https://'):
            errors.append(sid+': source_url must be https')
    ids=set()
    for path in (root/'experiments').glob('*.json'):
        ex=json.loads(path.read_text())
        eid=ex.get('id')
        if not eid or eid in ids: errors.append('duplicate/invalid experiment ID')
        ids.add(eid)
        if path.stem!=eid: errors.append(f'{path.name}: must match experiment id')
        for sid in ex.get('source_ids',[]):
            if sid not in known: errors.append(f'{eid}: source not in catalogue: {sid}')
        for f in ('goals','tasks','metadata_required','interpretation_warning','state'):
            if not ex.get(f): errors.append(f'{eid}: missing {f}')
    for s in sources:
        if s['experiment_id'] not in ids: errors.append(s['id']+': missing experiment file')
    demo=root/'examples/demo_SYNTHETIC_muscle_twitch.manifest.json'
    demo_data=json.loads(demo.read_text())
    if demo_data.get('data_class')!='SYNTHETIC':
        errors.append('Demo metadata must mark synthetic waveform')
    import hashlib
    actual=hashlib.sha256((root/'examples/demo_SYNTHETIC_muscle_twitch.csv').read_bytes()).hexdigest()
    if demo_data.get('derived_sha256')!=actual:
        errors.append('Synthetic demo checksum mismatch')
    return errors


if __name__=='__main__':
    errors=validate()
    print('\n'.join(errors) if errors else 'OK: sources, references, manifests and lesson metadata are consistent')
    sys.exit(1 if errors else 0)
