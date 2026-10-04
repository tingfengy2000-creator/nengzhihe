from operation_planning.schemas import TaskSpec, stable_hash
from operation_planning.search import generate_plans
from operation_planning.external_physical import summarize


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
