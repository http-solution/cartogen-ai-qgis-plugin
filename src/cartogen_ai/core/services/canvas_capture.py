"""The model sees the map (PLAN-032, roadmap step B): pure helpers that turn a canvas capture into a picture the model can look at.

Why: inspect_canvas_visually used to return the canvas as base64 TEXT inside a tool result, which a model reads as hundreds of thousands of
tokens of text, not as a picture (docs/ROADMAP_AUDIT_2026-10-27.md, finding 1). The chat clients already carry `image_url` parts for user
attachments, so the gap was plumbing: take the base64 out of the tool result and send the picture as an image part of a user message that
follows it, with the legend and the visible layers as text beside it.

No QGIS here, so every rule is unit-testable. Honest limits: which models can see pictures is a name heuristic (VISION_MODEL_HINTS), not a
query to the provider; no live vision call was made on any provider by the author of this module."""

MAX_EDGE_PIXELS = 1280
IMAGE_MARKER = "[Map picture of the current canvas]"
OLD_IMAGE_PLACEHOLDER = "[An earlier map picture was removed from this request to save space; the newest one follows or was not needed.]"

# Providers whose chat models take pictures, by client class name. "model" means: ask the model name (VISION_MODEL_HINTS).
_ALWAYS = frozenset({"GeminiClient", "ClaudeClient", "OpenAIClient"})
_BY_MODEL = frozenset({"OpenRouterClient", "OllamaClient", "CartogenClient"})
VISION_MODEL_HINTS = ("gemini", "claude", "gpt-4", "gpt-5", "gpt4", "vision", "llava", "pixtral", "-vl", "vl-", "gemma-3", "gemma3",
                      "moondream", "minicpm-v", "bakllava", "llama-4", "qwen2.5-vl", "qwen-vl", "4o", "grok-2-vision")


def fit_size(width, height, cap=MAX_EDGE_PIXELS):
    """(w, h) scaled down so the long edge is at most `cap`, never up, never below 1 pixel. Pure."""
    width, height = max(int(width or 0), 1), max(int(height or 0), 1)
    longest = max(width, height)
    if longest <= cap:
        return width, height
    scale = cap / longest
    return max(round(width * scale), 1), max(round(height * scale), 1)


def provider_supports_vision(client_class_name, model=None):
    """True when the chat model behind this client probably accepts a picture. A guess from the class name and the model name: the CLI bridges and
    anything unknown say False, so they get the text fallback instead of an error that would end the turn."""
    if client_class_name in _ALWAYS:
        return True
    if client_class_name in _BY_MODEL:
        name = str(model or "").lower()
        return any(hint in name for hint in VISION_MODEL_HINTS)
    return False


def build_image_message(image_b64, legend_text, layers_text, mime="png"):
    """The user message that shows the model the map: the picture, then the legend text, then the visible-layers text (that order). Pure."""
    return {"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{image_b64}"}},
        {"type": "text", "text": f"{IMAGE_MARKER} Legend: {legend_text or 'not available'}"},
        {"type": "text", "text": f"Visible layers, top to bottom: {layers_text or 'none'}"},
    ]}


def is_image_message(message):
    """True for a message build_image_message made (used to remove older pictures). Pure."""
    content = message.get("content") if isinstance(message, dict) else None
    return (isinstance(content, list) and len(content) == 3 and isinstance(content[1], dict)
            and str(content[1].get("text", "")).startswith(IMAGE_MARKER))


def split_image(result, vision_supported):
    """(result without the picture, message to send after the tool messages or None). The base64 never stays in the tool result: as text it
    costs hundreds of thousands of tokens. Without vision the model gets the legend and layers as text and a one-line reason. Pure."""
    if not isinstance(result, dict) or not isinstance(result.get("image_b64"), str) or not result["image_b64"]:
        return result, None
    clean = {k: v for k, v in result.items() if k != "image_b64"}
    legend, layers = result.get("legend_text"), result.get("layers_text")
    if result.get("blank"):
        clean["note"] = "The map canvas rendered blank (nothing visible in this extent); say so instead of describing a picture."
        return clean, None
    if not vision_supported:
        clean["note"] = ("This model cannot be sent a picture, so none was attached. What is on the map, from the project: "
                         f"legend: {legend or 'not available'}; visible layers: {layers or 'none'}.")
        return clean, None
    clean["note"] = "The map picture follows in the next message, with its legend and the visible layers as text; describe what you see in it."
    return clean, build_image_message(result["image_b64"], legend, layers, result.get("mime") or "png")


def compact_old_images(messages):
    """Replaces every picture message in `messages` (in place) with a short text, so only the newest picture is ever sent again. Returns how many
    were replaced. Pure."""
    replaced = 0
    for index, message in enumerate(messages):
        if is_image_message(message):
            messages[index] = {"role": "user", "content": OLD_IMAGE_PLACEHOLDER}
            replaced += 1
    return replaced
