# CarveWork Studio — local-first project chat

A **standalone local web app** for working on your CarveFoundry project through chat. Uses an **Ollama model running on your computer by default**. No OpenAI API key, ChatGPT Work subscription, prepaid API credits, or hosted inference is required for local chat. The separate, paid OpenAI API is available **only if you explicitly select it in Settings**; CarveWork does not silently fall back to paid API usage when Ollama is unavailable.

It does **not** access this ChatGPT browser conversation or reuse ChatGPT Plus as API credit. Your saved CarveWork conversations are independent and remain on your computer in SQLite. Context starts from `data/workspace/PROJECT_CONTEXT.md` and available local project files.

## Start on Arch Linux / KDE Plasma

Requires **Python 3.11+** and a running **Ollama 0.13.3 or newer** with the model installed. No pip packages, Node, npm, Flatpak, or Python virtual environment are required for CarveWork. First-time model download requires network access; generation after the model is installed is local.

```bash
# Check whether Ollama is already available:
ollama --version
ollama list

# If Ollama isn't running, start its existing service, or in a spare terminal:
ollama serve

# Download only if 'devstral-small-2:24b' isn't in ollama list (~15 GB):
ollama pull devstral-small-2:24b

cd /mnt/moar/Downloads/git/CarveFoundry
unset OPENAI_API_KEY  # optional reassurance; Ollama never uses this key
bash scripts/run-carvework.sh
```

Open **http://127.0.0.1:8765** in Firefox. The repository-root launcher automatically links the CarveFoundry checkout. **No need to load your `ai.key` file** for Ollama. The status bar explicitly shows `LOCAL · devstral-small-2:24b` and `OLLAMA READY` when the local server and model are available. If you have the same model under a different installed tag, choose that tag in Settings, which lists locally installed models. Ollama model names ending `-cloud` are rejected for local mode.

### Updates through Git — no release ZIPs

CarveWork ships in the main CarveFoundry repository under `tools/carve-work/`.
After a `git pull --ff-only` in your existing CarveFoundry checkout,
start it with the **repository-root launcher**:

```bash
cd /mnt/moar/Downloads/git/CarveFoundry
git pull --ff-only
bash scripts/run-carvework.sh
```

The launcher points `CARVEFOUNDRY_REPO` at that checkout. If you already
used `/home/scott/git/carve-work/data` and the new in-repository
`tools/carve-work/data` directory does not exist, it automatically reuses
the existing data directory. Conversations, handovers, saved tasks and
project context therefore remain available **without copying your database
into Git**. To choose the data location explicitly, run:

```bash
export CARVE_WORK_DATA=/home/scott/git/carve-work/data
bash scripts/run-carvework.sh
```

Only the application source and tests are tracked. The nested `.gitignore`
excludes `data/`, `ai.key`, `*.key`, local virtual environments and
generated browser-test data. Never add these files manually or force-add them.
Do not delete your old `/home/scott/git/carve-work` directory until
you have confirmed all prior chats are visible in the repository version.

## Provider settings and charges

Go to **Settings & context → AI provider**:

- **Ollama — local (default)**: `devstral-small-2:24b` Q4_K_M model, 16,384-token context configuration, one chat at a time, no OpenAI API requests or usage charges. Requires local CPU/GPU/RAM and uses your electricity. Longer contexts on a 16 GB GPU can offload to RAM/CPU and become slower. CarveWork checks that Ollama is running and the selected model exists before sending a message.
- **OpenAI API — paid opt-in**: available only when you manually switch provider and provide `OPENAI_API_KEY` in the server's environment. API model is separately configurable; existing paid-API model choice is preserved when migrating from the original CarveWork. A configured key is **not** proof of credits; the UI says `KEY SET · CREDITS UNVERIFIED`. Web research is available only in this provider and may add API charges. OpenAI API billing is separate from ChatGPT Plus.

Ollama requests are sent only to a **loopback HTTP** server (`http://127.0.0.1:11434` by default), never to a remote Ollama/cloud address. This can be configured with `CARVE_WORK_OLLAMA_URL` for another **local loopback port**, e.g. `http://127.0.0.1:12345`. The browser uses its localhost CarveWork server rather than exposing Ollama to the network.

## Automatic conversation handover

- CarveWork estimates per-thread token use and the underlying provider's reported prompt token count, then starts a new linked chat at ~76% of the configured app budget or the user turn limit. The local budget also reserves ~4K tokens below `ollama_ctx` for instructions, output, and tool use. Configure budget, local context, and turn count in Settings. The *configured* 16K local window should fit your existing tested setup; it is not a hardware guarantee.
- On rollover, CarveWork **asks the selected provider** (Ollama in local mode) for a precise handover, persists the full previous conversation, and includes the summary in the new thread's system instructions. Handovers under Ollama make **zero OpenAI API calls**.
- If the local model fails to summarize, a deterministic fallback includes the recent transcript, the prior handover, and the archived thread ID. The assistant can use `read_chat_history` / `search_chat_history` to recover details omitted by the compact summary.
- Manual rollover via **Create handover now ↗** works without copying or pasting. This is a context continuation, not a way around another provider's rate limits or bills. A genuine context error can also initiate a continuation without duplicating the just-sent user turn.

## Project tools and approvals

`list_files`, `read_file`, `search_files`, `write_file`, `run_command`, `read_chat_history`, `search_chat_history`, `add_task`, and `complete_task` work with Ollama and OpenAI. Source files are read from `repo/...` under `CARVEFOUNDRY_REPO` and artifacts go to `workspace/...`. Every agent write and shell command needs **your explicit Approve/Deny** action; denials do not write or run commands. Nothing is pushed to GitHub without your local permission to run an appropriate command. File and chat history remain stored locally. The source tree and sensitive filenames such as `ai.key`, `.env`, `.git`, `.venv` and credential key formats are blocked by the read-file and search tools.

Images (PNG/JPG/WebP/GIF, max 3 MB each) are supported by the local Devstral Small 2 vision model and in OpenAI mode. Text files can be browsed or searched; read/write tools cap a single text file at 100 KB. `data/workspace/PROJECT_CONTEXT.md` can be edited to refresh the persistent project brief. A failed request now produces a **persistent, selectable, copyable error panel** above the message box, rather than only a brief popup.

**Security:** This is a localhost-only development assistant that can execute approved local commands with your user permissions. Do not port-forward it, expose it publicly, or approve a command you have not read. Treat model-generated commands as untrusted even when the model runs offline.

## Run tests

```bash
python3 -m unittest discover -s tests -v
node --check static/app.js   # optional; Node is not required to run CarveWork
```

Tests use mock Ollama and OpenAI HTTP endpoints, a disposable SQLite workspace and fake tools. They make **no paid API requests**, do not need to download a 15 GB model, and do not touch your real CarveFoundry checkout. A live Ollama inference test and visual KDE/Wayland confirmation must happen on your machine.

**Project layout:** `tools/carve-work/engine.py` provider adapters, chat rollover, persistence and approval-gated tools; `server.py` browser/API server bound to loopback; `static/` browser interface; `tests/` deterministic regressions; `data/` generated private chats and workspace (excluded from release ZIP).
