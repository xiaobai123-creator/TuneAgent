# Coridis

Coridis 是一个按 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 的架构风格搭建的极简 Agent Harness 骨架，运行时基于 [Cordis](https://github.com/cordiverse/cordis)。

当前仓库只有骨架，没有具体实现。所有插件入口、provider 和 Agent Loop 都会以 `not implemented` 失败，等待后续分阶段实现 `web_search`、`web_fetch`、`read_file` 和 DeepSeek 模型调用。

## 架构原则

- **Everything is a plugin**：模型、工具、文件系统、Web 能力和 Agent Loop 都是 Cordis 插件。
- **Service Definition / Provider / Consumer 分离**：`fs`、`web`、`llm` 只定义能力接口；`*-local`、`*-http`、`*-deepseek` 提供实现；`tool-*` 是模型可见的消费者。
- **依赖通过 `inject` 声明**：插件不直接导入其它实现，只依赖稳定的 `ctx.<service>`。
- **注册即可逆副作用**：后续实现必须通过 `ctx.effect()` 或注册器返回的 disposer 清理。
- **组合优于硬编码**：运行入口由 profile + bundle + 有序 patch 层装配。

## 目录

```text
apps/cli                          CLI 启动器
packages/core/contracts           共享消息、工具调用与 Session 事件类型
packages/core/llm                 LLM 能力 seam（ctx.llm）
packages/core/tools               工具注册与执行 seam（ctx.tools）
packages/core/session             Session 持久化 seam（ctx.sessions）
packages/core/agent-loop          Agent Loop 插件
packages/llm/llm-deepseek         DeepSeek provider 骨架
packages/fs/fs                    文件系统能力 seam（ctx.fs）
packages/fs/fs-local              本地文件系统 provider 骨架
packages/fs/tool-fs               read_file 等文件工具骨架
packages/web/web                  Web 能力 seam（ctx.web）
packages/web/web-search-http      web_search provider 骨架
packages/web/web-fetch-http       web_fetch provider 骨架
packages/web/tool-web             web_search / web_fetch 工具骨架
packages/bundle/minimal           最小运行组合
profiles/minimal                  最小 profile 覆盖层
```

## 最小能力链路

```text
CLI -> agent-loop -> llm -> llm-deepseek
                   -> tools -> tool-fs -> fs -> fs-local
                            -> tool-web -> web -> web-search-http
                                              -> web-fetch-http
                   -> sessions
```

## 开发

```sh
pnpm install
pnpm typecheck
```

实现顺序建议：

1. `fs`、`fs-local` 与 `tool-fs`：打通 `read_file`。
2. `llm`、`llm-deepseek`、`tools`、`session` 与 `agent-loop`：打通单轮工具调用。
3. `web`、两个 Web provider 与 `tool-web`：加入 `web_search`、`web_fetch`。
4. `apps/cli` 与 profile 装配：形成最小可运行入口。

