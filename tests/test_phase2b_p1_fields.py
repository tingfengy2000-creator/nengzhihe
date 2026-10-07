"""Round-8 P1 response fields, independent of the long annual replay."""

from operation_planning.carbon import carbon_price_scenarios, factor_catalog
from operation_planning.project_load import project_load_context
from operation_planning.tariffs import profile, profile_public_dict, registry


def test_project_load_context_exposes_single_room_kwh_and_service():
    result = {
        "summary": {"electric_kwh": 3.0},
        "single_room_summary": {
            "electric_kwh": 1.5,
            "capacity_shortfall_hours": 2.0,
            "unmet_temp_degree_hours": 0.25,
            "unmet_rh_percent_hours": 0.0,
            "active_hours": 10.0,
        },
        "load_series": {
            "scope": "project; same-room aggregation of single-room trace",
            "units_per_room": 2,
            "project_aggregation": {"level": "project", "room_count": 2},
            "service_scope": "occupied intervals",
        },
    }
    context = project_load_context(result)
    assert context["single_room_annual_kwh"] == 1.5
    assert context["single_room_service_quality"]["status"] == "service_gap"
    assert context["single_room_service_quality"]["gaps"]["capacity_shortfall_hours"] == 2.0


def test_options_expose_carbon_price_scenarios():
    scenarios = carbon_price_scenarios()
    assert scenarios and scenarios[0]["carbon_price_cny_per_t"] == 97.49
    assert scenarios[0]["qualification"] == "unverified_scenario"
    catalog = factor_catalog()
    assert catalog["carbon_price_scenarios"] == scenarios


def test_tariff_registry_and_public_profile_expose_site_ids():
    rows = registry()["tariffs"]
    guangzhou = next(row for row in rows if row["tariff_id"] == "guangzhou_industrial_lt1kv_202610")
    assert "guangzhou" in guangzhou["site_ids"]
    public = profile_public_dict(profile("guangzhou_industrial_lt1kv_202610"))
    assert public["site_ids"] == guangzhou["site_ids"]

