"""Run one public physical SZVAV case through a fresh workbench card.

This thin round5 entry point leaves round4 bytes untouched. The card is
recomputed from the current source record on every run.
"""
from argparse import ArgumentParser
from html import escape
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from adapter import physical
from apar import calibrate, evaluate
from response_evidence import calibrate_response, evaluate_response

NORMAL_IDS = {"5138876d3912", "b5a5b08a1984"}
SOURCE = {
    "name": "OpenEI submission 910 archive / SZVAV.csv",
    "url": "https://data.openei.org/submissions/910",
    "nature": "The downloaded inventory identifies SZVAV as a FLEXLAB X3A controlled test-cell experiment; the OpenEI page summary also describes the collection as AFDD simulation data. This is not an operational-building trial.",
    "sha256": "512992155cb43c576a3ba1e45b37f20966f42c5b05980428fec8008bd054ee93",
    "signals": "1-minute temperature, occupancy, fan and requested actuator commands; no measured damper position or airflow",
}


def clock(minute):
    if minute is None:
        return "—"
    whole = int(round(float(minute)))
    return f"{whole // 60:02d}:{whole % 60:02d}"


def load_case(case_id):
    development = physical("development")
    for case in development:
        if case["id"] == case_id:
            return case, development
    for case in physical("holdout", allow_heldout=True):
        if case["id"] == case_id:
            return case, development
    raise SystemExit(f"unknown public SZVAV case id: {case_id}")


def build(case_id):
    case, development = load_case(case_id)
    normals = [c for c in development if c["id"] in NORMAL_IDS]
    base_cal = calibrate(normals)
    response_cal = calibrate_response(normals, base_cal)
    baseline = evaluate(case, base_cal, method="apar_professional_baseline")
    result = evaluate_response(case, base_cal, response_cal)
    result["method"] = "apar_plus_response_evidence"
    return {
        "source": SOURCE,
        "case_id": case_id,
        "recomputed": True,
        "baseline": baseline,
        "result": result,
        "calibration": {
            "normal_case_ids": sorted(NORMAL_IDS),
            "response_threshold_c": response_cal["threshold_c"],
            "threshold_source": "normal-only q95 + 0.20 C; frozen mechanism v1",
        },
    }


def render(card):
    result = card["result"]
    base = card["baseline"]
    mechanism = result["response_mechanism"]
    windows = mechanism.get("support_windows", [])
    actions = result.get("next_actions", [])
    rows = []
    for window in windows:
        rows.append(
            "<tr><td>{}–{}</td><td>{:.0f}</td><td>{:.2f} °C</td><td>{:.0%}</td></tr>".format(
                clock(window["start_minute"]),
                clock(window["end_minute"]),
                window["minutes"],
                window.get("residual_mean_c", 0.0),
                window["violation_fraction"],
            )
        )
    window_html = "".join(rows) or "<tr><td colspan='4'>没有达到支持阈值的后续窗口</td></tr>"
    action_html = "".join(
        "<li><b>{}</b>：{}</li>".format(escape(a.get("code", "")), escape(a.get("instruction", "")))
        for a in actions
    )
    return """<!doctype html><html lang='zh-CN'><meta charset='utf-8'>
<title>能智核 公共实测核验卡</title>
<style>body{{font-family:Segoe UI,'Microsoft YaHei',sans-serif;background:#f4f7fb;color:#17233b;margin:0;padding:28px}}main{{max-width:1040px;margin:auto}}h1{{margin:0 0 6px}}h2{{font-size:18px;margin:20px 0 10px}}.tag{{display:inline-block;background:#e5efff;color:#1c4e9e;border-radius:14px;padding:5px 10px;margin:4px 4px 12px 0;font-size:13px}}.card{{background:#fff;border-radius:14px;padding:18px 22px;box-shadow:0 3px 18px #193d6b18;margin:14px 0}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}.metric{{font-size:24px;font-weight:700}}.muted{{color:#5d6b82;font-size:13px;line-height:1.55}}table{{width:100%;border-collapse:collapse}}th,td{{padding:9px;border-bottom:1px solid #e7edf5;text-align:left}}ul{{line-height:1.7}}</style><main>
<h1>能智核｜公共建筑风阀疑点核验工作台</h1>
<span class='tag'>公开数据实时重算</span><span class='tag'>物理受控实验</span><span class='tag'>命令不是阀位反馈</span>
<div class='card'><h2>数据来源与适用边界</h2><p><b>{source_name}</b></p><p class='muted'>{nature}<br>{signals}<br>SHA-256：{sha}</p><p class='muted'>每次运行由程序重新计算；本卡不读取故障标签、注入参数或文件名。</p></div>
<div class='grid'><div class='card'><h2>专业规则基线</h2><div class='metric'>{base_state}</div><p class='muted'>规则告警：{base_alarms}<br>风阀疑点：{base_suspicion}</p></div><div class='card'><h2>能智核核验状态</h2><div class='metric'>{state}</div><p class='muted'>风阀疑点：{suspicion}<br>{explanation}</p></div></div>
<div class='card'><h2>告警之后，先查什么？</h2><p>当前缺口：{gap}</p><p>证据：{basis}<br>阈值：{threshold:.2f} °C；支持时长：{support:.0f} 分钟；后续证据等待：{wait} 分钟。</p><table><thead><tr><th>后续支持窗口</th><th>分钟</th><th>平均残差</th><th>超阈比例</th></tr></thead><tbody>{windows}</tbody></table><ul>{actions}</ul></div>
<div class='card'><h2>质量卡</h2><p>状态：{quality}; 实际间隔：{actual}; 时间跨度：{span:.0f} 分钟；有效运行分钟：{occupied:.0f}。</p><p class='muted'>完整定位仍需独立阀位或流量反馈。没有后续可区分窗口时，系统保留未决。</p></div></main></html>""".format(
        source_name=escape(card["source"]["name"]),
        nature=escape(card["source"]["nature"]),
        signals=escape(card["source"]["signals"]),
        sha=card["source"]["sha256"],
        base_state=escape(base["judgment_state"]),
        base_alarms=escape(str(base["apar_alarms"])),
        base_suspicion=escape(str(base["damper_related_suspicion"])),
        state=escape(result["judgment_state"]),
        suspicion=escape(str(result["damper_related_suspicion"])),
        explanation=escape(mechanism.get("explanation", "")),
        gap=escape(mechanism["current_gap"]),
        basis=escape(mechanism["evidence_basis"]),
        threshold=mechanism["threshold_c"],
        support=mechanism["support_minutes"],
        wait=mechanism.get("wait_minutes_from_first_eligible") if mechanism.get("wait_minutes_from_first_eligible") is not None else "—",
        windows=window_html,
        actions=action_html,
        quality=escape(result["quality"]["status"]),
        actual=escape(str(result["quality"]["actual_interval_minutes"])),
        span=result["quality"]["time_span_minutes"],
        occupied=result["quality"]["occupied_minutes"],
    )


def main():
    parser = ArgumentParser()
    parser.add_argument("--case-id", default="19e3873d3c2f")
    parser.add_argument("--output-dir", default=str(ROOT / "integration" / "public_case_output"))
    args = parser.parse_args()
    card = build(args.case_id)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "case_card.json").write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "case_card.html").write_text(render(card), encoding="utf-8")
    print(json.dumps({"case_id": args.case_id, "html": str(out / "case_card.html"), "json": str(out / "case_card.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
