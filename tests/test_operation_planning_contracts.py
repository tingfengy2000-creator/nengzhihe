from operation_planning.schemas import TaskSpec, stable_hash
from operation_planning.search import generate_plans


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
