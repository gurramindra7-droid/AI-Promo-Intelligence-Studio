"""Agent 1 - Hook Detection: is this line a promo OPENING that stops a scrolling stranger?"""
from __future__ import annotations

from agents.base import call, clamp, fmt_line

HOOK_TYPES = ["shocking_action", "shocking_line", "reveal", "confrontation", "emotional_conflict",
              "danger", "curiosity", "visual_spectacle", "other"]

SYSTEM = f"""You are the HOOK DETECTION agent in a promo-editing team for vertical microdramas.
Judge each listed line ONLY as a possible promo OPENING: would it stop a scrolling stranger within 3 seconds?
Look for unexpected actions, shocking dialogue, emotional conflict, physical confrontation, surprising
revelations, curiosity-generating situations and strong visual descriptions (ACTION / SHOT lines).
The 2 lines before each candidate are context only.

Rules: use only the listed line_ids; never output times; hook_score is an integer 0-5 (5 = instant scroll-stopper);
use the full 0-5 range across the batch; hook_type is one of {HOOK_TYPES};
reason <= 15 words; confidence 0.0-1.0 = how sure you are of the score.
Reply with JSON only: {{"results": [{{"line_id": "L001", "hook_score": 0, "hook_type": "other", "reason": "...", "confidence": 0.0}}]}}"""


def build_prompt(batch: list[dict], context: dict[str, list[dict]]) -> str:
    out = ["CANDIDATE OPENING LINES:"]
    for l in batch:
        ctx = " | ".join(fmt_line(c)[:90] for c in context.get(l["id"], []))
        out.append(f"{l['id']} [Ep{l['ep']}] {fmt_line(l)}" + (f"   (before: {ctx})" if ctx else ""))
    return "\n".join(out)


def validator(ids: set[str]):
    def check(d):
        if not isinstance(d, dict) or not isinstance(d.get("results"), list):
            return 'Top level must be {"results": [...]}.'
        bad = [r.get("line_id") for r in d["results"] if not isinstance(r, dict) or r.get("line_id") not in ids]
        if bad:
            return f"Unknown line_ids {bad[:5]}; use only the listed ids."
        for r in d["results"]:
            if not isinstance(r.get("hook_score"), (int, float)) or not 0 <= r["hook_score"] <= 5:
                return f"{r['line_id']}: hook_score must be 0-5."
        if len({r["line_id"] for r in d["results"]}) < 0.9 * len(ids):
            return "Score every listed line."
        return True
    return check


def normalise(r: dict) -> dict:
    return {"line_id": r["line_id"], "hook_score": int(round(clamp(r["hook_score"], 0, 5))),
            "hook_type": r.get("hook_type") if r.get("hook_type") in HOOK_TYPES else "other",
            "reason": str(r.get("reason", ""))[:160], "confidence": round(clamp(r.get("confidence", 0.5), 0, 1), 2)}


def run(llm, batch: list[dict], context: dict[str, list[dict]]) -> list[dict]:
    ids = {l["id"] for l in batch}
    d = call(llm, build_prompt(batch, context), SYSTEM, "agent_hook", validator(ids))
    return [normalise(r) for r in d["results"]]
