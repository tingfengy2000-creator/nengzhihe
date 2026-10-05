"""Short, hand-checkable regression tests for phase-two correctness fixes."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from operation_planning.pv import (  # noqa: E402
    PVQuote,
    PVScenario,
    GenerationSeries,
    _intervals,
    _open_meteo_azimuth_to_pvlib,
    _price_vectors,
    generate_pv,
    lifecycle_compare,
    match_load,
    run_pv_planning,
)
from operation_planning.weather import normalize_preceding_hour_payload
from pvlib import inverter


def _weather(start="2024-06-01T08:00:00", n=4):
    times = [(datetime.fromisoformat(start) + timedelta(hours=i)).isoformat() for i in range(n)]
    return {
        "time": times,
        "interval_seconds": [3600] * n,
        "context": {"site": {"latitude": 23.1291, "longitude": 113.2644, "timezone": "Asia/Shanghai"}},
        "hourly": {
            "shortwave_radiation": [500.0, 700.0, 400.0, 0.0][:n],
            "direct_normal_irradiance": [400.0, 600.0, 300.0, 0.0][:n],
            "diffuse_radiation": [100.0, 120.0, 100.0, 0.0][:n],
            "temperature_2m": [30.0] * n,
            "wind_speed_10m": [10.0] * n,
        },
        "source_file": "short-regression-weather",
    }


def _load(weather, power=1000.0):
    return {"timestamps": list(weather["time"]), "interval_seconds": [3600] * len(weather["time"]), "electric_power_w": [power] * len(weather["time"]), "source": "test", "scope": "short", "service_scope": "cooling_only", "model_version": "test", "assumptions": []}


def _quote():
    return PVQuote(module_cny_per_kwp=1800, inverter_cny_per_kwp=600, structure_cny_per_kwp=500, installation_cny_per_kwp=800, grid_connection_cny=0, maintenance_cny_per_kwp_year=30)


def test_lifecycle_zero_kwp_constant_load():
    start = datetime(2024, 1, 1)
    times = [(start + timedelta(hours=i)).isoformat() for i in range(8760)]
    target = 1249.05760334538
    load = {"timestamps": times, "interval_seconds": [3600] * len(times), "electric_power_w": [target / 8760 * 1000] * len(times)}
    generation = type("G", (), {"timestamps": times, "interval_seconds": [3600] * len(times), "pv_ac_power_w": [0.0] * len(times)})()
    baseline = match_load(load, generation, import_prices=[0.66] * len(times))
    result = lifecycle_compare(baseline, baseline, 0.0, PVScenario(study_years=10, quote=PVQuote()), load_series=load, generation=generation, import_prices=[0.66] * len(times))
    assert abs(result["npv_cny"] + 8243.780182079507) < 1e-8, result["npv_cny"]
    assert [round(row["grid_import_kwh"], 9) for row in result["yearly"][1:]] == [round(target, 9)] * 10
    assert result["capex_cny"] == 0.0


def test_pv_degradation_cannot_reduce_fixed_load_import():
    times = ["2024-01-01T00:00:00", "2024-01-01T01:00:00", "2024-01-01T02:00:00"]
    load = {"timestamps": times, "interval_seconds": [3600] * 3, "electric_power_w": [1000.0] * 3}
    generation = GenerationSeries(timestamps=times, interval_seconds=[3600] * 3, pv_dc_power_w=[500.0] * 3, pv_ac_power_w=[500.0] * 3, ghi_w_m2=[0.0] * 3, dni_w_m2=[0.0] * 3, dhi_w_m2=[0.0] * 3, poa_w_m2=[0.0] * 3, cell_temp_c=[25.0] * 3, source="test", model="test", metadata={})
    baseline = match_load(load, GenerationSeries(**{**generation.__dict__, "pv_ac_power_w": [0.0] * 3}), import_prices=[0.66] * 3)
    matched = match_load(load, generation, import_prices=[0.66] * 3)
    result = lifecycle_compare(matched, baseline, 1.0, PVScenario(study_years=4, annual_degradation=0.1, quote=_quote()), load_series=load, generation=generation, import_prices=[0.66] * 3)
    imports = [row["grid_import_kwh"] for row in result["yearly"][1:]]
    assert imports == sorted(imports)
    assert all(abs(row["load_kwh"] - 3.0) < 1e-9 for row in result["yearly"][1:])


def test_zero_kwp_does_not_inherit_connection_quote():
    scenario = PVScenario(quote=PVQuote(grid_connection_cny=999), requested_capacities_kwp=[0])
    weather = _weather(); load = _load(weather); g = generate_pv(weather, 0, scenario); m = match_load(load, g, import_prices=[0.66] * 4)
    result = lifecycle_compare(m, m, 0, scenario, load_series=load, generation=g, import_prices=[0.66] * 4)
    assert result["status"] == "complete" and result["capex_cny"] == 0.0


def test_direction_mapping_and_interval_midpoint():
    assert [_open_meteo_azimuth_to_pvlib(x) for x in (0, -90, 90, 180)] == [180.0, 90.0, 270.0, 0.0]
    raw = {"hourly": {"time": ["2024-03-01T07:00", "2024-03-01T08:00", "2024-03-01T09:00"], "temperature_2m": [20, 21, 22], "relative_humidity_2m": [50, 50, 50], "surface_pressure": [1010, 1010, 1010], "shortwave_radiation": [100, 700, 900]}}
    boundary = {"hourly": {"time": ["2024-03-01T10:00"], "temperature_2m": [23], "relative_humidity_2m": [50], "surface_pressure": [1010], "shortwave_radiation": [500]}}
    converted = normalize_preceding_hour_payload(raw, calendar_start="2024-03-01T07:00", calendar_end="2024-03-01T10:00", boundary_payload=boundary)
    assert converted["source_timestamp"][1] == "2024-03-01T09:00"
    assert converted["representative_time"][1] == "2024-03-01T08:30"
    weather = _weather(); gen = generate_pv(weather, 1, PVScenario(quote=_quote()))
    assert "midpoint" in gen.metadata["solar_position"]
    assert gen.metadata["representative_time_first"].endswith("08:30:00+08:00")


def test_right_label_radiation_is_converted_to_left_interval():
    raw_times = ["2024-03-01T07:00", "2024-03-01T08:00", "2024-03-01T09:00"]
    raw = {"hourly": {"time": raw_times, "temperature_2m": [20, 21, 22], "relative_humidity_2m": [50, 50, 50], "surface_pressure": [1010, 1010, 1010], "shortwave_radiation": [100, 700, 900]}}
    boundary = {"hourly": {"time": ["2024-03-01T10:00"], "temperature_2m": [23], "relative_humidity_2m": [50], "surface_pressure": [1010], "shortwave_radiation": [500]}}
    normalized = normalize_preceding_hour_payload(raw, calendar_start="2024-03-01T07:00", calendar_end="2024-03-01T10:00", boundary_payload=boundary)
    sem = normalized["_interval_semantics"]
    assert normalized["hourly"]["time"] == raw_times
    assert sem["source_timestamp"][0] == "2024-03-01T08:00"
    assert sem["interval_start"][0] == "2024-03-01T07:00"
    assert sem["representative_time"][0] == "2024-03-01T07:30"
    assert normalized["hourly"]["shortwave_radiation"][0] == 700
    assert normalized["hourly"]["temperature_2m"][0] == 20


def test_interval_normalization_crosses_leap_day_and_year_edges():
    start = datetime(2024, 2, 28, 23); end = datetime(2024, 3, 1, 2)
    times = [(start + timedelta(hours=i)).isoformat(timespec="minutes") for i in range(int((end - start).total_seconds() // 3600))]
    raw = {"hourly": {"time": times, "temperature_2m": list(range(len(times))), "relative_humidity_2m": [50] * len(times), "surface_pressure": [1010] * len(times), "shortwave_radiation": [100] * len(times)}}
    boundary = {"hourly": {"time": [end.isoformat(timespec="minutes")], "temperature_2m": [99], "relative_humidity_2m": [50], "surface_pressure": [1010], "shortwave_radiation": [100]}}
    normalized = normalize_preceding_hour_payload(raw, calendar_start=start.isoformat(timespec="minutes"), calendar_end=end.isoformat(timespec="minutes"), boundary_payload=boundary)
    assert len(normalized["hourly"]["time"]) == 27
    assert normalized["_interval_semantics"]["interval_end"][-1] == "2024-03-01T02:00"
    assert normalized["hourly"]["time"][1].startswith("2024-02-29")


def test_inverter_rated_ac_boundary_uses_pdc0_input_definition():
    dc_rated_w = 2000.0; ac_rated_w = 1700.0; eta = 0.96; passed_pdc0 = ac_rated_w / eta
    output = float(inverter.pvwatts(dc_rated_w, pdc0=passed_pdc0, eta_inv_nom=eta, eta_inv_ref=0.9637))
    assert abs(output - 1700.0) < 1e-9
    assert abs(float(inverter.pvwatts(dc_rated_w, pdc0=ac_rated_w, eta_inv_nom=eta, eta_inv_ref=0.9637)) - 1632.0) < 1e-9


def test_tou_price_splits_inside_physical_interval():
    scenario = PVScenario(tariff_id="custom_user", custom_tariff={"effective_start": "2024-01-01", "effective_end": "2024-01-01", "periods": [{"name": "flat", "start": "00:00", "end": "24:00", "price": 0.5}, {"name": "peak", "start": "08:30", "end": "09:00", "price": 1.0}]})
    prices, meta = _price_vectors(scenario, ["2024-01-01T08:00", "2024-01-01T09:00"], [3600, 3600])
    assert abs(prices[0] - 0.75) < 1e-12
    assert len(meta["interval_examples"][0]["segments"]) == 2


def test_tou_split_crosses_midnight():
    scenario = PVScenario(tariff_id="custom_user", custom_tariff={"effective_start": "2024-01-01", "effective_end": "2024-01-02", "periods": [{"name": "flat", "start": "00:00", "end": "24:00", "price": 0.5}, {"name": "peak", "start": "23:30", "end": "24:00", "price": 1.0}, {"name": "valley", "start": "00:00", "end": "00:30", "price": 0.2}]})
    prices, meta = _price_vectors(scenario, ["2024-01-01T23:30", "2024-01-02T00:30"], [3600, 3600])
    assert abs(prices[0] - 0.6) < 1e-12
    assert len(meta["interval_examples"][0]["segments"]) == 2


def test_real_interval_and_nonfinite_guards():
    times = ["2024-01-01T00:00:00", "2024-01-01T01:00:00", "2024-01-01T02:00:00"]
    assert _intervals(times, [3600, 3600, 3600]) == [3600, 3600, 3600]
    try:
        _intervals(times, [60, 60, 60])
    except ValueError:
        pass
    else:
        raise AssertionError("declared interval mismatch must reject")
    weather = _weather(); weather["hourly"]["shortwave_radiation"][1] = float("nan")
    try:
        generate_pv(weather, 1, PVScenario(quote=_quote()))
    except ValueError:
        pass
    else:
        raise AssertionError("NaN radiation must reject")


def test_missing_quote_and_export_price_are_not_zero():
    weather = _weather(); load = _load(weather)
    incomplete = run_pv_planning(load_result={"load_series": load}, weather=weather, scenario=PVScenario(requested_capacities_kwp=[0, 1], quote=PVQuote()))
    assert incomplete["recommendation"]["status"] == "not_available"
    export_missing = run_pv_planning(load_result={"load_series": load}, weather=weather, scenario=PVScenario(requested_capacities_kwp=[0, 1], quote=_quote(), allow_export=True))
    one = next(x for x in export_missing["candidates"] if x["capacity_kwp"] == 1)
    assert one["economics"]["status"] == "incomplete_economics"
    assert export_missing["recommendation"]["status"] == "not_available"


def test_tou_and_service_gap_are_explicit():
    weather = _weather(start="2024-01-01T08:00:00"); load = _load(weather)
    tariff = {"effective_start": "2024-01-01", "effective_end": "2024-01-01", "periods": [{"name": "flat", "start": "00:00", "end": "24:00", "price": 0.5}, {"name": "peak", "start": "08:00", "end": "10:00", "price": 1.0}]}
    scenario = PVScenario(requested_capacities_kwp=[0], quote=PVQuote(), tariff_id="custom_user", custom_tariff=tariff)
    report = run_pv_planning({"load_series": load, "summary": {"capacity_shortfall_hours": 1.0, "unmet_temp_degree_hours": 0, "unmet_rh_percent_hours": 0}}, weather, scenario)
    assert report["tariff"]["tariff_id"] == "custom_user" and report["service_quality"]["status"] == "service_gap"
    assert report["recommendation"].get("service_qualification")


def run_all():
    for name in sorted(globals()):
        if name.startswith("test_"):
            globals()[name]()
    print("phase2a correctness tests: PASS")


if __name__ == "__main__":
    run_all()
