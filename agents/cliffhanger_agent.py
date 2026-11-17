"""Agent 2 - Cliffhanger Detection: is this line a good place to CUT, leaving viewers needing more?"""
from __future__ import annotations

from agents.base import call, clamp, fmt_line

CLIFF_TYPES = ["unanswered_question", "reveal", "threat", "suspense", "unresolved_conflict",
               "surprise_appearance", "emotional_uncertainty", "other"]

SYSTEM = f"""You are the CLIFFHANGER DETECTION agent in a promo-editing team for vertical microdramas.
Judge each listed line ONLY as a possible promo ENDING: if the clip cuts right after it, does the viewer
urgently need to know what happens next? Look for unanswered questions, unexpected revelations, suspense,
threats, unresolved conflicts, surprising character appearances and emotional uncertainty.
A line that resolves the tension (an apology accepted, a question answered) is a weak cut.
The 2 lines after each candidate are context only - they show whether the moment resolves immediately.

Rules: use only the listed line_ids; never output times; cliffhanger_score is an integer 0-5;
use the full 0-5 range across the batch; cliffhanger_type is one of {CLIFF_TYPES};
reason <= 15 words; confidence 0.0-1.0.
Reply with JSON only: {{"results": [{{"line_id": "L001", "cliffhanger_score": 0, "cliffhanger_type": "other", "reason": "...", "confidence": 0.0}}]}}"""


def build_prompt(batch: list[dict], after: dict[str, list[dict]]) -> str:
    out = ["CANDIDATE ENDING LINES:"]
    for l in batch:
        ctx = " | ".join(fmt_line(c)[:90] for c in after.get(l["id"], []))
        out.append(f"{l['id']} [Ep{l['ep']}] {fmt_line(l)}" + (f"   (after: {ctx})" if ctx else ""))
    return "\n".join(out)


def validator(ids: set[str]):
    def check(d):
        if not isinstance(d, dict) or not isinstance(d.get("results"), list):
            return 'Top level must be {"results": [...]}.'
        bad = [r.get("line_id") for r in d["results"] if not isinstance(r, dict) or r.get("line_id") not in ids]
        if bad:
            return f"Unknown line_ids {bad[:5]}; use only the listed ids."
        for r in d["results"]:
            if not isinstance(r.get("cliffhanger_score"), (int, float)) or not 0 <= r["cliffhanger_score"] <= 5:
                return f"{r['line_id']}: cliffhanger_score must be 0-5."
        if len({r["line_id"] for r in d["results"]}) < 0.9 * len(ids):
            return "Score every listed line."
        return True
    return check


def normalise(r: dict) -> dict:
    return {"line_id": r["line_id"], "cliffhanger_score": int(round(clamp(r["cliffhanger_score"], 0, 5))),
            "cliffhanger_type": r.get("cliffhanger_type") if r.get("cliffhanger_type") in CLIFF_TYPES else "other",
            "reason": str(r.get("reason", ""))[:160], "confidence": round(clamp(r.get("confidence", 0.5), 0, 1), 2)}


def run(llm, batch: list[dict], after: dict[str, list[dict]]) -> list[dict]:
    ids = {l["id"] for l in batch}
    d = call(llm, build_prompt(batch, after), SYSTEM, "agent_cliffhanger", validator(ids))
    return [normalise(r) for r in d["results"]]
