# 更新与阶段评审约定

1. 当前产品入口为 `round4/`。前两轮源文件、冻结输入、原始成绩及评审 ZIP 保留；新实验建立新阶段，不覆盖旧成绩。
2. 每次完成更新，在 `CHANGELOG.md` 记录改动、检查结果和能力边界；对应阶段在 `docs/REVIEW_INDEX.md` 增加条目。
3. 运行 `python tools/check_repository.py` 与 `python tools/verify_round4.py`。检查在独立副本执行，不覆盖历史评审证据。材料变动须重新渲染并逐页复检。
4. 明确文件清单后暂存，检查 `git diff --cached --stat` 和实际差异，确认不含令牌、私人数据、模型权重或安装缓存，再提交和推送。不要自动提交未经核查的新用户导入数据。
5. 推送后检查远程提交 SHA 和 Actions。阶段评审创建新的标签与 Release，链接源码、材料、结果及交付包；已发布阶段标签不移动、不覆盖。
6. 用户后续在本任务中要求的每次项目更新，默认包括完成必要核查后提交并推送；如认证、联网或检查失败，保留本地工作并明确报告，不能声称已经同步。

常用命令（文件名须替换为本次实际修改的路径）：

```powershell
python tools/check_repository.py
python tools/verify_round4.py
git add -- round4/quality.py CHANGELOG.md docs/REVIEW_INDEX.md
git diff --cached --stat
git diff --cached
git commit -m "fix: describe the verified change"
git push origin main
```

不强推主分支，不改写已推送历史。不运行历史准备/冻结脚本覆盖已结束实验。112 条旧案例仅用于开发、失败分析和回归，新性能主张须另设留出并在评价前冻结口径。

三份匿名底稿的身份等行政字段须按赛事实际要求完成，成熟度仅自评第3级。审核附件属于评审材料，不自动成为仓库操作授权。
