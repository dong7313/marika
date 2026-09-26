"""Reference-guided component correspondence, preserved from the experiment implementation."""
import re
import numpy as np
RULES={'suggestion_score_max':.32,'runner_up_margin_min':.035}

def linear_sum_assignment(cost):
    """Rectangular Hungarian minimization; rows <= columns, no dependency install."""
    n,m=cost.shape;assert n<=m
    u=np.zeros(n+1);v=np.zeros(m+1);p=np.zeros(m+1,dtype=int);way=np.zeros(m+1,dtype=int)
    for i in range(1,n+1):
        p[0]=i;j0=0;minimum=np.full(m+1,np.inf);used=np.zeros(m+1,dtype=bool)
        while True:
            used[j0]=True;i0=p[j0];delta=np.inf;j1=0
            for j in range(1,m+1):
                if used[j]:continue
                cur=cost[i0-1,j-1]-u[i0]-v[j]
                if cur<minimum[j]:minimum[j]=cur;way[j]=j0
                if minimum[j]<delta:delta=minimum[j];j1=j
            for j in range(m+1):
                if used[j]:u[p[j]]+=delta;v[j]-=delta
                else:minimum[j]-=delta
            j0=j1
            if p[j0]==0:break
        while True:
            j1=way[j0];p[j0]=p[j1];j0=j1
            if j0==0:break
    pairs=sorted((p[j]-1,j-1) for j in range(1,m+1) if p[j])
    return np.array([a for a,b in pairs]),np.array([b for a,b in pairs])

def generic(n):return not n or bool(re.search(r'Open CASCADE|^\d+$|^SOLID|^=>|^part[_ -]?\d+$',n,re.I))

def descriptors(parts):
    boxes=np.array([p['bbox_mm'] for p in parts]);lo=boxes[:,0].min(axis=0);hi=boxes[:,1].max(axis=0);span=np.maximum(hi-lo,1e-6)
    centers=(np.array([p['center_mm'] for p in parts])-lo)/span
    size=np.maximum(boxes[:,1]-boxes[:,0],1e-6)
    dims=size/span
    fill=np.array([max(p['volume_mm3'],1e-9) for p in parts])/np.prod(size,axis=1)
    return centers,dims,fill

def map_parts(solids,parts):
    if not solids or not parts:return []
    gc,gd,gf=descriptors(solids);rc,rd,rf=descriptors(parts)
    cost=.55*np.linalg.norm(gc[:,None,:]-rc[None,:,:],axis=2)+.35*np.mean(np.abs(np.log(gd[:,None,:]/rd[None,:,:])),axis=2)+.10*np.abs(np.log(gf[:,None]/rf[None,:]))
    # Dummy columns permit unmatched solids. No forced one-to-one naming.
    expanded=np.concatenate([cost,np.full((len(solids),len(solids)),RULES['suggestion_score_max'])],axis=1)
    a,b=linear_sum_assignment(expanded);assign=dict(zip(a,b));result=[]
    for i,s in enumerate(solids):
        ranked=np.argsort(cost[i])[:3];j=assign[i]
        options=[dict(reference_id=int(k),name=parts[k]['name'],score=round(float(cost[i,k]),5)) for k in ranked]
        rowmargin=float(cost[i,ranked[1]]-cost[i,ranked[0]]) if len(ranked)>1 else 1.
        column=np.sort(cost[:,j]) if j<len(parts) else []
        colmargin=float(column[1]-column[0]) if len(column)>1 else 1.
        good=j<len(parts) and j==ranked[0] and int(np.argmin(cost[:,j]))==i and cost[i,j]<RULES['suggestion_score_max'] and rowmargin>=RULES['runner_up_margin_min'] and colmargin>=RULES['runner_up_margin_min'] and not generic(parts[j]['name']) and sum(p['name']==parts[j]['name'] for p in parts)==1
        result.append(dict(solid_id=s['id'],reference_id=int(j) if good else None,name=parts[j]['name'] if good else None,
            status='geometry_suggestion_unconfirmed' if good else 'ambiguous_or_unmatched',confirmed=False,
            candidates=options,row_margin=round(rowmargin,5),column_margin=round(colmargin,5),method='normalized_geometry_assignment_no_order_matching'))
    return result
