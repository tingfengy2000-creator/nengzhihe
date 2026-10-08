import unittest
from unittest.mock import patch

from operation_planning.agent_parse import _normalise_changes, _unsupported_feature_notes, parse_agent_request


class AgentParseContractTests(unittest.TestCase):
    def setUp(self):
        self.task = {
            "room": {
                "room_count": 1,
                "units_per_room": 2,
                "start_hour": 8,
                "end_hour": 18,
                "area_m2": 35,
                "equipment_id": "midea_msagbu12_mox201",
            },
            "hybrid": {
                "budget_cny": 30000,
                "allow_export": True,
                "pv_capacity_kwp": 1,
                "tariff_escalation_rate": 0.0,
                "wind": {"turbine_count": 0},
            },
            "storage": {"quote": {"cny_per_kwh": 553.94}, "capacities_kwh": [0, 5, 10]},
        }

    def test_six_supported_chinese_examples_have_bounded_fields(self):
        examples = [
            ([{"field": "room.units_per_room", "to": 3}], "room.units_per_room"),
            ([{"field": "room.equipment_id", "to": "midea_gaia12"}], "room.equipment_id"),
            ([{"field": "hybrid.budget_cny", "to": 50000}], "hybrid.budget_cny"),
            ([{"field": "room.start_hour", "to": 18}, {"field": "room.end_hour", "to": 22}], "room.end_hour"),
            ([{"field": "hybrid.allow_export", "to": False}], "hybrid.allow_export"),
            ([{"field": "hybrid.pv_capacity_kwp", "to": 2}], "hybrid.pv_capacity_kwp"),
        ]
        for raw, expected in examples:
            with self.subTest(expected=expected):
                changes = _normalise_changes(raw, self.task)
                self.assertIn(expected, {item["field"] for item in changes})
                self.assertTrue(all(set(item) == {"field", "from", "to", "label"} for item in changes))

    def test_relative_budget_is_resolved_once(self):
        changes = _normalise_changes(
            [{"field": "hybrid.budget_multiplier", "to": 2 / 3}], self.task
        )
        self.assertEqual(changes, [{"field": "hybrid.budget_cny", "from": 30000, "to": 20000.0, "label": "预算"}])

    def test_inconsistent_budget_forms_fail_closed(self):
        with self.assertRaises(ValueError):
            _normalise_changes(
                [
                    {"field": "hybrid.budget_cny", "to": 21000},
                    {"field": "hybrid.budget_multiplier", "to": 2 / 3},
                ],
                self.task,
            )

    def test_unsupported_field_fails_closed(self):
        with self.assertRaises(ValueError):
            _normalise_changes([{"field": "hybrid.secret_result", "to": 1}], self.task)

    def test_tariff_escalation_is_a_supported_change(self):
        changes = _normalise_changes([{"field": "hybrid.tariff_escalation_rate", "to": 0.03}], self.task)
        self.assertEqual(changes[0]["field"], "hybrid.tariff_escalation_rate")
        self.assertEqual(changes[0]["to"], 0.03)

    def test_wind_count_and_storage_quote_are_supported_changes(self):
        wind = _normalise_changes([{"field": "hybrid.wind.turbine_count", "to": 1}], self.task)
        storage = _normalise_changes([{"field": "storage.quote.cny_per_kwh", "to": 600.0}], self.task)
        capacities = _normalise_changes([{"field": "storage.capacities_kwh", "to": [0, 5, 10]}], self.task)
        self.assertEqual(wind[0]["from"], 0)
        self.assertEqual(storage[0]["from"], 553.94)
        self.assertEqual(capacities[0]["to"], [0, 5, 10])
        self.assertEqual(_unsupported_feature_notes("储能单价553.94元/kWh，容量列表0、5、10kWh"), [])

    def test_vague_budget_returns_clarification_without_calculation(self):
        with patch("operation_planning.agent_parse._read_config", return_value={"_endpoint": "http://127.0.0.1:1/v1", "model_id": "test"}), patch(
            "operation_planning.agent_parse._model_parse",
            return_value={"changes": [{"field": "hybrid.budget_cny", "to": 30000}], "unsupported": [], "question": None},
        ):
            result = parse_agent_request("预算调低一些，其他不变", self.task)
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(result["changes"], [])
        self.assertIn("预算", result["question"])


if __name__ == "__main__":
    unittest.main()
