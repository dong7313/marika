import cadquery as cq
from review_benchmark.core import extract

def test_rectangular_clearance_measurement(tmp_path):
    receiver=cq.Solid.makeBox(30,30,10,cq.Vector(-15,-15,0)).cut(cq.Solid.makeBox(10.2,8.4,10,cq.Vector(-5.1,-4.2,0)))
    male=cq.Solid.makeBox(10,8,14,cq.Vector(-5,-4,-2))
    step=tmp_path/'fit.step';cq.exporters.export(cq.Compound.makeCompound([male,receiver]),str(step))
    r=extract(step)
    good=[m for m in r['measurements'] if m['status']=='remeasured_original_STEP_planes']
    assert good
    assert any(all(abs(a-b)<1e-5 for a,b in zip(sorted(d['total_clearance_mm'] for d in m['dimensions']),[.2,.4])) for m in good)
    assert any(c['type']=='Mortise & Tenon' for c in r['detection']['candidates'])
