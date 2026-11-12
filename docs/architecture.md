# Coridis Architecture

## 目标

Coridis 的最小目标是运行一个单 Session、单 Agent 的本地编码助手循环：

1. CLI 读取用户任务。
2. Agent Loop 调用 LLM provider。
3. 模型返回文本或工具调用。
4. 工具注册表执行 `read_file`、`web_search`、`web_fetch`。
5. Session 记录所有模型可见输入与工具结果。
6. Agent Loop 继续下一轮，直到模型结束。

本阶段仅固定分层、包边界和装配方式，不实现上述任何行为。

## 包角色

| 包 | 角色 | Cordis 贡献 |
|---|---|---|
| `@coridis/contracts` | 纯类型 | 无 |
| `@coridis/llm` | Service Definition | `ctx.llm` |
| `@coridis/tools` | Service Definition | `ctx.tools` |
| `@coridis/session` | Service Definition | `ctx.sessions` |
| `@coridis/fs` | Service Definition | `ctx.fs` |
| `@coridis/web` | Service Definition | `ctx.web` |
| `@coridis/llm-deepseek` | LLM Provider | 向 `ctx.llm` 注册 provider |
| `@coridis/fs-local` | FS Provider | 向 `ctx.fs` 注册 provider |
| `@coridis/web-search-http` | Web Search Provider | 向 `ctx.web` 注册 search provider |
| `@coridis/web-fetch-http` | Web Fetch Provider | 向 `ctx.web` 注册 fetch provider |
| `@coridis/tool-fs` | Tool Consumer | 向 `ctx.tools` 注册 `read_file` |
| `@coridis/tool-web` | Tool Consumer | 向 `ctx.tools` 注册 `web_search`、`web_fetch` |
| `@coridis/agent-loop` | Agent Loop | 消费 `ctx.llm`、`ctx.tools`、`ctx.sessions` |
| `@coridis/bundle-minimal` | Bundle | 组合最小插件树 |
| `@coridis/cli` | App | 启动 profile |

## 扩展规则

- 新增模型 provider：向 `ctx.llm` 注册 adapter，不修改 Agent Loop。
- 新增模型可见能力：向 `ctx.tools` 注册工具，不修改 provider。
- 新增文件系统来源：实现 `FileSystem`，不修改工具包。
- 新增搜索或抓取来源：实现对应 Web provider，不修改 `tool-web`。
- 所有注册必须返回或安装 disposer。
- 模型可见输入必须先写入 Session；后续实现不得只保存在内存。

