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

    def test_public_pv_alias_is_supported_by_request_guard(self):
        with patch("operation_planning.agent_parse._read_config", return_value={"model_id": "test"}), patch(
            "operation_planning.agent_parse._model_parse",
            return_value={"changes": [{"field": "pv.capacity_kwp", "to": 2}], "unsupported": [], "question": None},
        ):
            result = parse_agent_request("光伏改为2kWp", self.task)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["changes"][0]["to"], 2)

    def test_model_cannot_convert_kwp_to_w_without_converting_back(self):
        with patch("operation_planning.agent_parse._read_config", return_value={"model_id": "test"}), patch(
            "operation_planning.agent_parse._model_parse",
            return_value={"changes": [{"field": "pv.capacity_kwp", "to": 2000}], "unsupported": [], "question": None},
        ):
            result = parse_agent_request("光伏改为2kWp，其他条件不变", self.task)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["changes"], [])
        self.assertIn("单位", result["reason"])

    def test_explicit_wp_to_kwp_proposal_is_valid(self):
        with patch("operation_planning.agent_parse._read_config", return_value={"model_id": "test"}), patch(
            "operation_planning.agent_parse._model_parse",
            return_value={"changes": [{"field": "pv.capacity_kwp", "to": 2}], "unsupported": [], "question": None},
        ):
            result = parse_agent_request("光伏容量改为2000Wp", self.task)
        self.assertEqual(result["status"], "ok")

    def test_vague_budget_cannot_invent_a_half_budget(self):
        with patch("operation_planning.agent_parse._read_config", return_value={"model_id": "test"}), patch(
            "operation_planning.agent_parse._model_parse",
            return_value={"changes": [{"field": "hybrid.budget_multiplier", "to": 0.5}], "unsupported": [], "question": None},
        ):
            result = parse_agent_request("预算调低一些", self.task)
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(result["changes"], [])
        self.assertIsNotNone(result["question"])

    def test_explicit_existing_value_is_not_ambiguous(self):
        self.task["hybrid"]["allow_export"] = False
        with patch("operation_planning.agent_parse._read_config", return_value={"model_id": "test"}), patch(
            "operation_planning.agent_parse._model_parse",
            return_value={"changes": [{"field": "hybrid.allow_export", "to": False}], "unsupported": [], "question": None},
        ):
            result = parse_agent_request("关闭卖电", self.task)
        self.assertEqual(result["status"], "ok")
        self.assertIsNone(result["question"])

    def _parse_proposal(self, request, changes, question=None):
        with patch("operation_planning.agent_parse._read_config", return_value={"model_id": "test"}), patch(
            "operation_planning.agent_parse._model_parse",
            return_value={"changes": changes, "unsupported": [], "question": question},
        ):
            return parse_agent_request(request, self.task)

    def test_extra_catalogue_field_is_dropped_but_wind_edit_survives(self):
        result = self._parse_proposal("风机改为0台", [
            {"field": "room.equipment_id", "to": "not_a_real_model"},
            {"field": "hybrid.wind.turbine_count", "to": 0},
        ])
        self.assertEqual(result["status"], "ok")
        self.assertEqual([x["field"] for x in result["changes"]], ["hybrid.wind.turbine_count"])
        self.assertEqual(result["dropped"], [{"field": "room.equipment_id", "reason": "用户未提及"}])

    def test_generic_units_do_not_authorize_unrelated_subjects(self):
        result = self._parse_proposal("风机改为0台", [
            {"field": "room.units_per_room", "to": 3},
            {"field": "hybrid.wind.turbine_count", "to": 0},
        ])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["dropped"][0]["field"], "room.units_per_room")
        result = self._parse_proposal("储能单价改为600元/kWh", [
            {"field": "hybrid.budget_cny", "to": 600},
            {"field": "hybrid.import_price_cny_per_kwh", "to": 600},
            {"field": "storage.capacities_kwh", "to": [600]},
            {"field": "storage.quote.cny_per_kwh", "to": 600},
        ])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["changes"]), 1)
        self.assertEqual(len(result["dropped"]), 3)

    def test_requested_invalid_value_still_fails_after_dropping_extra(self):
        result = self._parse_proposal("风机改为2台", [
            {"field": "room.equipment_id", "to": "bad"},
            {"field": "hybrid.wind.turbine_count", "to": 2},
        ])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["changes"], [])
        self.assertEqual(result["dropped"][0]["field"], "room.equipment_id")
        self.assertIn("范围", result["reason"])

    def test_dropped_only_is_not_success_and_never_invents_requested_wind(self):
        result = self._parse_proposal("不要风机了", [{"field": "room.equipment_id", "to": "midea_gaia12"}])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["changes"], [])
        self.assertEqual(len(result["dropped"]), 1)

    def test_tariff_growth_does_not_authorize_a_base_price_edit(self):
        result = self._parse_proposal("电价每年涨3%", [
            {"field": "hybrid.tariff_escalation_rate", "to": .03},
            {"field": "hybrid.import_price_cny_per_kwh", "to": .03},
        ])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["changes"]), 1)
        self.assertEqual(result["dropped"][0]["field"], "hybrid.import_price_cny_per_kwh")

    def test_unsupported_only_content_survives_stray_proposals(self):
        result = self._parse_proposal("让储能按峰谷电价自动套利并保证回本", [
            {"field": "hybrid.allow_export", "to": True},
            {"field": "storage.quote.cny_per_kwh", "to": 100},
            {"field": "hybrid.import_price_cny_per_kwh", "to": .66},
        ])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["changes"], [])
        self.assertTrue(result["unsupported"])
        self.assertEqual(len(result["dropped"]), 3)
        self.assertTrue(any("峰谷套利" in note for note in result["unsupported"]))

    def test_requested_unknown_field_is_not_silently_dropped(self):
        result = self._parse_proposal("光伏装5kWp", [{"field": "pv.requested_capacities_kwp", "to": 5}])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["dropped"], [])

    def test_vague_budget_and_extra_field_do_not_become_an_edit(self):
        result = self._parse_proposal("预算调低一些", [
            {"field": "room.equipment_id", "to": "midea_gaia12"},
            {"field": "hybrid.budget_multiplier", "to": .5},
        ])
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(result["changes"], [])
        self.assertEqual(len(result["dropped"]), 1)

    def test_unsupported_brand_does_not_block_explicit_budget(self):
        result = self._parse_proposal("空调换成格力，预算改为6万", [
            {"field": "room.equipment_id", "to": "gree_non_catalogue"},
            {"field": "hybrid.budget_cny", "to": 60000},
        ])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["changes"][0]["to"], 60000)
        self.assertTrue(result["unsupported"])

    def test_parse_path_calls_no_simulation_or_planning(self):
        with (patch("operation_planning.app._hybrid_capacity_run", side_effect=AssertionError("must not compute")) as hybrid,
              patch("operation_planning.app.simulate_room", side_effect=AssertionError("must not simulate")) as thermal):
            result = self._parse_proposal("光伏改为2kWp", [{"field": "pv.capacity_kwp", "to": 2}])
        self.assertEqual(result["status"], "ok")
        hybrid.assert_not_called()
        thermal.assert_not_called()


if __name__ == "__main__":
    unittest.main()
