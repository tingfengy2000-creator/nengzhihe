import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIEW = ROOT / "docs" / "handoff" / "replay_viewer" / "replay_cases_v5.json"


def test_v5_tiers_and_no_duplicate_primary_cases():
    data = json.loads(VIEW.read_text(encoding="utf-8"))
    ids = [c["case_id"] for c in data["cases"]]
    assert ids == ["tier_small", "tier_medium", "tier_large", "variant_budget_insufficient", "variant_missing_pv_quote", "variant_roof_area_insufficient"]
    assert "primary_not_worth_it" not in ids and "primary_worth_it" not in ids
    assert data["main_tariff"]["tariff_id"] == "guangzhou_industrial_lt1kv_202610"


def test_v5_capacity_sweep_and_roof_variants():
    data = json.loads(VIEW.read_text(encoding="utf-8"))
    by_id = {c["case_id"]: c for c in data["cases"]}
    assert 5.6 in [r["requested_capacity_kwp"] for r in by_id["tier_small"]["pv_capacity_sweep"]]
    assert 56.0 in [r["requested_capacity_kwp"] for r in by_id["tier_medium"]["pv_capacity_sweep"]]
    assert 320.0 in [r["requested_capacity_kwp"] for r in by_id["tier_large"]["pv_capacity_sweep"]]
    assert by_id["tier_large"]["service_quality"]["status"] == "within_modeled_scope"
    assert by_id["tier_large"]["room"]["area_m2"] if "room" in by_id["tier_large"] else True
    assert by_id["variant_budget_insufficient"]["input"]["roof_area_m2"] == 35
    assert by_id["variant_missing_pv_quote"]["input"]["roof_area_m2"] == 35
    assert by_id["variant_roof_area_insufficient"]["input"]["roof_area_m2"] == 1


def test_v5_selected_capacity_has_full_charts_and_carbon():
    data = json.loads(VIEW.read_text(encoding="utf-8"))
    for case in data["cases"][:3]:
        selected = case["pv_recommendation"]["recommended_capacity_kwp"]
        assert selected in [r["requested_capacity_kwp"] for r in case["pv_capacity_sweep"]]
        assert case["chart"]["scenario_id"] == "S3_pv_wind"
        assert "chart_recommended" in case
        assert "carbon_price_scenarios" in case
        assert all("total_cost_npv_cny" in row and "self_use_rate" in row and "waste_rate" in row and "cost_per_tco2_cny" in row for row in case["pv_capacity_sweep"])

