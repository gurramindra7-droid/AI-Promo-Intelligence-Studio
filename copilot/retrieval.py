"""Rule-based intent routing: question -> (tool, args). Used as the OFFLINE mode (no API key) and as a
fallback when the AI's tool choice is invalid. Simple on purpose: easy to read and to test."""
from __future__ import annotations

import re

from database import repositories as R

THEMES = ["revenge", "betrayal", "poison", "slap", "threat", "kidnap", "fire", "fight", "wedding", "marry",
          "love", "secret", "reveal", "death", "kill", "rescue", "humiliation", "duke", "duchess"]


def route(con, pid: int, q: str, last: dict | None = None) -> tuple[str, dict]:
    t = q.lower()
    ranking = "agents" if re.search(r"\bagent", t) and "agents" in R.ranking_kinds(con, pid) else "original"
    nums = [int(n) for n in re.findall(r"#?\b(\d{1,2})\b", t)]
    if "feedback" in t or "approv" in t or "reject" in t:
        return "get_feedback_summary", {}
    if "depend" in t or "previous episode" in t or "context" in t:
        return "promos_by_context_dependency", {"ranking": ranking}
    if ("why" in t or "explain" in t) and ("rank" in t or "score" in t or "#" in t or "promo" in t):
        if re.search(r"episode\s*\d+", t) and len(nums) >= 2 and "above" in t:
            eps = [int(x) for x in re.findall(r"episode\s*(\d+)", t)]
            ranks = [p["rank"] for p in R.get_promos(con, pid, ranking, limit=100) if p["episode"] in eps]
            return "compare_promos", {"ranks": ranks[:4], "ranking": ranking}
        m = re.search(r"episode\s*(\d+)", t)
        if m:
            return "explain_promo", {"episode": int(m.group(1)), "ranking": ranking}
        return "explain_promo", {"rank": nums[0] if nums else 1, "ranking": ranking}
    if "compare" in t:
        return "compare_promos", {"ranks": nums or [1, 2, 3, 4, 5], "ranking": ranking}
    if "alternative" in t and last and last.get("promos"):
        return "search_promos", {"query": (last["promos"][0].get("moment_type") or ""), "ranking": ranking}
    m = re.search(r"episode\s*(\d+)", t)
    if m and "cliffhanger" not in t:
        return "get_episode_details", {"episode": int(m.group(1))}
    names = [c["name"] for c in R.get_characters(con, pid)[:40]]
    for n in names:
        if re.search(rf"\b{re.escape(n.lower())}\b", t):
            return "get_character_episodes", {"name": n}
    for th in THEMES:
        if th in t:
            return "search_promos", {"query": th, "ranking": ranking}
    if "cliffhanger" in t:
        return "get_top_ranked_promos", {"limit": 5, "ranking": ranking}
    return "get_top_ranked_promos", {"limit": 5, "ranking": ranking}
