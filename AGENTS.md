# Current mainline notice
- 当前主线是“能智核”阶段二空调—光伏—风电方案试算与项目总负荷衔接；交接以 `START_HERE_5060.md`、`docs/handoff/5060_start_prompt.txt` 和对应 5090 分支说明为准。后续阶段分支普通推送供审查，不把本历史文件中的 round4 “推送 main” 约定用于当前交接，也不改 main。
- 下方 round4 条目是历史约束，适用于 round4 目录和旧证据；当前产品和交接规则优先读取上述入口。

# Scope
This project is independent of every other project under E:\比赛. Never modify, stop, or inspect private work in xiangyi-youju or 乡艺有据 directories for this task.

# First-round contract
- Public building energy anomaly verification is primary. Energy opportunity screening is subordinate.
- BDG2 measured building replay and LBNL SDAHU simulated labeled validation are separate evidence tracks.
- Explicitly identify measured, simulated, and artificial record perturbation data.
- Exclude actual actuator positions and other non-Basic simulator points from the allowed evidence pool; no fault filenames or severity in model input.
- Four strategies: fixed workflow, adaptive rules without LLM, local free LLM selector, complete information. Shared numerical engine and evidence pool. Full information is comparable only at a budget covering its full pool.
- Local model chooses tools only; all numerical evidence and diagnoses are computed by code.
- Before opening holdout payloads, freeze diagnosis, policy, model prompt, metrics, split manifest and hashes. Never tune on holdout outputs.
- Query-cost units and hypothetical field-acquisition costs are distinct. Current replay performs zero field acquisitions.
- At least one demo must preserve an equipment suspicion after deterministic data repair.
- No invented gains, customers, trials, energy savings or maturity. Negative active-policy results change claims, not architecture complexity.
- Original submission references are in E:\比赛\能智核_参赛设计\sources and requirements in its 参赛要求与方案调整.txt.

# Runtime
Use task-local dependencies and ports. Do not kill or reconfigure unrelated services. Bind preview to 127.0.0.1.

# GitHub review workflow (user authorized 2026-10-02)
- Repository: https://github.com/tingfengy2000-creator/nengzhihe (private). Current product is round4; root application files are round1 history.
- Each subsequent project update includes verification, CHANGELOG/review-index updates, a scoped commit and push to main. Confirm the remote commit and CI; report failed sync honestly.
- Follow CONTRIBUTING.md. Use immutable tags/releases for stage reviews. Never force-push or replace a review tag.
- Preserve old evidence and archive bytes. Never commit secrets, new private imports, model weights, installations, caches or duplicate test trees. No cache cleanup is authorized.
- Distinguish measured data, simulation and artificial perturbations. Historical 112 cases are regression only.

# Current round4 contract
- Primary position: 公共建筑风阀疑点核验与补证工作台. See round4/AGENTS.md.
- Main historical unit: 56 base day-scenarios; 112 only paired perturbation regression. 025/075 are stuck openings.
- No algorithm superiority, zero-false-alarm or human efficiency claim. Real participants remain zero until actual recruitment.
- Independent human review and signed answer/rubric hashes are mandatory before real enrollment; never sign on behalf of a person.
- Current no-install review: round4/delivery/review/index.html. Preserve prior round3 tag and all bytes.
