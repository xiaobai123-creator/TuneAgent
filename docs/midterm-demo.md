# 中期验收演示清单

目标：用 3–5 分钟证明三件事：

1. Agent 能听懂自然语言并调用工具；
2. 数据清洗有可解释的漏斗和报告；
3. 采集器已经在 24 小时自动抓取，数据可查询、可累积。

现场原则：**演示确定性的离线路径，不把成败押在模型 API 或外网搜索上。**

## 演示前 10 分钟检查

```bash
cd /root/agent-project

# 1. 测试是否全绿
.venv/bin/python -m pytest -q

# 2. 采集器是否在跑、数据是否在
.venv/bin/python scripts/run_watch.py --status

# 3. systemd 服务是否正常
systemctl is-active tuneagent-watch
systemctl is-enabled tuneagent-watch
```

预期：

- 测试输出 `81 passed`
- 采集状态显示总轮次大于 0、失败 0
- 服务输出 `active` 和 `enabled`

演示前不要在教室里现场执行 `pip install`，依赖提前装好；也不要在演示时删除数据库或重启服务器。

## 推荐演示顺序（约 4 分钟）

### 0:00–0:20 一句话介绍

> TuneAgent 是一个音乐搜索与数据采集 Agent。左边是交互式 Agent，右边是每 30 分钟自动抓取网易云新歌榜的采集器；两者共用清洗和持久化思路。

如果老师问“为什么有两套目录”，直接说：

> 最初按 deepseek-harness 的插件化分层搭了 TypeScript 骨架；后来接入网易云、清洗、下载和 24 小时采集，主体用 Python 落地。TS 骨架保留为架构参考，不参与主流程。

### 0:20–1:30 单次命令模式：搜索 + 清洗

这条命令默认使用本地 Mock 数据，不依赖网络和 API Key，适合稳定演示：

```bash
.venv/bin/python scripts/run_cli.py '国风 按热度 前15' \
  --export-cleaned data/demo_cleaned.json
```

讲解顺序：

1. 先看“解析结果”：关键词、排序方式、目标数量。
2. 看“清洗前候选”：原始搜索结果里既有免费歌，也有 `fee=8` 的 VIP/付费歌。
3. 看“清洗统计”：
   - 原始 20 条 → 去重后 20 条 → 可用 7 条 → 最终 Top 7；
   - 目标 15 首，但只有 7 首可用，所以如实显示“候选不足”；
   - 平台没有真实热度指标，所以“按热度”使用原始顺序作为回退，并在报告里说明。
4. 打开导出的 `data/demo_cleaned.json`，指出里面同时有 `query`、`report` 和 `songs`，说明“清洗结果不是只打印在屏幕上，而是可以交给后续程序使用”。

如果网络稳定，可以额外补一句：

```bash
.venv/bin/python scripts/run_cli.py '国风 按热度 前15' --real
```

但**不要把 `--real` 作为主演示**；现场网络或接口限流会影响节奏。

### 1:30–2:30 采集器：24 小时自动抓取

```bash
.venv/bin/python scripts/run_watch.py --status
```

讲解要点：

- 每 30 分钟抓一次网易云新歌榜；
- 每轮保存原始 JSON、解析后的歌曲、榜单快照和质量报告；
- 第一轮是基线，所以“新增 0、首次发现 100”；
- 后续轮次会统计新上榜、掉榜、排名上升/下降；
- 失败会记录 `failed` 并退避，但不会覆盖上一轮成功快照；
- 当前由 systemd 常驻，服务器重启后会自动恢复。

可补充：

```bash
systemctl is-active tuneagent-watch
systemctl is-enabled tuneagent-watch
```

看到 `active` 和 `enabled` 即可，不必现场展开 journal 日志。

### 2:30–3:10 测试与结构

```bash
.venv/bin/python -m pytest -q
```

说明：

- 81 个测试全部离线，不依赖真实网络；
- 覆盖 Agent 回退、工具执行、网易云适配、清洗、下载、Web 搜索、UI、采集和调度；
- 采集测试使用临时 SQLite 和 fake 数据源，不会污染演示数据。

然后打开 [README](../README.md) 的“项目结构”和“与 DeepSeek Harness 骨架的关系”两节，说明实际 Python 分层和早期 TS 骨架的边界。

### 3:10–4:00 可选：交互式 CLI

如果 API Key 和网络都正常：

```bash
.venv/bin/python scripts/interactive_cli.py
```

输入：

```text
国风 按热度 前15
```

展示工具调用、清洗结果和表格；输入 `/exit` 退出。

如果没有 API Key，CLI 会进入离线规则模式，仍然可以演示；但为了时间可控，**主演示用前面的 `run_cli.py` 就够了**。

## 老师可能问的问题

### 1. 为什么项目里有两套目录？

最初按老师建议搭了 harness 风格的 TypeScript 骨架；实际接入网易云、下载、UI 和 24 小时采集后，主体用 Python 实现。TS 骨架保留为架构参考，不参与主流程。两边的对应关系写在 [架构文档](architecture.md) 第 7 节。

### 2. 数据清洗体现在哪里？

- 按歌曲 ID 去重；
- 按“标准化标题 + 标准化歌手”去重，处理大小写、空格、标点差异；
- 只保留 `fee in (0, 1)` 的可用歌曲；
- 采集侧额外统计无法解析、时长非法、专辑/时长/歌手/fee 缺失；
- 清洗报告输出原始数、去重数、可用数、最终数，不隐藏候选不足。

### 3. 为什么榜单 100 首只有几首可用？

新歌榜里大量歌曲是 VIP/付费，`fee` 不是 0 或 1。交互式搜索只推荐免费可播放歌曲，所以会过滤掉大部分；采集器则保留这些歌用于榜单分析，只统计可用/VIP 数量。这正好说明“抓取到的数据”和“能推荐的数据”不是一回事。

### 4. 24 小时运行靠什么保证？

- `systemd` 负责开机自启和异常退出后自动拉起；
- 采集器内部有超时、单轮重试和失败退避（300 秒 → 3600 秒）；
- 失败会写入 `crawl_run`，不会覆盖上一轮成功快照；
- SQLite 使用 WAL，采集写入时读取状态不会被阻塞。

### 5. 磁盘会不会满？

每轮原始 JSON 约 330 KB，30 分钟一轮约 16 MB/天，三周约 350 MB；当前服务器还有 23 GB 空闲。采集器只存元数据，不下载音频。需要长期运行时，可以按 [采集器文档](collector.md) 的 SQL 清理旧原始 JSON，保留歌曲和榜单快照。

### 6. 为什么排序是“原始顺序”或“歌曲 ID 降序”？

网易云公开搜索接口不返回播放量、点赞量、收藏量。项目不会假装有这些指标：`hot` 保留平台原始顺序，其他排序用歌曲 ID 降序作为确定性回退，并在清洗报告里明确写出原因。

### 7. 版权和合规怎么处理？

- 采集器只保存公开榜单元数据，不下载音频；
- 真实下载需要用户自己的 Cookie，只下载账号有权访问的内容；
- 不绕过 VIP、地区、版权或 DRM；
- 下载文件和 Cookie 不提交到 Git，也不对外分发。

## 兜底方案

| 现场问题 | 处理方式 |
| --- | --- |
| 模型 API 失败 | 用 `run_cli.py` 的 Mock 路径，或让交互式 CLI 进入离线规则模式 |
| 网易云搜索失败 | `MusicToolExecutor` 自动回退 Mock；`run_cli.py` 默认就是 Mock |
| 采集器最近一轮失败 | 展示 `--status` 中的历史成功轮次和错误原因，说明退避机制；不要现场删库 |
| Gradio 打不开 | 跳过 UI；CLI + 采集状态 + 测试已经能证明核心功能 |
| 老师要求看数据库 | 用 `--status` 或 [采集器文档](collector.md) 里的 SQL，不要现场改数据 |

## 演示时不要做的事

- 不要现场 `pip install` 或创建虚拟环境，时间不可控；
- 不要现场删除 `data/tuneagent.db`、重启 systemd 或改配置；
- 不要承诺下载 VIP/付费歌曲；
- 不要把 TS 骨架说成当前主实现，也不要把 Python 实现藏起来；
- 不要在演示中执行 `--real` 下载，除非老师明确要求且账号有权访问。

## 演示后的收尾

```bash
# 确认采集器还在跑
systemctl is-active tuneagent-watch
.venv/bin/python scripts/run_watch.py --status
```

`data/demo_cleaned.json` 是运行数据，已被 `.gitignore` 排除，可以保留给老师看，也可以删除。
