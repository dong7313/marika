import cadquery as cq
from review_benchmark.core import geometry_check
from review_benchmark.worker import execute

def test_overlap_detected(tmp_path):
    shape=cq.Compound.makeCompound([cq.Solid.makeBox(10,10,10),cq.Solid.makeBox(10,10,10,cq.Vector(5,0,0))])
    path=tmp_path/'overlap.step';cq.exporters.export(shape,str(path))
    assert not geometry_check(path)['overlap_free']

def test_execution_requires_result_and_nonempty(tmp_path):
    import pytest
    code=tmp_path/'code.py';code.write_text('import cadquery as cq\nresult=cq.Workplane("XY")\n')
    with pytest.raises(ValueError):execute(code,tmp_path/'empty.step')
    code.write_text('import cadquery as cq\nresult=cq.Workplane("XY").box(2,3,4)\n')
    assert execute(code,tmp_path/'box.step')['ok']


def test_failed_rerun_removes_stale_success(tmp_path):
    from review_benchmark.cli import worker
    from review_benchmark.core import save
    source=tmp_path/'code.py';source.write_text('raise ValueError("fixture failure")')
    output=tmp_path/'execution.json';step=tmp_path/'model.step'
    save(output,{'ok':True});step.write_text('stale artifact')
    record=worker('execute',source,output,30,artifact=step)
    assert record.get('ok') is not True
    assert not step.exists()
