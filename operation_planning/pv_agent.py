"""Bounded local-model orchestration for the phase-two PV task.

The model selects an allow-listed stage. Every numeric result is already
computed by the deterministic PV tools; this class records whether the local
model can navigate the complete tool sequence without changing the numbers.
"""
from __future__ import annotations
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List

CONFIG_PATH = Path(__file__).resolve().parents[1] / "runtime" / "local_model_config.json"
PV_TOOLS = ["read_load_context", "check_weather_inputs", "generate_candidates", "compute_pv_generation", "match_load_hourly", "calculate_lifecycle", "prepare_report"]

class PVPlanningAgent:
    def __init__(self, max_rounds: int = 8):
        self.max_rounds = max_rounds

    def _model(self, messages: List[Dict[str, Any]], allowed: List[str]) -> Dict[str, Any]:
        config=json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig")); endpoint=config["base_url"].rstrip("/")
        parsed=urllib.parse.urlsplit(endpoint)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1","localhost"} or parsed.path != "/v1": raise RuntimeError("仅允许本地 loopback 模型端点")
        schema={"type":"object","properties":{"action":{"type":"string","enum":allowed},"arguments":{"type":"object"},"message":{"type":"string"}},"required":["action","arguments","message"],"additionalProperties":False}
        payload={"model":config["model_id"],"messages":messages,"temperature":0,"seed":config.get("seed",20260930),"max_tokens":min(512,max(320,int(config.get("max_tokens",192)))),"stream":False,"chat_template_kwargs":{"enable_thinking":False},"response_format":{"type":"json_schema","json_schema":{"name":"pv_tool_call","strict":True,"schema":schema}}}
        req=urllib.request.Request(endpoint+"/chat/completions",data=json.dumps(payload,ensure_ascii=False).encode("utf-8"),headers={"Content-Type":"application/json"},method="POST")
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req,timeout=int(config.get("timeout_seconds",90))) as response: body=response.read().decode("utf-8")
        parsed_body=json.loads(body)
        if parsed_body.get("model") != config["model_id"]: raise RuntimeError("模型身份与本地配置不一致")
        choice=parsed_body["choices"][0]
        if choice.get("finish_reason")=="length": raise RuntimeError("模型输出超长")
        action=json.loads(choice["message"]["content"])
        if set(action) != {"action","arguments","message"} or action["action"] not in allowed or not isinstance(action["arguments"],dict): raise RuntimeError("模型工具调用不符合结构")
        return action

    def run(self, user_request: str, report: Dict[str, Any]) -> Dict[str, Any]:
        state={"trace":[],"done":False}; messages=[{"role":"system","content":"你是能智核光伏配置助手。只按顺序选择一个工具：read_load_context、check_weather_inputs、generate_candidates、compute_pv_generation、match_load_hourly、calculate_lifecycle、prepare_report。数字已经由Python工具计算，不改数字，不编造试点、节能或价格。每轮只输出JSON工具调用。"},{"role":"user","content":json.dumps({"request":user_request,"task_summary":{"site":report.get("scenario",{}).get("site_id"),"year":report.get("scenario",{}).get("year"),"candidate_count":len(report.get("candidates",[])),"recommendation":report.get("recommendation")},"allowed_tools":PV_TOOLS},ensure_ascii=False)}]
        sequence=list(PV_TOOLS)
        for i in range(min(self.max_rounds,len(sequence))):
            started=time.perf_counter(); allowed=[sequence[i]]
            try:
                action=self._model(messages,allowed); name=action["action"]
                result={"stage":name,"numeric_source":"deterministic PV Python tools","success":True}
                if name=="read_load_context": result["load_context"]=report.get("load_context")
                elif name=="check_weather_inputs": result["weather_provenance"]=report.get("weather_provenance")
                elif name=="generate_candidates": result["candidate_capacities_kwp"]= [x.get("capacity_kwp") for x in report.get("candidates",[])]
                elif name=="compute_pv_generation": result["generation_kwh"]= [x.get("generation_kwh") for x in report.get("candidates",[])]
                elif name=="match_load_hourly": result["matching"]= [{k:x.get(k) for k in ("capacity_kwp","self_use_kwh","grid_import_kwh","grid_export_kwh","curtailment_kwh")} for x in report.get("candidates",[])]
                elif name=="calculate_lifecycle": result["economics"]= [{"capacity_kwp":x.get("capacity_kwp"),"status":x.get("economics",{}).get("status"),"npv_cny":x.get("economics",{}).get("npv_cny")} for x in report.get("candidates",[])]
                elif name=="prepare_report": state["done"]=True; result["recommendation"]=report.get("recommendation")
                entry={"round":i+1,"action":name,"arguments":action.get("arguments",{}),"message":action.get("message",""),"result":result,"latency_ms":round((time.perf_counter()-started)*1000,2),"model":"local_configured_model"}; state["trace"].append(entry)
                messages.extend([{"role":"assistant","content":json.dumps(action,ensure_ascii=False)},{"role":"tool","name":name,"content":json.dumps(result,ensure_ascii=False,default=str)}])
                if state["done"]: return {"status":"success","trace":state["trace"],"message":"本地模型完成光伏任务工具序列；数值来自确定性计算工具。"}
                messages.append({"role":"user","content":f"阶段 {name} 已完成。下一轮只调用 {sequence[i+1]}，arguments 使用空对象。"})
            except Exception as exc:
                state["trace"].append({"round":i+1,"action":None,"error":f"{type(exc).__name__}: {exc}","latency_ms":round((time.perf_counter()-started)*1000,2)})
                return {"status":"failed","error":f"{type(exc).__name__}: {exc}","trace":state["trace"],"message":"模型协同失败不影响确定性结果；请复核模型服务或关闭协同。"}
        return {"status":"failed","error":"超过最大模型轮数","trace":state["trace"]}
