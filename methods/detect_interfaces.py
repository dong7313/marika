"""STEP-only candidate detection; no generated/reference code or labels at inference."""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
import math
import time
from dataclasses import dataclass, asdict
from pathlib import Path
import cadquery as cq
import numpy as np
from OCP.BRepAdaptor import BRepAdaptor_Surface

@dataclass
class Config:
    max_gap_mm: float = 0.5
    min_area_mm2: float = 0.5
    min_overlap_ratio: float = 0.1
    parallel_angle_deg: float = 0.0001
    max_axis_offset_mm: float = 0.05
    min_axial_overlap_mm: float = 0.5
    numeric_eps_mm: float = 1e-6

def vec(v):
    return np.array(v.toTuple() if hasattr(v, 'toTuple') else (v.X(), v.Y(), v.Z()), dtype=float)

def bbox(s):
    b = s.BoundingBox()
    return np.array([b.xmin,b.ymin,b.zmin]), np.array([b.xmax,b.ymax,b.zmax])

def bbox_distance(a,b):
    return float(np.linalg.norm(np.maximum(0, np.maximum(a[0]-b[1], b[0]-a[1]))))

def face_info(f, sid, fid):
    d = {'solid_id': sid, 'face_id': fid, 'surface_type':f.geomType(),
         'area_mm2':f.Area(), 'center_mm':vec(f.Center()).tolist(),
         'bbox_mm':[x.tolist() for x in bbox(f)]}
    if f.geomType() == 'PLANE':
        d['normal'] = vec(f.normalAt()).tolist()
    if f.geomType() == 'CYLINDER':
        a = BRepAdaptor_Surface(f.wrapped)
        cy = a.Cylinder()
        axis, origin = vec(cy.Axis().Direction()), vec(cy.Location())
        u=(a.FirstUParameter()+a.LastUParameter())/2
        v=(a.FirstVParameter()+a.LastVParameter())/2
        point=vec(a.Value(u,v)); r=point-origin-axis*np.dot(point-origin,axis)
        sign=float(np.dot(vec(f.normalAt(cq.Vector(*point))),r))
        d.update(radius_mm=cy.Radius(), axis=axis.tolist(), axis_origin_mm=origin.tolist(),
                 material_side='outer' if sign>0 else 'inner',
                 full_cylinder=abs(a.LastUParameter()-a.FirstUParameter()-2*math.pi)<1e-5)
    return d

def planar_pair(f,g,a,b,c):
    na,nb=np.array(a['normal']),np.array(b['normal'])
    dot=float(np.clip(np.dot(na,nb),-1,1))
    angle=math.degrees(math.acos(dot))
    if 180-angle>c.parallel_angle_deg: return None
    gap=float(np.dot(np.array(b['center_mm'])-a['center_mm'],na))
    if gap < -c.numeric_eps_mm or gap > c.max_gap_mm+c.numeric_eps_mm: return None
    # Translate the opposing plane onto the first; Boolean common respects trimmed
    # wires/holes, unlike bounding-box area. Only essentially parallel planes accepted.
    aligned=g.translate(tuple(-gap*na))
    overlap=f.intersect(aligned).Area()
    ratio=overlap/min(a['area_mm2'],b['area_mm2'])
    if overlap<c.min_area_mm2 or ratio<c.min_overlap_ratio: return None
    return dict(type='planar_mating_candidate', nominal_gap_mm=gap,
                normal_angle_deg=angle, overlap_area_mm2=overlap, overlap_ratio=ratio,
                face_distance_mm=f.distance(g), normal_a=na.tolist())

def cylindrical_pair(f,g,a,b,c):
    if a['material_side']==b['material_side']: return None
    # Partial cylinders require angular overlap treatment; do not score them as full fits.
    if not a['full_cylinder'] or not b['full_cylinder']: return None
    axis=np.array(a['axis']); other=np.array(b['axis'])
    angle=math.degrees(math.acos(float(np.clip(abs(np.dot(axis,other)),0,1))))
    if angle>c.parallel_angle_deg: return None
    delta=np.array(b['axis_origin_mm'])-a['axis_origin_mm']
    offset=float(np.linalg.norm(delta-axis*np.dot(delta,axis)))
    if offset>c.max_axis_offset_mm: return None
    hole,shaft=(a,b) if a['material_side']=='inner' else (b,a)
    radial=hole['radius_mm']-shaft['radius_mm']
    if abs(radial)>c.max_gap_mm: return None
    # Axial extents of trimmed cylinder from vertices (full cylindrical end rings).
    def interval(face):
        ts=[float(np.dot(vec(v.Center()),axis)) for v in face.Vertices()]
        return min(ts),max(ts)
    ia,ib=interval(f),interval(g)
    length=min(ia[1],ib[1])-max(ia[0],ib[0])
    if length<c.min_axial_overlap_mm: return None
    return dict(type='cylindrical_fit_candidate',hole_solid_id=hole['solid_id'],
                hole_face_id=hole['face_id'],shaft_solid_id=shaft['solid_id'],
                shaft_face_id=shaft['face_id'],hole_diameter_mm=2*hole['radius_mm'],
                shaft_diameter_mm=2*shaft['radius_mm'],diametral_clearance_mm=2*radial,
                radial_clearance_mm=radial,axis_offset_mm=offset,angular_offset_deg=angle,
                axial_overlap_mm=length,minimum_radial_separation_mm=radial-offset,
                maximum_radial_separation_mm=radial+offset,
                nominal_relation='interference' if radial-offset < -c.numeric_eps_mm else
                    ('nominal_contact' if abs(radial)<c.numeric_eps_mm else 'clearance'))

def rectangular_groups(pairs,faces):
    """Connected groups with four opposing orthogonal side normals; still hypotheses."""
    groups=[]
    for sid in range(len(faces)):
        peers=sorted({p['solid_b'] if p['solid_a']==sid else p['solid_a'] for p in pairs
                      if p['type']=='planar_mating_candidate' and sid in (p['solid_a'],p['solid_b'])})
        for peer in peers:
            ps=[p for p in pairs if p['type']=='planar_mating_candidate' and
                {p['solid_a'],p['solid_b']}=={sid,peer}]
            ids=sorted({p['face_a'] if p['solid_a']==sid else p['face_b'] for p in ps})
            # Connect selected faces by shared B-Rep edges, not by guessed ROI/coordinates.
            edges={i:faces[sid][i].Edges() for i in ids}
            links={i:set() for i in ids}
            for i,j in itertools.combinations(ids,2):
                if any(e.isSame(h) for e in edges[i] for h in edges[j]):
                    links[i].add(j);links[j].add(i)
            seen=set()
            for i in ids:
                if i in seen:continue
                comp=set();stack=[i]
                while stack:
                    x=stack.pop()
                    if x in comp:continue
                    comp.add(x);stack.extend(links[x]-comp)
                seen.update(comp)
                ns={x:vec(faces[sid][x].normalAt()) for x in comp}
                opposite=[(x,y) for x,y in itertools.combinations(comp,2) if np.dot(ns[x],ns[y]) < -0.999999]
                if not any(abs(np.dot(ns[x[0]],ns[y[0]]))<1e-6 for x,y in itertools.combinations(opposite,2)):
                    continue
                # Male side normals must point away from its selected-face centroid.
                side_ids={x for pair in opposite for x in pair}
                center=np.mean([vec(faces[sid][x].Center()) for x in side_ids],axis=0)
                if not all(np.dot(vec(faces[sid][x].Center())-center,ns[x])>1e-6 for x in side_ids):continue
                selected=[p['pair_id'] for p in ps if (p['face_a'] if p['solid_a']==sid else p['face_b']) in comp]
                groups.append(dict(type='rectangular_insertion_candidate',male_solid_id=sid,
                                   receiver_solid_id=peer,male_face_ids=sorted(comp),side_face_ids=sorted(side_ids),pair_ids=selected,
                                   status='geometry_hypothesis_requires_semantic_review'))
    return groups

def detect_solids(solids,config=None):
    c=config or Config(); start=time.perf_counter()
    faces=[s.Faces() for s in solids]; boxes=[bbox(s) for s in solids]
    info=[[face_info(f,i,j) for j,f in enumerate(fs)] for i,fs in enumerate(faces)]
    pairs=[];errors=[]; tested=0
    for i,j in itertools.combinations(range(len(solids)),2):
        if bbox_distance(boxes[i],boxes[j])>c.max_gap_mm:continue
        for fi,a in enumerate(info[i]):
            for fj,b in enumerate(info[j]):
                if a['surface_type']!=b['surface_type'] or a['surface_type'] not in ('PLANE','CYLINDER'):continue
                if bbox_distance(np.array(a['bbox_mm']),np.array(b['bbox_mm']))>c.max_gap_mm:continue
                tested+=1
                try:
                    f,g=faces[i][fi],faces[j][fj]
                    p=planar_pair(f,g,a,b,c) if a['surface_type']=='PLANE' else cylindrical_pair(f,g,a,b,c)
                    if p:
                        p.update(pair_id=len(pairs),solid_a=i,face_a=fi,solid_b=j,face_b=fj)
                        pairs.append(p)
                except Exception as e:errors.append(dict(solid_a=i,face_a=fi,solid_b=j,face_b=fj,error=str(e)))
    groups=rectangular_groups(pairs,faces)
    return dict(config=asdict(c),solid_count=len(solids),face_count=sum(map(len,faces)),
                tested_face_pairs=tested,pairs=pairs,rectangular_candidates=groups,
                faces=info,errors=errors,elapsed_seconds=time.perf_counter()-start,
                status='candidate_detection_only',pmi={'status':'not_semantically_parsed'},
                limitations=['Solid IDs are geometric bodies, not proven semantic components.',
                             'Face IDs are zero-based import-order IDs, tied to input SHA256 and kernel version.',
                             'No manufacturing tolerance recommendation or MUSE compliance score is inferred.',
                             'Full parallel cylinders and essentially parallel planar faces only.',
                             'max_gap is a search threshold, not an allowed manufacturing tolerance.'])

def detect_step(path,config=None):
    p=Path(path); data=detect_solids(cq.importers.importStep(str(p)).solids().vals(),config)
    data.update(input_step=str(p.resolve()),input_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                cadquery_version=cq.__version__)
    return data

def main():
    parser=argparse.ArgumentParser();parser.add_argument('step');parser.add_argument('--output',required=True)
    parser.add_argument('--max-gap',type=float,default=0.5)
    args=parser.parse_args();result=detect_step(args.step,Config(max_gap_mm=args.max_gap))
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:result[k] for k in ('solid_count','face_count','tested_face_pairs','elapsed_seconds')}))
    print('pairs',len(result['pairs']),'rectangular candidates',len(result['rectangular_candidates']))

if __name__=='__main__':main()
