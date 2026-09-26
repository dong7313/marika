"""V2 STEP-only local-interface candidates. No MUSE pass threshold is used.

Candidates remain hypotheses. Slightly tilted planar overlap uses rigid alignment
as a screening approximation; original signed face-vertex separations are retained.
"""
import argparse
import hashlib
import itertools
import json
import math
import time
from dataclasses import dataclass,asdict
from pathlib import Path
import sys
import cadquery as cq
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from detect_interfaces import vec,bbox,bbox_distance,face_info
from OCP.BRepAdaptor import BRepAdaptor_Surface

@dataclass
class Config:
    search_gap_mm:float=3.0
    angle_deg:float=1.0
    min_overlap_mm2:float=0.5
    min_overlap_ratio:float=0.05
    min_axial_overlap_mm:float=0.5
    min_cylinder_arc_deg:float=90.0
    max_axis_offset_mm:float=3.0
    max_rectangle_trials:int=200000

def unit(x):
    return x/max(np.linalg.norm(x),1e-20)

def signed_range(points,origin,axis):
    t=(points-origin)@axis
    return float(t.min()),float(t.max())

def planar(f,g,a,b,c):
    na,nb=np.array(a['normal']),np.array(b['normal'])
    angle=math.degrees(math.acos(float(np.clip(-na@nb,-1,1))))
    if angle>c.angle_deg:return None
    ca,cb=np.array(a['center_mm']),np.array(b['center_mm'])
    gap=float((cb-ca)@na)
    if abs(gap)>c.search_gap_mm:return None
    aligned=g
    if angle>1e-7:
        axis=unit(np.cross(nb,-na))
        aligned=g.rotate(tuple(cb),tuple(cb+axis),angle)
    aligned=aligned.translate(tuple(-gap*na))
    area=f.intersect(aligned).Area()
    ratio=area/min(a['area_mm2'],b['area_mm2'])
    if area<c.min_overlap_mm2 or ratio<c.min_overlap_ratio:return None
    pts=np.array([vec(v.Center()) for v in g.Vertices()])
    bounds=signed_range(pts,ca,na) if len(pts) else (gap,gap)
    return dict(type='planar_face_candidate',nominal_gap_mm=gap,
       signed_face_vertex_range_mm=bounds,angular_deviation_deg=angle,
       aligned_overlap_area_mm2=area,overlap_ratio=ratio,
       overlap_method='rigid_aligned_screening' if angle>1e-7 else 'coplanar_boolean',
       relation='nominal_interference' if bounds[0]<-1e-6 else 'nominal_contact_or_clearance')

def rectangles(pairs,faces,infos,solids,c,diagnostics):
    """Build local four-wall features, not connected components of all paired faces.

    No direct edge sharing is required; corner fillets may separate the walls.
    All four trimmed faces must span the same local cross-section center and have
    axial overlap. Multiple tenons are separated by local centers/face identities.
    """
    groups=[];seen=set();trials=0
    for sid in range(len(faces)):
      peers={p['solid_b'] if p['solid_a']==sid else p['solid_a'] for p in pairs if sid in (p['solid_a'],p['solid_b'])}
      for peer in peers:
        pp=[p for p in pairs if {p['solid_a'],p['solid_b']}=={sid,peer}]
        ids=sorted({p['face_a'] if p['solid_a']==sid else p['face_b'] for p in pp})
        ns={i:np.array(infos[sid][i]['normal']) for i in ids}
        centers={i:np.array(infos[sid][i]['center_mm']) for i in ids}
        pts={i:np.array([vec(v.Center()) for v in faces[sid][i].Vertices()]) for i in ids}
        opp=[]
        for a,b in itertools.combinations(ids,2):
            if ns[a]@ns[b]<-0.999999 and (centers[a]-centers[b])@ns[a]>1e-5:
                opp.append((a,b))
        for (a,b),(d,e) in itertools.combinations(opp,2):
            trials+=1
            if trials>c.max_rectangle_trials:
                diagnostics.append(dict(stage='rectangular_grouping',reason='trial_limit',limit=c.max_rectangle_trials));return groups
            if len({a,b,d,e})!=4 or abs(ns[a]@ns[d])>1e-5:continue
            x,y=ns[a],ns[d];z=unit(np.cross(x,y));ii=(a,b,d,e)
            if any(len(pts[i])==0 for i in ii):continue
            cx=float((centers[a]@x+centers[b]@x)/2);cy=float((centers[d]@y+centers[e]@y)/2)
            intervals=[signed_range(pts[i],np.zeros(3),z) for i in ii]
            lo=max(t[0] for t in intervals);hi=min(t[1] for t in intervals)
            if hi-lo<c.min_axial_overlap_mm:continue
            # Each pair must cover the other pair's midline, avoiding remote walls.
            if any(not (min(pts[i]@y)-1e-5<=cy<=max(pts[i]@y)+1e-5) for i in (a,b)):continue
            if any(not (min(pts[i]@x)-1e-5<=cx<=max(pts[i]@x)+1e-5) for i in (d,e)):continue
            center=x*cx+y*cy+z*((lo+hi)/2)
            width=float((centers[a]-centers[b])@x);depth=float((centers[d]-centers[e])@y)
            # Face patches must reach both cross-section ends, allowing corner relief.
            slack=min(c.search_gap_mm,0.3*min(width,depth))
            if any(min(pts[i]@y)>cy-depth/2+slack or max(pts[i]@y)<cy+depth/2-slack for i in (a,b)):continue
            if any(min(pts[i]@x)>cx-width/2+slack or max(pts[i]@x)<cx+width/2-slack for i in (d,e)):continue
            # Trimmed side faces can span several separated tabs in their bounds.
            # Reject a fictitious large tab bridging empty space: require a 3x3
            # interior cross-section sample grid in the male and a cavity center.
            if not all(solids[sid].isInside(tuple(center+u*width*x+v*depth*y)) for u in (-.25,0,.25) for v in (-.25,0,.25)):continue
            if solids[peer].isInside(tuple(center)):continue
            selected=[]
            for i in ii:
                candidates=[p for p in pp if (p['face_a'] if p['solid_a']==sid else p['face_b'])==i]
                # Facing receiver wall must be concave relative to this local center.
                valid=[]
                for p in candidates:
                    j=p['face_b'] if p['solid_a']==sid else p['face_a']
                    inf=infos[peer][j]
                    if (np.array(inf['center_mm'])-center)@np.array(inf['normal']) < -1e-5:valid.append(p)
                if not valid:break
                selected.append(max(valid,key=lambda p:p['aligned_overlap_area_mm2']))
            if len(selected)!=4:continue
            # Merge equivalent subfaces by local geometry, preserving evidence union.
            key=(sid,peer,tuple(np.round(center,3)),tuple(sorted(round(v,3) for v in (width,depth))),round(hi-lo,3))
            if key in seen:continue
            seen.add(key)
            groups.append(dict(type='rectangular_insertion_candidate',male_solid_id=sid,receiver_solid_id=peer,
              male_face_ids=list(ii),pair_ids=[p['pair_id'] for p in selected],center_mm=center.tolist(),
              section_dimensions_mm=[width,depth],local_axes=[x.tolist(),y.tolist(),z.tolist()],axial_wall_overlap_mm=hi-lo,
              side_gaps_mm=[p['nominal_gap_mm'] for p in selected],
              evidence='four_local_convex_walls_with_corresponding_concave_receiver_walls_and_3x3_material_samples',
              compliance='not_evaluated'))
    return groups

def cylinder_features(faces,infos):
    """Merge same-support cylindrical patches only where their axial intervals meet."""
    groups=[]
    for sid,fs in enumerate(faces):
      local=[]
      for fid,f in enumerate(fs):
        a=infos[sid][fid]
        if a['surface_type']!='CYLINDER':continue
        axis=np.array(a['axis']);axis=axis if axis[np.argmax(abs(axis))]>0 else -axis
        origin=np.array(a['axis_origin_mm']);origin=origin-axis*(origin@axis)
        ps=np.array([vec(v.Center()) for v in f.Vertices()])
        if len(ps)==0:continue
        interval=signed_range(ps,np.zeros(3),axis)
        adaptor=BRepAdaptor_Surface(f.wrapped)
        u0,u1=adaptor.FirstUParameter(),adaptor.LastUParameter();v=(adaptor.FirstVParameter()+adaptor.LastVParameter())/2
        helper=np.eye(3)[np.argmin(abs(axis))];x=unit(np.cross(axis,helper));y=np.cross(axis,x)
        # Sample actual angular sweep to a 1-degree occupancy mask; only detection coverage.
        mask=np.zeros(360,dtype=bool)
        for u in np.linspace(u0,u1,max(3,int(abs(u1-u0)*360/math.pi)+1)):
            q=vec(adaptor.Value(float(u),v))-origin
            mask[int(math.degrees(math.atan2(q@y,q@x)))%360]=True
        found=None
        for g in local:
            if g['side']==a['material_side'] and abs(g['radius']-a['radius_mm'])<1e-5 and abs(g['axis']@axis)>1-1e-10 and np.linalg.norm(g['origin']-origin)<1e-5 and max(g['lo'],interval[0])<=min(g['hi'],interval[1])+1e-5:
                found=g;break
        if found:
            found['ids'].append(fid);found['mask']|=mask;found['lo']=min(found['lo'],interval[0]);found['hi']=max(found['hi'],interval[1])
        else:local.append(dict(sid=sid,ids=[fid],axis=axis,origin=origin,radius=a['radius_mm'],side=a['material_side'],lo=interval[0],hi=interval[1],mask=mask))
      groups.extend(local)
    return groups

def cylinders(features,c):
    result=[]
    for a,b in itertools.combinations(features,2):
        if a['sid']==b['sid'] or a['side']==b['side']:continue
        angle=math.degrees(math.acos(float(np.clip(abs(a['axis']@b['axis']),0,1))))
        # Curved-interface quantification is currently parallel-axis only.
        if angle>1e-4:continue
        delta=b['origin']-a['origin'];offset=float(np.linalg.norm(delta-a['axis']*(delta@a['axis'])))
        if offset>c.max_axis_offset_mm:continue
        lo=max(a['lo'],b['lo']);hi=min(a['hi'],b['hi'])
        if hi-lo<c.min_axial_overlap_mm:continue
        hole,shaft=(a,b) if a['side']=='inner' else (b,a)
        radial=hole['radius']-shaft['radius']
        if abs(radial)>c.search_gap_mm:continue
        coverage=int(np.sum(a['mask']&b['mask']))
        if coverage<c.min_cylinder_arc_deg:continue
        result.append(dict(type='cylindrical_insertion_candidate',male_solid_id=shaft['sid'],receiver_solid_id=hole['sid'],
            male_face_ids=shaft['ids'],receiver_face_ids=hole['ids'],
            center_mm=(a['origin']+a['axis']*((lo+hi)/2)).tolist(),radial_clearance_mm=radial,
            diametral_clearance_mm=2*radial,axis_offset_mm=offset,axial_overlap_mm=hi-lo,
            angular_coverage_estimate_deg=coverage,partial_surface=coverage<355,
            radial_separation_range_mm=[radial-offset,radial+offset],
            compliance='not_evaluated',semantic_status='may_be_round_tenon_or_other_shaft_hole'))
    return result

def detect_step(path,c=None):
    c=c or Config();start=time.perf_counter();path=Path(path)
    solids=cq.importers.importStep(str(path)).solids().vals()
    faces=[s.Faces() for s in solids];infos=[[face_info(f,i,j) for j,f in enumerate(fs)] for i,fs in enumerate(faces)]
    errors=[];pairs=[];rejected=0;tested=0
    boxes=[bbox(s) for s in solids]
    # Vectorized face bounds/normals avoid expensive Cartesian-pair Python loops.
    for i,j in itertools.combinations(range(len(solids)),2):
        if bbox_distance(boxes[i],boxes[j])>c.search_gap_mm:continue
        right=[b for b in infos[j] if b['surface_type']=='PLANE']
        if not right:continue
        norms=np.array([b['normal'] for b in right]);bounds=np.array([b['bbox_mm'] for b in right])
        for a in infos[i]:
            if a['surface_type']!='PLANE':continue
            ab=np.array(a['bbox_mm']);distance=np.linalg.norm(np.maximum(0,np.maximum(ab[0]-bounds[:,1],bounds[:,0]-ab[1])),axis=1)
            valid=(norms @ np.array(a['normal'])<=-math.cos(math.radians(c.angle_deg)))&(distance<=c.search_gap_mm)
            for k in np.flatnonzero(valid):
                b=right[k];tested+=1
                try:
                    p=planar(faces[i][a['face_id']],faces[j][b['face_id']],a,b,c)
                    if p:
                        p.update(pair_id=len(pairs),solid_a=i,face_a=a['face_id'],solid_b=j,face_b=b['face_id']);pairs.append(p)
                    else:rejected+=1
                except Exception as e:errors.append(dict(stage='planar_pair',solid_a=i,solid_b=j,face_a=a['face_id'],face_b=b['face_id'],error=str(e)))
    rect=rectangles(pairs,faces,infos,solids,c,errors)
    raw_cyl=cylinders(cylinder_features(faces,infos),c)
    cyl=[];associated_rounding=[]
    for arc in raw_cyl:
        parent=None
        if arc['partial_surface']:
            for r in rect:
                if (arc['male_solid_id'],arc['receiver_solid_id'])!=(r['male_solid_id'],r['receiver_solid_id']):continue
                delta=np.array(arc['center_mm'])-r['center_mm'];q=np.array(r['local_axes'])@delta
                if abs(q[0])<=r['section_dimensions_mm'][0]/2+1e-4 and abs(q[1])<=r['section_dimensions_mm'][1]/2+1e-4 and abs(q[2])<=r['axial_wall_overlap_mm']/2+1e-4:
                    parent=r;break
        if parent is None:cyl.append(arc)
        else:associated_rounding.append(arc)
    interfaces=rect+cyl
    for i,g in enumerate(interfaces):g['interface_id']=i
    status='no_solids' if not solids else ('single_solid_unassessable' if len(solids)==1 else ('partial' if errors else 'completed'))
    return dict(version='v2',input_step=str(path.resolve()),input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
      detector_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),cadquery_version=cq.__version__,config=asdict(c),
      status=status,solid_count=len(solids),face_count=sum(map(len,faces)),tested_planar_pairs=tested,
      rejected_after_prefilter=rejected,planar_pairs=pairs,interfaces=interfaces,rectangular_count=len(rect),cylindrical_count=len(cyl),
      candidate_count=len(interfaces),associated_corner_arcs=associated_rounding,errors=errors,elapsed_seconds=time.perf_counter()-start,
      tolerance_compliance='not_evaluated_requires_MUSE_requirement_mapping',
      limitations=['Candidate counts are not confirmed mortise/tenon counts.',
      'Search remains bounded to 3 mm, not a compliance tolerance.',
      'Single-solid boundaries cannot be recovered from geometry alone.',
      'Rectangular features require four nearly orthogonal planar wall patches; dovetails and open slots unsupported.',
      'Cylindrical arc coverage is sampled; axial/angle joint coverage and tilted axes need further development.',
      'No generated code/reference coordinates used during STEP-only inference.'])

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('step');ap.add_argument('--output',required=True);args=ap.parse_args()
    d=detect_step(args.step);out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf8')
    print({k:d[k] for k in ('status','candidate_count','rectangular_count','cylindrical_count','elapsed_seconds')})
