"""Portable orchestration of the released STEP-based evaluation algorithms."""
import importlib.util
import itertools
import json
import math
import os
from pathlib import Path
import sys
from .matching import map_parts
from .graph_metrics import counts, ged
from .clearance import measure_rect

ROOT = Path(__file__).resolve().parents[2]
TYPES = ('Interlocking', 'Snap-fit', 'Nailing', 'Bonding')

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module); return module

def detector():
    return load_module('review_v4', ROOT/'methods/v4/detector.py')

def extract(step, policy='v6'):
    import cadquery as cq
    d = detector(); geometry = d.v3.detect_step(Path(step))
    solids = cq.importers.importStep(str(step)).solids().vals()
    raw = d.infer(geometry, solids)
    raw['status'] = geometry['status']
    if policy == 'v6':
        sys.path.insert(0, str(ROOT/'methods/v6'))
        from connection_geometry_v6 import analyze
        from connection_policy_v6 import apply_policy
        raw = apply_policy(raw, analyze(solids, raw, d.v3.base))
    measurements = []
    for i, candidate in enumerate(geometry.get('interfaces', [])):
        if candidate['type'] != 'rectangular_insertion_candidate': continue
        try:
            item = measure_rect(candidate, geometry['planar_pairs'], solids)
            item['candidate_id'] = i; measurements.append(item)
        except Exception as exc:
            measurements.append({'candidate_id':i,'status':'measurement_failed','reason':type(exc).__name__})
    return {'detection':raw,'measurements':measurements,'status':geometry['status']}

def candidates(raw):
    if 'semantic_edges' not in raw:
        return [dict(solid_a=c['solid_a'],solid_b=c['solid_b'],type={'Mortise & Tenon':'Interlocking','Dowel Joint':'Interlocking'}.get(c['type'],c['type'])) for c in raw['candidates']]
    structural = {tuple(sorted((c['solid_a'], c['solid_b']))) for c in raw['candidates'] if c['type'] != 'Bonding'}
    return [dict(solid_a=e['a'],solid_b=e['b'],type=t) for e in raw['semantic_edges']
            if e['types'] or tuple(sorted((e['a'],e['b']))) in structural for t in (e['types'] or ['Unknown'])]

def graph_scores(raw, reference):
    if not reference.get('available'):
        return {'status':'reference_unavailable','mappings':[]}
    from .reference_scores import graph_comparison
    mappings=map_parts(raw['solids'],reference['nodes'])
    result=graph_comparison(raw['solids'],mappings,reference['nodes'],candidates(raw),reference['source_graph'])
    result['mappings']=mappings
    result['node']=prf(result['node'])
    result['edge']=prf(result['edge_counts']) if result.get('edge_counts') else None
    classes=[prf(c) for c in result.get('type_classes',{}).values() if 2*c['tp']+c['fp']+c['fn']>0]
    result['type']={k:sum(c[k] for c in classes)/len(classes) for k in ('precision','recall','f1')} if classes else None
    if result['type'] is not None:result['type']['defined']=True
    result['ged']={'value':result['ged'],'status':result['ged_status'],'upper_bound':result['ged_upper_bound']}
    return result

def prf(c):
    tp,fp,fn=c['tp'],c['fp'],c['fn'];den=2*tp+fp+fn
    return dict(tp=tp,fp=fp,fn=fn,precision=tp/(tp+fp) if tp+fp else 0.0,
                recall=tp/(tp+fn) if tp+fn else 0.0,f1=2*tp/den if den else 0.0,defined=bool(den))

def geometry_check(step):
    import cadquery as cq
    from dataclasses import asdict
    sys.path.insert(0,str(ROOT/'vendor'))
    from validator import CadQueryValidator
    solids = cq.importers.importStep(str(step)).solids().vals()
    v=CadQueryValidator();issues=[]
    for s in solids:issues.extend(v._check_watertightness(s));issues.extend(v._check_self_intersection(s))
    # Preserve legacy OCCT validity proxy; failures of a check remain unavailable.
    def passed(k):
        relevant=[i for i in issues if i.issue_type in k]
        return not any(i.severity=='error' for i in relevant)
    unavailable=any(i.issue_type in ['WatertightnessCheck','SelfIntersectionCheck'] for i in issues)
    overlap=0.0
    for a,b in itertools.combinations(solids,2):
        aa,bb=a.BoundingBox(),b.BoundingBox()
        if any(getattr(aa,k+'max')<=getattr(bb,k+'min') or getattr(bb,k+'max')<=getattr(aa,k+'min') for k in 'xyz'):continue
        overlap+=sum(abs(s.Volume()) for s in a.intersect(b).Solids())
    checks=dict(watertight=passed(['Watertightness']),manifold=passed(['NonManifoldEdge']),
                self_intersection_free=passed(['SelfIntersection']),overlap_free=overlap<=1e-6)
    if any(i.issue_type=='WatertightnessCheck' for i in issues):
        checks['watertight']=None;checks['manifold']=None
    if any(i.issue_type=='SelfIntersectionCheck' for i in issues):checks['self_intersection_free']=None
    return dict(**checks,valid=bool(solids) and all(x is True for x in checks.values()),solid_count=len(solids),
                intersection_volume_mm3=overlap,issues=[asdict(i) for i in issues])

def render(step, output):
    sys.path.insert(0,str(ROOT/'vendor/drawcad'))
    from cad_to_svg import CadQueryToSVG
    converter=CadQueryToSVG(name='CAD evaluation',paper_size='A3')
    converter.load_model_from_step(str(step));converter.render(str(output))
