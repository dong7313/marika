"""Executable CQ positive/negative controls for nail/dowel/glue classification."""
import importlib.util
import unittest
from pathlib import Path
import cadquery as cq
from connection_geometry_v6 import analyze
from connection_policy_v6 import apply_policy
from test_connection_v6 import bond,raw
V4=Path(__file__).resolve().parents[1]/'v4/detector.py'
spec=importlib.util.spec_from_file_location('v4_test',V4);v4=importlib.util.module_from_spec(spec);spec.loader.exec_module(v4)

def cyl(radius,height,z):return cq.Solid.makeCylinder(radius,height,cq.Vector(0,0,z))
def board(z,height,hole_start=None,hole_depth=None):
    s=cq.Solid.makeBox(20,20,height,cq.Vector(-10,-10,z))
    return s.cut(cyl(1.05,hole_depth,hole_start)) if hole_start is not None else s

def nail():return cyl(1,20,-10).fuse(cyl(2,2,10)).fuse(cq.Solid.makeCone(0,1,2,cq.Vector(0,0,-12)))

class GeometryTests(unittest.TestCase):
    def test_nail_with_tip_head_external_access_and_two_parts(self):
        solids=[board(0,10,0,10),board(-15,15,-12,12),nail()]
        r=raw([bond()]);a=analyze(solids,r,v4.v3.base)
        self.assertTrue(any(p['nail_candidate'] for p in a['connector_profiles']))
        out=apply_policy(r,a)
        self.assertIsNone(out['candidates'][0]['assessment']['category'])
        self.assertTrue(any(c['assessment']['category']=='Nailing' and set((c['solid_a'],c['solid_b']))=={0,1} for c in out['candidates']))

    def test_blocked_external_entry_is_not_nail(self):
        solids=[board(0,10,0,10),board(-15,15,-12,12),nail(),board(12.1,3)]
        a=analyze(solids,raw([]),v4.v3.base)
        self.assertFalse(any(p['nail_candidate'] for p in a['connector_profiles']))

    def test_rigid_rotation_and_translation_preserve_classification(self):
        fixtures=[([board(0,10,0,10),board(-15,15,-12,12),nail()], 'nail_candidate'),
                  ([board(0,10,0,5),board(-10,10,-5,5),cyl(1,8,-4)], 'embedded_wood_dowel_candidate')]
        for solids,flag in fixtures:
            transformed=[s.rotate((0,0,0),(1,1,0),43).translate((51,-23,7)) for s in solids]
            a=analyze(transformed,raw([]),v4.v3.base)
            self.assertTrue(any(p[flag] for p in a['connector_profiles']),flag)

    def test_headed_blunt_rod_is_not_nail(self):
        solids=[board(0,10,0,10),board(-15,15,-12,12),cyl(1,20,-10).fuse(cyl(2,2,10))]
        a=analyze(solids,raw([]),v4.v3.base)
        self.assertFalse(any(p['nail_candidate'] for p in a['connector_profiles']))

    def test_single_recipient_is_not_board_to_board_nail(self):
        a=analyze([board(-15,25,-12,22),nail()],raw([]),v4.v3.base)
        self.assertFalse(a['new_candidates'])

    def test_embedded_dowel_is_not_nail(self):
        solids=[board(0,10,0,5),board(-10,10,-5,5),cyl(1,8,-4)]
        a=analyze(solids,raw([bond()]),v4.v3.base)
        self.assertTrue(any(p['embedded_wood_dowel_candidate'] for p in a['connector_profiles']))
        self.assertFalse(any(p['nail_candidate'] for p in a['connector_profiles']))
        out=apply_policy(raw([bond()]),a)
        self.assertTrue(any(c['assessment']['subtype']=='wood_dowel_solid' for c in out['candidates']))
        self.assertIsNone(out['candidates'][0]['assessment']['category'])

    def test_through_pin_is_not_embedded_wood_dowel(self):
        solids=[board(0,10,0,10),board(-10,10,-10,10),cyl(1,24,-12)]
        a=analyze(solids,raw([]),v4.v3.base)
        self.assertFalse(any(p['embedded_wood_dowel_candidate'] for p in a['connector_profiles']))
        self.assertFalse(a['new_candidates'])

    def test_recessed_nail_head_with_open_entry(self):
        top=board(0,10,0,10).cut(cq.Solid.makeCylinder(2.1,3,cq.Vector(0,0,7)))
        solids=[top,board(-20,20,-16,16),nail().translate((0,0,-3))]
        a=analyze(solids,raw([]),v4.v3.base)
        self.assertTrue(any(p['nail_candidate'] for p in a['connector_profiles']))

    def test_plain_boards_use_glue_fallback(self):
        a=analyze([board(0,10),board(-10,10)],raw([bond()]),v4.v3.base)
        self.assertEqual(apply_policy(raw([bond()]),a)['semantic_pair_counts']['Bonding'],1)

    def test_interpenetration_rejects_glue(self):
        a=analyze([board(0,10),board(-9,10)],raw([bond()]),v4.v3.base)
        self.assertEqual(apply_policy(raw([bond()]),a)['semantic_pair_counts']['Bonding'],0)

if __name__=='__main__':unittest.main()
