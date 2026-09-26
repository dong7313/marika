"""Connection hypotheses and solid-pair graph. Geometry only; no label-conditioned counts."""
import argparse,hashlib,importlib.util,json,sys
from pathlib import Path
import cadquery as cq
import numpy as np
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('v3_geometry',HERE.parent/'v3/detector.py')
v3=importlib.util.module_from_spec(spec);sys.modules[spec.name]=v3;spec.loader.exec_module(v3)
TYPES=['Bonding','Snap-fit','Nailing','Dowel Joint','Mortise & Tenon']
RULES=dict(bonding_gap_mm=.3,bonding_angle_deg=.1,bonding_area_mm2=25,bonding_overlap_ratio=.1,
           headed_pin_radius_ratio=1.5,head_to_shaft_axial_distance_mm=1,snap_cross_axis_dot_max=.1)
def infer(d,solids):
    fs=[s.Faces() for s in solids];infos=[[v3.base.face_info(f,i,j) for j,f in enumerate(faces)] for i,faces in enumerate(fs)]
    cyl=v3.base.cylinder_features(fs,infos);out=[]
    def add(kind,a,b,evidence,unit,alternatives=None):
        out.append(dict(id=len(out),type=kind,solid_a=a,solid_b=b,evidence=evidence,count_unit=unit,
            confidence='geometry_hypothesis',alternative_explanations=alternatives or [],compliance='not_evaluated'))
    # One connected solid pair may have several patches; count one planar glue-region
    # hypothesis per solid pair, preserving every screened patch as evidence.
    bonds={}
    for p in d['planar_pairs']:
        if -1e-5<=p['nominal_gap_mm']<=RULES['bonding_gap_mm'] and p['angular_deviation_deg']<=RULES['bonding_angle_deg'] and p['aligned_overlap_area_mm2']>=RULES['bonding_area_mm2'] and p['overlap_ratio']>=RULES['bonding_overlap_ratio']:
            bonds.setdefault((p['solid_a'],p['solid_b']),[]).append(p)
    for (a,b),patches in bonds.items():add('Bonding',a,b,dict(planar_patches=patches),'one_solid_pair_with_planar_contact',['ordinary_contact','other_connection_surface'])
    rect=[g for g in d['interfaces'] if g['type']=='rectangular_insertion_candidate']
    for g in rect:add('Mortise & Tenon',g['male_solid_id'],g['receiver_solid_id'],g,'one_local_insertion',['ordinary_tab_slot','nonwood_joint'])
    for g in d['interfaces']:
        if g['type']=='opposed_dowel_hole_candidate':
            add('Dowel Joint',g['part_a'],g['part_b'],g,'one_opposed_hole_pair',['screw_or_bolt_holes','alignment_holes']);continue
        if g['type']!='cylindrical_insertion_candidate':continue
        male=g['male_solid_id'];feature=next((h for h in cyl if h['sid']==male and set(h['ids'])&set(g['male_face_ids'])),None)
        heads=[]
        if feature:
            for h in cyl:
                if h['sid']!=male or h['side']!='outer' or h['radius']<feature['radius']*RULES['headed_pin_radius_ratio']:continue
                if abs(h['axis']@feature['axis'])<1-1e-10 or np.linalg.norm(h['origin']-feature['origin'])>1e-4:continue
                distance=max(h['lo']-feature['hi'],feature['lo']-h['hi'],0)
                if distance<=RULES['head_to_shaft_axial_distance_mm']:heads.append(h['ids'])
        evidence=dict(interface=g,head_cylinder_faces=heads)
        add('Nailing' if heads else 'Dowel Joint',male,g['receiver_solid_id'],evidence,'one_pin_hole_interface',
            ['bolt','headed_dowel','integral_boss'] if heads else ['shaft_bearing','smooth_pin','unheaded_nail'])
    # Restricted snap-like subtype: rectangular insertion plus transverse curved
    # retention pair. Parallel corner fillets alone are explicitly not enough.
    curves=[g for g in d['interfaces'] if g['type']=='cylindrical_insertion_candidate']+d.get('associated_corner_arcs',[])
    for r in rect:
        retained=[]
        for g in curves:
            if (g['male_solid_id'],g['receiver_solid_id'])!=(r['male_solid_id'],r['receiver_solid_id']):continue
            a=infos[g['male_solid_id']][g['male_face_ids'][0]]
            if abs(np.dot(a['axis'],r['local_axes'][2]))>RULES['snap_cross_axis_dot_max']:continue
            q=np.array(r['local_axes'])@(np.array(g['center_mm'])-r['center_mm'])
            if abs(q[0])<=r['section_dimensions_mm'][0]/2+3 and abs(q[1])<=r['section_dimensions_mm'][1]/2+3 and abs(q[2])<=r['axial_wall_overlap_mm']/2+3:retained.append(g)
        if retained:add('Snap-fit',r['male_solid_id'],r['receiver_solid_id'],dict(insertion=r,transverse_curved_pairs=retained),'one_insertion_with_transverse_retention_candidates',['alignment_bump','nonelastic_latch','unverified_undercut'])
    metadata=[]
    for i,s in enumerate(solids):
        b=s.BoundingBox();metadata.append(dict(id=i,center_mm=list(s.Center().toTuple()),bbox_mm=[[b.xmin,b.ymin,b.zmin],[b.xmax,b.ymax,b.zmax]],volume_mm3=s.Volume(),faces=len(fs[i]),name=None))
    pairgraph={}
    for g in out:pairgraph.setdefault(tuple(sorted((g['solid_a'],g['solid_b']))),[]).append(g['id'])
    counts={t:sum(g['type']==t for g in out) for t in TYPES}
    return dict(types=counts,candidates=out,solids=metadata,solid_edges=[dict(a=a,b=b,candidate_ids=ids) for (a,b),ids in pairgraph.items()],
        distinct_connected_solid_pairs=len(pairgraph),counts_additive=False,
        limitations=['Types are hypotheses, not semantic classifications.','Bonding does not prove adhesive.','Nailing is a headed-pin heuristic, not nail verification.',
        'Snap-fit covers only insertion plus transverse curved pairs; does not prove undercut, elasticity or locking.',
        'One physical interface may have multiple candidate types; do not sum type counts.',
        'Solid names are not inferred from reference order. Human component mapping required.'])
def detect(path,cache=None):
    p=Path(path);digest=hashlib.sha256(p.read_bytes()).hexdigest()
    if cache:
        d=json.loads(Path(cache).read_text(encoding='utf8'))
        if d['input_sha256']!=digest:raise ValueError('STEP differs from frozen V3 geometry')
        if d['detector_sha256']!=hashlib.sha256((HERE.parent/'v3/detector.py').read_bytes()).hexdigest():raise ValueError('V3 detector changed')
    else:d=v3.detect_step(p)
    solids=cq.importers.importStep(str(p)).solids().vals();result=infer(d,solids)
    result.update(version='v4',step=str(p.resolve()),input_sha256=digest,status=d['status'],rules=RULES,
        detector_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        geometry_source='verified_v3_cache' if cache else 'fresh_v3_geometry',source_cache=str(cache) if cache else None,
        source_cache_sha256=hashlib.sha256(Path(cache).read_bytes()).hexdigest() if cache else None)
    if result['status'] not in ('completed','partial'):result['types']={t:None for t in TYPES}
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('step');p.add_argument('--cache');p.add_argument('--output',required=True);p.add_argument('--task-md');p.add_argument('--graph-md');a=p.parse_args()
    d=detect(a.step,a.cache)
    from graph import parse,document,section
    if a.task_md:
        src=document(a.task_md);d['task_source']=src['path'];d['required_connection_field']=section(src['text'],r'^Connection Methods?')
    if a.graph_md or a.task_md:
        src=document(a.graph_md or a.task_md);d['expected_graph']=parse(src['text']);d['graph_source']=src['path']
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf8')
