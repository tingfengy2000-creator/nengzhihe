import unittest

from operation_planning.storage import ideal_storage_upper_bound


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

    def test_export_is_not_applicable(self):
        result = ideal_storage_upper_bound(self._intervals(), capacities_kwh=[5], allow_export=True)
        self.assertEqual(result["status"], "not_applicable")


if __name__ == "__main__":
    unittest.main()
