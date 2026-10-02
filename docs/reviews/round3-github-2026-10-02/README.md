# GitHub 首次归档前的独立目录复查

本目录记录 2026-10-02 在待上传文件集合中进行的核查。测试在 `.review-work/` 隔离副本执行，原第三轮源文件与结果没有变化；该副本保留在本地，不加入仓库。

- [总回执](verification.json)：29 项可靠性检查、11 项隔离 HTTP 检查、112 条历史回归，全部通过。
- [逐项可靠性结果](reliability_tests.json)、[HTTP 结果](standalone_tests.json)、[回归分组](regression_summary.json)、[原始 CSV 任务](import_demo.json)。
- 四个同名 `.txt` 为这次实际执行的标准输出；不替代之前的冻结成绩。
- [归档前文件检查](repository_preflight.json) 为当次时点的文件数、体积与模式扫描结果；该回执本身及后续仓库说明不计入此前扫描总数。
- [SHA256SUMS](SHA256SUMS.txt) 包含三轮 ZIP、当前三份 Word 与 PDF 的字节摘要。

没有新增性能试验。历史正常/泄漏各 0/14，025 为 1/14，075 为 11/14；不能从这些软件核查推导算法领先或运维效率收益。

GitHub Actions 将在云端使用同样入口再次执行，实际状态与完整运行日志以该提交的 Actions 页面为准。
