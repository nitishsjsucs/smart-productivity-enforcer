# Smart Productivity Enforcer

An AI-powered system-level productivity enforcer that monitors your activity and automatically closes distracting applications and browser tabs during focus sessions. It runs a local 1.7B parameter language model (via Ollama) to make intelligent decisions about what counts as productive -- entirely offline, with zero API costs.

**Let's be honest:** this tool does not fix the underlying problem of getting distracted. That is a discipline issue, and no software can solve it for you. What this tool *does* is add enough friction to make mindless tab-switching and app-hopping harder. It is the difference between having a door and having no door -- you can still walk through it, but at least you have to think about it first.

## Platform Support

| Platform | Status |
|----------|--------|
| Windows 10/11 | Fully supported |
| macOS | Not supported |
| Linux | Not supported |

The enforcer relies heavily on Win32 APIs (`win32gui`, `win32con`, `win32process`) for window management, process control, and system-level enforcement. macOS and Linux support would require platform-specific reimplementations of the activity monitor, enforcer, and service modules.

## How It Works

The system operates as a continuous loop with three stages:

```
Activity Monitor --> Productivity Evaluator --> Enforcer
```

**1. Activity Monitor** -- Captures the currently active window using `win32gui`, identifies the running process via `psutil`, and retrieves browser tab URLs through either a bundled Chrome extension (WebSocket) or Playwright CDP.

**2. Productivity Evaluator** -- Runs the captured activity through a layered decision pipeline:
   - Hard-coded app rules (always allow VS Code, always block Steam, etc.)
   - Domain-level browser rules (allow github.com, block instagram.com)
   - YouTube-specific rules (block Shorts, allow whitelisted channels, check title keywords)
   - If still ambiguous, the LLM makes the final call

**3. Enforcer** -- If the activity is classified as unproductive or blocked, the enforcer closes the browser tab (via the Chrome extension or `Ctrl+W` keystroke) or terminates the application window (`WM_CLOSE`, falling back to process kill).

All evaluations are cached for 24 hours per unique URL or app, so the LLM is only invoked once per new piece of content.

## Local LLM (Default Configuration)

By default, the evaluator runs **Ollama** with **qwen3:1.7b** -- a 1.4GB local model that handles productivity classification without any API key or internet connection. The model runs entirely on your machine.

```json
{
  "llm": {
    "provider": "ollama",
    "model": "qwen3:1.7b",
    "temperature": 0.3
  }
}
```

If you prefer a cloud provider, you can switch to Google Gemini, OpenAI, or Anthropic by updating the config and setting the corresponding API key in your `.env` file.

| Provider | Model (default) | Requires API Key | Cost |
|----------|----------------|-----------------|------|
| Ollama (default) | qwen3:1.7b | No | Free |
| Google | gemini-2.0-flash | Yes | Pay-per-use |
| OpenAI | gpt-4o | Yes | Pay-per-use |
| Anthropic | claude-3-5-sonnet | Yes | Pay-per-use |

## Installation

### Prerequisites

- Python 3.9+
- Windows 10 or 11
- [Ollama](https://ollama.com) installed and running (for the default local model)

### Setup

```bash
git clone https://github.com/NitishKumar06/smart-productivity-enforcer.git
cd smart-productivity-enforcer

# Pull the local model
ollama pull qwen3:1.7b

# Install with uv (recommended)
uv sync

# Or with pip
pip install -e .
```

If you want to use a cloud LLM provider instead of the local model, create a `.env` file:

```bash
# Pick one:
GOOGLE_API_KEY=your-key-here
OPENAI_API_KEY=your-key-here
ANTHROPIC_API_KEY=your-key-here
```

### Browser Extension (Optional)

For accurate browser tab detection, load the bundled Chrome/Edge extension:

1. Open `chrome://extensions` or `edge://extensions`
2. Enable Developer Mode
3. Click "Load unpacked" and select the `extension/` directory

This gives the enforcer real-time access to tab URLs and titles, and the ability to close individual tabs rather than the entire browser window.

## Usage

### Starting a Focus Session

```bash
# Start a 60-minute session
spe start --duration 60

# Start with strict mode (password required to stop)
spe start --duration 90 --strict

# Use a preset
spe focus "Deep Work"
spe focus "Learning"

# Run in background (survives terminal close)
spe focus "Deep Work" --background
```

### Managing Rules

```bash
# Allow an application
spe allow "obsidian.exe" --app

# Block a domain
spe block "reddit.com" --domain

# Configure YouTube rules
spe youtube --block-shorts
spe youtube --add-channel "ThePrimeagen"
spe youtube --show
```

### Configuration

```bash
# Set your productivity goal (used as context for LLM decisions)
spe config --goal "Build the new feature for client X"

# Show current config
spe config --show

# Set a bypass password
spe config --set-password

# Reset everything
spe config --reset
```

### Viewing Activity

```bash
# Stats for today
spe stats --today

# Stats for the week
spe stats --week

# View activity logs
spe logs --days 3

# AI-powered analysis of your activity patterns
spe analyze --days 7
spe learn
```

## Focus Session Presets

| Preset | Duration | Strict Mode | Allowed Apps | Allowed Domains |
|--------|----------|-------------|--------------|-----------------|
| Deep Work | 90 min | Yes | VS Code, Windsurf, Terminal, PyCharm | github.com, stackoverflow.com, docs.python.org |
| Learning | 60 min | No | VS Code, Chrome, Edge | youtube.com, udemy.com, coursera.org, github.com |

You can define custom presets in `~/.smart-productivity-enforcer/config.json`.

## YouTube Handling

YouTube gets special treatment because it is the single biggest source of productive-time-turned-into-two-hours-of-shorts.

The evaluator checks in this order:

1. **Shorts** -- Blocked by default. Detected by URL pattern (`/shorts/`) and window title.
2. **Homepage** -- Blocked by default. The recommendation algorithm is the enemy.
3. **Channel whitelist** -- Channels like Fireship, 3Blue1Brown, freeCodeCamp are always allowed.
4. **Title keywords** -- Videos with "tutorial", "course", "programming", etc. are allowed.
5. **Entertainment keywords** -- Videos with "funny", "prank", "reaction", etc. are closed.
6. **LLM fallback** -- For anything ambiguous, the model decides based on your stated goal.

## Bypass Protection

The enforcer is designed to resist being disabled mid-session. During a strict focus session:

- **Ctrl+C is intercepted** and blocked unless the session is over or a password is provided.
- **Killing the process** can be countered by registering it as a Windows Task Scheduler task that auto-restarts.
- **Session state is persisted** to disk, so restarting the app resumes the session.
- **A password is required** to force-stop a strict session early.

```bash
# Set up auto-restart via Task Scheduler
python -c "from smart_productivity_enforcer.windows_service import TaskSchedulerIntegration; TaskSchedulerIntegration.create_startup_task()"

# Emergency stop (requires password)
spe stop --password "your-password"
```

This is not unbreakable -- you are an adult with admin access to your own machine. But it adds enough friction that "just one quick video" becomes a conscious decision rather than an autopilot reflex.

## Configuration Reference

All configuration lives in `~/.smart-productivity-enforcer/config.json`.

| Setting | Description | Default |
|---------|-------------|---------|
| `user_goal` | Your stated productivity goal (used as LLM context) | "Focus on software development and learning" |
| `check_interval_seconds` | How often the monitor checks the active window | 10 |
| `llm.provider` | LLM provider: `ollama`, `google`, `openai`, `anthropic` | `ollama` |
| `llm.model` | Model name | `qwen3:1.7b` |
| `enforcement.enabled` | Master switch for enforcement actions | true |
| `enforcement.warning_before_close` | Show a notification before closing | true |
| `enforcement.warning_duration_seconds` | Seconds to wait after warning | 5 |
| `enforcement.require_password_to_disable` | Require password to stop strict sessions | true |
| `youtube.block_shorts` | Block YouTube Shorts | true |
| `youtube.block_homepage_suggestions` | Block the YouTube homepage | true |

## Logs and Screenshots

Activity and enforcement logs are written to:

- `~/.smart-productivity-enforcer/logs/activity_YYYY-MM-DD.jsonl`
- `~/.smart-productivity-enforcer/logs/enforcement_YYYY-MM-DD.jsonl`
- `~/.smart-productivity-enforcer/screenshots/` (captured at enforcement time)

## Project Structure

```
smart-productivity-enforcer/
  smart_productivity_enforcer/
    activity_monitor.py     # Window and process tracking via Win32
    llm_evaluator.py        # Rule engine + LLM classification with caching
    enforcer.py             # Tab/app closing and process termination
    daemon.py               # Main monitoring loop and session management
    config.py               # Pydantic configuration models
    cli.py                  # Typer-based CLI (spe command)
    browser_controller.py   # Playwright CDP browser integration
    websocket_server.py     # WebSocket server for Chrome extension
    activity_logger.py      # JSONL activity logging and daily analysis
    background_service.py   # Background/detached process management
    windows_service.py      # Task Scheduler and Windows service integration
  extension/
    manifest.json           # Chrome extension manifest (Manifest V3)
    background.js           # Extension background service worker
    popup.html/js           # Extension popup UI
  run.py                    # Quick-start script
  pyproject.toml            # Project metadata and dependencies
```

## My Contributions

- **Activity Monitor** — Built the system-level activity monitoring engine that tracks active window titles, application usage, and browser tab content in real-time on Windows using Win32 APIs.
- **LLM-Based Distraction Detection** — Designed and implemented the local language model integration that classifies activities as productive or distracting based on configurable user-defined rules and natural language understanding.
- **Automated Enforcement** — Developed the enforcement module that automatically closes distracting applications and browser tabs, with configurable grace periods, whitelisting, and escalation policies.
- **Chrome Extension Bridge** — Created the Chrome Manifest V3 extension and WebSocket bridge that enables tab-level monitoring and selective tab closure from the Python backend.
- **CLI & Background Service** — Implemented the Typer-based CLI (`spe` command) and Windows Task Scheduler integration for headless background operation with JSONL activity logging and daily analysis reports.

---

## License

MIT
