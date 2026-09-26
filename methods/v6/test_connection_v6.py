import copy
import unittest
from connection_policy_v6 import apply_policy


def bond(a=0,b=1,id=0,area=40):
    return dict(id=id,type='Bonding',solid_a=a,solid_b=b,evidence=dict(planar_patches=[dict(nominal_gap_mm=0,angular_deviation_deg=0,aligned_overlap_area_mm2=area,overlap_ratio=.5)]))


def raw(candidates):return dict(version='v4',candidates=candidates,types={'Bonding':1})

class PolicyTests(unittest.TestCase):
    def test_glue_fallback(self):
        audit=dict(pair_checks={'0|1':dict(penetration_checked=True,penetrating=False)})
        self.assertEqual(apply_policy(raw([bond()]),audit)['candidates'][0]['assessment']['category'],'Bonding')
        self.assertIsNone(apply_policy(raw([bond()]))['candidates'][0]['assessment']['category'])
        audit['pair_checks']['0|1']['penetrating']=True
        self.assertIsNone(apply_policy(raw([bond()]),audit)['candidates'][0]['assessment']['category'])

    def test_other_structure_blocks_glue_even_unknown(self):
        for kind in ['Dowel Joint','Nailing','Mortise & Tenon','Snap-fit']:
            r=raw([bond(),dict(id=1,type=kind,solid_a=1,solid_b=0,evidence={})])
            audit=dict(pair_checks={'0|1':dict(penetration_checked=True,penetrating=False)})
            self.assertEqual(apply_policy(r,audit)['candidates'][0]['assessment']['status'],'suppressed_by_structure')

    def test_fallback_is_per_pair(self):
        r=raw([bond(),bond(1,2,2),dict(id=1,type='Mortise & Tenon',solid_a=1,solid_b=0,evidence={})])
        audit=dict(pair_checks={'1|2':dict(penetration_checked=True,penetrating=False)})
        out=apply_policy(r,audit)
        self.assertIsNone(out['candidates'][0]['assessment']['category'])
        self.assertEqual(out['candidates'][1]['assessment']['category'],'Bonding')

    def test_blind_holes_required_and_original_preserved(self):
        r=raw([dict(id=9,type='Dowel Joint',solid_a=0,solid_b=1,evidence={'type':'opposed_dowel_hole_candidate'})])
        original=copy.deepcopy(r)
        self.assertIsNone(apply_policy(r)['candidates'][0]['assessment']['category'])
        out=apply_policy(r,dict(candidate_features={'9':dict(both_blind=True)}))
        self.assertEqual(out['candidates'][0]['assessment']['subtype'],'wood_dowel_holes')
        self.assertEqual(r,original)

if __name__=='__main__':unittest.main()
