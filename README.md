<div align="center">

<br />

<img width="81" height="81" alt="image" src="https://github.com/user-attachments/assets/c997c90b-5208-4be2-93dd-2ef3714db32d" />
&nbsp;&nbsp;&nbsp;
<img width="81" height="81" alt="image" src="https://github.com/user-attachments/assets/de530e7f-2f3b-43b9-be7e-76077280be7f" />


<br />
<br />

# n1-brightdata

### An autonomous web research agent powered by **Yutori n1** and **Bright Data Scraping Browser**

Give it a task. It browses the web. It brings back answers.

<br />

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Bright Data](https://img.shields.io/badge/Powered%20by-Bright%20Data-FF6B35?style=flat-square)](https://brightdata.com)
[![Yutori](https://img.shields.io/badge/Model-n1--latest-8B5CF6?style=flat-square)](https://yutori.com)

</div>

---

<div align="center">

## How It Works

</div>

```
  You give it a task
        │
        ▼
  Opens Bright Data Scraping Browser (real Chromium, residential IPs)
        │
        ▼
  Takes a screenshot → sends to Yutori n1 model
        │
        ▼
  n1 reasons: click here, type this, scroll there...
        │
        ▼
  Repeats until confident enough to answer
        │
        ▼
  Returns result to your terminal
```

<div align="center">

The agent uses **Bright Data's Scraping Browser** for undetectable, scalable browsing and **Yutori's n1** reasoning model to make decisions — all controlled from a single CLI command.

</div>

---

<div align="center">

## Prerequisites

</div>

Before you begin, you'll need accounts and credentials from two services:

| Service | What you need | Where to get it |
|:-------:|:-------------:|:---------------:|
| **Bright Data** | Scraping Browser CDP URL | [brightdata.com](https://brightdata.com) → Scraping Browser zone |
| **Yutori** | API Key | [yutori.com](https://yutori.com) |

---

<div align="center">

## Installation

</div>

**1. Clone the repository**

```bash
git clone https://github.com/meirk-brd/n1-brightdata.git
cd n1-brightdata
```

**2. (Recommended) Create a virtual environment**

```bash
python -m venv .venv
source .venv/bin/activate       # macOS / Linux
# .venv\Scripts\activate        # Windows
```

**3. Install the CLI**

```bash
pip install -e .
```

This installs the `n1-brightdata` command globally in your environment. Because it's editable (`-e`), any local code changes take effect immediately — no reinstall needed.

**4. Install the browser**

```bash
playwright install chromium
```

---

<div align="center">

## Configuration

</div>

### Option A — Interactive Setup (Recommended)

Run the built-in setup wizard. It walks you through every credential, saves them to `.env`, installs Playwright, and optionally tests your connections:

```bash
n1-brightdata setup
```

### Option B — Manual `credentials.json`

Create the file at `~/.n1-brightdata/credentials.json`:

```bash
mkdir -p ~/.n1-brightdata
cat > ~/.n1-brightdata/credentials.json << 'EOF'
{
  "YUTORI_API_KEY": "your_yutori_api_key_here",
  "BRD_CDP_URL": "wss://brd-customer-XXXXXX-zone-scraping_browser:PASSWORD@brd.superproxy.io:9222"
}
EOF
chmod 600 ~/.n1-brightdata/credentials.json
```

### Optional Tuning (project-level)

Tuning parameters stay in a local `.env` file or shell environment — they are not stored in `credentials.json`:

```bash
# .env  (in your project directory, or export in your shell)
N1_SCREENSHOT_FORMAT=jpeg          # jpeg | png
N1_JPEG_QUALITY=60                 # 1–100
N1_SCREENSHOT_TIMEOUT_MS=90000     # screenshot timeout in milliseconds
N1_MAX_REQUEST_BYTES=9500000       # trim old screenshots if payload exceeds this
N1_KEEP_RECENT_SCREENSHOTS=6       # how many screenshots to keep in context
N1_ENABLE_SUFFICIENCY_CHECK=true   # stop early when the agent is confident
N1_STOP_CONFIDENCE_THRESHOLD=0.78  # confidence threshold for early stopping (0–1)
```

### Configuration Precedence

```
CLI flags  >  Shell env vars  >  .env file (tuning)  >  ~/.n1-brightdata/credentials.json
```

---

<div align="center">

## Usage

</div>

### Basic

```bash
n1-brightdata "What is the current price of Bitcoin?"
```

### With a Starting URL

```bash
n1-brightdata "Find the top 5 trending repositories" --url "https://github.com/trending"
```

### Limit the Number of Steps

```bash
n1-brightdata "Summarize today's top news" --url "https://news.ycombinator.com" --max-steps 15
```

### Full Command Reference

```
n1-brightdata [TASK] [OPTIONS]
```

| Option | Type | Default | Description |
|:-------|:----:|:-------:|:------------|
| `TASK` | string | *(required)* | The task for the agent to complete |
| `--url` | string | `https://www.google.com` | Starting URL before the agent loop begins |
| `--max-steps` | integer | `30` | Maximum number of browser actions (min: 1) |
| `--screenshot-format` | `jpeg` \| `png` | `jpeg` | Format of screenshots sent to the model |
| `--jpeg-quality` | integer | `60` | JPEG quality when format is `jpeg` (1–100) |
| `--screenshot-timeout-ms` | integer | `90000` | Screenshot timeout in milliseconds |
| `--yutori-api-key` | string | *(env)* | Yutori API key (overrides env / .env) |
| `--brd-cdp-url` | string | *(env)* | Bright Data CDP WebSocket URL (overrides env / .env) |
| `--env-file` | path | `./.env` | Custom path to a `.env` credentials file |

### Help

```bash
n1-brightdata --help
n1-brightdata run --help
n1-brightdata setup --help
```

---

<div align="center">

## Examples

</div>

```bash
# Research a topic
n1-brightdata "What are the key differences between GPT-4o and Claude 3.5 Sonnet?"

# Scrape structured data
n1-brightdata "List the top 10 products on Product Hunt today" --url "https://www.producthunt.com"

# Monitor a specific page
n1-brightdata "Is there a sale on the MacBook Pro 16-inch?" \
  --url "https://www.apple.com/shop/buy-mac/macbook-pro" \
  --max-steps 10

# High-quality screenshots for visual tasks
n1-brightdata "Describe the layout of the Airbnb homepage" \
  --url "https://www.airbnb.com" \
  --screenshot-format png

# Use a different .env for multiple accounts
n1-brightdata "Check order status" --env-file ~/.config/n1/work.env
```

---

<div align="center">

## Project Structure

</div>

```
n1-brightdata/
├── src/
│   └── n1_brightdata/
│       ├── __init__.py      # Package exports: AgentConfig, build_agent_config, run_agent
│       ├── agent.py         # Core agentic loop, browser tools, n1 model integration
│       ├── cli.py           # Click CLI: `run` and `setup` commands
│       └── console.py       # Rich terminal UI: banners, step display, progress
├── pyproject.toml           # Project metadata, dependencies, CLI entrypoint
└── .env                     # Your credentials (not committed)
```

---

<div align="center">

## Browser Tools

The agent can perform these actions autonomously:

</div>

<div align="center">

| Action | Description |
|:------:|:-----------:|
| `left_click` | Click at coordinates |
| `double_click` | Double-click at coordinates |
| `triple_click` | Triple-click (select all text in field) |
| `right_click` | Right-click context menu |
| `hover` | Mouse hover at coordinates |
| `drag` | Drag from one coordinate to another |
| `scroll` | Scroll up / down / left / right |
| `type` | Type text (with optional clear & Enter) |
| `key_press` | Press key combinations (e.g. `Ctrl+F`) |
| `goto_url` | Navigate to a URL |
| `go_back` | Browser back button |
| `refresh` | Reload the current page |
| `wait` | Pause for 800ms |

</div>

---

<div align="center">

## Dependencies

</div>

<div align="center">

| Package | Purpose |
|:-------:|:-------:|
| `yutori >= 0.4.0` | Yutori SDK for n1 model access |
| `openai` | OpenAI-compatible API client |
| `playwright` | Chromium browser automation |
| `click` | CLI framework |
| `python-dotenv` | `.env` file loading |
| `rich >= 13.0` | Beautiful terminal output |

</div>

---

<div align="center">

## License

MIT © [Bright Data](https://brightdata.com)

<br />

*Built with [Bright Data Scraping Browser](https://brightdata.com/products/scraping-browser) + [Yutori n1](https://yutori.com)*

</div>
