# Interactive CLI Agent

TuneAgent's interactive CLI uses an OpenAI-compatible model for intent and tool
calling, with an offline rule-based fallback.

## Architecture

```text
tuneagent/agent/llm_client.py
tuneagent/agent/tool_executor.py
tuneagent/agent/engine.py
          |
          | structured AgentEvent objects
          v
scripts/interactive_cli.py
```

The core Agent modules do not import Rich or prompt_toolkit. A future Web UI can
consume the same events by replacing only the presentation layer.

`tuneagent/cli_entry.py` is the thin console entry point installed as the
`tuneagent` command; it delegates to `scripts/interactive_cli.py`.

## Installation

### Global command (recommended)

Linux:

```bash
./install.sh
```

Windows: double-click `install.bat`, or run it from a terminal:

```bat
.\install.bat
```

Reopen the terminal after installation, then start the CLI from any directory:

```bash
tuneagent
```

The installer uses `uv` when available and otherwise bootstraps `pipx`. It
installs the lightweight `.[cli]` extra, so Gradio, pandas and numpy are not
downloaded. The install is editable: changes from `git pull` take effect
without reinstalling, but dependency changes require running the installer
again.

### Repo-local virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -e '.[cli]'
```

For the Gradio UI or the full test suite:

```bash
python -m pip install -e '.[all]'
```

## DeepSeek configuration

Create or update `.env` in the project root:

```dotenv
DEEPSEEK_API_KEY=your-deepseek-api-key
```

The model list is in `config/llm_models.toml`. API keys are referenced through
environment variable names and are never stored in the TOML file.

To configure a backup model:

```dotenv
OPENAI_API_KEY=your-openai-api-key
```

## Launch

After the global install:

```bash
tuneagent
```

Or launch directly from the repository:

```bash
python scripts/interactive_cli.py
```

Without an API key the CLI starts in offline rule mode and uses the Mock fixture.
If all configured models fail, the current request also falls back to offline
mode.

## Commands

- `/model` lists configured models.
- `/model <number-or-name>` switches the current model.
- `/login` validates the configured Netease cookie without downloading audio.
- `/help` shows usage examples.
- `/exit` or `/quit` exits.

## Downloads

The model can only pass a numeric song ID to `download_song`. The terminal
requests confirmation before the controlled downloader runs. Cookie values and
resolved audio URLs are never included in tool results or manifests.

Only download songs that your own account is legitimately allowed to access.
