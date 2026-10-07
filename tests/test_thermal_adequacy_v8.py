"""14.1 P0 thermal sizing contract.

The default 35 m² room is an explicit lightweight-office planning scenario,
not a calibrated building.  Pre-cooling energy remains in the load while
service adequacy is scored only during occupied intervals.
"""
from operation_planning.app import _thermal_capacity_sweep
from operation_planning.weather import load_weather
from operation_planning.thermal_model import RoomSpec, simulate_room


def _default_room_payload(max_units=3):
    return {
        "site_id": "guangzhou",
        "year": 2024,
        "max_units": max_units,
        "room": {
            "area_m2": 35,
            "height_m": 3,
            "equipment_id": "midea_msagbu12_mox201",
            "start_hour": 8,
            "end_hour": 18,
            "weekdays_only": True,
            "people_count": 4,
            "equipment_gain_w": 300,
        },
    }


def test_default_35m2_room_uses_explicit_lightweight_mass_and_pre_cooling():
    result = simulate_room(load_weather("guangzhou", 2024), RoomSpec())
    assert result["room"]["thermal_mass_kj_per_m2"] == 100.0
    assert result["room"]["pre_cool_minutes"] == 60
    assert len(result["load_series"]["active"]) == len(result["load_series"]["timestamps"])
    assert len(result["load_series"]["cooling_active"]) == len(result["load_series"]["timestamps"])
    assert all(
        active or shortfall == 0
        for active, shortfall in zip(result["load_series"]["active"], result["load_series"]["capacity_shortfall_w"])
    )
    assert result["summary"]["pre_cooling_hours"] > 0
    assert result["load_series"]["adequacy_rule"]["name"] == "occupied_hours_only_with_bounded_precooling"


def test_thermal_size_default_35m2_minimum_two_units_without_fabricated_success():
    report = _thermal_capacity_sweep(_default_room_payload())
    assert report["minimum_adequate_units_per_room"] == 2
    one = report["candidates"][0]
    two = report["candidates"][1]
    assert one["service_status"] == "service_gap"
    assert one["capacity_shortfall_hours"] > 0
    assert two["service_status"] == "within_modeled_scope"
    assert two["capacity_shortfall_hours"] == 0
    assert report["adequacy_rule"]["pre_cool_minutes"] == 60
    assert report["adequacy_rule"]["thermal_mass_kj_per_m2"] == 100.0
