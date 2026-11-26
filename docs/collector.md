# 24 小时自动采集

TuneAgent 的采集器会定时抓取网易云音乐「新歌榜」，完成解析、去重、字段校验后写入 SQLite，并记录每一轮的抓取结果和榜位变化。它不依赖登录 Cookie，也不下载音频，只保存榜单元数据，适合在服务器上长期后台运行。

## 一次采集做了什么

```text
网易云榜单 API
      |
      v
NeteaseChartSource.fetch_raw()     原样保存 JSON（按 sha256 去重）
      |
      v
NeteaseChartSource.parse()         Song.from_netease，逐条解析
      |
      v
clean_collected_songs()            去重 -> 丢弃非法时长 -> 统计缺失字段
      |
      v
CollectorRunner                    与上一轮成功快照对比
      |
      v
SQLite                             原始数据、歌曲、榜单快照、运行记录
```

关键行为：

- 第一轮是基线：`new_count = 0`，当前所有歌曲记为「首次发现」。
- 后续轮次与**最近一次成功运行**比较，统计新上榜、掉榜、排名上升/下降。
- 抓取或解析失败会记录一条 `failed` 运行；失败不会覆盖上一轮成功快照。
- 原始响应按内容哈希去重：只有两次响应字节完全一致时才会复用同一条 `raw_blob`。榜单里的封面图 CDN 域名（`p1` / `p2`）会变化，所以实际连续抓取通常会各存一份。
- 榜单数据只保留元数据，不下载歌曲，不绕过付费或版权限制。

## 快速开始

在项目根目录执行：

```bash
# 只抓一轮，适合先验证网络和配置
.venv/bin/python scripts/run_watch.py --once

# 查看运行状态
.venv/bin/python scripts/run_watch.py --status

# 常驻运行，默认每 30 分钟抓一次
.venv/bin/python scripts/run_watch.py
```

Windows 下把 `.venv/bin/python` 换成 `.venv\Scripts\python.exe`。

首次运行会创建：

- `data/tuneagent.db`：采集数据库。
- `logs/watch.log`：轮转日志（单文件 5 MB，保留 5 份）。

`--once` 的成功/失败会体现在进程退出码：`0` 成功，`1` 失败。

常用参数：

```bash
.venv/bin/python scripts/run_watch.py --once --interval 600
.venv/bin/python scripts/run_watch.py --max-runs 3 --interval 5   # 演示用
.venv/bin/python scripts/run_watch.py --db data/demo.db --status
.venv/bin/python scripts/run_watch.py --config config/watch.toml --verbose
```

`--max-runs` 只能和常驻模式一起用，不能与 `--once` / `--status` 同时使用。

## 配置

默认配置文件是 `config/watch.toml`：

```toml
[collector]
db_path = "data/tuneagent.db"
log_path = "logs/watch.log"
interval_seconds = 1800
failure_backoff_seconds = 300
max_backoff_seconds = 3600
request_timeout_seconds = 20
retries = 2
retry_backoff_seconds = 2.0

[source]
name = "netease-new-songs"
type = "netease-chart"
chart_id = 3779629
chart_url = "https://music.163.com/api/playlist/detail"
```

| 配置项 | 说明 |
| --- | --- |
| `db_path` | SQLite 文件路径，相对路径按项目根目录解析 |
| `log_path` | 日志文件路径，自动创建父目录 |
| `interval_seconds` | 成功一轮后的等待时间，默认 1800 秒 |
| `failure_backoff_seconds` | 首次失败后的等待时间，默认 300 秒 |
| `max_backoff_seconds` | 失败退避上限，默认 3600 秒 |
| `request_timeout_seconds` | 单次 HTTP 请求超时 |
| `retries` | 单轮抓取失败后的额外重试次数 |
| `retry_backoff_seconds` | 单轮内重试的指数退避基数 |
| `source.name` | 写入数据库的数据源标识，状态查询按它过滤 |
| `source.type` | 目前只支持 `netease-chart` |
| `chart_id` | 网易云榜单 ID，`3779629` 为云音乐新歌榜 |
| `chart_url` | 榜单接口地址 |

命令行参数优先级高于配置文件；没有配置文件时会使用内置默认值。

## 24 小时运行

### 方式一：nohup

```bash
cd /path/to/agent-project
mkdir -p logs data
nohup .venv/bin/python scripts/run_watch.py >> logs/watch.out 2>&1 &
echo $! > logs/watch.pid
```

查看状态和日志：

```bash
.venv/bin/python scripts/run_watch.py --status
tail -f logs/watch.log
```

停止：

```bash
kill "$(cat logs/watch.pid)"
```

进程收到 `SIGINT` / `SIGTERM` 后会完成当前轮次（或等待中的休眠）再退出，不会留下 `running` 状态的半截记录。

### 方式二：systemd（推荐，服务器重启后自动恢复）

本项目的实际部署以 root 用户运行，项目目录为 `/root/agent-project`。新建 `/etc/systemd/system/tuneagent-watch.service`：

```ini
[Unit]
Description=TuneAgent Netease chart collector
Documentation=file:///root/agent-project/docs/collector.md
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/root/agent-project
ExecStart=/root/agent-project/.venv/bin/python /root/agent-project/scripts/run_watch.py
Restart=always
RestartSec=30
TimeoutStopSec=90
Environment=PYTHONUNBUFFERED=1
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

如果部署到其它用户或目录，需要同步修改 `User`、`Group`、`WorkingDirectory`、`ExecStart` 和 `Documentation`。服务以非 root 用户运行时，要确保该用户对项目目录、`data/` 和 `logs/` 有写权限。

注册并启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now tuneagent-watch
sudo systemctl status tuneagent-watch --no-pager
```

查看运行日志：

```bash
journalctl -u tuneagent-watch -n 50 --no-pager
journalctl -u tuneagent-watch -f
```

重启和停止：

```bash
sudo systemctl restart tuneagent-watch
sudo systemctl stop tuneagent-watch
```

`enable` 会创建开机自启链接；`Restart=always` 负责进程异常退出后的自动拉起。服务日志同时写入 journal 和项目内的 `logs/watch.log`。

### 抓取频率建议

新歌榜更新并不频繁，30 分钟一轮已经足够。答辩演示可以临时用：

```bash
.venv/bin/python scripts/run_watch.py --max-runs 3 --interval 5
```

不建议把间隔调到几秒，既没有数据收益，也容易给数据源造成压力。

## 数据库结构

| 表 | 作用 |
| --- | --- |
| `crawl_run` | 每轮采集的状态、计数、错误信息和清洗质量 JSON |
| `raw_blob` | 原始 JSON 内容，按 sha256 主键去重 |
| `raw_payload` | 每轮抓取与原始内容的对应关系 |
| `song` | 去重后的歌曲主数据，`song_id` 为主键 |
| `song_snapshot` | 每轮每首歌的排名、上轮排名、排名变化、是否新歌 |
| `source_state` | 数据源最近成功时间、连续失败次数、累计运行/失败次数 |

时间统一以 UTC ISO 8601 写入，`--status` 输出时转换为服务器本地时间。

### 存储占用

当前榜单响应约 330 KB/轮。按 30 分钟间隔运行，原始数据约占 15–20 MB/天；三周答辩周期约 300–400 MB。`song`、`song_snapshot` 和运行记录的体积很小，主要占用来自 `raw_blob`。

如果需要长期运行并控制体积，可以手动删除较早的原始响应，保留歌曲和榜单快照：

```sql
-- 先删除旧的抓取-原始数据关联
DELETE FROM raw_payload
WHERE run_id IN (
    SELECT id FROM crawl_run
    WHERE started_at < strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now', '-14 days')
);

-- 再删除已经没有任何运行引用的原始内容
DELETE FROM raw_blob
WHERE sha256 NOT IN (SELECT sha256 FROM raw_payload);
```

执行前建议先备份 `data/tuneagent.db`，并确认不再需要复查这些轮次的原始 JSON。

### 常用查询

最近 10 轮：

```sql
SELECT id, started_at, status, raw_count, dedup_count, valid_count,
       new_count, first_seen_count, dropped_count, error
FROM crawl_run
ORDER BY id DESC
LIMIT 10;
```

最新一轮榜单：

```sql
SELECT s.rank, song.title, song.artists, song.album,
       song.duration_ms, song.fee, s.is_new, s.rank_delta
FROM song_snapshot AS s
JOIN song ON song.song_id = s.song_id
WHERE s.run_id = (SELECT MAX(id) FROM crawl_run WHERE status = 'success')
ORDER BY s.rank;
```

最近 24 小时首次出现的歌曲：

```sql
SELECT song_id, title, artists, first_seen_at
FROM song
WHERE first_seen_at >= strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now', '-1 day')
ORDER BY first_seen_at DESC;
```

每个数据源的运行健康度：

```sql
SELECT * FROM source_state;
```

## 清洗指标

每轮运行会写入 `crawl_run.quality_json`，格式示例：

```json
{
  "summary": "原始 8 条 -> 去重后 5 条 -> 有效 4 条（可用 2，VIP/付费 2，无效 3）",
  "raw_count": 8,
  "parsed_count": 6,
  "deduplicated_count": 5,
  "valid_count": 4,
  "duplicate_count": 1,
  "duplicate_rate": 0.1667,
  "unparsable_count": 2,
  "invalid_duration_count": 1,
  "invalid_count": 3,
  "invalid_rate": 0.375,
  "available_count": 2,
  "vip_count": 2
}
```

字段含义：

- `raw_count`：原始记录数，包含解析失败的记录。
- `unparsable_count`：缺少有效 `id` 或 `name`，无法构造 `Song` 的记录。
- `duplicate_count`：按歌曲 ID 或「标准化标题 + 标准化歌手」判定的重复记录。
- `deduplicated_count`：解析成功且去重后的数量。
- `invalid_duration_count`：时长为 `0` 或负数的记录，直接丢弃。
- `valid_count`：进入数据库的有效歌曲数。
- `available_count`：`fee in (0, 1)`，可正常播放的歌曲数。
- `vip_count`：有 `fee` 字段但不属于免费范围的歌曲数；保留在库中用于分析，但不会被推荐。
- `missing_*_count` / `missing_*_rate`：有效歌曲中专辑、时长、歌手、`fee` 缺失的数量与比例。

注意：缺失字段统计只针对最终有效歌曲。例如时长非法的歌曲已经被丢弃，不会再计入「缺失 `fee`」。

## 失败与退避

- 单轮内抓取失败会按 `retries` 和 `retry_backoff_seconds` 做指数退避重试。
- 单轮最终失败后，调度器从 `failure_backoff_seconds` 开始翻倍等待，直到 `max_backoff_seconds`。
- 一旦成功，等待时间恢复为 `interval_seconds`，`consecutive_failures` 清零。
- 解析失败前已经保存了原始响应，可在 `raw_blob` 中复查，便于定位是接口变化还是网络返回异常。

常见排查：

```bash
# 手动跑一轮，看完整错误
.venv/bin/python scripts/run_watch.py --once --verbose

# 检查数据库和日志是否在更新
.venv/bin/python scripts/run_watch.py --status
tail -n 50 logs/watch.log
```

如果长期失败，优先检查服务器 DNS、出网访问、系统时间和接口是否仍可访问。采集器本身不会修改系统代理或网络配置。

## 合规说明

- 只访问网易云公开榜单接口，不模拟登录、不携带账号 Cookie。
- 只保存歌曲元数据和榜单位置，不下载音频文件。
- 默认 30 分钟一轮，带超时、重试和失败退避。
- 数据仅用于课程项目的数据采集与清洗演示，不对外提供下载或商业化分发。

## 测试

```bash
.venv/bin/python -m pytest tests/test_collector.py -q
.venv/bin/python -m pytest -q
```

采集器测试完全离线：榜单解析和清洗使用 `tests/fixtures/netease_chart_sample.json`，网络错误通过 mock 模拟，不会在测试中访问网易云。
