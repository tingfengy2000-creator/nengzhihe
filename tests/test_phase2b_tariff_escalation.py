import copy
import unittest

from operation_planning.hybrid import HybridScenario, _escalation_sensitivity
from operation_planning.pv import PVScenario, lifecycle_compare, _escalation_sensitivity as pv_escalation_sensitivity
from operation_planning.storage import surplus_paths_from_match
from operation_planning.task_changes import validate_modifications
from scripts.compact_replay_v9 import build


class TariffEscalationContractTests(unittest.TestCase):
    def test_rate_range_and_negative_schema(self):
        self.assertEqual(PVScenario(tariff_escalation_rate=-0.02).tariff_escalation_rate, -0.02)
        self.assertEqual(HybridScenario(tariff_escalation_rate=0.10).tariff_escalation_rate, 0.10)
        with self.assertRaises(ValueError):
            PVScenario(tariff_escalation_rate=0.1001)
        with self.assertRaises(ValueError):
            HybridScenario(tariff_escalation_rate=-0.0501)
        self.assertEqual(validate_modifications({"hybrid": {"tariff_escalation_rate": -0.02}})["hybrid"]["tariff_escalation_rate"], -0.02)

    def test_pv_g_zero_is_itemwise_unchanged(self):
        match = {
            "summary": {"load_kwh": 1.0, "pv_generation_kwh": 0.0, "self_use_kwh": 0.0,
                        "grid_import_kwh": 1.0, "grid_export_kwh": 0.0, "curtailment_kwh": 0.0,
                        "import_cost_cny": 0.66, "export_income_cny": 0.0},
            "interval_kwh": {"grid_import": [1.0], "grid_export": [0.0]},
        }
        base = PVScenario(study_years=2, tariff_escalation_rate=0.0)
        explicit = PVScenario(study_years=2, tariff_escalation_rate=0.0)
        left = lifecycle_compare(match, match, 0.0, base, import_prices=[0.66], export_prices=None)
        right = lifecycle_compare(match, match, 0.0, explicit, import_prices=[0.66], export_prices=None)
        self.assertEqual(left, right)

    def test_storage_escalates_only_economic_savings(self):
        intervals = {"timestamps": ["2024-01-01T00:00:00+08:00", "2024-01-01T01:00:00+08:00", "2024-01-01T02:00:00+08:00"],
                     "interval_seconds": [3600, 3600, 3600], "load_kwh": [0.0, 3.0, 0.0],
                     "generation_kwh": [4.0, 0.0, 0.0], "self_use_kwh": [0.0, 0.0, 0.0],
                     "grid_import_kwh": [0.0, 3.0, 0.0], "curtailment_kwh": [4.0, 0.0, 0.0]}
        quote = {"cny_per_kwh": 1.0, "installation_cny": 0.0, "maintenance_cny_per_year": 0.0, "life_years": 10}
        flat = surplus_paths_from_match(intervals, capacities_kwh=[5], storage_quote=quote, import_prices=[0.5, 1.0, 0.5], study_years=3)
        rising = surplus_paths_from_match(intervals, capacities_kwh=[5], storage_quote=quote, import_prices=[0.5, 1.0, 0.5], study_years=3, tariff_escalation_rate=0.10)
        self.assertGreater(rising["storage"]["candidates"][0]["study_period_net_benefit_cny"], flat["storage"]["candidates"][0]["study_period_net_benefit_cny"])

    def test_hybrid_sensitivity_four_rates_monotonic_baseline_cost(self):
        def candidate(sid, capex, costs):
            return {"scenario_id": sid, "economics": {"status": "complete", "capex_cny": capex,
                    "incremental_npv_vs_s0_cny": 40.0 if sid == "S1_pv" else 0.0,
                    "yearly": [{"year": 0, "grid_import_cost_cny": 0.0},
                                *[{"year": i, "grid_import_cost_cny": value, "maintenance_cny": 0.0,
                                   "replacement_cny": 0.0, "export_income_cny": 0.0, "residual_cny": 0.0}
                                  for i, value in enumerate(costs, 1)]]}}
        candidates = [candidate("S0_grid", 0.0, [100.0] * 3), candidate("S1_pv", 50.0, [70.0] * 3)]
        candidates[1]["incremental_npv_vs_s0_cny"] = 40.0
        rec = _escalation_sensitivity(candidates, {"scenario_id": "S1_pv"}, study_years=3, discount_rate=0.0)
        self.assertEqual(rec["rates"], [-0.02, 0.0, 0.02, 0.04])
        costs = [row["s0_total_cost_npv_cny"] for row in rec["rows"]]
        self.assertEqual(costs, sorted(costs))
        self.assertEqual(rec["rows"][1]["recommended_total_cost_npv_cny"], 260.0)
        self.assertEqual(rec["rows"][1]["incremental_npv_vs_s0_cny"], 40.0)
        self.assertEqual(rec["rows"][1]["cumulative_payback_year"], 2)
        self.assertIn("第1年节省", rec["rows"][1]["simple_payback_note"])

    def test_pv_sensitivity_uses_candidate_sign_and_cumulative_payback(self):
        def candidate(capacity, capex, costs):
            return {"capacity_kwp": capacity, "incremental_npv_vs_s0_cny": 40.0 if capacity else 0.0,
                    "economics": {"status": "complete", "capex_cny": capex,
                                  "incremental_npv_vs_s0_cny": 40.0 if capacity else 0.0, "yearly": [
                        {"year": 0, "electricity_cost_cny": 0.0},
                        *[{"year": i, "electricity_cost_cny": value, "maintenance_cny": 0.0,
                           "replacement_cny": 0.0, "export_income_cny": 0.0, "residual_cny": 0.0}
                          for i, value in enumerate(costs, 1)]
                    ]}}
        candidates = [candidate(0, 0, [100.0] * 3), candidate(1, 50, [70.0] * 3)]
        rec = pv_escalation_sensitivity(candidates, {"status": "conditional", "capacity_kwp": 1}, PVScenario(study_years=3))
        self.assertEqual(rec["rows"][1]["incremental_npv_vs_s0_cny"], 40.0)
        self.assertEqual(rec["rows"][1]["cumulative_payback_year"], 2)

    def test_compact_replay_has_sensitivity_contract(self):
        source = {"cases": [{"recommendation": {"scenario_id": "S1_pv"}, "input": {},
                   "candidates": [{"scenario_id": "S0_grid", "capex_cny": 0.0, "economics": {"yearly": [{"year": 0}, {"year": 1, "grid_import_cost_cny": 100.0}]}},
                                  {"scenario_id": "S1_pv", "capex_cny": 50.0, "economics": {"simple_payback_years": 2.0, "yearly": [{"year": 0}, {"year": 1, "grid_import_cost_cny": 70.0}]}}]}]}
        result = build(source)
        case = result["cases"][0]
        self.assertEqual(case["tariff_escalation"]["rate"], 0.0)
        self.assertEqual(case["escalation_sensitivity"]["rates"], [-0.02, 0.0, 0.02, 0.04])
        self.assertEqual(case["candidates"][1]["economics"]["simple_payback_years"], 2.0)
        self.assertIn("cumulative_payback_year", case["escalation_sensitivity"]["rows"][1])


if __name__ == "__main__":
    unittest.main()
