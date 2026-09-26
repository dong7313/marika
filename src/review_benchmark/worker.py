"""Timeout-isolated CAD worker; subprocess isolation is not a security boundary."""
import argparse
import json
import math
from pathlib import Path
import runpy
import sys
from .core import ROOT, read, save, extract, graph_scores, geometry_check, render

def execute(code, step):
    import cadquery as cq
    ns={'cq':cq,'cadquery':cq,'math':math,'__name__':'__candidate__'}
    exec(compile(Path(code).read_text(), 'candidate.py','exec'),ns,ns)
    result=ns.get('result')
    if result is None:raise ValueError('Missing result variable')
    if isinstance(result,cq.Assembly):shape=result.toCompound()
    elif isinstance(result,cq.Workplane):
        values=[v for v in result.vals() if isinstance(v,cq.Shape)]
        shape=cq.Compound.makeCompound(values)
    elif isinstance(result,cq.Shape):shape=result
    else:raise TypeError('result must be a CadQuery Shape, Workplane or Assembly')
    if not shape.Solids():raise ValueError('Empty CAD artifact')
    cq.exporters.export(shape,str(step),'STEP')
    if not Path(step).is_file() or not Path(step).stat().st_size:raise ValueError('STEP export failed')
    return {'ok':True,'solid_count':len(shape.Solids())}

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['execute','geometry','sie','render','extract']);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--artifact',type=Path);p.add_argument('--reference',type=Path);p.add_argument('--reference-cache',type=Path)
    args=p.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True)
    try:
        if args.action=='execute':result=execute(args.input,args.artifact)
        elif args.action=='geometry':result=geometry_check(args.input)
        elif args.action=='render':render(args.input,args.artifact);result={'ok':True}
        elif args.action=='extract':result=extract(args.input)
        else:
            from .gap_comparison import compare_gaps
            ref=read(args.reference);raw=extract(args.input);scored=graph_scores(raw['detection'],ref)
            cache=read(args.reference_cache) if args.reference_cache and args.reference_cache.is_file() else None
            gaps=compare_gaps({'algorithm2':scored.get('mappings',[]),'measurements':raw['measurements']},cache)
            result={'status':'completed','scores':scored,'gap_comparison':gaps,'evidence':raw}
        save(args.output,result)
    except Exception as exc:
        save(args.output,{'status':'failed','error_type':type(exc).__name__,'error':str(exc)[:1000]})
        raise
if __name__=='__main__':main()
