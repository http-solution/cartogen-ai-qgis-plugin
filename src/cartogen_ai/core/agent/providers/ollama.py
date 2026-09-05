import json
import requests
from .base import BaseAiProvider, DEFAULT_MAX_TOKENS, post_with_retry


def _server_root(endpoint_url):
    """Derives the bare Ollama server root from a stored chat/completions URL,
    e.g. 'http://localhost:11434/v1/chat/completions' -> 'http://localhost:11434'."""
    url = (endpoint_url or "http://localhost:11434").rstrip("/")
    for suffix in ("/v1/chat/completions", "/api/chat", "/chat/completions"):
        if url.endswith(suffix):
            return url[: -len(suffix)]
    return url


def list_models(endpoint_url):
    """Fetches the list of locally-pulled models from a running Ollama server's
    /api/tags endpoint. No auth -- this is a local service."""
    try:
        response = requests.get(
            f"{_server_root(endpoint_url)}/api/tags",
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        ids = sorted({m.get("name", "") for m in data.get("models", []) if m.get("name")})
        return {"success": True, "models": ids}
    except requests.exceptions.HTTPError as e:
        return {"error": f"Ollama models list failed ({e.response.status_code}): {e.response.text}"}
    except Exception as e:
        return {"error": f"Ollama models list request failed: {e} (is Ollama running?)"}


class OllamaClient(BaseAiProvider):
    def __init__(self, endpoint_url="http://localhost:11434/v1/chat/completions", model="llama3.1", status_callback=None):
        self.base_url = endpoint_url
        self.model = model
        self._status_callback = status_callback

    def set_status_callback(self, callback):
        self._status_callback = callback

    def _emit_status(self, text):
        if self._status_callback:
            try:
                self._status_callback(text)
            except Exception:
                pass

    def complete(self, messages, tools=None, max_tokens=None):
        self._emit_status(f"Using Ollama: {self.model}")
        headers = {
            "Content-Type": "application/json",
        }

        payload = {"model": self.model, "messages": messages, "max_tokens": max_tokens or DEFAULT_MAX_TOKENS}
        if tools:
            payload["tools"] = tools
            
        # Local server is the client most likely to hit a transient failure in
        # practice (still loading a model, briefly saturated) -- route through
        # the same shared retry helper every other provider client uses
        # instead of a bare requests.post with no retry at all. timeout stays
        # 180s (vs. 60s elsewhere) -- local models can take a while.
        try:
            response = post_with_retry(
                self.base_url, headers, json.dumps(payload), timeout=180,
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.HTTPError as e:
            return {"error": f"Ollama HTTP error ({e.response.status_code}): {e.response.text}"}
        except requests.exceptions.RequestException as e:
            return {"error": f"Ollama connection failed: {e} (is Ollama running?)"}

        try:
            out = {"message": data["choices"][0]["message"], "model": self.model}
            # Ollama's OpenAI-compatible endpoint reports token counts under its own
            # native field names (eval_count/prompt_eval_count), not the OpenAI-shaped
            # 'usage' object extract_openai_style_usage expects -- confirmed against
            # Ollama's own API docs (github.com/ollama/ollama/blob/main/docs/api.md),
            # not assumed. Handled separately here rather than folding into that shared
            # helper, since the two field-name conventions don't overlap.
            if isinstance(data.get("prompt_eval_count"), int) or isinstance(data.get("eval_count"), int):
                out["usage"] = {
                    "input_tokens": data.get("prompt_eval_count") or 0,
                    "output_tokens": data.get("eval_count") or 0,
                }
            return out
        except (KeyError, IndexError, TypeError) as e:
            return {"error": f"Unexpected response format from Ollama: {e}"}
