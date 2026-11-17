"""Agent 3 - Stranger Understanding: does the clip make sense to someone who never saw the show?
Blind by design: it sees only the clip's own lines - no show name, no story, no other clips."""
from __future__ import annotations

from agents.base import call, clamp, fmt_line

SYSTEM = """You are the STRANGER UNDERSTANDING agent. You are an ordinary viewer scrolling short videos who has
NEVER seen this show. You get the script of one 20-60 second promo clip ("[CUT]" = a jump; ACTION/SHOT = what
you would see). Judge honestly, without inventing backstory:
- Who is involved? What is happening? Is the central conflict understandable?
- Does it depend on previous episodes? Is essential context missing? Is the ending interesting?
Note: a clip may deliberately open a mystery - an unexplained question that makes you curious is fine;
only count context as missing when you cannot follow WHAT is happening.

standalone_score: integer 0-5 (5 = fully understandable alone). context_dependency: low | medium | high.
missing_context: up to 4 short items. explanation <= 30 words.
Reply with JSON only: {"standalone_score": 0, "context_dependency": "low", "missing_context": [], "explanation": "..."}"""


def clip_text(lines: list[dict], segments: list[dict]) -> str:
    starts = {s["first_id"] for s in segments[1:]}
    out = []
    for l in lines:
        if l["id"] in starts:
            out.append("[CUT]")
        if l["type"] != "scene":
            out.append(fmt_line(l))
    return "\n".join(out)


def validate(d):
    if not isinstance(d, dict):
        return "Reply must be a JSON object."
    if not isinstance(d.get("standalone_score"), (int, float)) or not 0 <= d["standalone_score"] <= 5:
        return "standalone_score must be 0-5."
    if d.get("context_dependency") not in ("low", "medium", "high"):
        return "context_dependency must be low, medium or high."
    if not isinstance(d.get("missing_context", []), list):
        return "missing_context must be a list."
    return True


def run(llm, lines: list[dict], segments: list[dict]) -> dict:
    d = call(llm, "PROMO CLIP SCRIPT:\n" + clip_text(lines, segments), SYSTEM, "agent_stranger", validate)
    return {"standalone_score": int(round(clamp(d["standalone_score"], 0, 5))),
            "context_dependency": d["context_dependency"],
            "missing_context": [str(x)[:100] for x in d.get("missing_context", [])][:4],
            "explanation": str(d.get("explanation", ""))[:300]}
