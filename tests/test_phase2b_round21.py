import unittest
from unittest.mock import patch

from operation_planning.pv import GenerationSeries, PVScenario, _price_vectors
from operation_planning.storage import surplus_paths_from_match


class Round21BackendContractTests(unittest.TestCase):
    def test_custom_tariff_current_application_echoes_prices_and_period(self):
        tariff = {
            "base_tariff_id": "guangzhou_industrial_lt1kv_202610",
            "effective_start": "2026-10-01",
            "effective_end": "2026-10-31",
            "periods": [
                {"name": "valley", "start": "00:00", "end": "08:00", "price": 0.20},
                {"name": "peak", "start": "08:00", "end": "12:00", "price": 1.10},
                {"name": "super_peak", "start": "12:00", "end": "14:00", "price": 1.50},
                {"name": "flat", "start": "14:00", "end": "24:00", "price": 0.70},
            ],
        }
        scenario = PVScenario(
            tariff_id="custom_user",
            custom_tariff=tariff,
            tariff_application="current_tariff_on_reference_weather",
        )
        prices, meta = _price_vectors(
            scenario,
            ["2024-07-15T07:00:00+08:00", "2024-07-15T08:00:00+08:00"],
            [3600, 3600],
        )
        self.assertEqual(prices, [0.20, 1.10])
        echo = meta["custom_tariff_echo"]
        self.assertEqual(echo["effective_start"], "2026-10-01")
        self.assertEqual(echo["effective_end"], "2026-10-31")
        self.assertEqual(echo["prices_cny_per_kwh"]["valley"], 0.20)
        self.assertEqual(echo["prices_cny_per_kwh"]["super_peak"], 1.50)
        self.assertEqual(meta["tariff_application"], "current_tariff_on_reference_weather")

    def test_export_payback_status_uses_user_language(self):
        intervals = {
            "timestamps": ["2024-01-01T00:00:00+08:00", "2024-01-01T01:00:00+08:00"],
            "interval_seconds": [3600, 3600],
            "load_kwh": [0.0, 0.0],
            "generation_kwh": [0.0, 0.0],
            "self_use_kwh": [0.0, 0.0],
            "grid_import_kwh": [0.0, 0.0],
            "curtailment_kwh": [0.0, 0.0],
        }
        no_connection = surplus_paths_from_match(
            intervals, capacities_kwh=[0], export={"price_cny_per_kwh": 0.25}, study_years=10
        )
        self.assertEqual(no_connection["export"]["path"]["payback_status"], "无需额外投入")
        no_surplus = surplus_paths_from_match(
            intervals, capacities_kwh=[0], export={"price_cny_per_kwh": 0.25, "connection_cny": 100}, study_years=10
        )
        self.assertEqual(no_surplus["export"]["path"]["payback_status"], "没有可卖余电，无法回本")
        no_price = surplus_paths_from_match(
            intervals, capacities_kwh=[0], export={"connection_cny": 100}, study_years=10
        )
        self.assertEqual(no_price["export"]["path"]["payback_status"], "缺少上网电价，无法计算回本")

    def test_pv_grid_only_candidate_has_no_surplus_paths(self):
        # Keep this contract at the report boundary without relying on a
        # weather download: generation and matching are replaced with the
        # already validated zero-capacity physical fixture.
        times = ["2024-01-01T00:00:00+08:00", "2024-01-01T01:00:00+08:00"]
        weather = {"time": times, "interval_seconds": [3600, 3600]}
        load = {
            "timestamps": times, "interval_seconds": [3600, 3600],
            "electric_power_w": [1000.0, 1000.0], "source": "test",
            "scope": "test", "service_scope": "cooling_only", "model_version": "test",
        }
        zero_generation = GenerationSeries(
            timestamps=times, interval_seconds=[3600, 3600],
            pv_dc_power_w=[0.0, 0.0], pv_ac_power_w=[0.0, 0.0],
            ghi_w_m2=[0.0, 0.0], dni_w_m2=[0.0, 0.0], dhi_w_m2=[0.0, 0.0],
            poa_w_m2=[0.0, 0.0], cell_temp_c=[25.0, 25.0],
            source="test", model="test", metadata={},
        )
        with patch("operation_planning.pv.generate_pv", return_value=zero_generation):
            from operation_planning.pv import match_load, run_pv_planning, PVQuote
            result = run_pv_planning(
                {"load_series": load}, weather,
                PVScenario(requested_capacities_kwp=[0], quote=PVQuote()),
            )
        candidate = result["candidates"][0]
        self.assertEqual(candidate["capacity_kwp"], 0.0)
        self.assertNotIn("surplus_paths", candidate)


if __name__ == "__main__":
    unittest.main()
