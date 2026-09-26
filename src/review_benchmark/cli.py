"""Reviewer entry point: setup, generate, evaluate, aggregate."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile
from .core import ROOT,read,save

def worker(action, source, out, timeout, **options):
    cmd=[sys.executable,'-m','review_benchmark.worker',action,'--input',str(source.resolve()),'--output',str(out.resolve())]
    for k,v in options.items():
        if v is not None:cmd.extend(['--'+k.replace('_','-'),str(Path(v).resolve())])
    # Never reuse stale success records or artifacts after a failed rerun.
    out.unlink(missing_ok=True)
    if options.get('artifact') is not None:Path(options['artifact']).unlink(missing_ok=True)
    env=os.environ.copy()
    # Model credentials are not inherited by executable CAD workers.
    env={k:v for k,v in env.items() if not any(s in k.upper() for s in ['KEY','TOKEN','SECRET','PASSWORD'])}
    try:
        done=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=timeout)
        if out.is_file():return read(out)
        result={'status':'failed','error_type':'WorkerExit','exit_code':done.returncode}
    except subprocess.TimeoutExpired:result={'status':'timeout'}
    save(out,result);return result

def tasks(data,selected):
    all_tasks=[json.loads(l)['case_id'] for l in (data/'metadata.jsonl').read_text().splitlines() if l.strip()]
    if len(set(all_tasks))!=106:raise ValueError('Expected exactly 106 benchmark tasks')
    if selected:
        unknown=set(selected)-set(all_tasks)
        if unknown:raise ValueError('Unknown task: '+', '.join(sorted(unknown)))
        return [t for t in all_tasks if t in selected]
    return all_tasks

def setup(args):
    checksums={line.split()[1]:line.split()[0] for line in (ROOT/'data/SHA256SUMS').read_text().splitlines() if line.strip()}
    for archive in sorted((ROOT/'data').glob('*.zip')):
        with archive.open('rb') as stream:
            digest=hashlib.file_digest(stream,'sha256').hexdigest()
        if digest != checksums.get(archive.name):raise ValueError('Archive checksum mismatch: '+archive.name)
        with zipfile.ZipFile(archive) as z:
            for info in z.infolist():
                target=(ROOT/info.filename).resolve()
                if ROOT.resolve() not in target.parents:raise ValueError('Unsafe archive path')
            z.extractall(ROOT)
    print('Extracted benchmark data and reference assets.')

def generate(args):
    from .api import Client,code
    client=Client(args.base_url,args.key_env,args.timeout)
    system=(ROOT/'prompts/generation_system.txt').read_text()
    args.output.mkdir(parents=True,exist_ok=True)
    save(args.output/'run_config.json',{'model':args.model,'temperature':args.temperature,'samples':args.samples,'tasks':tasks(args.data,args.tasks),'generation':'single_pass'})
    for task in tasks(args.data,args.tasks):
        desc=(args.data/'cases'/task/'design_description.md').read_text()
        user='Task specification:\n\n```markdown\n'+desc.strip()+'\n```\n\nReturn only executable Python code.\nUse only stdlib/math/cadquery and keep the output deterministic.\n'
        for sample in range(1,args.samples+1):
            folder=args.output/task/f'sample_{sample}';folder.mkdir(parents=True,exist_ok=True)
            if (folder/'code.py').is_file() and not args.overwrite:continue
            save(folder/'prompt.json',{'system_prompt':system,'user_prompt':user,'model':args.model})
            text=client.complete(args.model,[{'role':'system','content':system},{'role':'user','content':user}],args.temperature)
            (folder/'code.py').write_text(code(text));print(f'Generated {task} sample {sample}',flush=True)

def evaluate(args):
    from .api import Client,image_block,json_object
    selected=tasks(args.data,args.tasks);client=Client(args.base_url,args.key_env,args.timeout) if args.judge_model else None
    for task in selected:
        reference=ROOT/'reference/graphs'/f'{task}.json';cache=args.output/'reference_cache'/f'{task}.json'
        folders=sorted((args.runs/task).glob('sample_*'))
        # Missing generations are retained by aggregate, not silently excluded.
        for folder in folders:
            target=args.output/task/folder.name;target.mkdir(parents=True,exist_ok=True)
            step=target/'model.step';record={'task':task,'sample':folder.name,'code':{'ok':False},'geometry':{},'function':{'Functional':0,'Robust':0,'status':'not_evaluated'}}
            if (folder/'code.py').is_file():
                record['code']=worker('execute',folder/'code.py',target/'execution.json',args.execution_timeout,artifact=step)
            elif (folder/'model.step').is_file():
                import shutil
                shutil.copy2(folder/'model.step',step);record['code']={'ok':False,'status':'imported_step_execution_unverified'}
            if step.is_file():
                record['geometry']=worker('geometry',step,target/'geometry.json',args.evaluation_timeout)
                if not cache.is_file():
                    worker('extract',ROOT/'reference/steps'/f'{task}.step',cache,args.evaluation_timeout)
                record['sie']=worker('sie',step,target/'sie.json',args.evaluation_timeout,reference=reference,reference_cache=cache)
                svg=target/'drawing.svg';png=target/'drawing.png'
                render=worker('render',step,target/'render.json',args.evaluation_timeout,artifact=svg)
                record['render']=render
                if render.get('ok'):
                    try:subprocess.run(['rsvg-convert',str(svg),'-o',str(png)],check=True,capture_output=True,timeout=60)
                    except (FileNotFoundError,subprocess.SubprocessError):record['render']['png_status']='unavailable'
                if client and record['code'].get('ok') and png.is_file():
                    case=args.data/'cases'/task
                    inputs=[{'type':'text','text':'<Task_Doc>\n'+(case/'design_description.md').read_text()+'\n</Task_Doc>\n<Evaluation_Rubric>\n'+(case/'evaluation_rubric.md').read_text()+'\n</Evaluation_Rubric>\n<Reference_SVG>'}]
                    refs=sorted(p for p in case.glob('*.png') if not p.name.endswith('_stp_render.png'))
                    if refs:inputs.append(image_block(refs[0]))
                    inputs.extend([{'type':'text','text':'</Reference_SVG>\n<Generated_SVG>'},image_block(png),{'type':'text','text':'</Generated_SVG>'}])
                    try:
                        value=json_object(client.complete(args.judge_model,[{'role':'system','content':(ROOT/'prompts/judge_system.txt').read_text()},{'role':'user','content':inputs}],args.temperature))
                        save(target/'judge.json',value)
                        scores={i['category_en']:i['score'] for i in value['items']}
                        f,r=scores['Functional Adaptation'],scores['Usage Stability']
                        if f not in (0,1) or r not in (0,1):raise ValueError('Expected binary judge scores')
                        record['function']={'Functional':f,'Robust':r,'status':'completed','model':args.judge_model}
                    except Exception as exc:record['function']['status']='judge_failed';record['function']['error_type']=type(exc).__name__
            save(target/'evaluation.json',record);print(f'Evaluated {task}/{folder.name}',flush=True)
    aggregate_data(args.data,args.output,args.output/'summary.json')

def aggregate_data(data, results, output):
    names=tasks(data,None);rows=[]
    for task in names:
        files=sorted((results/task).glob('sample_*/evaluation.json'));samples=[read(p) for p in files]
        # Within-task sample means, then a fixed 106-task mean. Missing tasks = zero.
        row={'task':task,'samples':len(samples)}
        vals={k:[] for k in ['code','geometry','watertight','manifold','self_intersection_free','overlap_free','node_f1','edge_f1','type_f1','Functional','Robust','joint_success']}
        coverage={k:0 for k in ['node','edge','type','gap','ged']};gaps=[];geds=[]
        for sample in samples:
            code=bool(sample.get('code',{}).get('ok'));geom=sample.get('geometry',{});sie=sample.get('sie',{});scores=sie.get('scores',{});fn=sample.get('function',{})
            vals['code'].append(float(code));vals['geometry'].append(float(code and geom.get('valid') is True))
            for k in ['watertight','manifold','self_intersection_free','overlap_free']:vals[k].append(float(code and geom.get(k) is True))
            for k in ['node','edge','type']:
                score=scores.get(k) or {};coverage[k]+=bool(score.get('defined'));vals[k+'_f1'].append(float(score.get('f1') or 0))
            for k in ['Functional','Robust']:vals[k].append(float(fn.get(k,0)) if code else 0.0)
            vals['joint_success'].append(float(code and geom.get('valid') is True and all(vals[k+'_f1'][-1]==1 for k in ['node','edge','type']) and all(vals[k][-1]==1 for k in ['Functional','Robust'])))
            comp=sie.get('gap_comparison',{}).get('comparisons',[]);gaps.extend(c['absolute_deviation_mm'] for c in comp);coverage['gap']+=bool(comp)
            distance=(scores.get('ged') or {}).get('value')
            if distance is not None:geds.append(distance);coverage['ged']+=1
        row.update({k:sum(v)/len(v) if v else 0.0 for k,v in vals.items()});row.update(coverage=coverage,gap_errors_mm=gaps,ged_values=geds);rows.append(row)
    measures=list(vals);gap_errors=[e for row in rows for e in row['gap_errors_mm']];distances=[e for row in rows for e in row['ged_values']]
    summary={'protocol':'paper-taskmean106-zero-fill','task_denominator':106,'rates':{k:sum(row[k] for row in rows)/106 for k in measures},
             'clearance_mae_mm':sum(gap_errors)/len(gap_errors) if gap_errors else None,'N_delta':len(gap_errors),
             'ged':sum(distances)/len(distances) if distances else None,'exact_ged_observations':len(distances),
             'coverage_tasks':{k:sum(row['coverage'][k]>0 for row in rows) for k in coverage},'evaluated_tasks':sum(row['samples']>0 for row in rows),'tasks':rows}
    save(output,summary);return summary

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('setup-data').set_defaults(func=setup)
    for name,fn in [('generate',generate),('evaluate',evaluate),('aggregate',None)]:
        q=sub.add_parser(name);q.add_argument('--data',type=Path,default=ROOT/'dataset');q.add_argument('--output',type=Path,required=True)
        if name=='aggregate':q.add_argument('--runs',type=Path,required=True);q.set_defaults(func=lambda a:aggregate_data(a.data,a.runs,a.output));continue
        q.add_argument('--tasks',nargs='+');q.add_argument('--base-url');q.add_argument('--key-env',default='MODEL_API_KEY');q.add_argument('--timeout',type=int,default=300);q.add_argument('--temperature',type=float,default=None)
        if name=='generate':q.add_argument('--model',required=True);q.add_argument('--samples',type=int,default=1);q.add_argument('--overwrite',action='store_true')
        else:q.add_argument('--runs',type=Path,required=True);q.add_argument('--judge-model');q.add_argument('--execution-timeout',type=int,default=180);q.add_argument('--evaluation-timeout',type=int,default=600)
        q.set_defaults(func=fn)
    args=p.parse_args();args.func(args)
if __name__=='__main__':main()
