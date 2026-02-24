import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import APIStatusError, OpenAI
from playwright.sync_api import sync_playwright
from yutori.n1.payload import (
    DEFAULT_KEEP_RECENT_SCREENSHOTS,
    DEFAULT_MAX_REQUEST_BYTES,
    trim_images_to_fit,
)

from .console import (
    print_banner,
    print_config_summary,
    print_done,
    print_early_stop,
    print_error,
    print_final_answer,
    print_step,
    print_tool_action,
    print_trim_notice,
    status_spinner,
)

DEFAULT_MODEL = "n1-latest"
DEFAULT_VIEWPORT_W = 1280
DEFAULT_VIEWPORT_H = 800
DEFAULT_SCREENSHOT_FORMAT = "jpeg"
DEFAULT_JPEG_QUALITY = 60
DEFAULT_SCREENSHOT_TIMEOUT_MS = 90_000
DEFAULT_ENABLE_SUFFICIENCY_CHECK = True
DEFAULT_STOP_CONFIDENCE_THRESHOLD = 0.78

BROWSER_AGENT_SYSTEM_PROMPT = (
    "You are a web research and browsing agent.\n"
    "Use tools only when a specific missing fact is required.\n"
    "Stop as soon as the user task can be answered with reasonable confidence.\n"
    "Do not perform redundant confirmation passes once the key answer is established.\n"
    "Before every tool call, ask: what exact missing fact will this retrieve?\n"
    "If no concrete missing fact exists, return a final answer and do not call tools.\n"
    "When you see '[Steps remaining: N]' in a message and N <= 3, stop browsing immediately "
    "and compile all gathered information into a complete final answer without calling any tools."
)


@dataclass(frozen=True)
class AgentConfig:
    yutori_api_key: str
    brd_cdp_url: str
    model: str = DEFAULT_MODEL
    viewport_w: int = DEFAULT_VIEWPORT_W
    viewport_h: int = DEFAULT_VIEWPORT_H
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES
    keep_recent_screenshots: int = DEFAULT_KEEP_RECENT_SCREENSHOTS
    screenshot_format: str = DEFAULT_SCREENSHOT_FORMAT
    jpeg_quality: int = DEFAULT_JPEG_QUALITY
    screenshot_timeout_ms: int = DEFAULT_SCREENSHOT_TIMEOUT_MS
    enable_sufficiency_check: bool = DEFAULT_ENABLE_SUFFICIENCY_CHECK
    stop_confidence_threshold: float = DEFAULT_STOP_CONFIDENCE_THRESHOLD

    def __post_init__(self) -> None:
        screenshot_format = self.screenshot_format.strip().lower()
        if screenshot_format not in {"png", "jpeg"}:
            screenshot_format = DEFAULT_SCREENSHOT_FORMAT
        object.__setattr__(self, "screenshot_format", screenshot_format)
        object.__setattr__(
            self,
            "keep_recent_screenshots",
            max(1, int(self.keep_recent_screenshots)),
        )
        object.__setattr__(
            self,
            "screenshot_timeout_ms",
            max(1, int(self.screenshot_timeout_ms)),
        )
        threshold = float(self.stop_confidence_threshold)
        if threshold < 0.0:
            threshold = 0.0
        elif threshold > 1.0:
            threshold = 1.0
        object.__setattr__(self, "stop_confidence_threshold", threshold)

    @property
    def image_mime(self) -> str:
        return "image/jpeg" if self.screenshot_format == "jpeg" else "image/png"

    @property
    def cdp_wss(self) -> str:
        return self.brd_cdp_url


CREDENTIALS_PATH = Path.home() / ".n1-brightdata" / "credentials.json"


def _load_global_credentials() -> None:
    """Inject credentials from ~/.n1-brightdata/credentials.json into os.environ."""
    if not CREDENTIALS_PATH.exists():
        return
    try:
        data = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return
    for key in ("YUTORI_API_KEY", "BRD_CDP_URL"):
        value = data.get(key, "")
        if isinstance(value, str) and value.strip():
            os.environ.setdefault(key, value.strip())


def _load_env_file(env_file: str | Path) -> None:
    """Load a .env file into os.environ (for optional tuning vars)."""
    env_path = Path(env_file).expanduser()
    if not env_path.is_absolute():
        env_path = (Path.cwd() / env_path).resolve()
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
    except Exception:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            os.environ.setdefault(key, value)
    else:
        load_dotenv(dotenv_path=env_path, override=False)


def load_env(env_file: str | Path | None = None) -> None:
    """Load credentials from ~/.n1-brightdata/credentials.json, then optionally a .env file."""
    _load_global_credentials()
    if env_file is not None:
        _load_env_file(env_file)
    else:
        local_env = Path.cwd() / ".env"
        if local_env.exists():
            _load_env_file(local_env)


def get_required_env(name: str, provided: str | None = None) -> str:
    value = (provided if provided is not None else os.environ.get(name) or "").strip()
    if not value or value == "YOUR_API_KEY":
        # Env var is empty/placeholder – try credentials saved by `yutori auth login`
        if name == "YUTORI_API_KEY":
            from yutori.auth import resolve_api_key

            sdk_key = resolve_api_key()
            if sdk_key:
                return sdk_key
        raise RuntimeError(f"Missing {name}. Set it in the shell or in .env.")
    return value


def _get_optional_env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer. Got: {raw!r}") from exc


def _get_optional_env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a float. Got: {raw!r}") from exc


def _get_optional_env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default

    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(
        f"{name} must be a boolean string (true/false/1/0). Got: {raw!r}"
    )


def build_agent_config(
    *,
    env_file: str | Path | None = None,
    yutori_api_key: str | None = None,
    brd_cdp_url: str | None = None,
    screenshot_format: str | None = None,
    jpeg_quality: int | None = None,
    screenshot_timeout_ms: int | None = None,
    max_request_bytes: int | None = None,
    keep_recent_screenshots: int | None = None,
    model: str = DEFAULT_MODEL,
    enable_sufficiency_check: bool | None = None,
    stop_confidence_threshold: float | None = None,
) -> AgentConfig:
    load_env(env_file)

    if screenshot_format is None:
        screenshot_format = (os.environ.get("N1_SCREENSHOT_FORMAT") or DEFAULT_SCREENSHOT_FORMAT).strip().lower()

    return AgentConfig(
        yutori_api_key=get_required_env("YUTORI_API_KEY", yutori_api_key),
        brd_cdp_url=get_required_env("BRD_CDP_URL", brd_cdp_url),
        model=model,
        max_request_bytes=max_request_bytes
        if max_request_bytes is not None
        else _get_optional_env_int("N1_MAX_REQUEST_BYTES", DEFAULT_MAX_REQUEST_BYTES),
        keep_recent_screenshots=keep_recent_screenshots
        if keep_recent_screenshots is not None
        else _get_optional_env_int(
            "N1_KEEP_RECENT_SCREENSHOTS", DEFAULT_KEEP_RECENT_SCREENSHOTS
        ),
        screenshot_format=screenshot_format,
        jpeg_quality=jpeg_quality
        if jpeg_quality is not None
        else _get_optional_env_int("N1_JPEG_QUALITY", DEFAULT_JPEG_QUALITY),
        screenshot_timeout_ms=screenshot_timeout_ms
        if screenshot_timeout_ms is not None
        else _get_optional_env_int(
            "N1_SCREENSHOT_TIMEOUT_MS", DEFAULT_SCREENSHOT_TIMEOUT_MS
        ),
        enable_sufficiency_check=enable_sufficiency_check
        if enable_sufficiency_check is not None
        else _get_optional_env_bool(
            "N1_ENABLE_SUFFICIENCY_CHECK", DEFAULT_ENABLE_SUFFICIENCY_CHECK
        ),
        stop_confidence_threshold=stop_confidence_threshold
        if stop_confidence_threshold is not None
        else _get_optional_env_float(
            "N1_STOP_CONFIDENCE_THRESHOLD", DEFAULT_STOP_CONFIDENCE_THRESHOLD
        ),
    )


def create_client(config: AgentConfig) -> OpenAI:
    return OpenAI(
        base_url="https://api.yutori.com/v1",
        api_key=config.yutori_api_key,
    )


def screenshot_b64(page: Any, config: AgentConfig) -> str:
    page.set_viewport_size({"width": config.viewport_w, "height": config.viewport_h})
    screenshot_kwargs = {"type": config.screenshot_format}
    if config.screenshot_format == "jpeg":
        screenshot_kwargs["quality"] = config.jpeg_quality
    screenshot_kwargs["timeout"] = config.screenshot_timeout_ms
    img_bytes = page.screenshot(**screenshot_kwargs)
    return base64.b64encode(img_bytes).decode("utf-8")


def to_abs(coords_1000: tuple[int, int], config: AgentConfig) -> tuple[int, int]:
    """n1 outputs coords in a 1000x1000 space."""
    x1000, y1000 = coords_1000
    x = round((x1000 / 1000) * config.viewport_w)
    y = round((y1000 / 1000) * config.viewport_h)
    return x, y


def run_tool(page: Any, tool_name: str, args: dict[str, Any], config: AgentConfig) -> None:
    if tool_name == "left_click":
        x, y = to_abs(tuple(args["coordinates"]), config)
        page.mouse.click(x, y)
    elif tool_name == "double_click":
        x, y = to_abs(tuple(args["coordinates"]), config)
        page.mouse.dblclick(x, y)
    elif tool_name == "triple_click":
        x, y = to_abs(tuple(args["coordinates"]), config)
        page.mouse.click(x, y, click_count=3)
    elif tool_name == "right_click":
        x, y = to_abs(tuple(args["coordinates"]), config)
        page.mouse.click(x, y, button="right")
    elif tool_name == "hover":
        x, y = to_abs(tuple(args["coordinates"]), config)
        page.mouse.move(x, y)
    elif tool_name == "drag":
        sx, sy = to_abs(tuple(args["start_coordinates"]), config)
        tx, ty = to_abs(tuple(args["coordinates"]), config)
        page.mouse.move(sx, sy)
        page.mouse.down()
        page.mouse.move(tx, ty)
        page.mouse.up()
    elif tool_name == "scroll":
        direction = args["direction"]
        amount = int(args["amount"])
        dx = dy = 0
        if direction == "down":
            dy = int(0.10 * config.viewport_h * amount)
        elif direction == "up":
            dy = -int(0.10 * config.viewport_h * amount)
        elif direction == "right":
            dx = int(0.10 * config.viewport_w * amount)
        elif direction == "left":
            dx = -int(0.10 * config.viewport_w * amount)
        page.mouse.wheel(dx, dy)
    elif tool_name == "type":
        text = args["text"]
        if args.get("clear_before_typing"):
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
        page.keyboard.type(text)
        if args.get("press_enter_after"):
            page.keyboard.press("Enter")
    elif tool_name == "key_press":
        page.keyboard.press(args["key_comb"])
    elif tool_name == "goto_url":
        page.goto(args["url"], wait_until="domcontentloaded")
    elif tool_name == "go_back":
        page.go_back(wait_until="domcontentloaded")
    elif tool_name == "refresh":
        page.reload(wait_until="domcontentloaded")
    elif tool_name == "wait":
        page.wait_for_timeout(800)
    else:
        raise ValueError(f"Unsupported tool: {tool_name}")


def n1_step(messages: list[dict[str, Any]], *, client: OpenAI, config: AgentConfig) -> Any:
    size_bytes, removed = trim_images_to_fit(
        messages,
        max_bytes=config.max_request_bytes,
        keep_recent=config.keep_recent_screenshots,
    )
    if removed:
        print_trim_notice(removed, size_bytes / (1024 * 1024))

    try:
        return client.chat.completions.create(
            model=config.model,
            messages=messages,
        )
    except APIStatusError as exc:
        if "content length exceeded" in str(exc).lower():
            retry_budget = max(config.max_request_bytes - 250_000, 1_000_000)
            size_bytes, removed = trim_images_to_fit(
                messages,
                max_bytes=retry_budget,
                keep_recent=config.keep_recent_screenshots,
            )
            if removed:
                print_trim_notice(removed, size_bytes / (1024 * 1024), retry=True)
                return client.chat.completions.create(
                    model=config.model,
                    messages=messages,
                )
        raise


def _extract_response_error_detail(resp: Any) -> str | None:
    def _field(obj: Any, key: str) -> Any:
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)

    def _text(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        value = value.strip()
        return value or None

    detail = _text(_field(resp, "detail"))
    if detail:
        return detail

    error = _field(resp, "error")
    if isinstance(error, dict):
        nested = _text(error.get("message")) or _text(error.get("detail"))
        if nested:
            return nested
    else:
        nested = _text(_field(error, "message")) or _text(error)
        if nested:
            return nested

    return _text(_field(resp, "message"))


def _first_choice_message(resp: Any, *, context: str) -> Any:
    if resp is None:
        raise RuntimeError(f"{context} returned no response.")

    choices = getattr(resp, "choices", None)
    if not isinstance(choices, list) or not choices:
        detail = _extract_response_error_detail(resp)
        base_msg = (
            f"{context} did not include completion choices. "
            "The API likely returned an error payload instead of a chat completion."
        )
        if detail:
            raise RuntimeError(f"{base_msg} API detail: {detail}")
        raise RuntimeError(base_msg)

    message = getattr(choices[0], "message", None)
    if message is None:
        raise RuntimeError(f"{context} returned a choice without a message.")
    return message


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    chunks.append(text.strip())
        return "\n".join(chunks).strip()
    return str(content).strip()


def _parse_json_object(text: str) -> dict[str, Any] | None:
    candidate = text.strip()
    if not candidate:
        return None

    parsed: Any
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(candidate[start : end + 1])
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return None
    return None


def maybe_finalize_early(
    *,
    client: OpenAI,
    config: AgentConfig,
    task: str,
    assistant_text: str,
) -> str | None:
    if not config.enable_sufficiency_check:
        return None
    if not assistant_text.strip():
        return None

    check_messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "You are a strict answer sufficiency checker.\n"
                "Decide if the draft already answers the task well enough to stop browsing.\n"
                "Return ONLY JSON with keys: is_sufficient (bool), confidence (0..1), "
                "final_answer (string), missing (string).\n"
                "If sufficient, final_answer must be complete and concise.\n"
                "If not sufficient, set missing to the key unresolved gap."
            ),
        },
        {
            "role": "user",
            "content": (
                f"TASK:\n{task}\n\n"
                f"DRAFT_ANSWER:\n{assistant_text}\n\n"
                "Should the agent stop now?"
            ),
        },
    ]

    try:
        resp = client.chat.completions.create(model=config.model, messages=check_messages)
    except Exception:
        return None

    try:
        judge_msg = _first_choice_message(resp, context="Sufficiency check response")
    except RuntimeError:
        return None
    judge_text = _content_to_text(judge_msg.content)
    parsed = _parse_json_object(judge_text)
    if not parsed:
        return None

    is_sufficient = bool(parsed.get("is_sufficient"))
    if not is_sufficient:
        return None

    try:
        confidence = float(parsed.get("confidence", 0.0))
    except Exception:
        confidence = 0.0
    if confidence < config.stop_confidence_threshold:
        return None

    final_answer = str(parsed.get("final_answer") or "").strip()
    if not final_answer:
        return None
    return final_answer


def _tool_args_summary(tool_name: str, args: dict[str, Any]) -> str:
    if "coordinates" in args:
        return f"({args['coordinates'][0]}, {args['coordinates'][1]})"
    if tool_name == "type":
        text = args.get("text", "")
        preview = text[:40] + "..." if len(text) > 40 else text
        return f'text="{preview}"'
    if tool_name == "goto_url":
        return args.get("url", "")
    if tool_name == "scroll":
        return f'{args.get("direction", "down")} x{args.get("amount", 1)}'
    if tool_name == "key_press":
        return args.get("key_comb", "")
    return ""


def _force_finalize(
    *,
    messages: list[dict[str, Any]],
    client: OpenAI,
    config: AgentConfig,
    task: str,
) -> None:
    """Called when max_steps is exhausted. Asks the model to synthesize a final answer
    from everything gathered so far, without calling any more tools."""
    synthesis_messages = messages + [
        {
            "role": "user",
            "content": (
                "You have reached the maximum number of browsing steps. "
                "Do NOT call any tools. "
                "Based solely on everything you have observed so far, "
                "compile and return a complete final answer to the original task:\n\n"
                f"{task}"
            ),
        }
    ]

    try:
        with status_spinner("Synthesizing final answer..."):
            resp = n1_step(synthesis_messages, client=client, config=config)
        msg = _first_choice_message(resp, context="Force-finalize response")
        answer = _content_to_text(msg.content)
        if answer:
            print_final_answer(answer)
        else:
            print_error("Agent exhausted all steps and could not produce a final answer.")
    except Exception as exc:
        print_error(f"Failed to synthesize final answer: {exc}")

    print_done()


def run_agent(
    *,
    task: str,
    start_url: str,
    config: AgentConfig,
    max_steps: int = 30,
) -> None:
    print_banner()
    print_config_summary(task, start_url, max_steps, config.model)

    client = create_client(config)

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(config.cdp_wss)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.pages[0] if context.pages else context.new_page()

        page.set_viewport_size({"width": config.viewport_w, "height": config.viewport_h})
        page.goto(start_url, wait_until="domcontentloaded")

        b64 = screenshot_b64(page, config)
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": BROWSER_AGENT_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"[Steps remaining: {max_steps}]\n{task}"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{config.image_mime};base64,{b64}"},
                    },
                ],
            }
        ]

        completed = False
        for step in range(1, max_steps + 1):
            remaining = max_steps - step
            with status_spinner(f"Step {step}/{max_steps} Thinking..."):
                resp = n1_step(messages, client=client, config=config)
            msg = _first_choice_message(resp, context=f"Agent step {step} response")
            tool_calls = getattr(msg, "tool_calls", None) or []
            assistant_text = _content_to_text(msg.content)

            print_step(step, max_steps, assistant_text)

            if not tool_calls:
                if assistant_text:
                    print_final_answer(assistant_text)
                print_done()
                completed = True
                break

            final_answer = maybe_finalize_early(
                client=client,
                config=config,
                task=task,
                assistant_text=assistant_text,
            )
            if final_answer:
                print_early_stop()
                print_final_answer(final_answer)
                print_done()
                completed = True
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_text,
                    "tool_calls": [tc.model_dump() for tc in tool_calls],
                }
            )

            for tc in tool_calls:
                tool_name = tc.function.name
                args = json.loads(tc.function.arguments)
                print_tool_action(tool_name, _tool_args_summary(tool_name, args))
                run_tool(page, tool_name, args, config)

                b64_new = screenshot_b64(page, config)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": [
                            {
                                "type": "text",
                                "text": f"[Steps remaining: {remaining}]\nCurrent URL: {page.url}",
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{config.image_mime};base64,{b64_new}"
                                },
                            },
                        ],
                    }
                )

        if not completed:
            _force_finalize(messages=messages, client=client, config=config, task=task)

        browser.close()


def main(
    *,
    task: str,
    start_url: str,
    env_file: str | Path | None = None,
    max_steps: int = 30,
) -> None:
    config = build_agent_config(env_file=env_file)
    run_agent(task=task, start_url=start_url, config=config, max_steps=max_steps)
