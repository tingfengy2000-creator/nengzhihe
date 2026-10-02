"""Meaningful scope, numerical and repair checks; development/demo cases only."""
import copy, json, sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from engine import ROOT, quality, repair_duplicates, operating_minutes, corr, building_evidence, diagnose, load_calibration
from policies import run_case

class Contracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fault=json.loads((ROOT/'data/cases/NZH-76889C2BA896.json').read_text(encoding='utf-8'))
        cls.building=json.loads((ROOT/'data/cases/NZH-CFF0E57369E1.json').read_text(encoding='utf-8'))
    def test_repair_does_not_clear_equipment(self):
        before=run_case(self.fault,'fixed',4,save=False)
        after=run_case(self.fault,'fixed',4,repair=True,save=False)
        self.assertEqual(before['final']['quality']['duplicates'],12)
        self.assertEqual(after['final']['quality']['duplicates'],0)
        self.assertEqual(before['final']['label'],'damper_stuck')
        self.assertEqual(after['final']['label'],'damper_stuck')
    def test_duplicate_time_is_not_extra_operating_time(self):
        self.assertEqual(operating_minutes(self.fault),operating_minutes(repair_duplicates(self.fault)))
    def test_conflicting_records_are_not_silently_deleted(self):
        c=repair_duplicates(self.fault); t=c['timestamps'][0]
        c['timestamps'].append(t)
        for key,vals in c['series'].items(): vals.append(vals[0]+1 if key=='SA_TEMP' else vals[0])
        self.assertEqual(quality(repair_duplicates(c))['duplicates'],1)
    def test_injected_actuator_channels_rejected(self):
        c=copy.deepcopy(self.fault); c['series']['OA_DMPR']=[0]*len(c['timestamps'])
        with self.assertRaises(ValueError): run_case(c,save=False)
    def test_missing_is_not_zero(self):
        self.assertIsNone(corr(np.ones(5),np.ones(5)))
        c=copy.deepcopy(self.building)
        c['series']['reference_kwh']=[None]*len(c['timestamps'])
        self.assertIsNone(building_evidence(c,'operating_context')['positive_reference_difference_kwh'])
    def test_incomplete_calibration_abstains(self):
        cal=load_calibration(); cal['classes']=['normal']
        self.assertEqual(diagnose(self.fault,{},cal)['status'],'not_ready')
    def test_budget_and_full_information(self):
        for budget in [1,2,3,4]:
            for strategy in ['fixed','adaptive_rule']:
                r=run_case(self.fault,strategy,budget,save=False)
                self.assertLessEqual(r['cost']['query_units'],budget)
                self.assertEqual(r['cost']['field_acquisition_units'],0)
        self.assertEqual(run_case(self.fault,'full_information',4,save=False)['cost']['query_units'],4)
        with self.assertRaises(ValueError): run_case(self.fault,'full_information',3,save=False)
    def test_local_payload_cannot_read_hidden_evidence(self):
        seen=[]
        def fake(payload,allowed):
            seen.append(payload)
            self.assertEqual(set(payload['revealed_evidence']),{'quality'})
            serialized=json.dumps(payload)
            for forbidden in ['source_file','base_case_id',self.fault['id'],'OA_DMPR"','CHWC_VLV"']:
                self.assertNotIn(forbidden,serialized)
            return {'action':None,'response_valid':False,'latency_ms':1,'error':'test invalid response'}
        with patch('policies.choose_action',fake): r=run_case(self.fault,'local_model',2,save=False)
        self.assertEqual(len(seen),1)
        self.assertEqual(r['final']['label'],'unresolved')
        self.assertEqual(r['status'],'model_error')
        self.assertEqual(r['cost']['query_units'],1)

if __name__=='__main__': unittest.main(verbosity=2)
