"""Official BOPTEST v0.9.0 adapter plus the local bestest_air FMU backend."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any, Dict, Iterable, Optional
from urllib import request as urlrequest


ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "vendor" / "project1-boptest"
FMU_PATH = VENDOR / "testcases" / "bestest_air" / "models" / "wrapped.fmu"
RUNNER = ROOT / "runtime" / "local_fmu_runner.py"
LIB_DIR = ROOT / "runtime" / "boptest_linux" / "lib4" / "usr" / "lib" / "x86_64-linux-gnu"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    rest = resolved.as_posix().split(":", 1)[-1]
    return f"/mnt/{drive}{rest}"


class BOPTESTHTTPClient:
    """Small stdlib client for the official public/local REST interface."""

    def __init__(self, base_url: str = "https://api.boptest.net", timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.test_id: Optional[str] = None

    def _call(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urlrequest.Request(self.base_url + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        with urlrequest.urlopen(req, timeout=self.timeout) as response:
            body = response.read().decode("utf-8")
        return json.loads(body) if body else None

    def version(self) -> Any:
        return self._call("GET", "/version")

    def select(self, testcase: str = "bestest_air") -> Any:
        value = self._call("POST", f"/testcases/{testcase}/select")
        self.test_id = value.get("testid") if isinstance(value, dict) else None
        return value

    def _tid(self) -> str:
        if not self.test_id:
            raise RuntimeError("先 select testcase")
        return self.test_id

    def name(self) -> Any:
        return self._call("GET", f"/name/{self._tid()}")

    def measurements(self) -> Any:
        return self._call("GET", f"/measurements/{self._tid()}")

    def inputs(self) -> Any:
        return self._call("GET", f"/inputs/{self._tid()}")

    def forecast_points(self) -> Any:
        return self._call("GET", f"/forecast_points/{self._tid()}")

    def forecast(self, point_names: Iterable[str], horizon: int = 86400) -> Any:
        query = ",".join(point_names)
        return self._call("GET", f"/forecast/{self._tid()}?point_names={query}&horizon={int(horizon)}")

    def initialize(self, start_time: int = 0, warmup_period: int = 0, **kwargs: Any) -> Any:
        payload = {"start_time": start_time, "warmup_period": warmup_period, **kwargs}
        return self._call("PUT", f"/initialize/{self._tid()}", payload)

    def step(self, inputs: Dict[str, float]) -> Any:
        return self._call("POST", f"/step/{self._tid()}", inputs)

    def advance(self, **kwargs: Any) -> Any:
        return self._call("POST", f"/advance/{self._tid()}", kwargs)

    def results(self, start_time: int, final_time: int, **kwargs: Any) -> Any:
        payload = {"start_time": start_time, "final_time": final_time, **kwargs}
        return self._call("PUT", f"/results/{self._tid()}", payload)

    def kpi(self) -> Any:
        return self._call("GET", f"/kpi/{self._tid()}")

    def release(self) -> Any:
        if not self.test_id:
            return None
        result = self._call("PUT", f"/stop/{self.test_id}")
        self.test_id = None
        return result


class LocalBestestAirFMUAdapter:
    """Run the pinned official FMU via WSL without Docker or paid services."""

    testcase = "bestest_air"
    version = "v0.9.0"
    commit = "9b1610bf7a108826bb3d22c72bffd2d71d7bb0a9"

    def __init__(self, fmu_path: Path = FMU_PATH, step_seconds: int = 900, timeout: int = 900):
        self.fmu_path = Path(fmu_path)
        self.step_seconds = step_seconds
        self.timeout = timeout
        if not self.fmu_path.exists():
            raise FileNotFoundError(f"未找到官方 FMU：{self.fmu_path}; 请先运行 fetch_boptest.ps1")
        self.fmu_sha256 = sha256(self.fmu_path)

    def provenance(self) -> Dict[str, Any]:
        return {
            "testcase": self.testcase,
            "version": self.version,
            "repository_commit": self.commit,
            "fmu_path": str(self.fmu_path),
            "fmu_sha256": self.fmu_sha256,
            "license": "BSD-3-Clause (project1-boptest repository; verify before redistribution)",
            "execution": "official FMI 2.0 co-simulation FMU, WSL local replay",
        }

    def select_case(self) -> Dict[str, Any]:
        return self.provenance()

    def get_measurements(self) -> Dict[str, Any]:
        return {
            "zon_reaTRooAir_y": {"unit": "K", "description": "zone air temperature"},
            "fcu_reaPCoo_y": {"unit": "W", "description": "cooling electric power"},
            "fcu_reaPFan_y": {"unit": "W", "description": "fan electric power"},
            "fcu_reaPHea_y": {"unit": "W", "description": "heating gas power"},
        }

    def get_inputs(self) -> Dict[str, Any]:
        return {
            "con_oveTSetCoo_activate": {"unit": "1", "type": "Boolean"},
            "con_oveTSetCoo_u": {"unit": "K", "type": "Real"},
            "con_oveTSetHea_activate": {"unit": "1", "type": "Boolean"},
            "con_oveTSetHea_u": {"unit": "K", "type": "Real"},
        }

    def get_forecast_points(self) -> Dict[str, Any]:
        return {"status": "local FMU adapter does not alter weather or clone state", "points": []}

    def initialize(self, task: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
        return {"initialized": True, "simulation_day": task["simulation_day"], "plan_id": plan["plan_id"], "state_cloning": False}

    def step(self, *_: Any, **__: Any) -> Dict[str, Any]:
        raise NotImplementedError("本地 FMU 后端按同一历史条件整段回放；不伪造任意状态 step")

    def advance(self, *_: Any, **__: Any) -> Dict[str, Any]:
        raise NotImplementedError("本地 FMU 后端不改变天气或内部状态")

    def run(self, task: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
        request = {
            "fmu_path": _wsl_path(self.fmu_path),
            "simulation_day": int(task["simulation_day"]),
            "business_start_hour": int(task["business_start_hour"]),
            "business_end_hour": int(task["business_end_hour"]),
            "lower_temp_c": float(task["lower_temp_c"]),
            "upper_temp_c": float(task["upper_temp_c"]),
            "tolerance_c": float(task["tolerance_c"]),
            "recovery_hours": int(task.get("recovery_hours", 24)),
            "segments": plan.get("segments", []),
            "step_seconds": self.step_seconds,
        }
        command = [
            "wsl.exe", "-d", "Ubuntu-24.04", "--", "bash", "-lc",
            f"export LD_LIBRARY_PATH='{_wsl_path(LIB_DIR)}'; python3 '{_wsl_path(RUNNER)}'",
        ]
        started = time.perf_counter()
        completed = subprocess.run(
            command,
            input=json.dumps(request, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.timeout,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"WSL FMU runner failed ({completed.returncode}): {completed.stderr[-2000:]}")
        try:
            # WSL may prepend a locale warning to stdout.  The runner emits
            # exactly one JSON object; decode from its first object boundary.
            raw = completed.stdout.lstrip("\ufeff\r\n \t")
            if not raw.startswith("{"):
                raw = raw[raw.find("{"):]
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"WSL FMU runner returned non-JSON: {completed.stdout[-1000:]}") from exc
        if not payload.get("ok"):
            raise RuntimeError(payload.get("error", "FMU runner failed"))
        data = payload["result"]
        data["adapter_runtime_seconds"] = time.perf_counter() - started
        return data
