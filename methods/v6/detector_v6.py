"""V6 wood assembly classifier. Reuse V4 evidence and inspect STEP geometry.
--from-evidence INPUT --step MODEL avoids rerunning V4 detection.
Without --step, structural/blind-end/penetration checks remain unresolved.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from connection_policy_v6 import apply_policy


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--from-evidence',type=Path)
    p.add_argument('--step',type=Path)
    p.add_argument('--v4-detector',type=Path,default=Path(__file__).resolve().parent.parent/'v4'/'detector.py')
    p.add_argument('--geometry-cache',type=Path)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if not args.from_evidence and not args.step:p.error('Provide --from-evidence and/or --step')
    v4=None
    def load_v4():
        spec=importlib.util.spec_from_file_location('geometry_v4',args.v4_detector)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
    if args.from_evidence:
        raw=json.loads(args.from_evidence.read_text(encoding='utf-8-sig'))
    else:
        v4=load_v4();raw=v4.detect(args.step)
    audit={}
    if args.step:
        import cadquery as cq
        from connection_geometry_v6 import analyze
        step_sha=hashlib.sha256(args.step.read_bytes()).hexdigest()
        if raw.get('input_sha256')!=step_sha:raise ValueError('STEP hash differs from evidence; candidate face IDs cannot be reused')
        extractor_sha=hashlib.sha256(Path(__file__).with_name('connection_geometry_v6.py').read_bytes()).hexdigest()
        evidence_sha=hashlib.sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest()
        if args.geometry_cache and args.geometry_cache.exists():
            cached=json.loads(args.geometry_cache.read_text())
            if (cached.get('input_sha256'),cached.get('extractor_sha256'),cached.get('evidence_sha256'))!=(step_sha,extractor_sha,evidence_sha):
                raise ValueError('Geometry cache provenance differs')
            audit=cached['audit']
        else:
            if v4 is None:v4=load_v4()
            solids=cq.importers.importStep(str(args.step)).solids().vals()
            if len(solids)!=len(raw['solids']):raise ValueError('Solid count differs from original evidence')
            audit=analyze(solids,raw,v4.v3.base)
            if args.geometry_cache:
                args.geometry_cache.parent.mkdir(parents=True,exist_ok=True)
                args.geometry_cache.write_text(json.dumps(dict(input_sha256=step_sha,extractor_sha256=extractor_sha,evidence_sha256=evidence_sha,audit=audit)),encoding='utf-8')
        audit['input_sha256']=step_sha
        audit['extractor_sha256']=extractor_sha
        audit['evidence_sha256']=evidence_sha
    out=apply_policy(raw,audit)
    out['policy_sha256']=hashlib.sha256(Path(__file__).with_name('connection_policy_v6.py').read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(file=str(args.output),pairs=out['semantic_pair_counts']),ensure_ascii=False))

if __name__=='__main__':main()
