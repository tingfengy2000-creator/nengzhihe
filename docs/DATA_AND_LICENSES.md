# 数据、许可与仓库范围

本仓库包含能智核的代码、案例、已结束实验标签、逐例结果、审核附件、比赛模板、材料和交付包，没有包含其他项目目录。

## 来源

- BDG2 实测历史：[官方项目](https://github.com/buds-lab/building-data-genome-project-2)，保留 [许可](../data/raw/bdg2_LICENSE)、[说明](../data/raw/bdg2_README.md)及来源清单。只作回放，无设备故障真值。
- LBNL SDAHU 仿真：[数据及许可](https://doi.org/10.6084/m9.figshare.22338283.v1)、[官方说明](https://fdddata.lbl.gov/data/Simulated_LBNL_FDD_Data_Sets_SDAHU/LBNL_FDD_Data_Sets_SDAHU.pdf)。作者、版本、CC BY 4.0 见 [来源说明](../round3/DATA_SOURCES.txt)及 [元数据](../round3/data/source_docs/lbnl_figshare_metadata.json)。
- 演示 CSV 是官方年度数据的单日原始数值片段，见 [provenance.json](../round3/data/public_csv/provenance.json)。原始采样与软件重采样分开记载。
- 人为重复记录只作软件鲁棒性演示，不算新的设备或独立故障案例。

历史 `data/private/` 表示首轮曾封存的公共数据标签和案例，不是私有楼宇数据。实验已结束，现上传供复核，不可再作为新盲态留出。第三轮旧 112 条同样只作开发、失败分析与回归。

## 未上传但留在本地的文件

| 类型 | 原因 | 恢复 / 复现入口 |
| --- | --- | --- |
| LBNL 年度 ZIP、BDG2 大型电表/气象 CSV | 非启动所必需，避免重复分发大型原始文件 | [source_manifest](../data/source_manifest.json)、[准备脚本](../scripts/prepare_data.py)、[CSV 提取](../round3/scripts/prepare_public_csv.py) |
| 首轮模型、llama.cpp/CUDA 二进制 | 下载缓存和第三方组件 | [runtime/README](../runtime/README.txt)、下载脚本及许可证 |
| LibreOffice 安装、解压目录和分块 | 渲染环境可重新获取 | [renderer_source](../round3/runtime/renderer_source.json)、[渲染脚本](../round3/scripts/render_private.py) |
| 中间渲染、测试副本、日志、即时导入与运行记录 | 重复或临时产物 | 最终页面、冻结回执及选定 HTML 示例已上传 |

上述本地文件没有删除。新机器可用仓库冻结输入启动第三轮并回归，不等于能离线重建年度原始数据。首轮模型复跑需另下载指定版本权重和运行器。

第三方数据、文档、模型、工具分别适用原许可。自编代码暂未新增开源许可，不将第三方内容整体重新授权。比赛模板按原要求引用和填写；私有仓库不替代提交材料的匿名要求。
