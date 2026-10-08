import unittest

from scripts.compact_replay_v9 import build


class CompactReplayV9Tests(unittest.TestCase):
    def test_payback_fields_are_preserved_or_recovered_from_stored_cashflows(self):
        source = {
            "cases": [{
                "case_id": "tiny",
                "candidates": [
                    {"scenario_id": "S0_grid", "capex_cny": 0.0, "economics": {"yearly": [{"year": 1, "grid_import_cost_cny": 100.0, "maintenance_cny": 0.0, "export_income_cny": 0.0}]}},
                    {"scenario_id": "S1_pv", "capex_cny": 300.0, "economics": {"yearly": [{"year": 1, "grid_import_cost_cny": 50.0, "maintenance_cny": 5.0, "export_income_cny": 0.0}]}},
                ],
            }],
        }
        result = build(source)
        rows = result["cases"][0]["candidates"]
        self.assertEqual(rows[0]["economics"]["simple_payback_years"], None)
        self.assertEqual(rows[0]["economics"]["annual_saving_after_maintenance_cny"], 0.0)
        self.assertAlmostEqual(rows[1]["economics"]["annual_saving_after_maintenance_cny"], 45.0)
        self.assertAlmostEqual(rows[1]["economics"]["simple_payback_years"], 300 / 45)

    def test_existing_authoritative_values_are_not_overwritten(self):
        source = {"cases": [{"case_id": "tiny", "candidates": [{"scenario_id": "S0_grid", "capex_cny": 0.0, "economics": {"simple_payback_years": 7.0, "annual_saving_after_maintenance_cny": 12.0, "yearly": []}}]}]}
        row = build(source)["cases"][0]["candidates"][0]
        self.assertEqual(row["economics"]["simple_payback_years"], 7.0)
        self.assertEqual(row["economics"]["annual_saving_after_maintenance_cny"], 12.0)


if __name__ == "__main__":
    unittest.main()
