"""Shared helpers: env loading, paths, JSON IO, and the OpenRouter HTTP client.

Stdlib only — no third-party dependencies. Works on Python 3.9+.
"""
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
FIXTURES_DIR = DATA_DIR / "fixtures"
RESULTS_DIR = DATA_DIR / "results"
PRED_DIR = DATA_DIR / "predictions"
OUTPUT_DIR = ROOT / "output"

OPENROUTER_BASE = "https://openrouter.ai/api/v1"

# Knockout rounds in order. TP = third-place play-off, F = final.
ROUND_ORDER = ["R32", "R16", "QF", "SF", "TP", "F"]
ROUND_LABELS = {
    "R32": "Round of 32",
    "R16": "Round of 16",
    "QF": "Quarter-finals",
    "SF": "Semi-finals",
    "TP": "Third-place play-off",
    "F": "Final",
}


def load_env(path=None):
    """Minimal .env loader (no third-party deps). Real environment vars win."""
    path = Path(path) if path else ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def get_api_key():
    load_env()
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise SystemExit(
            "Missing OPENROUTER_API_KEY. Copy .env.example to .env and add your key "
            "(get one at https://openrouter.ai/keys)."
        )
    return key


def load_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text())


def save_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False))


def load_models_config():
    cfg = load_json(CONFIG_DIR / "models.json")
    if not cfg:
        raise SystemExit("config/models.json not found.")
    return cfg


def enabled_models(cfg):
    return [m for m in cfg.get("models", []) if m.get("enabled", True)]


def slugify(text):
    return re.sub(r"[^a-z0-9._-]+", "-", str(text).lower()).strip("-")


# ---------------------------------------------------------------------------
# Robust JSON extraction from a model's free-text response
# ---------------------------------------------------------------------------
def extract_json(text):
    """Pull the first JSON object/array out of a model response (handles ``` fences)."""
    if not text:
        raise ValueError("empty response")
    fenced = re.findall(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    for candidate in fenced + [text]:
        candidate = candidate.strip()
        try:
            return json.loads(candidate)
        except Exception:
            pass
        blob = _first_balanced(candidate)
        if blob is not None:
            try:
                return json.loads(blob)
            except Exception:
                continue
    raise ValueError("no parseable JSON found in response")


def _first_balanced(text):
    """Return the first balanced {...} or [...] substring, or None."""
    start = None
    open_ch = close_ch = None
    for i, ch in enumerate(text):
        if ch in "{[":
            start, open_ch = i, ch
            close_ch = "}" if ch == "{" else "]"
            break
    if start is None:
        return None
    depth = 0
    in_str = esc = False
    for j in range(start, len(text)):
        ch = text[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start:j + 1]
    return None


# ---------------------------------------------------------------------------
# OpenRouter client (stdlib urllib)
# ---------------------------------------------------------------------------
class OpenRouter:
    def __init__(self, api_key=None, temperature=None):
        self.api_key = api_key or get_api_key()
        if temperature is None:
            temperature = float(os.environ.get("PREDICT_TEMPERATURE", "0.2"))
        self.temperature = temperature

    def _headers(self):
        return {
            "Authorization": "Bearer " + self.api_key,
            "Content-Type": "application/json",
            "HTTP-Referer": "https://localhost/wc-predictor",
            "X-Title": "World Cup Model Predictor",
        }

    def chat(self, model, system, user, temperature=None, timeout=180):
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature if temperature is None else temperature,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            OPENROUTER_BASE + "/chat/completions",
            data=data, headers=self._headers(), method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            raise RuntimeError("HTTP %s from OpenRouter: %s" % (e.code, detail))
        msg = body["choices"][0]["message"]
        content = msg.get("content")
        if not content:
            raise RuntimeError("empty content in response: %s" % json.dumps(body)[:500])
        return content

    def list_models(self, timeout=60):
        req = urllib.request.Request(
            OPENROUTER_BASE + "/models", headers=self._headers(), method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body.get("data", [])
