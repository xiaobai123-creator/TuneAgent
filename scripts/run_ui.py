#!/usr/bin/env python3
"""Launch the local TuneAgent Gradio interface."""

from __future__ import annotations

import logging
import os
import sys

import gradio as gr

from _bootstrap import ensure_project_root_on_path

ensure_project_root_on_path()

from tuneagent.ui.service import (
    DEFAULT_PLATFORM_LABEL,
    RESULT_HEADERS,
    available_platforms,
    run_search,
)

DEFAULT_REQUEST = "国风 按热度 前15"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7860

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger("tuneagent.ui")


def handle_search(request_text: str, platform_label: str) -> tuple[str, list, str]:
    try:
        result = run_search(request_text, platform_label)
    except Exception:
        LOGGER.exception("Unexpected UI search failure")
        return (
            "### 系统错误\n\n搜索过程中发生意外错误，请查看服务器日志后重试。",
            [],
            "",
        )
    return result.status_markdown, result.rows, result.report_markdown


def build_demo() -> gr.Blocks:
    platforms = list(available_platforms())
    with gr.Blocks(title="TuneAgent 国风音乐助手") as demo:
        gr.Markdown(
            "# 🎵 TuneAgent 国风音乐助手\n"
            "输入自然语言，搜索、去重、过滤 VIP 歌曲并返回可播放结果。"
        )
        with gr.Row():
            request_text = gr.Textbox(
                value=DEFAULT_REQUEST,
                label="自然语言搜索",
                placeholder="例如：国风 按点赞 前10",
                scale=4,
            )
            platform = gr.Dropdown(
                choices=platforms,
                value=DEFAULT_PLATFORM_LABEL,
                label="平台",
                scale=1,
            )
        search_button = gr.Button("开始搜索", variant="primary")
        status = gr.Markdown(
            "### 准备就绪\n\n点击“开始搜索”或按 Enter 发起查询。"
        )
        results = gr.Dataframe(
            headers=list(RESULT_HEADERS),
            datatype=["number", "str", "str", "str", "str", "number"],
            value=[],
            label="清洗后的歌曲",
            interactive=False,
            wrap=True,
        )
        report = gr.Markdown(
            "### 清洗报告\n\n搜索后将在这里显示漏斗统计和排序说明。"
        )

        outputs = [status, results, report]
        search_button.click(
            fn=handle_search,
            inputs=[request_text, platform],
            outputs=outputs,
        )
        request_text.submit(
            fn=handle_search,
            inputs=[request_text, platform],
            outputs=outputs,
        )
    return demo


def main() -> int:
    host = os.getenv("APP_UI_HOST", DEFAULT_HOST)
    try:
        port = int(os.getenv("APP_UI_PORT", DEFAULT_PORT))
    except ValueError as error:
        raise ValueError("APP_UI_PORT must be an integer") from error
    if not 1 <= port <= 65535:
        raise ValueError("APP_UI_PORT must be between 1 and 65535")

    demo = build_demo()
    print(f"TuneAgent UI: http://{host}:{port}")
    print("SSH tunnel example: ssh -N -L 7860:127.0.0.1:7860 <user>@<server>")
    demo.launch(
        server_name=host,
        server_port=port,
        share=False,
        show_error=False,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"run_ui: {error}", file=sys.stderr)
        raise SystemExit(1) from error
