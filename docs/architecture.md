# TuneAgent Architecture

本文描述当前**实际运行**的 Python 架构，以及它与早期 Cordis / TypeScript 骨架的关系。

## 1. 设计目标

TuneAgent 要解决两件事：

1. **交互式任务**：用户用自然语言提出音乐搜索、联网查询或下载请求，Agent 调用工具完成，并给出可解释的清洗结果。
2. **无人值守任务**：每 30 分钟抓取一次网易云新歌榜，持久化原始数据和清洗结果，比较相邻批次的榜位变化。

设计上尽量保持“展示层”和“核心逻辑”分离：`tuneagent/agent` 不依赖 Rich、prompt_toolkit 或 Gradio；CLI 和 Web UI 只是消费 `AgentEvent` 的不同外壳。

## 2. 总览

```text
入口层
  run.sh / run.bat ──> scripts/interactive_cli.py
  scripts/run_ui.py ─> tuneagent/ui/service.py
  scripts/run_cli.py
  scripts/run_watch.py ─> tuneagent/collector/scheduler.py

交互式链路
  scripts/interactive_cli.py
        │
        v
  AgentEngine ──> LLMClient（DeepSeek 主模型 / OpenAI 兼容备用）
        │                 │
        │                 └─ 无 Key 或全部失败时：离线规则解析
        v
  MusicToolExecutor
        ├─> NeteaseAdapter / MockNeteaseAdapter
        ├─> platforms/web_search.py（Bing RSS）
        └─> RealNeteaseDownloader（可选，Cookie + 用户确认）
        │
        v
  CleaningPipeline（去重、可用性过滤、排序回退）

采集链路
  scripts/run_watch.py
        │
        v
  Scheduler ──> CollectorRunner
                    ├─> NeteaseChartSource.fetch_raw() / parse()
                    ├─> clean_collected_songs()
                    ├─> 与上一轮成功快照比较
                    └─> CollectorStore（SQLite）
```

## 3. 模块职责

| 模块 | 职责 |
| --- | --- |
| `tuneagent/agent/engine.py` | Agent 多轮循环：组织消息、调用模型、执行工具、发出事件；在线失败时回退离线规则 |
| `tuneagent/agent/llm_client.py` | OpenAI 兼容客户端，模型列表、主备切换、工具调用解析 |
| `tuneagent/agent/tool_executor.py` | 工具定义、参数校验、搜索/联网/下载执行 |
| `tuneagent/agent/events.py` | 与展示层无关的事件对象（文本、工具开始/结束、错误等） |
| `tuneagent/agent/intent_parser.py` | 离线规则解析，例如“国风 按热度 前15” |
| `tuneagent/platforms/netease.py` | 网易云公开搜索接口适配 |
| `tuneagent/platforms/mock.py` | 本地 fixture 适配器，供离线演示和测试 |
| `tuneagent/platforms/real_download.py` | 受控真实下载：Cookie、标准 MP3、原子写入、SHA-256 清单 |
| `tuneagent/platforms/web_search.py` | 通过 Bing RSS 搜索公开网页，解析标题、链接、摘要 |
| `tuneagent/cleaning/models.py` | 平台无关的 `Song` 模型 |
| `tuneagent/cleaning/pipeline.py` | 单次搜索的清洗：去重、过滤不可用、排序回退、清洗报告 |
| `tuneagent/collector/chart.py` | 网易云榜单抓取与解析 |
| `tuneagent/collector/cleaning.py` | 采集批次清洗：去重、非法时长、缺失字段、可用/VIP 统计 |
| `tuneagent/collector/store.py` | SQLite schema、运行记录、原始数据、歌曲、快照、状态 |
| `tuneagent/collector/runner.py` | 单轮采集：抓取 → 保存原始 → 解析 → 清洗 → 对比 → 入库 |
| `tuneagent/collector/scheduler.py` | 固定间隔运行、失败指数退避、优雅停止 |
| `tuneagent/ui/service.py` | Gradio 搜索服务，目前使用离线 Mock 平台 |
| `scripts/*.py` | 各运行入口和开发工具 |
| `tests/*` | 离线测试与 fixtures |

## 4. 一次交互请求的数据流

以“国风 按热度 前15”为例：

1. `scripts/interactive_cli.py` 读取输入，交给 `AgentEngine`。
2. `AgentEngine` 把系统提示和用户消息发给 `LLMClient`。
3. 模型返回工具调用，例如 `search_music(keyword="国风", sort_by="hot", limit=15)`。
4. `MusicToolExecutor` 校验参数，选择 `NeteaseAdapter`；真实搜索不可用时自动回退 `MockNeteaseAdapter`。
5. 搜索结果进入 `CleaningPipeline`：
   - 按歌曲 ID 或“标准化标题 + 标准化歌手”去重；
   - 只保留 `fee in (0, 1)` 的可用歌曲；
   - 按请求的排序字段排序；平台没有真实播放/点赞/收藏指标时，使用歌曲 ID 降序作为确定性回退，并在报告中如实说明；
   - 截取目标数量，生成 `CleaningReport`。
6. `AgentEngine` 把工具结果和清洗报告发回模型，模型组织最终回答。
7. CLI 把事件渲染成表格、进度和状态；如果用户明确要求下载，终端还会再次确认，确认后才调用 `RealNeteaseDownloader`。

**离线模式**：没有配置模型 Key，或所有模型都失败时，`AgentEngine` 使用 `parse_intent` 解析请求，并用 Mock 适配器完成搜索。这样即使验收现场没有网络或 API Key，CLI 仍能演示完整的清洗流程。

**Web UI**：`scripts/run_ui.py` 复用 `tuneagent/ui/service.py`，目前只提供 Mock 平台，用于展示搜索、去重和清洗漏斗，不承担真实下载。

## 5. 24 小时采集的数据流

1. `run_watch.py` 创建 `CollectorStore` 和 `NeteaseChartSource`，交给 `CollectorRunner`。
2. `Scheduler` 立即执行第一轮，之后按 `interval_seconds`（默认 1800 秒）循环。
3. `NeteaseChartSource.fetch_raw()` 请求公开榜单接口，`save_raw()` 把原始 JSON 写入 `raw_blob`，同一份内容按 SHA-256 去重。
4. `parse()` 把每条 track 转成 `Song`；缺少有效 `id` 或 `name` 的记录计入 `unparsable_count`。
5. `clean_collected_songs()`：
   - 按 ID 和标准化标题 + 歌手去重；
   - 丢弃时长为 0 或负数的记录；
   - **保留 VIP/付费歌曲**，只统计 `available_count` 和 `vip_count`，因为榜单分析需要完整样本；
   - 统计专辑、时长、歌手、`fee` 缺失数量。
6. `previous_snapshot()` 取最近一次成功运行的快照，计算：
   - `new_count`：本轮有、上一轮没有；
   - `dropped_count`：上一轮有、本轮没有；
   - `rank_up_count` / `rank_down_count`：共同歌曲的名次变化；
   - `first_seen_count`：数据库中第一次出现的歌曲。
7. `commit_success()` 在一个事务里更新 `song`、`song_snapshot`、`crawl_run` 和 `source_state`。
8. 任一步失败时，`mark_failed()` 记录错误和连续失败次数；调度器按 300 秒起步、逐次翻倍、上限 3600 秒退避。失败不会写入快照，也不会覆盖上一轮成功数据。

第一轮没有历史快照，因此 `new_count = 0`，当前所有歌曲都记为“首次发现”；这是基线，不是异常。

## 6. SQLite 数据模型

| 表 | 作用 |
| --- | --- |
| `crawl_run` | 每轮采集的状态、计数、错误和 `quality_json` |
| `raw_blob` | 原始 JSON 内容，按 SHA-256 主键去重 |
| `raw_payload` | 每轮抓取与原始内容的对应关系 |
| `song` | 去重后的歌曲主档案 |
| `song_snapshot` | 每轮每首歌的排名、上轮排名、排名差、是否新歌 |
| `source_state` | 数据源最近成功、连续失败、累计运行/失败次数 |

时间统一以 UTC ISO 8601 存储，`--status` 显示时转换为本地时间。详细 SQL 和清理方式见 [采集器文档](collector.md)。

## 7. 与初始 Cordis / TypeScript 骨架的关系

项目最初按 DeepSeek Harness / Cordis 的插件化风格搭了一套 TypeScript 骨架。它保留了分层和依赖注入的设计思路，但大部分插件仍是 `not implemented`，不是当前运行路径。

| 初始骨架概念 | 实际 Python 实现 | 说明 |
| --- | --- | --- |
| Agent Loop | `AgentEngine` | 多轮模型/工具循环 |
| LLM Provider | `LLMClient` | DeepSeek 主模型 + OpenAI 兼容备用 |
| Tool Registry | `MusicToolExecutor` | `search_music`、`web_search`、`download_song` |
| Web Provider | `platforms/web_search.py` | Bing RSS |
| 平台适配 | `platforms/netease.py` | 网易云公开搜索 |
| 清洗 | `cleaning/pipeline.py` | 去重、可用性过滤、排序回退 |
| Bundle / Profile | `run.sh` / `run.bat` / `scripts` | 简化为脚本入口 |

TS 骨架中的 `apps/cli` 保留了一个可选桥接壳，可以转调 Python 单次命令模式；主体 CLI、UI 和采集器都不依赖 Node 或 pnpm。中期验收以 Python 入口为准，TS 骨架作为“初始架构设计”的说明材料，不强行把已经实现的 Python 代码改写成 Cordis 插件树。

## 8. 测试策略

测试目标是把网络和模型 API 都隔离掉：

- `tests/test_agent_engine.py`：工具循环、模型失败、离线回退、事件；
- `tests/test_cleaning_pipeline.py`：去重、可用性、排序回退；
- `tests/test_collector.py`：榜单解析、清洗指标、SQLite、增量对比、重试、调度；
- `tests/test_netease_adapter.py` / `test_mock_adapter.py`：平台适配；
- `tests/test_real_download.py`：Cookie、下载边界、原子写入；
- `tests/test_web_search.py`：Bing RSS 解析和链接校验；
- `tests/test_ui_service.py`：Gradio 服务的清洗报告。

运行：

```bash
python -m pytest -q
```

当前 81 个测试通过，全部使用本地 fixtures、Mock 适配器、Fake 数据源和临时 SQLite。

## 9. 设计取舍与限制

- **只接入网易云一个平台**：课程项目优先做深一条链路，而不是铺很多平台。
- **公开接口可能变化**：采集器有超时、重试和退避，但不能保证接口永远可用；失败会保留上一轮成功快照。
- **UI 只演示 Mock 数据**：真实搜索和下载以交互式 CLI 为主，避免在浏览器里暴露 Cookie 或下载权限。
- **下载只支持标准音质 MP3**：不做 VIP/版权绕过，不做批量下载。
- **采集器只存元数据**：不下载音频；原始 JSON 约 330 KB/轮，长期运行时可按文档清理旧原始数据。
- **对话状态在进程内**：CLI 只持久化输入历史，退出后不保留完整会话；采集数据则持久化在 SQLite。
- **排序指标有回退**：网易云公开接口不提供播放/点赞/收藏量，相关排序使用歌曲 ID 降序，并在报告中明确说明，不假装是真实热度。
- **TS 骨架不是生产代码**：它用于说明初始架构，当前主流程不需要 Node/pnpm。

## 10. 后续演进

优先级从高到低：

1. **P1 功能**：增加关键词/其他榜单采集源、Gradio 历史页、Agent 查询采集历史的工具、CSV/JSON 导出。
2. **展示整理**：把 TS 骨架归档到单独目录或分支，统一入口命名，补充中期/答辩演示材料。
3. **可选重构**：等核心功能和验收完成后再考虑目录合并，不在验收前动运行代码。

相关文档：[README](../README.md)、[采集器](collector.md)、[交互式 CLI](interactive-cli.md)、[真实下载](real-download.md)、[中期演示清单](midterm-demo.md)。
