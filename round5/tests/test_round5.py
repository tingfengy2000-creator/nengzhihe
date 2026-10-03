import sys,json,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from adapter import physical
from apar import calibrate,expressions
from response_evidence import calibrate_response,evaluate_response

class Round5(unittest.TestCase):
    def test_missing_markers_and_real_cadence(self):
        c=physical('development')[0]
        self.assertEqual(len(c['minute']),1440)
        self.assertEqual(set(np.diff(c['minute'])),{1.})
        self.assertGreater(int(np.isnan(c['signals']['HSP']).sum()),0)
        self.assertFalse(np.any(np.isinf(c['signals']['HSP'])))

    def test_label_fields_do_not_enter_signal_contract(self):
        c=physical('development')[0]
        self.assertNotIn('fault_type',c)
        self.assertNotIn('injection_setting',c)
        self.assertNotIn('date',c)
        self.assertEqual(set(c['signals']),{'SA','HSP','CSP','OA','MA','RA','FAN','SF','OAD','RAD','EAD','CC','HC','OCC'})

    def test_no_flow_point_disables_minimum_oa_rules(self):
        dev=physical('development');normal=[c for c in dev if c['id'] in {'5138876d3912','b5a5b08a1984'}]
        cal=calibrate(normal)
        self.assertIsNone(cal['fmin'])
        self.assertIn('2',cal['disabled_rules']);self.assertIn('18',cal['disabled_rules'])

    def test_holdout_requires_frozen_entry(self):
        with self.assertRaises(ValueError): physical('holdout')

    def test_response_threshold_is_normal_only(self):
        dev=physical('development');normal=[c for c in dev if c['id'] in {'5138876d3912','b5a5b08a1984'}]
        base=calibrate(normal);response=calibrate_response(normal,base)
        self.assertEqual(response['normal_ids'],normal and [c['id'] for c in normal])
        self.assertGreater(response['threshold_c'],response['normal_q95_c'])

    def test_response_evidence_requires_later_block_and_preserves_gap(self):
        dev=physical('development');normal=[c for c in dev if c['id'] in {'5138876d3912','b5a5b08a1984'}]
        base=calibrate(normal);response=calibrate_response(normal,base)
        damper=next(c for c in dev if c['id']=='19e3873d3c2f')
        coil=next(c for c in dev if c['id']=='0fb594c24122')
        damper_result=evaluate_response(damper,base,response)
        coil_result=evaluate_response(coil,base,response)
        self.assertEqual(damper_result['judgment_state'],'damper_supported_by_command_response')
        self.assertEqual(damper_result['response_mechanism']['wait_minutes_from_first_eligible'],15.0)
        self.assertEqual(coil_result['judgment_state'],'missing_discriminating_air_path_evidence')
        self.assertFalse(coil_result['damper_related_suspicion'])

if __name__=='__main__':unittest.main()
