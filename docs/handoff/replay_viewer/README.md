# 5060固定回放入口

这个目录只包含静态HTML、CSS、JavaScript和从5090已验收结果提取的固定样例。它不会导入或执行热湿、光伏、风电、生命周期或LLM核心，也不会把任意新请求映射成旧答案。

在仓库根目录执行：

```powershell
python -m http.server 8060 --directory docs/handoff/replay_viewer
```

然后打开 <http://127.0.0.1:8060/>。5060的localhost与5090的localhost相互独立，不需要访问5090的`127.0.0.1`，也不需要安装本地模型。

样例包含默认四方案、预算60000元、PV报价缺失、屋顶1㎡和真实Agent任务记录。默认样例的图表保留完整8784个小时；浏览器只抽取显示点，年度指标直接使用已保存结果。

未列入固定样例的条件显示“待计算/待5090验算”。前端导出应从当前已显示的report生成，不能为了导出再次调用完整计算。

## 空调成本接口样例

本轮5090真实请求—响应样例位于 `aircost_cases.json`，包含一间房两台设备、三间同类房间、用户寿命8/12年、用户分时电价边界和广州2024完整天气。`batch_quote_legacy_preserved.json` 是旧证据原样保留，`batch_quote_corrected.json` 与 `batch_quote_diff.json` 是本轮修正对照；运行环境和输出哈希见 `operation_planning/results/phase2b_aircost_handoff_5090/run_manifest.json`。回放页面未执行这些计算，5060应从固定响应读取；未列出的新条件显示“待5090验算”。
