"""Contract checks for the verified Guangzhou tariff and hot-day rule."""

from datetime import date

from operation_planning.pv import PVScenario, _price_vectors
from operation_planning.tariffs import (
    GUANGZHOU_202610_OFFICIAL_URL,
    high_temperature_dates,
    profile,
    rate_at,
)


def test_verified_profile_and_hot_day_rate() -> None:
    tariff = profile("guangzhou_industrial_lt1kv_202610")
    assert tariff.verified is True
    assert tariff.source_url == GUANGZHOU_202610_OFFICIAL_URL
    hot = high_temperature_dates(
        ["2024-10-10T10:00", "2024-10-10T15:00", "2024-10-11T12:00"],
        [35.1, 35.0, 34.9],
    )
    assert hot == ["2024-10-10"]
    assert rate_at(tariff, date(2024, 10, 10), 11 * 3600, validate_dates=False)[0] == "peak"
    assert rate_at(tariff, date(2024, 10, 10), 11 * 3600, validate_dates=False, high_temp_dates=hot)[0] == "super_peak"
    assert rate_at(tariff, date(2024, 10, 11), 11 * 3600, validate_dates=False, high_temp_dates=hot)[0] == "peak"


def test_pv_price_vector_records_hot_day_count() -> None:
    timestamps = ["2024-10-10T10:00", "2024-10-10T11:00"]
    weather = {"time": timestamps, "hourly": {"temperature_2m": [35.2, 35.2]}}
    scenario = PVScenario(
        tariff_id="guangzhou_industrial_lt1kv_202610",
        tariff_application="current_tariff_on_reference_weather",
        roof_area_m2=10,
    )
    prices, meta = _price_vectors(scenario, timestamps, [3600, 3600], weather)
    assert len(prices) == 2
    assert meta["high_temp_super_peak_day_count"] == 1
    assert meta["high_temp_super_peak_days"] == ["2024-10-10"]
    assert meta["super_peak_day_count"] == 1
    # 10–11 is ordinary peak; 11–12 is the high-temperature super-peak window.
    assert all(abs(a - b) < 1e-12 for a, b in zip(prices, [1.34176875, 1.67036875]))


if __name__ == "__main__":
    test_verified_profile_and_hot_day_rate()
    test_pv_price_vector_records_hot_day_count()
    print("verified tariff contracts: PASS")
