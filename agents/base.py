"""Shared agent machinery.

Every agent: its own system prompt, its own JSON output schema, its own validator. Calls go
through the ORIGINAL src/llm.py wrapper, so they inherit: JSON validation with one corrective
retry, waiting on rate limits, backup model, disk cache, and a log of which model really answered.
Agents only ever return line ids / candidate keys - never timestamps.
"""
from __future__ import annotations

import common.paths  # noqa: F401  (makes src/ importable)
from llm import LLM, LLMError  # noqa: E402  (original wrapper, unchanged)

from common.paths import CONFIG
from common.settings import get_settings


class AgentConfigError(RuntimeError):
    """Raised when an agent cannot run (e.g. no API key). Never replaced by made-up results."""


def make_llm(role: str) -> LLM:
    """An LLM for one agent role; model from config.yaml `studio:` or STUDIO_<ROLE>_MODEL."""
    return LLM(CONFIG, model_override=get_settings().model_for(role))


def clamp(v, lo: float, hi: float) -> float:
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return lo


def call(llm, prompt: str, system: str, task: str, validate) -> dict:
    """One validated JSON call. Turns 'no usable answer' into an explicit error, never a guess."""
    try:
        return llm.call_json(prompt, system=system, task=task, validate=validate)
    except LLMError as e:
        msg = str(e)
        if "is empty in .env" in msg or "not set" in msg:
            raise AgentConfigError(f"{task}: no API key for {llm.model} - add it to .env (see .env.example).") from e
        raise


def fmt_line(l: dict) -> str:
    who = ""
    if l.get("speaker"):
        who = f"{l['speaker']} ({l['delivery']}): " if l.get("delivery") else f"{l['speaker']}: "
    tag = {"action": "ACTION: ", "sfx": "SOUND: ", "scene": "SCENE: ", "camera": "SHOT: "}.get(l["type"], "")
    return f"{tag}{who}{l['text']}"
