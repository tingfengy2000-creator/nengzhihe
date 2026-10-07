import unittest

from operation_planning.storage import ideal_storage_upper_bound, surplus_paths_from_match


class StorageUpperBoundTests(unittest.TestCase):
    def _intervals(self):
        return {
            "timestamps": ["2024-01-01T00:00:00+08:00", "2024-01-01T01:00:00+08:00", "2024-01-01T02:00:00+08:00"],
            "interval_seconds": [3600, 3600, 3600],
            "load_kwh": [0.0, 3.0, 0.0],
            "generation_kwh": [4.0, 0.0, 0.0],
            "self_use_kwh": [0.0, 0.0, 0.0],
            "grid_import_kwh": [0.0, 3.0, 0.0],
            "curtailment_kwh": [4.0, 0.0, 0.0],
        }

    def test_b_zero_is_identical_no_storage(self):
        result = ideal_storage_upper_bound(self._intervals(), capacities_kwh=[0])
        row = result["candidates"][0]
        self.assertEqual(row["recovered_kwh_year1"], 0.0)
        self.assertEqual(row["charged_kwh_year1"], 0.0)
        self.assertEqual(row["remaining_curtailment_kwh_year1"], 4.0)
        self.assertEqual(row["grid_import_kwh_year1"], 3.0)

    def test_storage_conservation(self):
        result = ideal_storage_upper_bound(self._intervals(), capacities_kwh=[5])
        row = result["candidates"][0]
        self.assertAlmostEqual(row["charged_kwh_year1"], 2.5, places=8)  # B/2 kW for one hour
        self.assertAlmostEqual(row["recovered_kwh_year1"], 2.25, places=8)  # 2.5 * 0.9 round trip
        self.assertAlmostEqual(row["remaining_curtailment_kwh_year1"], 1.5, places=8)
        self.assertAlmostEqual(row["grid_import_kwh_year1"], 0.75, places=8)
        self.assertTrue(row["conservation"]["passed"])

    def test_export_path_can_be_evaluated_independently(self):
        result = ideal_storage_upper_bound(self._intervals(), capacities_kwh=[5], allow_export=True)
        self.assertEqual(result["status"], "calculated")
        self.assertTrue(result["allow_export"])
        self.assertAlmostEqual(result["candidates"][0]["remaining_curtailment_kwh_year1"], 1.5)

    def test_surplus_paths_quote_and_export(self):
        paths = surplus_paths_from_match(
            self._intervals(), capacities_kwh=[0, 5], round_trip_efficiency=0.90,
            allow_export=False,
            storage_quote={"cny_per_kwh": 100, "installation_cny": 20,
                           "maintenance_cny_per_year": 10, "life_years": 5},
            export={"price_cny_per_kwh": 0.50, "connection_cny": 10,
                    "source": "test scenario"},
            import_prices=[0.50, 1.00, 0.50], study_years=10,
        )
        self.assertAlmostEqual(paths["surplus_kwh_year1"], 4.0)
        self.assertEqual(paths["storage"]["candidates"][0]["economics_status"], "complete")
        self.assertEqual(paths["storage"]["candidates"][0]["initial_investment_cny"], 0.0)
        self.assertEqual(paths["storage"]["candidates"][0]["annual_bill_saving_cny"], 0.0)
        self.assertEqual(paths["storage"]["candidates"][0]["study_period_total_cost_cny"], 0.0)
        self.assertEqual(paths["storage"]["candidates"][1]["economics_status"], "complete")
        self.assertAlmostEqual(paths["export"]["path"]["annual_revenue_cny"], 2.0)

    def test_missing_storage_quote_is_incomplete_for_nonzero(self):
        paths = surplus_paths_from_match(self._intervals(), capacities_kwh=[0, 5], import_prices=[0.5, 1.0, 0.5])
        rows = paths["storage"]["candidates"]
        self.assertEqual(rows[0]["economics_status"], "complete")
        self.assertEqual(rows[1]["economics_status"], "incomplete")
        self.assertIsNone(paths["storage"]["recommended_capacity_kwh"])
        self.assertEqual(paths["export"]["path"]["economics_status"], "incomplete")


if __name__ == "__main__":
    unittest.main()
