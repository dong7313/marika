from collections import defaultdict, Counter
import math
from .graph_metrics import ratio

def compare_gaps(row,ref):
    mapping={m['solid_id']:m['reference_id'] for m in row.get('algorithm2',[]) if m['name']}
    gen=defaultdict(list);gold=defaultdict(list);reasons=Counter();comparisons=[]
    for m in row.get('measurements',[]):
        if m['status']!='remeasured_original_STEP_planes': reasons['generated_measurement_failed']+=1;continue
        a,b=mapping.get(m['male_solid']),mapping.get(m['receiver_solid'])
        if a is None or b is None: reasons['unmapped_component']+=1;continue
        gen[(a,b)].append(m)
    for m in (ref or {}).get('measurements',[]):
        if m['status']=='remeasured_original_STEP_planes':gold[(m['male_solid'],m['receiver_solid'])].append(m)
    for pair,ms in gen.items():
        rs=gold.get(pair,[])
        if len(ms)!=1 or len(rs)!=1:
            reasons['nonunique_or_missing_reference_interface']+=len(ms);continue
        m,r=ms[0],rs[0];matches=[]
        for i,d in enumerate(m['dimensions']):
            possible=[j for j,e in enumerate(r['dimensions']) if abs(sum(x*y for x,y in zip(d['axis'],e['axis'])))>=math.cos(math.pi/180)]
            if len(possible)!=1: break
            matches.append((i,possible[0]))
        if len(matches)!=2 or len({j for i,j in matches})!=2:
            reasons['cross_section_axis_not_corresponding']+=1;continue
        for i,j in matches:
            pd=m['dimensions'][i];gd=r['dimensions'][j]
            comparisons.append(dict(candidate_id=m['candidate_id'],generated_solid_pair=[m['male_solid'],m['receiver_solid']],
                reference_solid_pair=list(pair),generated_axis=pd['axis'],reference_axis=gd['axis'],
                generated_total_gap_mm=pd['total_clearance_mm'],reference_total_gap_mm=gd['total_clearance_mm'],
                absolute_deviation_mm=abs(pd['total_clearance_mm']-gd['total_clearance_mm']),
                generated_side_face_pairs=[[w['male_face'],w['receiver_face']] for w in m['walls'][i*2:i*2+2]],
                reference_side_face_pairs=[[w['male_face'],w['receiver_face']] for w in r['walls'][j*2:j*2+2]]))
    return dict(mae_mm=ratio(sum(c['absolute_deviation_mm'] for c in comparisons),len(comparisons)),
                comparison_count=len(comparisons),comparison_interfaces=len(comparisons)//2,
                generated_measured_interfaces=sum(m['status']=='remeasured_original_STEP_planes' for m in row.get('measurements',[])),
                excluded_interfaces=dict(reasons),reference_measurement_status=(ref or {}).get('status','not_run_no_rectangular_candidates'),
                comparisons=comparisons,interpretation='deviation_from_reference_geometry_not_independent_measurement_accuracy_or_tolerance_compliance')
