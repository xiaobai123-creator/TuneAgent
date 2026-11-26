# TuneAgent

TuneAgent 是一个面向“数据爬虫与清洗”课程的本地音乐发现 Agent。它可以用自然语言搜索网易云音乐、清洗去重、过滤不可用歌曲，也可以每 30 分钟自动采集网易云新歌榜，把原始数据、清洗结果和榜位变化持久化到 SQLite。

当前项目的核心实现是 Python，入口是交互式 CLI 和 24 小时采集器；仓库里另外保留了一套早期按 DeepSeek Harness / Cordis 风格搭建的 TypeScript 架构骨架，作为设计参考，不参与主运行流程。

## 现在能做什么

- **自然语言搜索**：输入“国风 按热度 前15”，Agent 调用搜索工具，返回清洗后的可播放歌曲。
- **数据清洗**：按歌曲 ID 和“标准化标题 + 歌手”去重，过滤 VIP/不可用歌曲，统计缺失字段和清洗漏斗。
- **联网搜索**：通过 Bing RSS 搜索公开网页，结果保留来源链接。
- **受控下载**：使用自己的网易云 Cookie，只下载标准音质 MP3，终端二次确认，不绕过 VIP 或版权限制。
- **24 小时采集**：定时抓取网易云新歌榜，保存原始 JSON、歌曲档案、每轮榜单快照和质量报告。
- **跨批次对比**：统计新上榜、掉榜、排名上升/下降，并保留上一轮成功快照。
- **可选 Web UI**：Gradio 界面用于演示搜索和清洗漏斗，目前使用离线 Mock 数据。
- **离线测试**：81 个测试，不依赖真实网络和模型 API。

## 快速开始

### 一键启动

- **Linux / macOS**：在项目根目录运行 `bash run.sh`
- **Windows**：双击项目根目录的 `run.bat`

启动脚本会自动检测 Python、创建 `.venv`、安装 `.[all]` 依赖，然后启动交互式 CLI。首次安装需要网络。

### 手动启动

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -e ".[all]"
python scripts/interactive_cli.py
```

### 配置模型

```bash
cp .env.example .env
```

在 `.env` 中填写：

```dotenv
DEEPSEEK_API_KEY=your-deepseek-api-key
# 可选备用模型
OPENAI_API_KEY=your-openai-api-key
```

模型列表在 `config/llm_models.toml`，API Key 只通过环境变量读取，不写进配置文件。

不填 Key 也能运行：CLI 会进入离线规则模式，使用本地 Mock 数据和规则解析；在线模型全部失败时，当前请求也会自动回退到离线模式。

## 主要入口

| 入口 | 命令 | 说明 |
| --- | --- | --- |
| 交互式 CLI | `python scripts/interactive_cli.py` | 主入口，支持模型对话、工具调用、下载确认 |
| 单次命令模式 | `python scripts/run_cli.py '国风 按热度 前15'` | 适合调试和自动化；默认 Mock，加 `--real` 使用网易云公开搜索 |
| 24 小时采集 | `python scripts/run_watch.py --status` | 查看采集状态；`--once` 只抓一轮 |
| Gradio UI | `python scripts/run_ui.py` | 可选，离线 Mock 数据演示，默认 `127.0.0.1:7860` |

`run_cli.py` 还可以把清洗结果导出成 JSON，适合验收时展示清洗报告：

```bash
python scripts/run_cli.py '国风 按热度 前15' --export-cleaned data/demo_cleaned.json
```

## 24 小时采集

采集器默认每 30 分钟抓取一次网易云新歌榜，数据写入 `data/tuneagent.db`，日志写入 `logs/watch.log`。

```bash
# 只抓一轮，验证网络和配置
python scripts/run_watch.py --once

# 查看累计轮次、成功/失败、最近新增
python scripts/run_watch.py --status

# 常驻运行
python scripts/run_watch.py
```

采集器会：

- 保存原始榜单 JSON，并按内容哈希去重；
- 解析成歌曲记录，统计无法解析、时长非法、缺失字段；
- 统计免费可用、VIP/付费、专辑/时长/歌手/费用缺失；
- 与上一轮成功快照对比，记录新上榜、掉榜、排名变化；
- 失败时按 300 秒 → 3600 秒退避，并且不覆盖上一轮成功快照。

配置在 `config/watch.toml`。服务器常驻、systemd、数据库查询和清理方法见 [采集器文档](docs/collector.md)。

## 项目结构

```text
tuneagent/agent        Agent 循环、LLM 客户端、工具执行、事件
tuneagent/platforms    网易云适配、Mock、真实下载、Cookie、Bing RSS 搜索
tuneagent/cleaning     单次搜索的清洗管线与歌曲模型
tuneagent/collector    24 小时采集、跨批次清洗、SQLite、调度
tuneagent/ui           Gradio 搜索与清洗报告服务
scripts/               启动脚本和命令行工具
tests/                 离线测试与 fixtures
config/                模型列表、采集器配置
docs/                  使用、架构、演示和部署文档

apps/                  ┐
packages/              ├─ 早期 Cordis / TypeScript 架构参考，不参与主流程
profiles/              ┘
```

运行时会生成 `data/`、`logs/`、`downloads/` 等目录，运行数据已在 `.gitignore` 中排除。

## 与 DeepSeek Harness 骨架的关系

最初按照老师建议，用 DeepSeek Harness / Cordis 的插件化分层搭了一套 TypeScript 骨架：

```text
apps/cli
packages/core/{contracts,llm,tools,session,agent-loop}
packages/llm/llm-deepseek
packages/fs/{fs,fs-local,tool-fs}
packages/web/{web,web-search-http,web-fetch-http,tool-web}
packages/bundle/minimal
profiles/minimal
```

这套骨架保留了“能力接口 / provider / consumer / agent loop”的分层思想，但大部分插件仍是 `not implemented`。后续接入网易云公开接口、清洗、下载、CLI、Gradio 和 24 小时采集时，主体实现落在了 Python `tuneagent/` 中。

两边的概念对应关系：

| 初始骨架概念 | 实际 Python 实现 |
| --- | --- |
| Agent Loop | `tuneagent/agent/engine.py` |
| LLM Provider | `tuneagent/agent/llm_client.py` |
| Tool Registry | `tuneagent/agent/tool_executor.py` |
| Web Provider | `tuneagent/platforms/web_search.py` |
| 平台适配 | `tuneagent/platforms/netease.py` |
| 清洗管线 | `tuneagent/cleaning/pipeline.py` |
| 运行配置 | `run.sh` / `run.bat` / `scripts/*.py` |

TS 骨架不参与 `run.sh` 和 `run_watch.py` 的主流程；`apps/cli` 中保留了一个可选桥接壳，可以转调 Python 单次命令模式，但需要额外安装 `pnpm`。中期验收以 Python CLI 和采集器为准，TS 部分作为“初始架构设计”的说明材料。

更完整的模块图和数据流见 [架构文档](docs/architecture.md)。

## 测试

```bash
python -m pytest -q
```

当前全量离线测试 **81 个通过**，覆盖 Agent 回退、工具执行、网易云适配、清洗管线、Cookie、下载、Web 搜索、UI 服务、24 小时采集与调度。测试使用本地 fixtures 和临时 SQLite，不会访问真实网络。

## 文档

- [交互式 CLI](docs/interactive-cli.md)
- [真实下载与 Cookie](docs/real-download.md)
- [Cookie 获取指南](docs/cookie_guide.md)
- [24 小时采集器](docs/collector.md)
- [架构说明](docs/architecture.md)
- [中期验收演示清单](docs/midterm-demo.md)

## 合规说明

- 采集器只保存公开榜单的歌曲元数据，不下载音频。
- 真实下载需要用户自己的网易云 Cookie，只允许下载账号有权访问的内容；不绕过 VIP、地区、版权或 DRM 限制。
- 下载的音频和 Cookie 不应提交到 Git，也不应对外分发。
- 项目仅用于课程学习与演示，请遵守网易云服务条款和当地版权法律。
