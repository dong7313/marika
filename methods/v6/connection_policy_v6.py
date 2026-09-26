"""Wood-assembly scope: nails vs wooden dowels; glue-compatible fallback per pair."""
from copy import deepcopy

POLICY_VERSION = 'connection-policy-v6-wood'
RULES = dict(bonding_gap_mm=0.3, bonding_angle_deg=0.1,
             bonding_area_mm2=25.0, bonding_overlap_ratio=0.1)
CATEGORIES = ['Interlocking', 'Snap-fit', 'Nailing', 'Bonding']


def pair(c):
    return tuple(sorted((c['solid_a'], c['solid_b'])))


def base_assessment(c):
    return dict(raw_type=c['type'], category=None, subtype=None,
                policy_version=POLICY_VERSION, status='type_unresolved',
                connector_presence='not_established', evidence_kind='insufficient_geometry',
                label='结构待确认', reason='Insufficient supported geometric evidence.')


def assess_structure(c, geometry):
    a = base_assessment(c)
    ev = c.get('evidence') or {}
    interface = ev.get('interface', ev)
    kind = interface.get('type')
    feature = geometry.get('candidate_features', {}).get(str(c['id']), {})
    if c['type'] == 'Nailing' and ev.get('type') == 'nail_geometry_candidate':
        a.update(category='Nailing', subtype='driven_nail', evidence_kind='head_shaft_point_external_entry',
                 connector_presence='explicit_connector_solid', status='geometry_hypothesis',
                 label='Nailing · 钉接候选', reason='Slender shaft, head, opposed pointed cone, outward entry access and at least two engaged parts.')
    elif ev.get('type') == 'embedded_wood_dowel_candidate':
        a.update(category='Interlocking', subtype='wood_dowel_solid', evidence_kind='embedded_cylinder_two_blind_ends',
                 connector_presence='explicit_connector_solid', status='geometry_hypothesis',
                 label='Interlocking · 木工圆榫候选（内置圆杆）',
                 reason='Uniform, headless round connector enclosed by blind-ended holes in two parts.')
    elif c['type'] in ('Mortise & Tenon', 'Interlocking', 'Snap-fit'):
        category = 'Snap-fit' if c['type'] == 'Snap-fit' else 'Interlocking'
        a.update(category=category, subtype='snap_fit' if category=='Snap-fit' else 'rectangular_tenon',
                 evidence_kind='legacy_insertion_geometry', status='geometry_hypothesis',
                 label=category+(' · 卡扣候选' if category=='Snap-fit' else ' · 榫卯候选'),
                 reason='Existing geometric structure candidate; no adhesive inference.')
    elif kind == 'opposed_dowel_hole_candidate':
        a.update(evidence_kind='opposed_holes', label='对孔结构 · 盲孔待确认')
        if feature.get('both_blind'):
            a.update(category='Interlocking', subtype='wood_dowel_holes', status='geometry_hypothesis',
                     label='Interlocking · 木工圆榫候选（两侧盲孔）',
                     reason='Opposed mating-face holes terminate inside both wooden parts; connector is not modeled.')
        else:
            a['reason']='Opposed holes exist, but two blind terminations are not established; do not substitute Bonding.'
    elif kind == 'cylindrical_insertion_candidate':
        a.update(evidence_kind='shaft_insertion', connector_presence='shaft_geometry_present',
                 label='圆杆插孔结构 · 类型待确认')
        if feature.get('embedded_dowel'):
            a.update(category='Interlocking', subtype='wood_dowel_solid', status='geometry_hypothesis',
                     connector_presence='explicit_connector_solid', label='Interlocking · 木工圆榫候选（内置圆杆）',
                     reason='Headless, non-pointed cylindrical connector spans two parts and is enclosed by their blind holes.')
        elif feature.get('nail_detected'):
            a.update(category='Nailing', subtype='driven_nail', status='geometry_hypothesis',
                     label='Nailing · 钉接候选', reason='Same connector passed the independent nail-geometry checks.')
        else:
            a['reason']='A shaft/hole fit alone is not sufficient to distinguish a nail from a wooden dowel.'
    return a


def bonding_patch_ok(p, rules):
    fields=['nominal_gap_mm','angular_deviation_deg','aligned_overlap_area_mm2','overlap_ratio']
    if not all(isinstance(p.get(k), (int,float)) for k in fields):
        return False
    return (-1e-5 <= p['nominal_gap_mm'] <= rules['bonding_gap_mm']
            and 0 <= p['angular_deviation_deg'] <= rules['bonding_angle_deg']
            and p['aligned_overlap_area_mm2'] >= rules['bonding_area_mm2']
            and rules['bonding_overlap_ratio'] <= p['overlap_ratio'] <= 1.00001)


def apply_policy(raw, geometry=None, rules=None):
    geometry=geometry or {}
    rules=dict(RULES, **(rules or {}))
    out=deepcopy(raw)
    candidates=out['candidates']
    next_id=max((c['id'] for c in candidates), default=-1)+1
    for addition in geometry.get('new_candidates', []):
        c=deepcopy(addition);c['id']=next_id;next_id+=1;candidates.append(c)
    blocked=set()
    for c in candidates:
        c['assessment']=assess_structure(c, geometry)
        if c['type']!='Bonding':
            # An unresolved insertion/hole is still structural evidence, not an absence.
            blocked.add(pair(c))
    for c in candidates:
        if c['type']!='Bonding':continue
        a=c['assessment'];a.update(evidence_kind='planar_bondable_surface', label='接触证据 · 不作为连接类型')
        key=pair(c)
        if key in blocked:
            a.update(status='suppressed_by_structure',reason='Another connection structure exists on this component pair; Bonding fallback is disabled.')
            continue
        patches=c.get('evidence',{}).get('planar_patches',[])
        overlap=geometry.get('pair_checks',{}).get(f'{key[0]}|{key[1]}',{})
        valid=[p for p in patches if bonding_patch_ok(p,rules)]
        if valid and overlap.get('penetration_checked') and not overlap.get('penetrating'):
            a.update(category='Bonding',subtype='bondable_surface_fallback', status='geometry_hypothesis',
                     label='Bonding · 可胶接面候选（无其他结构）',
                     reason='No other detected structure on this pair; qualifying mating patch and no solid-volume interference. Material, adhesive and load performance are not verified.',
                     qualifying_patch_count=len(valid))
        else:
            a.update(label='接触候选 · 可胶接性待确认', reason='Mating-patch thresholds or non-interference verification are incomplete/failed.')
    out.update(raw_version=raw.get('version'),version='v6-wood',
               classification_policy=dict(version=POLICY_VERSION,scope='wood_nails_and_dowels_no_mechanical_pins_or_pivots',
                   nailing_definition='Explicit nail-like head/shaft/point with external insertion access and two engaged parts',
                   bonding_definition='Geometric bondability fallback ONLY when the same component pair has no other detected structure',
                   unknown_structure_blocks_bonding=True,rules=rules,
                   prediction_status='geometry_hypotheses',note='Raw type/types are retained for audit; use assessment.category for V6 predictions.'),
               geometry_audit=geometry)
    out['semantic_candidate_counts']={t:sum(c['assessment']['category']==t for c in candidates) for t in CATEGORIES}
    out['semantic_pair_counts']={t:len({pair(c) for c in candidates if c['assessment']['category']==t}) for t in CATEGORIES}
    edge_groups={}
    for c in candidates:
        edge_groups.setdefault(pair(c),[]).append(c)
    out['semantic_edges']=[dict(a=a,b=b,candidate_ids=[c['id'] for c in cs],
        types=[t for t in CATEGORIES if any(c['assessment']['category']==t for c in cs)],
        subtypes=sorted({c['assessment']['subtype'] for c in cs if c['assessment']['subtype']}),
        status='geometry_hypothesis' if any(c['assessment']['category'] for c in cs) else 'type_unresolved')
        for (a,b),cs in sorted(edge_groups.items())]
    out['unresolved_candidate_count']=sum(c['assessment']['category'] is None for c in candidates)
    return out
