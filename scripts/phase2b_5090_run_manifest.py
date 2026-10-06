"""Run the bounded phase2B 5090 verification set and record provenance."""
from __future__ import annotations
import hashlib, json, os, platform, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "operation_planning" / "results" / "phase2b_semantics_5090"


def now(): return datetime.now(timezone.utc).isoformat()
def sha(path):
    h = hashlib.sha256();
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""): h.update(block)
    return h.hexdigest()


def run(command):
    started = now(); t0 = time.perf_counter()
    p = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, encoding="utf-8", errors="replace")
    ended = now()
    return {"command": command, "started_at": started, "ended_at": ended, "wall_time_ms": round((time.perf_counter() - t0) * 1000, 2), "exit_code": p.returncode, "stdout_tail": p.stdout[-2000:], "stderr_tail": p.stderr[-2000:], "status": "passed" if p.returncode == 0 else "failed"}


def main():
    commands = [[sys.executable, "tests/test_phase2b_wind.py"], [sys.executable, "tests/test_phase2a_correctness.py"], [sys.executable, "tests/test_phase2_pv.py"], [sys.executable, "scripts/phase2b_wind_agent.py"], [sys.executable, "scripts/phase2b_wind_demo.py"], [sys.executable, "scripts/phase2b_5090_replay.py"]]
    records = [run(command) for command in commands]
    tracked = [ROOT / "operation_planning" / "results" / "phase2b_semantics_5090" / name for name in ("agent_task_records.json", "guangzhou_2024_full_chain.json", "fixed_configuration_9_groups.json", "replay_cases.json")]
    config = ROOT / "runtime" / "local_model_config.json"; profile = ROOT / "operation_planning" / "data" / "wind_profiles" / "sd6_swcc_11_04.json"
    try: commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception: commit = "unknown"
    manifest = {"run_id": "phase2b-5090-semantics-final", "source_commit": commit, "machine_role": "5090", "gpu_probe": "nvidia-smi --query-gpu=name,driver_version --format=csv,noheader", "python": sys.version, "platform": platform.platform(), "model_config_sha256": sha(config), "model_id": json.loads(config.read_text(encoding="utf-8-sig"))["model_id"], "model_revision": json.loads(config.read_text(encoding="utf-8-sig"))["model_revision"], "external_api": False, "wind_profile_sha256": sha(profile), "commands": records, "outputs": [{"path": str(path.relative_to(ROOT)), "sha256": sha(path), "bytes": path.stat().st_size} for path in tracked if path.exists()], "source_scope": "public cached Guangzhou/Beijing/Harbin weather and public SD6 curve; no private data or model weights uploaded", "status": "READY_FOR_REVIEW" if all(row["exit_code"] == 0 for row in records) else "HAS_FAILURE"}
    OUT.mkdir(parents=True, exist_ok=True); (OUT / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"run_id": manifest["run_id"], "source_commit": commit, "status": manifest["status"], "commands": len(records)}, ensure_ascii=False))


if __name__ == "__main__": main()
