import json
import unittest
from pathlib import Path

from operation_planning.pv import PVScenario, _price_vectors


class CarbonV4ContractTests(unittest.TestCase):
    def test_guangzhou_official_profile_requires_explicit_reference_application(self):
        timestamps = ["2024-01-01T07:00:00+08:00", "2024-01-01T08:00:00+08:00", "2024-01-01T09:00:00+08:00"]
        with self.assertRaises(ValueError):
            _price_vectors(PVScenario(tariff_id="guangzhou_industrial_lt1kv_202110"), timestamps, [3600, 3600, 3600])
        prices, metadata = _price_vectors(
            PVScenario(tariff_id="guangzhou_industrial_lt1kv_202110", tariff_application="current_tariff_on_reference_weather"),
            timestamps,
            [3600, 3600, 3600],
        )
        self.assertAlmostEqual(prices[0], 0.2556)
        self.assertAlmostEqual(prices[1], 0.6725)
        self.assertEqual(metadata["tariff_application"], "current_tariff_on_reference_weather")

    def test_v4_has_three_tiers_and_recommended_chart(self):
        path = Path(__file__).parents[1] / "docs" / "handoff" / "replay_viewer" / "replay_cases_v4.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        cases = {row["case_id"]: row for row in data["cases"]}
        self.assertEqual({"tier_small", "tier_medium", "tier_large"}, set(cases) & {"tier_small", "tier_medium", "tier_large"})
        for row in cases.values():
            self.assertEqual(row["chart"]["scenario_id"], "S3_pv_wind")
            self.assertEqual(row["chart_recommended"]["scenario_id"], row["recommendation"]["scenario_id"])
            self.assertEqual(len(row["carbon_price_scenarios"]), 2)


if __name__ == "__main__":
    unittest.main()
