import numpy as np
import cadquery as cq

def measure_rect(g,planar,solids):
    male=g['male_solid_id'];receiver=g['receiver_solid_id']
    fs=[s.Faces() for s in solids];axes=np.array(g['local_axes']);center=np.array(g['center_mm'])
    byid={p['pair_id']:p for p in planar};walls=[]
    for mf,pid in zip(g['male_face_ids'],g['pair_ids']):
        p=byid[pid]
        assert {p['solid_a'],p['solid_b']}=={male,receiver}
        assert (p['face_a'] if p['solid_a']==male else p['face_b'])==mf
        rf=p['face_b'] if p['solid_a']==male else p['face_a']
        a,b=fs[male][mf],fs[receiver][rf]
        assert a.geomType()==b.geomType()=='PLANE'
        na=np.array(a.normalAt().toTuple());nb=np.array(b.normalAt().toTuple())
        ca=np.array(a.Center().toTuple());cb=np.array(b.Center().toTuple())
        gap=float((cb-ca)@na)
        walls.append(dict(male_face=mf,receiver_face=rf,normal=na.tolist(),signed_gap_mm=gap,
            opposite_normal_error=float(abs(na@nb+1)),male_plane_point=ca.tolist(),receiver_plane_point=cb.tolist()))
    dimensions=[]
    for k,(a,b) in enumerate(((0,1),(2,3))):
        axis=axes[k];wa,wb=walls[a],walls[b]
        m=float(abs((np.array(wa['male_plane_point'])-wb['male_plane_point'])@axis))
        f=float(abs((np.array(wa['receiver_plane_point'])-wb['receiver_plane_point'])@axis))
        assert abs((f-m)-(wa['signed_gap_mm']+wb['signed_gap_mm']))<1e-5
        dimensions.append(dict(axis=axis.tolist(),tenon_mm=m,mortise_mm=f,total_clearance_mm=f-m,
            side_gaps_mm=[wa['signed_gap_mm'],wb['signed_gap_mm']]))
        assert abs(m-g['section_dimensions_mm'][k])<1e-5,'cached face identity/width mismatch'
    assert np.max(np.abs(np.array([w['signed_gap_mm'] for w in walls])-g['side_gaps_mm']))<1e-5,'cached face identity/gap mismatch'
    width,depth=g['section_dimensions_mm']
    assert all(solids[male].isInside(tuple(center+u*width*axes[0]+v*depth*axes[1])) for u in (-.25,0,.25) for v in (-.25,0,.25)),'local tenon material missing'
    assert not solids[receiver].isInside(tuple(center)),'local receiver center not cavity'
    # Independent local check on original, unaligned faces; do not measure aligned copies.
    valid=all(w['opposite_normal_error']<1e-8 for w in walls)
    return dict(status='remeasured_original_STEP_planes' if valid else 'invalid_normal_pair',male_solid=male,receiver_solid=receiver,
        center_mm=center.tolist(),walls=walls,dimensions=dimensions,axial_wall_overlap_mm=g['axial_wall_overlap_mm'],
        interface_location_status='V4_local_four_wall_candidate_rechecked_not_human_confirmed')
