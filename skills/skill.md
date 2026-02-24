# n1-brightdata Agent Skill

## What This Tool Is

`n1-brightdata` is a CLI that runs an autonomous web research agent. It connects the **Yutori n1** reasoning model to a **Bright Data Scraping Browser** (a real Chromium browser with residential IPs) and loops through a screenshot → reason → act cycle until the task is answered.

Use this CLI when a user needs live, current data from the web — prices, headlines, page content, search results, competitor info, availability checks, etc.

---

## Prerequisites

The CLI must be installed and credentials must be configured. Check by running:

```bash
n1-brightdata --help
```

If not installed:

```bash
pip install n1-brightdata
n1-brightdata setup   # interactive wizard: prompts for Bright Data CDP URL and Yutori API key
```

Setup stores credentials globally at `~/.n1-brightdata/credentials.json` (permissions 0o600). They are loaded automatically on every run — no need to re-enter them.

---

## How To Run a Task

### Basic usage

```bash
n1-brightdata "your research task here"
```

The bare string is automatically routed to the `run` subcommand. Both of these are equivalent:

```bash
n1-brightdata "What is the current price of Bitcoin?"
n1-brightdata run "What is the current price of Bitcoin?"
```

### Start at a specific URL

```bash
n1-brightdata "Find the top 5 trending repositories today" \
  --url "https://github.com/trending"
```

Default starting URL is `https://www.google.com`.

### Control how many browsing steps the agent can take

```bash
n1-brightdata "Is there a sale on MacBook Pro?" \
  --url "https://apple.com/shop" \
  --max-steps 10
```

Default is 30 steps. Each step is one screenshot-to-action cycle.

### Use PNG screenshots (better for visual/layout tasks)

```bash
n1-brightdata "Describe the layout of Airbnb's homepage" \
  --url "https://airbnb.com" \
  --screenshot-format png
```

Default format is `jpeg` with quality 60. Use `png` when the task requires reading fine details.

---

## All CLI Options

| Option | Default | Description |
|---|---|---|
| `TASK` | required | The research task to complete |
| `--url` | `https://www.google.com` | URL to start browsing from |
| `--max-steps` | `30` | Maximum browsing actions before forced finalization |
| `--screenshot-format` | `jpeg` | `jpeg` or `png` |
| `--jpeg-quality` | `60` | JPEG compression 1–100 (lower = smaller payload) |
| `--screenshot-timeout-ms` | `90000` | Timeout per screenshot in milliseconds |
| `--yutori-api-key` | from credentials | Override Yutori API key for this run |
| `--brd-cdp-url` | from credentials | Override Bright Data CDP URL for this run |
| `--env-file` | `./.env` | Path to a project-level `.env` file |

---

## Credential Precedence

The CLI resolves credentials in this order (highest to lowest priority):

```
CLI flags  >  shell env vars  >  .env file  >  ~/.n1-brightdata/credentials.json
```

To override for a single run without touching saved credentials:

```bash
YUTORI_API_KEY="sk-..." BRD_CDP_URL="wss://..." n1-brightdata "task"
```

---

## Project-Level Tuning (`.env` file)

For fine-grained control, create a `.env` in the project root:

```bash
N1_SCREENSHOT_FORMAT=jpeg
N1_JPEG_QUALITY=60
N1_SCREENSHOT_TIMEOUT_MS=90000
N1_MAX_REQUEST_BYTES=9500000       # trim old screenshots if payload exceeds this
N1_KEEP_RECENT_SCREENSHOTS=6       # how many recent screenshots to keep in context
N1_ENABLE_SUFFICIENCY_CHECK=true   # stop early when agent is confident
N1_STOP_CONFIDENCE_THRESHOLD=0.78  # 0.0–1.0 confidence required to stop early
```

---

## Programmatic API

Import and call from Python when you need to integrate the agent into a larger workflow:

```python
from n1_brightdata import build_agent_config, run_agent

config = build_agent_config(
    env_file=".env",                    # optional: path to .env
    yutori_api_key="sk-...",            # optional: override credential
    brd_cdp_url="wss://...",            # optional: override credential
    screenshot_format="jpeg",
    jpeg_quality=60,
    max_request_bytes=9_500_000,
    keep_recent_screenshots=6,
    enable_sufficiency_check=True,
    stop_confidence_threshold=0.78,
)

run_agent(
    task="Find the current price of ETH/USD",
    start_url="https://www.google.com",
    config=config,
    max_steps=20,
)
```

`run_agent()` blocks until completion. The final answer is printed to the terminal via Rich.

---

## How the Agent Works (Internals)

Understanding this helps you write better tasks and set appropriate limits.

```
User task
   ↓
Take screenshot of current page
   ↓
Send screenshot + task + history → Yutori n1 model
   ↓
Model returns tool calls OR final answer
   ↓ (if tool calls)
Execute browser action via Playwright (click, type, scroll, navigate, etc.)
   ↓
Optionally: sufficiency check (is the current answer good enough to stop?)
   ↓
Loop → repeat up to max_steps
   ↓ (if no tool calls OR sufficiency passed OR max_steps reached)
Return final answer
```

### Browser actions the agent can take

| Tool | What it does |
|---|---|
| `left_click` | Click at coordinates |
| `double_click` | Double-click |
| `triple_click` | Select all text in a field |
| `right_click` | Open context menu |
| `hover` | Hover mouse |
| `drag` | Drag from one point to another |
| `scroll` | Scroll up/down/left/right by N units |
| `type` | Type text; can clear field first, can press Enter after |
| `key_press` | Press key combo (e.g., `Ctrl+F`, `Escape`) |
| `goto_url` | Navigate to a URL |
| `go_back` | Browser back |
| `refresh` | Reload page |
| `wait` | Pause 800ms |

Coordinates are in a 1000×1000 normalized space — the model reasons in this space and the CLI converts to actual pixels.

---

## Common Patterns

### Research a product or price

```bash
n1-brightdata "What is the current price of a 16-inch MacBook Pro M4 Max on Apple's website?" \
  --url "https://www.apple.com/shop/buy-mac/macbook-pro/16-inch"
```

### Summarize a news article or blog post

```bash
n1-brightdata "Summarize the key points of this article" \
  --url "https://example.com/some-article" \
  --max-steps 5
```

### Scrape structured data

```bash
n1-brightdata "List the top 10 Python packages on PyPI this week with their download counts" \
  --url "https://pypistats.org/top"
```

### Check availability or status

```bash
n1-brightdata "Is this product in stock and what color options are available?" \
  --url "https://example-store.com/product/123" \
  --max-steps 8
```

### Multi-step research starting from search

```bash
n1-brightdata "Find the CEO of Bright Data and their LinkedIn profile URL"
```

(starts at Google, agent searches, navigates, extracts the answer)

---

## Tips for Writing Good Tasks

- **Be specific.** "Find the price" is weaker than "Find the current USD price of plan X on the pricing page."
- **Set `--url`** when you know the right starting page — it saves steps and tokens.
- **Lower `--max-steps`** for simple lookups (5–10) to keep runs fast and cheap.
- **Raise `--max-steps`** for multi-hop research tasks (30–50).
- **Use `--screenshot-format png`** only when fine visual details matter — it increases payload size.
- **Disable sufficiency check** (`N1_ENABLE_SUFFICIENCY_CHECK=false`) if the agent keeps stopping too early.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `credentials not found` | Setup not run | Run `n1-brightdata setup` |
| `connection refused` / CDP error | Bad Bright Data URL or zone inactive | Check `BRD_CDP_URL` in credentials, verify zone is active in Bright Data dashboard |
| `401 Unauthorized` | Bad Yutori key | Re-run `n1-brightdata setup` and enter correct key |
| Agent stops too early | Sufficiency threshold too low | Raise `N1_STOP_CONFIDENCE_THRESHOLD` to `0.9` or set `N1_ENABLE_SUFFICIENCY_CHECK=false` |
| Agent runs all steps without finishing | Task too vague or page blocks access | Make task more specific; try a different `--url` |
| Screenshots too large / slow | High resolution or PNG | Use `--jpeg-quality 40` or reduce `N1_KEEP_RECENT_SCREENSHOTS` |
| `content length exceeded` | Payload too big | Lower `N1_MAX_REQUEST_BYTES` or `N1_KEEP_RECENT_SCREENSHOTS` |

---

## Setup Command Reference

```bash
n1-brightdata setup
```

This interactive wizard:
1. Detects and displays any existing saved credentials (masked)
2. Prompts for Bright Data Scraping Browser CDP URL (`wss://brd-customer-...`)
3. Prompts for Yutori API key
4. Saves both to `~/.n1-brightdata/credentials.json` with secure permissions
5. Installs the Playwright Chromium browser (`playwright install chromium`)
6. Optionally tests connectivity to both services

Run this once after installing the package. Re-run it to update credentials.
