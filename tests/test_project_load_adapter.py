"""Short contracts for the single-room to project-load boundary."""
from __future__ import annotations

import unittest

from operation_planning.project_load import aggregate_project_load
from operation_planning.thermal_model import RoomSpec, simulate_room
from operation_planning.pv import PVScenario, run_pv_planning
from operation_planning.hybrid import HybridScenario, run_hybrid_planning


def _weather() -> dict:
    return {
        "time": ["2024-07-15T08:00", "2024-07-15T09:00", "2024-07-15T10:00"],
        "hourly": {
            "temperature_2m": [30.0, 30.0, 30.0],
            "relative_humidity_2m": [70.0, 70.0, 70.0],
            "surface_pressure": [1010.0, 1010.0, 1010.0],
            "shortwave_radiation": [300.0, 300.0, 300.0],
        },
    }


class ProjectLoadAdapterContracts(unittest.TestCase):
    def test_one_room_is_unchanged_and_three_rooms_scale_once(self):
        one = simulate_room(_weather(), RoomSpec(equipment_count=2, room_count=1))
        three = simulate_room(_weather(), RoomSpec(equipment_count=2, room_count=3))
        one_project = aggregate_project_load(one)
        three_project = aggregate_project_load(three)
        self.assertEqual(one_project["load_series"]["electric_power_w"], one["load_series"]["electric_power_w"])
        self.assertEqual(one_project["summary"]["electric_kwh"], one["summary"]["electric_kwh"])
        self.assertEqual(three_project["project_load_contract"]["room_count"], 3)
        for a, b in zip(one_project["load_series"]["electric_power_w"], three_project["load_series"]["electric_power_w"]):
            self.assertAlmostEqual(b, 3 * a)
        self.assertAlmostEqual(three_project["summary"]["electric_kwh"], 3 * one_project["summary"]["electric_kwh"])

    def test_adapter_is_idempotent(self):
        project = aggregate_project_load(simulate_room(_weather(), RoomSpec(room_count=3, equipment_count=2)))
        again = aggregate_project_load(project)
        self.assertEqual(again["load_series"]["electric_power_w"], project["load_series"]["electric_power_w"])
        self.assertEqual(again["summary"]["electric_kwh"], project["summary"]["electric_kwh"])

    def test_direct_matching_rejects_unadapted_multiroom_trace(self):
        load = {"load_series": {"room_count": 3, "timestamps": []}}
        with self.assertRaisesRegex(ValueError, "aggregate_project_load"):
            run_pv_planning(load, {}, PVScenario())
        with self.assertRaisesRegex(ValueError, "aggregate_project_load"):
            run_hybrid_planning(load, {}, PVScenario(), HybridScenario())


if __name__ == "__main__":
    unittest.main()
