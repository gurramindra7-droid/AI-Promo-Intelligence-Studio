"""
llm.py - the ONLY place in the project that talks to an AI model.

Why one wrapper?
  * Model swap = change `llm.model` in config.yaml. No other code changes.
  * Every AI reply must be valid JSON. We check it here and ask again once if it is not.
  * Replies are cached on disk, so re-running is free and avoids free-tier rate limits.
  * Tokens, cost and time are logged for every call (used in the run log + doc).

Usage from other modules:
    from llm import LLM
    llm = LLM("config.yaml")
    data = llm.call_json(system="...", prompt="...", task="tagger",
                         validate=lambda d: "beats" in d)
    print(llm.usage_summary())

Quick test (needs a key in .env):
    python src/llm.py --test
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Which .env variable each provider needs (LiteLLM reads these automatically).
KEY_ENV = {
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


class LLMError(RuntimeError):
    """Raised when no model returns usable JSON."""


def load_config(path: str | Path = "config.yaml") -> dict:
    path = Path(path)
    if not path.is_absolute() and not path.exists():
        path = PROJECT_ROOT / path
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def extract_json(text: str) -> Any:
    """Parse JSON from a model reply. Models sometimes wrap it in ```json fences
    or add a sentence before it, so we strip that before parsing."""
    if text is None:
        raise ValueError("empty reply")
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fall back to the outermost {...} or [...] block.
        starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
        if not starts:
            raise
        start = min(starts)
        end = max(text.rfind("}"), text.rfind("]"))
        return json.loads(text[start : end + 1])


class LLM:
    def __init__(self, config_path: str | Path = "config.yaml", model_override: str | None = None,
                 use_cache: bool | None = None):
        load_dotenv(PROJECT_ROOT / ".env")
        cfg = load_config(config_path)["llm"]
        # --model on the command line beats config.yaml (handy for a live model swap)
        self.model: str = model_override or cfg["model"]
        self.fallback_model: str | None = cfg.get("fallback_model")
        self.temperature: float = cfg.get("temperature", 0.2)
        self.max_tokens: int = cfg.get("max_tokens", 8192)
        self.timeout: int = cfg.get("timeout_seconds", 120)
        self.reasoning_effort: str | None = cfg.get("reasoning_effort")   # e.g. "low" for gpt-oss
        self.json_retries: int = cfg.get("json_retries", 1)
        self.use_cache: bool = cfg.get("use_cache", True) if use_cache is None else use_cache
        self.cache_dir = PROJECT_ROOT / cfg.get("cache_dir", "cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.calls: list[dict] = []  # one entry per call, for the run log

    # ---------- caching ----------
    def _cache_key(self, model: str, system: str, prompt: str) -> str:
        raw = json.dumps([model, self.temperature, system, prompt], ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    def _cache_get(self, key: str) -> Any | None:
        p = self.cache_dir / f"{key}.json"
        if self.use_cache and p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        return None

    def _cache_put(self, key: str, data: Any) -> None:
        p = self.cache_dir / f"{key}.json"
        p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---------- one raw model call ----------
    def _complete(self, model: str, messages: list[dict]) -> tuple[str, dict]:
        import litellm  # imported here so other modules load fast

        litellm.suppress_debug_info = True
        # Some models reject settings others accept (e.g. Gemini 3.x rejects
        # `temperature`). drop_params removes unsupported ones instead of failing,
        # so swapping models in config.yaml never breaks the pipeline.
        litellm.drop_params = True
        kwargs = dict(
            model=model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout=self.timeout,
        )
        if self.reasoning_effort:   # less hidden "thinking" = fewer tokens (dropped where unsupported)
            kwargs["reasoning_effort"] = self.reasoning_effort
        try:
            resp = litellm.completion(response_format={"type": "json_object"}, **kwargs)
        except Exception as e:  # some models don't support JSON mode -> plain call
            if "response_format" in str(e) or "json" in str(e).lower():
                resp = litellm.completion(**kwargs)
            else:
                raise
        text = resp.choices[0].message.content
        usage = getattr(resp, "usage", None)
        try:
            cost = litellm.completion_cost(completion_response=resp)
        except Exception:
            cost = 0.0
        info = {
            "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
            "cost_usd": cost or 0.0,
        }
        return text, info

    def _complete_with_wait(self, model: str, messages: list[dict]) -> tuple[str, dict]:
        """Free tiers often say 'busy' (503) or 'too many requests' (429) for a few
        seconds. Wait and retry the SAME model first, so one show is scored by one
        model (consistent scores). Only if it keeps failing do we fall back."""
        waits = [5, 15, 30, 60, 60, 90]   # free-tier per-minute limits reset within ~60s
        for i in range(len(waits) + 1):
            try:
                return self._complete(model, messages)
            except Exception as e:
                msg = str(e).lower()
                if "request too large" in msg:
                    raise   # waiting won't help: this single request is over the per-minute limit
                if "exceeded your current quota" in msg or "perday" in msg or "tokens per day" in msg \
                        or "requests per day" in msg:
                    raise   # a DAILY quota is used up (e.g. Gemini free = 20/day): no point waiting minutes
                busy = any(k in msg for k in ("503", "429", "unavailable", "high demand",
                                              "rate limit", "resource_exhausted", "timeout"))
                if not busy or i == len(waits):
                    raise
                # Groq says exactly how long to wait ("Please try again in 12.3s") - use it.
                asked = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", msg)
                wait = (int(asked.group(1) or 0) * 60 + float(asked.group(2)) + 1) if asked else waits[i]
                wait = min(max(wait, waits[i] if not asked else 1), 120)
                print(f"  [llm] {model} busy, waiting {wait:.0f}s and retrying...")
                time.sleep(wait)

    # ---------- public: ask for JSON ----------
    def call_json(
        self,
        prompt: str,
        system: str = "You are a precise assistant. Reply with valid JSON only.",
        task: str = "general",
        validate: Callable[[Any], bool | str] | None = None,
    ) -> Any:
        """Send a prompt, return parsed JSON.

        validate(data) may return True (ok), False, or an error string describing
        what is wrong; on failure we retry with that feedback (json_retries times),
        then try the fallback model, then raise LLMError.
        """
        models = [self.model] + ([self.fallback_model] if self.fallback_model else [])
        last_error = ""
        for model in models:
            env_var = KEY_ENV.get(model.split("/")[0])
            if env_var and not os.getenv(env_var):
                last_error = f"{model}: {env_var} is empty in .env"
                print(f"  [llm] skipping {model}: {env_var} not set in .env")
                continue
            key = self._cache_key(model, system, prompt)
            cached = self._cache_get(key)
            if cached is not None:
                self.calls.append({"task": task, "model": model, "cached": True,
                                   "prompt_tokens": 0, "completion_tokens": 0,
                                   "cost_usd": 0.0, "seconds": 0.0})
                return cached

            messages = [{"role": "system", "content": system},
                        {"role": "user", "content": prompt}]
            for attempt in range(self.json_retries + 1):
                t0 = time.time()
                try:
                    text, info = self._complete_with_wait(model, messages)
                except Exception as e:
                    last_error = f"{model}: API error: {e}"
                    print(f"  [llm] {last_error[:300]}")
                    break  # API failure -> go to fallback model
                info.update(task=task, model=model, cached=False,
                            seconds=round(time.time() - t0, 2), attempt=attempt)
                self.calls.append(info)

                try:
                    data = extract_json(text)
                    verdict = validate(data) if validate else True
                    if verdict is True:
                        self._cache_put(key, data)
                        return data
                    problem = verdict if isinstance(verdict, str) else "JSON did not match the required format."
                except (ValueError, json.JSONDecodeError) as e:
                    problem = f"Reply was not valid JSON ({e})."

                last_error = f"{model}: {problem}"
                print(f"  [llm] attempt {attempt + 1} rejected: {problem[:200]}")
                messages = messages + [
                    {"role": "assistant", "content": text or ""},
                    {"role": "user", "content": f"{problem} Reply again with ONLY the corrected JSON."},
                ]
        raise LLMError(f"No valid JSON for task '{task}'. Last error: {last_error}")

    # ---------- run log ----------
    def usage_summary(self) -> dict:
        live = [c for c in self.calls if not c["cached"]]
        return {
            "model": self.model,
            "fallback_model": self.fallback_model,
            # which model actually answered, and how often (shows silent fallbacks)
            "answered_by": {m: sum(1 for c in self.calls if c["model"] == m)
                            for m in dict.fromkeys(c["model"] for c in self.calls)},
            "calls_total": len(self.calls),
            "calls_cached": len(self.calls) - len(live),
            "calls_by_task": {t: sum(1 for c in self.calls if c["task"] == t)
                              for t in dict.fromkeys(c["task"] for c in self.calls)},
            "prompt_tokens": sum(c["prompt_tokens"] for c in live),
            "completion_tokens": sum(c["completion_tokens"] for c in live),
            "cost_usd": round(sum(c["cost_usd"] for c in live), 5),
            "seconds": round(sum(c["seconds"] for c in live), 1),
        }


def _test(config_path: str) -> None:
    llm = LLM(config_path)
    print(f"Model: {llm.model}  (fallback: {llm.fallback_model})")
    try:
        data = llm.call_json(
            prompt='Return JSON {"ok": true, "hook_word": "<one dramatic word>"}',
            task="smoke_test",
            validate=lambda d: isinstance(d, dict) and d.get("ok") is True or "need ok=true",
        )
    except LLMError as e:
        print(f"FAILED: {e}")
        print("Fix: paste your key into .env (see .env.example), then run this test again.")
        raise SystemExit(1)
    print("Reply:", data)
    print("Usage:", llm.usage_summary())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="send one tiny prompt to check the key works")
    ap.add_argument("--config", default="config.yaml")
    args = ap.parse_args()
    if args.test:
        _test(args.config)
    else:
        ap.print_help()
