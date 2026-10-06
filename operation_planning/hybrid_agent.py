"""Local-model task execution for the phase-two wind/PV comparison."""
from __future__ import annotations
import json, re, time, urllib.parse, urllib.request
from pathlib import Path
from typing import Any, Dict, List
from .thermal_model import RoomSpec, simulate_room
from .weather import load_weather, load_pv_weather
from .pv import scenario_from_dict
from .wind import WindScenario, WindQuote, WindTurbineProfile
from .hybrid import HybridScenario, hybrid_task_from_dict, run_hybrid_planning

CONFIG_PATH=Path(__file__).resolve().parents[1]/"runtime"/"local_model_config.json"
TOOLS=["interpret_request","validate_task","read_load_context","check_weather_inputs","select_wind_profile","compute_generation","match_supply_demand","calculate_lifecycle","prepare_report"]

class HybridPlanningAgent:
    def __init__(self,max_rounds:int=12): self.max_rounds=max_rounds
    def _model(self,messages:List[Dict[str,Any]],allowed:List[str])->Dict[str,Any]:
        config=json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig")); endpoint=config["base_url"].rstrip("/"); parsed=urllib.parse.urlsplit(endpoint)
        if parsed.scheme!="http" or parsed.hostname not in {"127.0.0.1","localhost"} or parsed.path!="/v1": raise RuntimeError("仅允许本地loopback模型端点")
        schema={"type":"object","properties":{"action":{"type":"string","enum":allowed},"arguments":{"type":"object"},"message":{"type":"string"}},"required":["action","arguments","message"],"additionalProperties":False}
        body={"model":config["model_id"],"messages":messages,"temperature":0,"seed":config.get("seed",20260930),"max_tokens":512,"stream":False,"chat_template_kwargs":{"enable_thinking":False},"response_format":{"type":"json_schema","json_schema":{"name":"hybrid_tool_call","strict":True,"schema":schema}}}
        req=urllib.request.Request(endpoint+"/chat/completions",data=json.dumps(body,ensure_ascii=False).encode(),headers={"Content-Type":"application/json"},method="POST")
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=int(config.get("timeout_seconds",90))) as response: payload=json.loads(response.read().decode())
        if payload.get("model")!=config["model_id"]: raise RuntimeError("模型身份与本地配置不一致")
        action=json.loads(payload["choices"][0]["message"]["content"])
        if set(action)!={"action","arguments","message"} or action["action"] not in allowed or not isinstance(action["arguments"],dict): raise RuntimeError("模型工具调用不符合结构")
        return action
    @staticmethod
    def _changes(request:str,args:Dict[str,Any])->Dict[str,Any]:
        ch={k:v for k,v in args.items() if k in {"budget_cny","budget_multiplier","pv_capacity_kwp","wind_turbine_count","hub_height_m","hub_height_max_m","allow_export","export_price_cny_per_kwh"}}
        # Models sometimes describe a relative change as an expression in
        # budget_cny.  The validated multiplier is the actual task value; an
        # unevaluable expression must not be handed to float() as if it were
        # a number.
        if "budget_cny" in ch:
            try:
                ch["budget_cny"] = float(ch["budget_cny"])
            except (TypeError, ValueError):
                if "budget_multiplier" in ch or re.search(r"预算\s*(?:减少|下调)\s*(?:三分之一|一半)", request):
                    ch.pop("budget_cny", None)
                else:
                    raise ValueError("模型给出的budget_cny不是可解析数值")
        m=re.search(r"预算(?:改为|调整为|设为)\s*([0-9]+(?:\.[0-9]+)?)",request); 
        if m: ch["budget_cny"]=float(m.group(1))
        if re.search(r"预算\s*(?:减少|下调)\s*三分之一", request): ch["budget_multiplier"]=2/3
        if re.search(r"预算\s*(?:减少|下调)\s*一半", request): ch["budget_multiplier"]=0.5
        m=re.search(r"(?:塔架|轮毂|高度)最多\s*([0-9]+(?:\.[0-9]+)?)\s*米",request)
        if m: ch["hub_height_max_m"]=float(m.group(1))
        m=re.search(r"(?:塔架|轮毂|高度)(?:改为|调整为|设为)\s*([0-9]+(?:\.[0-9]+)?)\s*米",request)
        if m: ch["hub_height_m"]=float(m.group(1))
        if "允许外送" in request: ch["allow_export"]=True
        if "不允许外送" in request: ch["allow_export"]=False
        if "没有卖电价格" in request or "缺少外送价" in request: ch["export_price_cny_per_kwh"]=None
        if "使用时段改到晚上" in request: ch["start_hour"],ch["end_hour"]=18,22
        m=re.search(r"使用时段(?:改为|改成|调整为|设为)\s*(\d{1,2})\s*点\s*[-至到]\s*(\d{1,2})\s*点",request)
        if m: ch["start_hour"],ch["end_hour"]=int(m.group(1)),int(m.group(2))
        return ch
    @staticmethod
    def _apply(base:Dict[str,Any],ch:Dict[str,Any])->Dict[str,Any]:
        out={**base,"room":dict(base.get("room") or {}),"hybrid":dict(base.get("hybrid") or {})}; out["hybrid"]["wind"]=dict(out["hybrid"].get("wind") or {})
        for k,v in ch.items():
            if k in {"start_hour","end_hour"}: out["room"][k]=int(v)
            elif k=="wind_turbine_count": out["hybrid"]["wind"]["turbine_count"]=int(v)
            elif k in {"hub_height_m","hub_height_max_m"}: out["hybrid"]["wind"][k]=float(v)
            elif k=="budget_multiplier":
                current=out["hybrid"].get("budget_cny")
                if current is not None: out["hybrid"]["budget_cny"]=float(current)*float(v)
            else: out["hybrid"][k]=v
        return out
    def _tool(self,name:str,state:Dict[str,Any],args:Dict[str,Any])->Dict[str,Any]:
        if name=="interpret_request": state["changes"]=self._changes(state["request"],args); state["payload"]=self._apply(state["payload"],state["changes"]); return {"modifications":state["changes"],"numeric_source":"bounded request parser and model arguments"}
        if name=="validate_task":
            p=state["payload"]; state["room"]=RoomSpec(**{k:v for k,v in (p.get("room") or {}).items() if k in RoomSpec.__dataclass_fields__}); state["pv"],state["hybrid"]=hybrid_task_from_dict(p,site_id=state["site_id"],year=state["year"])
            if state["hybrid"].allow_export and state["hybrid"].export_price_cny_per_kwh is None: return {"status":"needs_clarification","question":"已允许外送但没有外送价格；请选择只保留物理结果，或提供外送价。"}
            return {"status":"validated","budget_cny":state["hybrid"].budget_cny,"turbine_count":state["hybrid"].wind.turbine_count}
        if name=="read_load_context": state["load_weather"]=state["payload"].get("weather") or load_weather(state["site_id"],state["year"]); state["pv_weather"]=state["payload"].get("pv_weather") or load_pv_weather(state["site_id"],state["year"]); state["load_result"]=simulate_room(state["load_weather"],state["room"]); return {"load_kwh":state["load_result"].get("summary",{}).get("electric_kwh"),"service":state["load_result"].get("summary",{})}
        if name=="check_weather_inputs":
            if state["load_result"]["load_series"]["timestamps"]!=state["pv_weather"]["time"]: raise ValueError("负荷与风光天气时间轴不一致")
            return {"source_file":state["pv_weather"].get("source_file"),"hash":state["pv_weather"].get("hash"),"records":len(state["pv_weather"].get("time",[]))}
        if name=="select_wind_profile": state["profile"]=WindTurbineProfile.from_file(); return {"profile_id":state["profile"].profile_id,"source_url":state["profile"].source_url}
        if name in {"compute_generation","match_supply_demand","calculate_lifecycle"}:
            # The first computational tool performs the real full plan. Later
            # tools inspect its intermediate result instead of running all
            # weather, generation, matching and lifecycle steps again.
            if "report" not in state:
                state["report"] = run_hybrid_planning(state["load_result"],state["pv_weather"],state["pv"],state["hybrid"],state["profile"])
                state["full_plan_calls"] = int(state.get("full_plan_calls",0)) + 1
            report=state["report"]
            if name=="compute_generation":
                return {"scenario_count":len(report["candidates"]),"generation_kwh":[c["generation_kwh"] for c in report["candidates"]],"full_plan_calls":state["full_plan_calls"],"numeric_source":"single deterministic full-plan tool"}
            if name=="match_supply_demand":
                return {"scenario_count":len(report["candidates"]),"matching_kwh":[{"scenario_id":c["scenario_id"],"self_use_kwh":c["self_use_kwh"],"grid_import_kwh":c["grid_import_kwh"],"curtailment_kwh":c["curtailment_kwh"]} for c in report["candidates"]],"full_plan_calls":state["full_plan_calls"],"numeric_source":"inspect cached intermediate result; no second physical run"}
            return {"scenario_count":len(report["candidates"]),"recommendation":report["recommendation"],"economic_status":[{"scenario_id":c["scenario_id"],"status":c["economics"].get("status"),"incremental_npv_vs_s0_cny":c["economics"].get("incremental_npv_vs_s0_cny")} for c in report["candidates"]],"full_plan_calls":state["full_plan_calls"],"numeric_source":"inspect cached intermediate result; no second physical run"}
        if name=="prepare_report": state["report"]["agent_task"]={"request":state["request"],"modifications":state.get("changes",{}),"workflow":"request→validate→load/weather→profile→generation/matching/lifecycle"}; return {"status":"report_ready"}
        raise ValueError("未知工具")
    def run(self,user_request:str,task:Dict[str,Any])->Dict[str,Any]:
        state={"request":user_request,"payload":dict(task),"site_id":str(task.get("site_id","guangzhou")),"year":int(task.get("year",2024)),"trace":[]}; messages=[{"role":"system","content":"你是能智核风光方案任务执行助手。严格按顺序选择工具，用户修改必须先写入arguments；不输出推荐数字，所有数字由工具计算。外送开启但缺价格要请求澄清。工具arguments必须符合任务schema，使用时段修改写入room.start_hour和room.end_hour。"},{"role":"user","content":json.dumps({"request":user_request,"allowed_tools":TOOLS,"task_schema":{"room":["start_hour","end_hour"],"hybrid":["budget_cny","budget_multiplier","hub_height_max_m","allow_export","export_price_cny_per_kwh"],"numeric_source":"deterministic tools"}},ensure_ascii=False)}]
        for i in range(min(self.max_rounds,len(TOOLS))):
            started=time.perf_counter();
            try:
                first_model_error=None
                try:
                    action=self._model(messages,[TOOLS[i]])
                except Exception as first_exc:
                    first_model_error=f"{type(first_exc).__name__}: {first_exc}"
                    messages.append({"role":"user","content":f"上一次结构化工具调用失败（{first_model_error}）。仅重试一次，仍须输出符合schema的{TOOLS[i]}调用；不要猜测数值。"})
                    action=self._model(messages,[TOOLS[i]])
                result=self._tool(action["action"],state,action.get("arguments",{})); entry={"round":i+1,"action":action["action"],"arguments":action.get("arguments",{}),"message":action.get("message",""),"result":result,"latency_ms":round((time.perf_counter()-started)*1000,2),"model":"local_configured_model"};
                if first_model_error: entry["first_model_error"]=first_model_error
                state["trace"].append(entry); messages += [{"role":"assistant","content":json.dumps(action,ensure_ascii=False)},{"role":"tool","name":action["action"],"content":json.dumps(result,ensure_ascii=False,default=str)}]
                if result.get("status")=="needs_clarification": return {"status":"needs_clarification","question":result["question"],"trace":state["trace"]}
                if action["action"]=="prepare_report": return {"status":"success","report":state["report"],"trace":state["trace"],"message":"本地模型完成任务修改并调用了风光计算工具；数字来自确定性工具。"}
                messages.append({"role":"user","content":f"{action['action']}已完成，请调用下一工具 {TOOLS[i+1]}，arguments为空即可。"})
            except Exception as exc:
                failure={"round":i+1,"action":None,"error":f"{type(exc).__name__}: {exc}","latency_ms":round((time.perf_counter()-started)*1000,2)}
                if 'first_model_error' in locals() and first_model_error: failure["first_model_error"]=first_model_error
                state["trace"].append(failure)
                return {"status":"failed","error":f"{type(exc).__name__}: {exc}","trace":state["trace"],"message":"模型协同失败；没有用确定性路径冒充Agent成功。"}
        return {"status":"failed","error":"超过最大模型轮数","trace":state["trace"]}
