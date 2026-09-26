"""V3: retain V2 insertion candidates, add opposed dowel-hole mouths.

No code/reference coordinates are used. A hole pair is a candidate connection,
not proof of a wooden joint, a present dowel, or tolerance compliance.
"""
import argparse, hashlib, itertools, json, sys, time, importlib.util
from pathlib import Path
import cadquery as cq
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'v2'))
spec=importlib.util.spec_from_file_location('muse_v2_base',HERE.parent/'v2/detector.py')
base=importlib.util.module_from_spec(spec);sys.modules[spec.name]=base;spec.loader.exec_module(base)

RULES=dict(max_mouth_gap_mm=3.0,max_axis_offset_mm=0.5,
           max_offset_radius_fraction=0.25,min_full_arc_deg=355,
           radius_difference_floor_mm=0.1,radius_difference_fraction=0.1,
           min_hole_depth_mm=0.5,parallel_axis_angle_deg=0.0001)

def hole_mouths(faces,infos,features):
    mouths=[]
    for h in features:
        if h['side']!='inner' or np.sum(h['mask'])<RULES['min_full_arc_deg']:continue
        if h['hi']-h['lo']<RULES['min_hole_depth_mm']:continue
        sid=h['sid'];edges=[e for fid in h['ids'] for e in faces[sid][fid].Edges()]
        for end,sign in [(h['lo'],-1),(h['hi'],1)]:
            point=h['origin']+end*h['axis'];normal=sign*h['axis']
            for fid,info in enumerate(infos[sid]):
                if info['surface_type']!='PLANE':continue
                # A blind bottom faces INTO the hole, not out of its axial interval.
                if np.dot(info['normal'],normal)<1-1e-8:continue
                if abs(np.dot(np.array(info['center_mm'])-point,normal))>1e-5:continue
                if not any(e.isSame(p) for e in edges for p in faces[sid][fid].Edges()):continue
                mouths.append(dict(sid=sid,hole_ids=h['ids'],mouth_face=fid,
                    point=point,normal=normal,radius=h['radius'],depth=h['hi']-h['lo']))
    return mouths

def pair_holes(mouths,planar_pairs,solids,existing):
    contacts={frozenset(((p['solid_a'],p['face_a']),(p['solid_b'],p['face_b']))) for p in planar_pairs}
    out=[];seen=set();suppressed=0
    for a,b in itertools.combinations(mouths,2):
        if a['sid']==b['sid'] or np.dot(a['normal'],b['normal'])>-1+1e-10:continue
        if frozenset(((a['sid'],a['mouth_face']),(b['sid'],b['mouth_face']))) not in contacts:continue
        delta=b['point']-a['point'];gap=float(delta@a['normal'])
        if gap < -1e-5 or gap>RULES['max_mouth_gap_mm']:continue
        offset=float(np.linalg.norm(delta-gap*a['normal']))
        if offset>min(RULES['max_axis_offset_mm'],RULES['max_offset_radius_fraction']*min(a['radius'],b['radius'])):continue
        if abs(a['radius']-b['radius'])>max(RULES['radius_difference_floor_mm'],RULES['radius_difference_fraction']*min(a['radius'],b['radius'])):continue
        key=tuple(sorted(((a['sid'],tuple(a['hole_ids'])),(b['sid'],tuple(b['hole_ids'])))))
        if key in seen:continue
        seen.add(key)
        # If an explicit shaft already mates with either hole, keep V2 evidence
        # but do not add a second implicit-connector count for that same aperture.
        if any(g['type']=='cylindrical_insertion_candidate' and any(
            g['receiver_solid_id']==h['sid'] and set(g['receiver_face_ids'])&set(h['hole_ids']) for h in (a,b)) for g in existing):
            suppressed+=1;continue
        midpoint=(a['point']+b['point'])/2
        if gap>1e-5 and any(s.isInside(tuple(midpoint),1e-6) for sid,s in enumerate(solids) if sid not in (a['sid'],b['sid'])):continue
        out.append(dict(type='opposed_dowel_hole_candidate',part_a=a['sid'],part_b=b['sid'],
            hole_faces_a=a['hole_ids'],hole_faces_b=b['hole_ids'],mouth_face_a=a['mouth_face'],mouth_face_b=b['mouth_face'],
            mouth_a_mm=a['point'].tolist(),mouth_b_mm=b['point'].tolist(),center_mm=midpoint.tolist(),
            mouth_gap_mm=gap,axis_offset_mm=offset,diameter_a_mm=2*a['radius'],diameter_b_mm=2*b['radius'],
            diameter_difference_mm=2*(b['radius']-a['radius']),hole_depth_a_mm=a['depth'],hole_depth_b_mm=b['depth'],
            connector_status='not_established',semantic_status='possible_dowel_or_other_aligned_fastener_holes',
            compliance='not_evaluated',count_unit='one_opposed_hole_pair_not_one_entire_board_connection'))
    return out,suppressed

def detect_step(path):
    start=time.perf_counter();d=base.detect_step(path)
    solids=cq.importers.importStep(str(path)).solids().vals()
    faces=[s.Faces() for s in solids]
    infos=[[base.face_info(f,i,j) for j,f in enumerate(fs)] for i,fs in enumerate(faces)]
    mouths=hole_mouths(faces,infos,base.cylinder_features(faces,infos))
    extra,suppressed=pair_holes(mouths,d['planar_pairs'],solids,d['interfaces'])
    d.update(version='v3',base_detector_sha256=d['detector_sha256'],
        detector_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        shared_geometry_sha256=hashlib.sha256((HERE.parent/'detect_interfaces.py').read_bytes()).hexdigest(),
        dowel_hole_count=len(extra),hole_mouth_count=len(mouths),suppressed_explicit_shaft_pairs=suppressed,
        hole_pair_rules=RULES,v2_candidate_count=d['candidate_count'])
    d['interfaces']+=extra;d['candidate_count']=len(d['interfaces'])
    for i,g in enumerate(d['interfaces']):g['interface_id']=i
    d['elapsed_seconds']=time.perf_counter()-start
    d['limitations']+=['Opposed holes may be screw/bolt holes, not necessarily wooden dowels.',
        'One opposed hole pair is one candidate; multiple holes at a board joint count separately.',
        'Only full cylindrical holes with planar mouths and parallel axes are supported.',
        'Hole diameters do not provide dowel clearance without an actual dowel diameter.']
    return d

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('step');ap.add_argument('--output',required=True);a=ap.parse_args()
    d=detect_step(a.step);out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf8')
    print({k:d[k] for k in ('status','candidate_count','dowel_hole_count')})
