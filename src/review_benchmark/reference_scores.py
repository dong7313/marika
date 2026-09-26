import re
from collections import Counter
from .graph_metrics import counts, ged, ratio
TYPES=("Interlocking","Snap-fit","Nailing","Bonding")
def category(text):
    s=re.sub('[^a-z]','',text.lower())
    return {'doweljoint':'Interlocking','wooddowel':'Interlocking','woodendowel':'Interlocking','interlocking':'Interlocking','interlockingunspecified':'Interlocking',
            'mortisetenon':'Interlocking','snapfit':'Snap-fit','nailing':'Nailing',
            'pivot':'Pivot','bonding':'Bonding'}.get(s)

def norm(s): return re.sub('[^a-z0-9]','',s.lower())

def graph_comparison(solids,mappings,refparts,candidates,source_graph):
    """Conservative named text graph: unresolved groups stay outside precision/recall."""
    refs={p['id']:p for p in refparts}; valid={p['id'] for p in refparts if p.get('name')}
    mapped={m['solid_id']:m['reference_id'] for m in mappings if m.get('name') and m.get('reference_id') in valid}
    # Node score is reference matching coverage, NOT correctness of Alg2 labels.
    tp=len(set(mapped.values())); np=len(solids); ng=len(refparts)
    node=dict(tp=tp,fp=np-tp,fn=ng-tp,value=ratio(2*tp,np+ng),scope='automatic_reference_correspondence_proxy')
    lookup={norm(p['name']):p['id'] for p in refparts if p.get('name')}
    unique_names=Counter(norm(p['name']) for p in refparts if p.get('name'))
    expected={}; unresolved=[]; ignored=[]
    for e in source_graph['edges']:
        if norm(e['raw_type']) in ('supportbase','support','none','noconnection'): ignored.append(e); continue
        a,b=norm(e['a']),norm(e['b'])
        if a not in lookup or b not in lookup or unique_names[a]!=1 or unique_names[b]!=1:
            unresolved.append(e); continue
        if lookup[a]==lookup[b]: unresolved.append(e); continue
        pair=tuple(sorted((lookup[a],lookup[b]))); t=category(e['raw_type'])
        entry=expected.setdefault(pair,set())
        if t: entry.add(t)
        else: unresolved.append({**e,'reason':'type_outside_paper_five_classes'})
    generated={}
    for e in candidates:
        a=mapped.get(e['solid_a'],'unmatched:'+str(e['solid_a']))
        b=mapped.get(e['solid_b'],'unmatched:'+str(e['solid_b']))
        pair=tuple(sorted((str(a),str(b))))
        t=category(e['type']); labels=generated.setdefault(pair,set())
        if t: labels.add(t)
    gt={tuple(sorted(map(str,p))):labels for p,labels in expected.items()}
    complete=bool(source_graph['raw']) and not source_graph['unparsed'] and not unresolved
    matched=len(set(generated)&set(gt)); result=dict(node=node,reference_edges=len(gt),matched_explicit_edges=matched,
        explicit_edge_recall=ratio(matched,len(gt)),unresolved_source_edges=len(unresolved),
        ignored_support_edges=len(ignored),source_graph_complete=complete,source_unresolved=unresolved,
        edge_f1=None,type_f1=None,ged=None,ged_upper_bound=None,ged_status='incomplete_reference_graph',
        prediction_named_pairs=len(generated),reference_pair_labels=[dict(a=a,b=b,types=sorted(ts)) for (a,b),ts in gt.items()])
    if complete:
        result['edge_counts']=counts(generated,gt);result['edge_f1']=result['edge_counts']['f1']
        pt={(*p,t) for p,ts in generated.items() for t in ts}; gtt={(*p,t) for p,ts in gt.items() for t in ts}
        result['type_counts']=counts(pt,gtt)
        result['type_classes']={t:counts({x for x in pt if x[2]==t},{x for x in gtt if x[2]==t}) for t in TYPES}
        values=[c['f1'] for c in result['type_classes'].values() if c['f1'] is not None]
        result['type_f1']=ratio(sum(values),len(values))
        # GED is unrestricted: do not present a fixed-mapping edit cost as exact GED.
        pn=[dict(id=s['id'],label=refs[mapped[s['id']]]['name'] if s['id'] in mapped else None) for s in solids]
        pe={}
        for c in candidates:
            p=tuple(sorted((c['solid_a'],c['solid_b']))); pe.setdefault(p,set())
            if (t:=category(c['type'])): pe[p].add(t)
        gp=dict(nodes=pn,edges=[dict(a=a,b=b,types=sorted(ts)) for (a,b),ts in pe.items()])
        gg=dict(nodes=[dict(id=p['id'],label=p['name']) for p in refparts],
                edges=[dict(a=a,b=b,types=sorted(ts)) for (a,b),ts in expected.items()])
        dist=ged(gp,gg);result.update(ged=dist['value'],ged_upper_bound=dist['upper_bound'],ged_status=dist['status'])
    return result
