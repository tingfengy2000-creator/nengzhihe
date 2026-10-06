"""5090 short contracts for the editable air-cost handoff."""
from __future__ import annotations

import unittest

from operation_planning.lifecycle import life_cycle_cost
from operation_planning.tariffs import custom_profile
from operation_planning.thermal_model import RoomSpec, simulate_room


def _weather() -> dict:
    return {
        "time": ["2024-07-15T08:00", "2024-07-15T08:30", "2024-07-15T09:00"],
        "hourly": {
            "temperature_2m": [30.0, 30.0, 30.0],
            "relative_humidity_2m": [70.0, 70.0, 70.0],
            "surface_pressure": [1010.0, 1010.0, 1010.0],
            "shortwave_radiation": [300.0, 300.0, 300.0],
        },
    }


class AirCostHandoffContracts(unittest.TestCase):
    def test_units_and_rooms_are_not_double_counted(self):
        one = simulate_room(_weather(), RoomSpec(equipment_count=2, room_count=1))
        three = simulate_room(_weather(), RoomSpec(equipment_count=2, room_count=3))
        common = dict(study_years=1, price_cny_per_kwh=0.66, equipment_price_cny=3200, installation_cny=900, maintenance_cny_per_year=0)
        one_cost = life_cycle_cost(one, room_count=1, units_per_room=2, **common)
        three_cost = life_cycle_cost(three, room_count=3, units_per_room=2, **common)
        self.assertEqual(one_cost["lifecycle"]["initial_cny"], 8200)
        self.assertEqual(three_cost["lifecycle"]["quote_quantity"], 6)
        self.assertAlmostEqual(three_cost["monthly"]["2024-07"]["electric_kwh"], 3 * one_cost["monthly"]["2024-07"]["electric_kwh"])
        self.assertEqual(three_cost["lifecycle"]["equipment_cny"], 19200)

    def test_user_lifetime_changes_replacement_only(self):
        result = simulate_room(_weather(), RoomSpec(equipment_count=2))
        common = dict(study_years=10, price_cny_per_kwh=0.66, room_count=1, units_per_room=2, equipment_price_cny=3200, installation_cny=900, maintenance_cny_per_year=0)
        life8 = life_cycle_cost(result, expected_life_years=8, **common)
        life12 = life_cycle_cost(result, expected_life_years=12, **common)
        life10 = life_cycle_cost(result, expected_life_years=10, **common)
        self.assertEqual(life8["lifecycle"]["replacement_events"][0]["year"], 8)
        self.assertEqual(life12["lifecycle"]["replacement_events"], [])
        self.assertEqual(life10["lifecycle"]["replacement_events"], [])
        self.assertEqual(life8["monthly"]["2024-07"]["electric_kwh"], life12["monthly"]["2024-07"]["electric_kwh"])

    def test_tariff_interval_boundary_is_split(self):
        result = simulate_room(_weather(), RoomSpec(equipment_count=1))
        rows = [{"timestamp": "2024-07-15T08:00", "interval_seconds": 1800, "electric_power_w": 1000, "delivered_cooling_w": 0, "delivered_latent_w": 0}, {"timestamp": "2024-07-15T08:30", "interval_seconds": 1800, "electric_power_w": 1000, "delivered_cooling_w": 0, "delivered_latent_w": 0}]
        tariff = custom_profile({"effective_start": "2024-07-15", "effective_end": "2024-07-15", "periods": [{"name": "peak", "start": "08:00", "end": "08:30", "price": 0.5}, {"name": "flat", "start": "08:30", "end": "24:00", "price": 1.0}, {"name": "flat", "start": "00:00", "end": "08:00", "price": 1.0}]})
        result["rows"] = rows
        cost = life_cycle_cost(result, study_years=1, tariff_profile=tariff, calendar_start="2024-07-15", equipment_price_cny=0, installation_cny=0, maintenance_cny_per_year=0)
        self.assertAlmostEqual(cost["monthly"]["2024-07"]["cost_cny"], 0.75, places=9)


if __name__ == "__main__":
    unittest.main()
