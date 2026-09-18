import json
from .base import (
    BaseAiProvider, post_with_retry, get_with_retry, format_http_error, format_request_exception,
    requests, HTTPError, RequestException,
)
from ..model_selector import filter_chat_model_ids

ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MAX_TOKENS = 8096


def list_models(api_key):
    """Fetches the live model list from Anthropic's /v1/models endpoint."""
    try:
        response = get_with_retry(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        ids = [m.get("id", "") for m in data.get("data", [])]
        return {"success": True, "models": filter_chat_model_ids(ids)}
    except HTTPError as e:
        return {"error": format_http_error("Claude models list failed", e)}
    except Exception as e:
        return {"error": format_request_exception("Claude models list request failed", e)}


def _translate_user_content(content):
    """Converts OpenAI-style vision content blocks (image_url) to Anthropic's
    image block shape. Passes plain strings and already-Anthropic-shaped
    blocks through unchanged."""
    if not isinstance(content, list):
        return content
    converted = []
    for block in content:
        btype = block.get("type") if isinstance(block, dict) else None
        if btype == "text":
            converted.append({"type": "text", "text": block.get("text", "")})
        elif btype == "image_url":
            url = (block.get("image_url") or {}).get("url", "")
            if url.startswith("data:"):
                try:
                    header, b64_data = url.split(",", 1)
                    mime = header.split(";")[0].replace("data:", "") or "image/png"
                except ValueError:
                    mime, b64_data = "image/png", ""
                converted.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": mime, "data": b64_data},
                })
            else:
                converted.append({"type": "image", "source": {"type": "url", "url": url}})
        else:
            converted.append(block)
    return converted


def to_anthropic_request(openai_messages, openai_tools):
    """Translates this plugin's internal OpenAI-shaped conversation (used by
    agent.py and every other provider) into Anthropic's native Messages API
    shape: system as a top-level field, no 'system' or 'tool' roles inside
    messages, and tool_use/tool_result content blocks instead of tool_calls."""
    system_text = ""
    anthropic_messages = []
    pending_tool_results = []

    def flush_tool_results():
        nonlocal pending_tool_results
        if pending_tool_results:
            anthropic_messages.append({"role": "user", "content": pending_tool_results})
            pending_tool_results = []

    for msg in openai_messages:
        role = msg.get("role")

        if role == "system":
            piece = str(msg.get("content", ""))
            system_text = f"{system_text}\n{piece}".strip() if system_text else piece
            continue

        if role == "tool":
            pending_tool_results.append({
                "type": "tool_result",
                "tool_use_id": msg.get("tool_call_id", ""),
                "content": str(msg.get("content", "")),
            })
            continue

        flush_tool_results()

        if role == "assistant":
            content_blocks = []
            text = msg.get("content")
            if text:
                content_blocks.append({"type": "text", "text": text})
            for call in (msg.get("tool_calls") or []):
                fn = call.get("function", {}) if isinstance(call, dict) else {}
                try:
                    tool_input = json.loads(fn.get("arguments") or "{}")
                except (TypeError, ValueError):
                    tool_input = {}
                content_blocks.append({
                    "type": "tool_use",
                    "id": call.get("id", ""),
                    "name": fn.get("name", ""),
                    "input": tool_input,
                })
            if not content_blocks:
                content_blocks = [{"type": "text", "text": ""}]
            anthropic_messages.append({"role": "assistant", "content": content_blocks})
        elif role == "user":
            anthropic_messages.append({
                "role": "user",
                "content": _translate_user_content(msg.get("content", "")),
            })

    flush_tool_results()

    anthropic_tools = None
    if openai_tools:
        anthropic_tools = []
        for t in openai_tools:
            fn = t.get("function", {}) if isinstance(t, dict) else {}
            anthropic_tools.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
            })

    return system_text, anthropic_messages, anthropic_tools


def from_anthropic_response(data, fallback_model):
    """Translates an Anthropic Messages API response back into the OpenAI-shaped
    {"message": ..., "model": ...} dict every other provider in this codebase
    returns from complete(), so agent.py's tool-calling loop needs no changes."""
    blocks = data.get("content", []) or []
    text_parts = []
    tool_calls = []
    for block in blocks:
        btype = block.get("type")
        if btype == "text":
            text_parts.append(block.get("text", ""))
        elif btype == "tool_use":
            tool_calls.append({
                "id": block.get("id", ""),
                "type": "function",
                "function": {
                    "name": block.get("name", ""),
                    "arguments": json.dumps(block.get("input", {}), default=str),
                },
            })

    content_text = "\n".join(p for p in text_parts if p) or None
    if not content_text and not tool_calls and data.get("stop_reason") == "refusal":
        content_text = "[Claude declined this request for safety reasons.]"

    message = {"role": "assistant", "content": content_text}
    if tool_calls:
        message["tool_calls"] = tool_calls

    out = {"message": message, "model": data.get("model", fallback_model)}
    # Anthropic's native field names (input_tokens/output_tokens) already match this
    # plugin's common usage shape (see base.extract_openai_style_usage's docstring for
    # why that shape was picked) -- but Anthropic's own "input_tokens" is deliberately
    # narrow: it excludes anything served from or written to the prompt cache (this
    # client's OpenRouter/native Claude calls already send cache_control breakpoints --
    # see build_anthropic_request -- so a multi-tool-call turn's repeated system
    # prompt/tools genuinely gets cache hits after the first iteration). Reconstructed
    # to the FULL request size here (input_tokens + cache_read_input_tokens +
    # cache_creation_input_tokens, Anthropic's own documented formula for "total input
    # tokens processed") so "~N tokens this session" means the same thing across every
    # provider -- Gemini/OpenAI's own "prompt_tokens" already includes cached tokens in
    # its headline number, with the cache-hit portion reported as a separate breakdown
    # (see extract_openai_style_usage) rather than subtracted from the total the way
    # Anthropic's raw field is. cached_tokens (2026-09-13, direct request: "implement
    # gemini caching") is the read-from-cache portion specifically -- how much of the
    # total was actually discounted, not written to the report at all before this.
    usage = data.get("usage")
    if isinstance(usage, dict) and ("input_tokens" in usage or "output_tokens" in usage):
        cache_read = usage.get("cache_read_input_tokens") or 0
        cache_creation = usage.get("cache_creation_input_tokens") or 0
        out["usage"] = {
            "input_tokens": (usage.get("input_tokens") or 0) + cache_read + cache_creation,
            "output_tokens": usage.get("output_tokens") or 0,
        }
        if cache_read:
            out["usage"]["cached_tokens"] = cache_read
    return out


class ClaudeClient(BaseAiProvider):
    """Adapter for Anthropic's native Messages API. Uses raw HTTP (requests)
    rather than the official `anthropic` SDK to match this plugin's existing
    pattern across all providers -- QGIS's bundled Python environment doesn't
    carry the anthropic package, and every other provider here (OpenRouter,
    Gemini, Groq, Cerebras, DeepSeek, Ollama) is a thin requests-based client
    with no SDK dependency."""

    def __init__(self, api_key, model="claude-opus-5", status_callback=None):
        self.api_key = api_key
        self.model = model
        self._status_callback = status_callback
        self.base_url = "https://api.anthropic.com/v1/messages"

    def set_status_callback(self, callback):
        self._status_callback = callback

    def _emit_status(self, text):
        if self._status_callback:
            try:
                self._status_callback(text)
            except Exception:
                pass

    def complete(self, messages, tools=None, max_tokens=None):
        self._emit_status(f"Using Claude: {self.model}")
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        system_text, anthropic_messages, anthropic_tools = to_anthropic_request(messages, tools)
        payload = {
            "model": self.model,
            "max_tokens": max_tokens or DEFAULT_MAX_TOKENS,
            "messages": anthropic_messages,
        }
        if system_text:
            # The system prompt and tool schemas are identical on every iteration
            # of the SAME tool-calling turn (often 5-20+ requests) and largely
            # identical across turns too. Marking them as cache breakpoints means
            # Anthropic serves iterations 2+ from cache instead of reprocessing
            # ~1,500 tokens of fixed content on every single request.
            payload["system"] = [
                {"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}
            ]
        if anthropic_tools:
            anthropic_tools[-1] = {**anthropic_tools[-1], "cache_control": {"type": "ephemeral"}}
            payload["tools"] = anthropic_tools
        if anthropic_messages:
            # Cost/performance pass, 2026-09-19: system+tools above cache the fixed prefix, but
            # every iteration of a multi-tool-call turn (often 5-20+ requests) also resends the
            # WHOLE growing `messages` list -- each iteration only appends one new tool_result,
            # yet every prior tool_result was still being reprocessed at full price on every
            # subsequent call. Confirmed against Anthropic's own docs (platform.claude.com/docs,
            # "Prompt caching" -- fetched 2026-09-18, not assumed) that a top-level
            # `cache_control` field on the request auto-places a breakpoint on the last
            # cacheable message block and walks it forward as the conversation grows, exactly
            # this shape ("the robust combination for agent loops": one explicit breakpoint on
            # the static system/tools prefix + automatic caching for the message tail). Uses a
            # 3rd of the 4 allowed breakpoints (system + tools' explicit markers are the other
            # 2), so this stays within the request-level limit.
            payload["cache_control"] = {"type": "ephemeral"}

        try:
            response = post_with_retry(self.base_url, headers, json.dumps(payload), timeout=60)
            response.raise_for_status()
            data = response.json()
            return from_anthropic_response(data, self.model)
        except HTTPError as e:
            return {"error": format_http_error("Claude API error", e)}
        except Exception as e:
            return {"error": format_request_exception("Claude API request failed", e)}
