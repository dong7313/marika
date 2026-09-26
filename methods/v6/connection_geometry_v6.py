"""Analytic STEP checks. Geometry heuristics, not material or assembly certification."""
import itertools
import math
import numpy as np
from OCP.BRepAdaptor import BRepAdaptor_Surface


def vec(p):
    return np.array([p.X(),p.Y(),p.Z()], dtype=float)


def inside(s,p):
    return s.isInside(tuple(float(x) for x in p),1e-6)


def bounds(s):
    b=s.BoundingBox()
    return np.array([b.xmin,b.ymin,b.zmin]),np.array([b.xmax,b.ymax,b.zmax])


def bbox_distance(a,b):
    return float(np.linalg.norm(np.maximum(0,np.maximum(a[0]-b[1],b[0]-a[1]))))


def project_bounds(b,axis):
    ts=[np.dot(v,axis) for v in itertools.product(*zip(*b))]
    return min(ts),max(ts)


def blind_hole(solid, feature, mouth):
    axis=feature['axis'];origin=feature['origin'];t=float(np.dot(mouth,axis))
    far=feature['hi'] if abs(t-feature['lo'])<abs(t-feature['hi']) else feature['lo']
    direction=1 if far>t else -1
    delta=max(1e-3,min(.02,feature['radius']*.02))
    helper=np.eye(3)[np.argmin(abs(axis))];x=np.cross(axis,helper);x/=np.linalg.norm(x)
    # Behind the far end, material must close the center and two interior radial probes.
    probes=[origin+(far+direction*delta)*axis+q*feature['radius']*x for q in [0,.4,-.4]]
    return bool(all(inside(solid,p) for p in probes))


def cone_info(face, axis, origin):
    if face.geomType()!='CONE':return None
    ad=BRepAdaptor_Surface(face.wrapped)
    cy=ad.Cone();a=vec(cy.Axis().Direction());o=vec(cy.Location());o=o-axis*np.dot(o,axis)
    if abs(np.dot(a,axis))<1-1e-8 or np.linalg.norm(o-origin)>1e-4:return None
    us=[ad.FirstUParameter(),(ad.FirstUParameter()+ad.LastUParameter())/2,ad.LastUParameter()]
    vs=[ad.FirstVParameter(),ad.LastVParameter()]
    rings=[]
    for v in vs:
        pts=[vec(ad.Value(float(u),float(v))) for u in us]
        rings.append((float(np.mean([np.dot(p,axis) for p in pts])),float(np.mean([np.linalg.norm(p-origin-axis*np.dot(p,axis)) for p in pts]))))
    return dict(t0=rings[0][0],r0=rings[0][1],t1=rings[1][0],r1=rings[1][1])


def connector_profile(sid,solid,faces,features):
    cylinders=[f for f in features if f['sid']==sid and f['side']=='outer' and int(np.sum(f['mask']))>=350]
    if not cylinders:return None
    shaft=max(cylinders,key=lambda f:(f['hi']-f['lo'])/max(f['radius'],1e-6))
    axis=shaft['axis'];origin=shaft['origin'];radius=shaft['radius'];length=shaft['hi']-shaft['lo']
    if length/(2*radius)<3:return None
    if any(f['sid']==sid and f['side']=='inner' for f in features):return None
    coax=[f for f in cylinders if abs(np.dot(f['axis'],axis))>1-1e-8 and np.linalg.norm(f['origin']-origin)<1e-4]
    if len(coax)!=len(cylinders):return None
    cones=[]
    for face in faces:
        if face.geomType()=='PLANE':
            if abs(np.dot(np.array(face.normalAt().toTuple()),axis))<1-1e-6:return None
        elif face.geomType()=='CONE':
            c=cone_info(face,axis,origin)
            if c is None:return None
            cones.append(c)
        elif face.geomType()!='CYLINDER':return None
    heads=[]
    for f in coax:
        if f['radius']>=1.3*radius:
            t=(f['lo']+f['hi'])/2
            if min(abs(t-shaft['lo']),abs(t-shaft['hi']))<=max(2*radius,1):heads.append(t)
    for c in cones:
        if max(c['r0'],c['r1'])>=1.3*radius and min(c['r0'],c['r1'])>=.8*radius:
            t=(c['t0']+c['t1'])/2
            if min(abs(t-shaft['lo']),abs(t-shaft['hi']))<=max(2*radius,1):heads.append(t)
    tips=[]
    for c in cones:
        if min(c['r0'],c['r1'])<=.2*radius and .8*radius<=max(c['r0'],c['r1'])<=1.2*radius:
            tips.append(c['t0'] if c['r0']<c['r1'] else c['t1'])
    endpoints=[t for f in coax for t in (f['lo'],f['hi'])]+[t for c in cones for t in (c['t0'],c['t1'])]
    axial=(min(endpoints),max(endpoints))  # True axial ends, not a world-axis bounding-box projection.
    nails=[(h,t) for h in heads for t in tips if (h-(shaft['lo']+shaft['hi'])/2)*(t-(shaft['lo']+shaft['hi'])/2)<0]
    # Uniform round dowels may have small end chamfers, but no necks/heads/points.
    dowel=(not heads and not tips and all(abs(f['radius']-radius)<=1e-4 for f in coax)
           and all(.7*radius<=min(c['r0'],c['r1'])<=max(c['r0'],c['r1'])<=1.01*radius for c in cones))
    return dict(sid=sid,axis=axis,origin=origin,radius=radius,lo=shaft['lo'],hi=shaft['hi'],extent=axial,
                nail_ends=nails,dowel=dowel,shaft_faces=shaft['ids'])


def engaged_parts(profile,solids,boxes):
    sid=profile['sid'];axis=profile['axis'];origin=profile['origin'];r=profile['radius']
    helper=np.eye(3)[np.argmin(abs(axis))];x=np.cross(axis,helper);x/=np.linalg.norm(x);y=np.cross(axis,x)
    result=[]
    for j,s in enumerate(solids):
        if j==sid or bbox_distance(boxes[sid],boxes[j])>.3:continue
        if s.distance(solids[sid])>.3:continue
        hits=[]
        for t in np.linspace(profile['lo']+.01,profile['hi']-.01,33):
            p=origin+t*axis
            if inside(s,p) or any(inside(s,p+(r+offset)*(math.cos(a)*x+math.sin(a)*y)) for offset in [.02,.15,.3] for a in np.linspace(0,2*math.pi,8,endpoint=False)):
                hits.append(float(t))
        if len(hits)>=2:result.append(dict(solid_id=j,lo=min(hits),hi=max(hits)))
    return sorted(result,key=lambda h:(h['lo']+h['hi'])/2)


def analyze(solids,raw,base):
    faces=[s.Faces() for s in solids]
    infos=[[base.face_info(f,i,j) for j,f in enumerate(fs)] for i,fs in enumerate(faces)]
    features=base.cylinder_features(faces,infos)
    boxes=[bounds(s) for s in solids]
    audit=dict(candidate_features={},pair_checks={},connector_profiles=[],new_candidates=[],
               method='analytic_cylinders_cones_blind_ends_external_access_v6',
               limitations=['Only analytic cylindrical shafts and conical points are supported.',
                            'Simplified screws modeled identically to smooth nails cannot be distinguished.',
                            'Mechanical pins/pivots are excluded by dataset scope, not recognized from material.',
                            'No nail solid or unsupported nail geometry remains unresolved.'])
    def matching(sid,ids,side):
        return next((f for f in features if f['sid']==sid and f['side']==side and set(f['ids'])&set(ids)),None)
    for c in raw['candidates']:
        ev=c.get('evidence',{});g=ev.get('interface',ev)
        if g.get('type')=='opposed_dowel_hole_candidate':
            fa=matching(g['part_a'],g['hole_faces_a'],'inner');fb=matching(g['part_b'],g['hole_faces_b'],'inner')
            ba=blind_hole(solids[g['part_a']],fa,np.array(g['mouth_a_mm'])) if fa else False
            bb=blind_hole(solids[g['part_b']],fb,np.array(g['mouth_b_mm'])) if fb else False
            audit['candidate_features'][str(c['id'])]=dict(blind_a=ba,blind_b=bb,both_blind=ba and bb)
    profiles={}
    for sid,solid in enumerate(solids):
        p=connector_profile(sid,solid,faces[sid],features)
        if not p or not(p['nail_ends'] or p['dowel']):continue
        hosts=engaged_parts(p,solids,boxes)
        if len(hosts)<2:continue
        head_access=False
        for h,t in p['nail_ends']:
            sign=1 if h>t else -1
            end=p['extent'][1] if sign>0 else p['extent'][0]
            others=[j for j in range(len(solids)) if j!=sid]
            maxhost=max(project_bounds(boxes[j],p['axis'])[1] for j in others) if sign>0 else min(project_bounds(boxes[j],p['axis'])[0] for j in others)
            run=max(abs(maxhost-end)+2*p['radius'],4*p['radius'])
            probes=[p['origin']+(end+sign*d)*p['axis'] for d in np.linspace(.01,run,12)]
            # Check every assembly part, including caps not touched by the shaft.
            if all(not inside(solids[j],q) for j in others for q in probes):head_access=True
        nail=bool(p['nail_ends'] and head_access)
        # Embedded dowels must terminate against blind material at BOTH ends.
        end_closed=[]
        for t,sgn in [(p['extent'][0],-1),(p['extent'][1],1)]:
            closed=False
            for f in features:
                if f['sid'] not in [h['solid_id'] for h in hosts] or f['side']!='inner':continue
                if abs(np.dot(f['axis'],p['axis']))<1-1e-8 or np.linalg.norm(f['origin']-p['origin'])>1e-4:continue
                if not(-1e-5<=f['radius']-p['radius']<=.3 and f['lo']-1e-5<=t<=f['hi']+1e-5):continue
                mouth=f['origin']+(f['hi'] if sgn<0 else f['lo'])*f['axis']
                if blind_hole(solids[f['sid']],f,mouth):closed=True;break
            end_closed.append(closed)
        dowel=bool(p['dowel'] and all(end_closed))
        profiles[sid]=dict(nail_detected=nail,embedded_dowel=dowel)
        audit['connector_profiles'].append(dict(solid_id=sid,shaft_radius_mm=p['radius'],shaft_faces=p['shaft_faces'],
            head_point_pattern=bool(p['nail_ends']),external_access=head_access,engaged_parts=hosts,nail_candidate=nail,embedded_wood_dowel_candidate=dowel))
        if not(nail or dowel):continue
        links=[(sid,h['solid_id'],'connector_to_part') for h in hosts]
        for a,b in zip(hosts,hosts[1:]):
            if abs((a['lo']+a['hi'])-(b['lo']+b['hi']))<.02:continue
            if max(0,b['lo']-a['hi'])<=3 and bbox_distance(boxes[a['solid_id']],boxes[b['solid_id']])<=3:
                links.append((a['solid_id'],b['solid_id'],'assembly_pair_via_connector'))
        for a,b,role in links:
            ev=dict(type='nail_geometry_candidate' if nail else 'embedded_wood_dowel_candidate',connector_solid_id=sid,
                    shaft_radius_mm=p['radius'],head_point_pattern=bool(p['nail_ends']),external_access=head_access,
                    hosts=[x['solid_id'] for x in hosts],relation_role=role)
            audit['new_candidates'].append(dict(type='Nailing' if nail else 'Wood Dowel',solid_a=a,solid_b=b,evidence=ev,
                count_unit='one_component_pair_via_explicit_connector',confidence='geometry_hypothesis'))
    for c in raw['candidates']:
        ev=c.get('evidence',{});g=ev.get('interface',ev)
        if g.get('type')=='cylindrical_insertion_candidate':
            audit['candidate_features'][str(c['id'])]=profiles.get(g['male_solid_id'],{})
    structural={tuple(sorted((c['solid_a'],c['solid_b']))) for c in raw['candidates']+audit['new_candidates'] if c['type']!='Bonding'}
    for c in raw['candidates']:
        if c['type']!='Bonding':continue
        a,b=sorted((c['solid_a'],c['solid_b']));key=f'{a}|{b}'
        if (a,b) in structural:continue
        try:
            volume=float(solids[a].intersect(solids[b]).Volume())
            tol=max(1e-6,min(solids[a].Volume(),solids[b].Volume())*1e-8)
            audit['pair_checks'][key]=dict(penetration_checked=True,intersection_volume_mm3=volume,penetrating=volume>tol)
        except Exception as exc:
            audit['pair_checks'][key]=dict(penetration_checked=False,error=type(exc).__name__)
    return audit
