"""Agent 4 - Editorial Critic: a skeptical senior editor who challenges the other agents.
Reviews candidates in small batches so it can spot repetition between them."""
from __future__ import annotations

from agents.base import call

SYSTEM = """You are the EDITORIAL CRITIC agent: a skeptical senior promo editor for vertical microdramas.
Other agents proposed these promo clips and scored them. Challenge them. Look for weak hooks, artificially
constructed cliffhangers (the cut lands on a line that is not really unresolved), clips that repeat another
candidate's moment, missing story context, weak emotional engagement, and anything misleading about the show.
Approve only clips you would actually post. If a better moment is visible in the clip itself (a stronger
line to open or close on), name it in alternative_suggestion using its line_id - never invent times.

editorial_verdict: approve | review | reject. strengths / weaknesses: up to 3 short items each.
final_reasoning <= 35 words.
Reply with JSON only: {"reviews": [{"cand_key": "...", "editorial_verdict": "review", "strengths": [],
"weaknesses": [], "alternative_suggestion": "", "final_reasoning": "..."}]}"""


def build_prompt(batch: list[dict], others: list[str]) -> str:
    out = ["OTHER SHORTLISTED CLIPS (for spotting repetition):"] + [f"- {o}" for o in others[:20]]
    out.append("\nCLIPS TO REVIEW:")
    for c in batch:
        out.append(f"\ncand_key: {c['cand_key']}  (Ep{c['episode']}, {c['duration']:.0f}s)")
        out.append(f"scores: hook {c['hook_score']}/5 ({c.get('hook_type')}), cliffhanger {c['cliff_score']}/5 "
                   f"({c.get('cliff_type')}), standalone {c['standalone_score']}/5")
        out.append("script:\n" + c["text"])
    return "\n".join(out)


def validator(keys: set[str]):
    def check(d):
        if not isinstance(d, dict) or not isinstance(d.get("reviews"), list):
            return 'Top level must be {"reviews": [...]}.'
        got = {r.get("cand_key") for r in d["reviews"] if isinstance(r, dict)}
        if not keys <= got:
            return f"Review every clip; missing cand_key(s): {sorted(keys - got)[:5]}"
        for r in d["reviews"]:
            if r.get("editorial_verdict") not in ("approve", "review", "reject"):
                return "editorial_verdict must be approve, review or reject."
        return True
    return check


def normalise(r: dict) -> dict:
    return {"cand_key": r["cand_key"], "editorial_verdict": r["editorial_verdict"],
            "strengths": [str(x)[:120] for x in r.get("strengths", [])][:3],
            "weaknesses": [str(x)[:120] for x in r.get("weaknesses", [])][:3],
            "alternative_suggestion": str(r.get("alternative_suggestion", ""))[:200],
            "final_reasoning": str(r.get("final_reasoning", ""))[:300]}


def run(llm, batch: list[dict], others: list[str]) -> dict[str, dict]:
    keys = {c["cand_key"] for c in batch}
    d = call(llm, build_prompt(batch, others), SYSTEM, "agent_critic", validator(keys))
    return {r["cand_key"]: normalise(r) for r in d["reviews"] if r.get("cand_key") in keys}
