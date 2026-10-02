能智核独立本地推理运行环境

范围
仅服务于本项目的下一步补证动作选择。未读取评测数据和标签；未读取、修改或停止“乡艺有据”项目文件、配置和进程。所有推理使用本机loopback，不使用付费API。下载需要联网，完成下载后的推理不需要外部网络。

模型
Qwen/Qwen3-4B-GGUF，Qwen3-4B-Q4_K_M.gguf
固定仓库revision：bc640142c66e1fdd12af0bd68f40445458f3869b
模型SHA256：7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5
许可：Apache-2.0，见MODEL_LICENSE.txt（Qwen官方仓库原文件）
官方模型卡：https://huggingface.co/Qwen/Qwen3-4B-GGUF

运行器
ggml-org/llama.cpp b11146，Windows CUDA 13.4 x64便携包；该构建由v0.5.0 release的nightly-tag.txt指定。
llama.cpp许可：MIT，见RUNNER_LICENSE.txt。
CUDA运行库属于NVIDIA，其再分发条款与llama.cpp MIT许可不同；打包交付时应保留下载包中的第三方声明，不宣称整个runtime均为MIT。
官方构建：https://github.com/ggml-org/llama.cpp/releases/tag/b11146
官方接口：https://github.com/ggml-org/llama.cpp/blob/b11146/tools/server/README.md
官方资产摘要在llama_binary_release.json；模型LFS摘要在model_file_metadata.json。

启动
在PowerShell执行：
  & 'E:\比赛\nengzhihe\runtime\start_model.ps1'
独立端口127.0.0.1:18191，后台隐藏窗口，单并行slot，4096上下文，4个CPU线程，低CPU优先级，256 batch/128 ubatch。未启用任何内建文件/命令/网络工具。
启动脚本遇到该端口已监听时不会覆盖或停止任何进程；请检查health及models端点确认身份。
接口：http://127.0.0.1:18191/v1/chat/completions
模型ID：nengzhihe-qwen3-4b-q4km
配置文件：local_model_config.json
标准输出/错误：server.stdout.log、server.stderr.log；本项目进程ID：server.pid。

客户端
从项目目录import model_client，调用choose_action(payload: dict, allowed_actions: list[str])。
返回action、reason、latency_ms、raw、response_valid。
仅接受白名单内动作，严格JSON，两字段输出，温度0、固定seed=20260930、禁止thinking。
不存在规则兜底或假LLM回复；连接失败、截断或结构非法时action=null且response_valid=false，应作为模型失败如实计入实验。
调用者必须仅传已揭示证据和动作预算。不得传标签、源文件名、故障注入变量或未揭示证据。
现场补采与已有数据查询的成本由payload区分；调用者负责执行预算约束与真实数值计算。reason不是数值证据。
每次调用发送新的messages，不读取其他案例对话；所有请求明确绕过系统HTTP代理，只访问loopback。

复现
分段下载脚本download_model_ranges.py固定官方URL，核验HTTP Content-Range，支持保留分块后继续下载。
verify_downloads.py使用官方模型LFS及GitHub发布摘要核验三个文件，再解压到runtime/llama。
实际小型接口检查记录将保存到local_model_smoke.json。该记录仅验证接口可调用，不是用能诊断性能或主动策略收益结果。

实际验证（2026-09-30）
三个下载文件均匹配官方SHA256，见checksum_verification.json。
运行器实际版本：0.5.0-dev，build 11146，commit 7fe450e19，Clang 20.1.8 Windows x86_64。
llama-server.exe SHA256：7b886298b688509ced3e92b420edd57dd3d665da72c1fc207d7a537be5870352。
纯接口玩具请求真实返回query_available_feedback，JSON有效，端到端212.376毫秒；见local_model_smoke.json原始回复。该值只代表一次小请求，不是诊断性能或真实评测负载的延时承诺。
启动前/后整卡显存分别为10248/13729 MiB，观察到净增3481 MiB；该差值不是进程级独占测量。原始快照见gpu_before_model.csv与gpu_after_model.csv。
仅停止本项目模型时，运行runtime/stop_model.ps1。其同时核对PID、可执行路径及18191端口参数。
临时下载分块保留；下载完成后的清理动作被自动审批策略拒绝，未执行删除。打包源码时排除model_parts与*.ranges目录。

从干净拷贝安装（源码目录含本说明与脚本）
方式一：python runtime/download_runtime.py，等待三个二进制和三个说明/许可文件完成，再运行python runtime/verify_downloads.py。
方式二：慢连接时，可分别使用download_model_ranges.py默认参数下载模型，以及以下参数下载两个资产：
  python runtime/download_model_ranges.py --url https://github.com/ggml-org/llama.cpp/releases/download/b11146/llama-b11146-bin-win-cuda-13.4-x64.zip --size 149758833 --name llama-b11146-bin-win-cuda-13.4-x64.zip --workers 12
  python runtime/download_model_ranges.py --url https://github.com/ggml-org/llama.cpp/releases/download/b11146/cudart-llama-bin-win-cuda-13.4-x64.zip --size 423535356 --name cudart-llama-bin-win-cuda-13.4-x64.zip --workers 12
范围下载保留的分块可在中断后继续使用。完成后运行python runtime/verify_downloads.py，成功后才运行start_model.ps1。模型卡与许可文件应随源码包保留；其固定原始URL位于download_runtime.py。
