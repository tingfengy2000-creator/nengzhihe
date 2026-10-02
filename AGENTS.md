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
- Repository: https://github.com/tingfengy2000-creator/nengzhihe (private). Current product is round3; root application files are round1 history.
- Each subsequent project update includes verification, CHANGELOG/review-index updates, a scoped commit and push to main. Confirm the remote commit and CI; report failed sync honestly.
- Follow CONTRIBUTING.md. Use immutable tags/releases for stage reviews. Never force-push or replace a review tag.
- Preserve old evidence and archive bytes. Never commit secrets, new private imports, model weights, installations, caches or duplicate test trees. No cache cleanup is authorized.
- Distinguish measured data, simulation and artificial perturbations. Historical 112 cases are regression only.
