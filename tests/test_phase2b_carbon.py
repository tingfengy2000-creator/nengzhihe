"""Focused carbon-contract checks; physics fixtures are intentionally short."""
from __future__ import annotations

import unittest

from operation_planning.carbon import factor_catalog, resolve_factor
from operation_planning.hybrid import HybridScenario, run_hybrid_planning
from operation_planning.pv import PVQuote, PVScenario
from operation_planning.wind import WindScenario, WindTurbineProfile, WindQuote


def _fixture():
    times = ["2024-07-15T08:00", "2024-07-15T09:00", "2024-07-15T10:00"]
    weather = {"time": times, "hourly": {"temperature_2m": [30, 30, 30], "relative_humidity_2m": [70, 70, 70], "surface_pressure": [1010, 1010, 1010], "shortwave_radiation": [300, 300, 300], "direct_normal_irradiance": [0, 0, 0], "diffuse_radiation": [0, 0, 0], "wind_speed_10m": [10, 10, 10]}}
    load = {"load_series": {"timestamps": times, "interval_seconds": [3600, 3600, 3600], "electric_power_w": [1000, 1000, 1000], "room_count": 1, "units_per_room": 1, "scope": "project; fixture", "project_aggregation": {"level": "project", "room_count": 1}}, "summary": {"electric_kwh": 3.0, "capacity_shortfall_hours": 0, "unmet_temp_degree_hours": 0, "unmet_rh_percent_hours": 0}}
    return weather, load


class CarbonContracts(unittest.TestCase):
    def _report(self, *, quote=True, allow_export=False):
        weather, load = _fixture()
        pvq = PVQuote(module_cny_per_kwp=100, inverter_cny_per_kwp=20, structure_cny_per_kwp=10, installation_cny_per_kwp=20, grid_connection_cny=0, maintenance_cny_per_kwp_year=1) if quote else PVQuote()
        wq = WindQuote(turbine_cny=100, tower_cny=20, foundation_cny=10, installation_cny=10, grid_connection_cny=0, maintenance_cny_per_year=1) if quote else WindQuote()
        pvs = PVScenario(roof_area_m2=50, requested_capacities_kwp=[0, 1], quote=pvq, allow_export=allow_export, export_price_cny_per_kwh=0.1 if allow_export else None)
        hs = HybridScenario(pv_capacity_kwp=1, wind=WindScenario(turbine_count=0), pv_quote=pvq, wind_quote=wq, shared_connection_cny=0, allow_export=allow_export, export_price_cny_per_kwh=0.1 if allow_export else None, study_years=2)
        return run_hybrid_planning(load, weather, pvs, hs, WindTurbineProfile.from_file(), include_hourly=False, carbon={"carbon_price_cny_per_t": None})

    def test_factor_registry_and_default(self):
        self.assertEqual(resolve_factor("guangzhou")["value_kgco2_per_kwh"], 0.4419)
        self.assertEqual(resolve_factor("beijing")["value_kgco2_per_kwh"], 0.5554)
        self.assertEqual(resolve_factor("harbin")["value_kgco2_per_kwh"], 0.5229)
        catalog = factor_catalog()
        row = next(x for x in catalog["factors"] if x["factor_id"] == "grid_avg_guangdong_2023")
        self.assertIn("W020251231726284332528.pdf", row["attachment_url"])

    def test_conservation_s0_and_empty_price(self):
        report = self._report()
        s0 = next(x for x in report["candidates"] if x["scenario_id"] == "S0_grid")
        s1 = next(x for x in report["candidates"] if x["scenario_id"] == "S1_pv")
        self.assertEqual(s0["carbon"]["avoided_tco2_study_period"], 0.0)
        self.assertTrue(s1["carbon"]["conservation_check"]["passed"])
        self.assertIsNone(s1["carbon"]["carbon_revenue_cny_study_period"])
        self.assertLessEqual(s1["annual_offset_estimate"]["covered_kwh"], report["baseline"]["load_kwh"] + 1e-12)

    def test_unknown_quote_keeps_physics_but_cost_unknown(self):
        report = self._report(quote=False)
        s1 = next(x for x in report["candidates"] if x["scenario_id"] == "S1_pv")
        self.assertGreaterEqual(s1["carbon"]["avoided_kgco2_year1"], 0.0)
        self.assertIsNone(s1["carbon"]["cost_per_tco2_cny"])
        self.assertIsNone(s1["carbon"]["incremental_npv_with_carbon_cny"])

    def test_export_is_separate_from_avoided(self):
        report = self._report(allow_export=True)
        s1 = next(x for x in report["candidates"] if x["scenario_id"] == "S1_pv")
        factor = report["carbon_context"]["factor"]["value_kgco2_per_kwh"]
        self.assertAlmostEqual(s1["carbon"]["avoided_kgco2_year1"], s1["self_use_kwh"] * factor, places=7)
        self.assertAlmostEqual(s1["carbon"]["export_avoided_kgco2_year1"], s1["grid_export_kwh"] * factor, places=7)


if __name__ == "__main__":
    unittest.main()
