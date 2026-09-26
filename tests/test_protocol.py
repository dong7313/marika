import json
from pathlib import Path
from review_benchmark.core import prf,save
from review_benchmark.cli import aggregate_data
from review_benchmark.matching import map_parts
from review_benchmark.graph_metrics import ged

def test_all_106_including_missing_and_geometry_independent(tmp_path):
    data=tmp_path/'dataset';data.mkdir();(data/'metadata.jsonl').write_text('\n'.join(json.dumps({'case_id':str(i)}) for i in range(106)))
    good={'defined':True,'f1':1.0}
    save(tmp_path/'results/0/sample_1/evaluation.json',{'code':{'ok':False},'geometry':{'valid':False},'sie':{'scores':{'node':good,'edge':good,'type':good,'ged':{'value':0}},'gap_comparison':{'comparisons':[{'absolute_deviation_mm':.2},{'absolute_deviation_mm':.4}]}},'function':{'Functional':1,'Robust':1}})
    a=aggregate_data(data,tmp_path/'results',tmp_path/'summary.json')
    assert a['task_denominator']==106
    assert a['rates']['node_f1']==1/106 and a['rates']['edge_f1']==1/106
    assert a['rates']['Functional']==0 and a['rates']['joint_success']==0
    assert abs(a['clearance_mae_mm']-.3)<1e-9 and a['N_delta']==2
    assert a['ged']==0 and a['exact_ged_observations']==1

def test_empty_sets_are_not_perfect():
    assert prf({'tp':0,'fp':0,'fn':0})['f1']==0
    assert not prf({'tp':0,'fp':0,'fn':0})['defined']

def test_ambiguous_components_rejected():
    parts=[{'id':i,'name':f'component_{i}','bbox_mm':[[0,0,0],[1,1,1]],'center_mm':[.5,.5,.5],'volume_mm3':1} for i in range(2)]
    assert all(m['name'] is None for m in map_parts(parts,parts))

def test_ged_large_unequal_is_not_reported_exact():
    a={'nodes':[{'id':i,'label':str(i)} for i in range(7)],'edges':[]}
    b={'nodes':[],'edges':[]}
    assert ged(a,b)['value'] is None
