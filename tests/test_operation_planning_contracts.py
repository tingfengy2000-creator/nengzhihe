from operation_planning.schemas import TaskSpec, stable_hash
from operation_planning.search import generate_plans
from operation_planning.external_physical import summarize
from datetime import date
from operation_planning.tariffs import TARIFFS, integrate_power, rate_at
from operation_planning.weather import load_weather, parse_user_csv
from operation_planning.thermal_model import RoomSpec, simulate_room
from operation_planning.psychrometrics import humidity_ratio, enthalpy_kj_kg, wet_bulb_c
from operation_planning.lifecycle import life_cycle_cost


def test_task_rejects_unsupported_scope_and_grid_is_bounded():
    task = TaskSpec(task_id="t", max_candidates=36)
    assert not task.validate()
    plans = generate_plans(task)
    assert len(plans) <= 36
    assert plans[0].plan_id == "baseline"


def test_physical_cache_key_is_stable_for_same_inputs():
    first = stable_hash({"simulation_day": 153, "plan": "baseline"})
    second = stable_hash({"plan": "baseline", "simulation_day": 153})
    assert first == second


def test_external_physical_adapter_fails_closed_without_planning_channels():
    result = summarize()
    assert result["counts"]["date_blocks"] == 6
    assert result["planning_eligibility"]["status"] == "insufficient_for_counterfactual_plan"
    assert result["planning_eligibility"]["required_channels"]["zone_air_temperature"] is False
    assert "Fault Detection Ground Truth" in result["adapter"]["excluded_from_diagnostics"]


def test_candidate_segments_follow_task_hours_and_cover_categories():
    task = TaskSpec(task_id="hours", business_start_hour=7, business_end_hour=17, max_candidates=9)
    plans = generate_plans(task)
    assert any(s.start_minute == 390 and s.end_minute == 420 for p in plans if p.kind == "pre_cool" for s in p.segments)
    assert any(p.kind == "setpoint_shift" for p in plans)
    assert any(p.kind == "pre_cool_and_shift" for p in plans)


def test_verified_tariff_rates_and_jump_safe_integration():
    tariff = TARIFFS["fujian_industrial_lt1kv_202607"]
    assert rate_at(tariff, date(2026, 7, 15), 7 * 3600)[0] == "valley"
    assert rate_at(tariff, date(2026, 7, 15), 11 * 3600)[0] == "super_peak"
    # A long interval from the simulation-day boundary crossing 08:00 is
    # split at the tariff boundary (times are seconds from the model day).
    cost, by_period = integrate_power([0, 9 * 3600], [1000, 1000], tariff, date(2026, 7, 15), 0, 9 * 3600)
    expected = 8.0 * 0.40579316 + 1.0 * 0.64033775
    assert abs(cost - expected) < 1e-9
    assert set(by_period) == {"valley", "flat"}


def test_first_stage_weather_and_heat_moisture_response():
    weather = load_weather("guangzhou", 2024)
    result_60 = simulate_room(weather, RoomSpec(rh_setpoint_percent=60, cooling_setpoint_c=26, equipment_id="midea_msagbu12_mox201"))
    result_50 = simulate_room(weather, RoomSpec(rh_setpoint_percent=50, cooling_setpoint_c=26, equipment_id="midea_msagbu12_mox201"))
    assert len(result_60["rows"]) >= 8760
    assert result_60["summary"]["latent_cooling_kwh"] > 0
    assert result_50["summary"]["latent_cooling_kwh"] >= result_60["summary"]["latent_cooling_kwh"]
    assert result_60["rows"][0]["timestamp"].startswith("2024-")
    assert "outdoor_enthalpy_kj_kg" in result_60["rows"][0]


def test_psychrolib_reference_values_are_si_and_monotone():
    w60 = humidity_ratio(26.0, 60.0, 101325.0)
    w80 = humidity_ratio(26.0, 80.0, 101325.0)
    assert 0.012 < w60 < 0.0135
    assert w80 > w60
    assert 50 < enthalpy_kj_kg(26.0, w60) < 65
    assert 15 < wet_bulb_c(26.0, 60.0) < 24


def test_model_keeps_capacity_shortfall_and_load_series_provenance():
    result = simulate_room(load_weather("guangzhou", 2024), RoomSpec(equipment_count=1))
    assert result["summary"]["capacity_shortfall_hours"] > 0
    assert len(result["load_series"]["timestamps"]) == len(result["rows"])
    assert all(x["interval_seconds"] == 3600 for x in result["rows"][:10])


def test_lifecycle_missing_quote_does_not_become_zero():
    result = simulate_room(load_weather("guangzhou", 2024), RoomSpec())
    cost = life_cycle_cost(result, price_cny_per_kwh=0.66)
    assert cost["lifecycle"]["status"] == "incomplete_quote"
    assert "设备报价" in cost["lifecycle"]["missing"]


def test_user_weather_csv_is_checked_and_labeled():
    csv = "timestamp,temp_c,rh_percent,pressure_hpa,solar_w_m2\n2024-07-01T00:00,28,80,1005,0\n2024-07-01T01:00,28,80,1005,0\n"
    weather = parse_user_csv(csv)
    assert weather["context"]["dataset_kind"] == "user_uploaded"
    assert weather["source_file"] == "user_csv"
