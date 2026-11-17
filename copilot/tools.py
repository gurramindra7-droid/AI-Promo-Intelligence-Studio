"""The ONLY things the copilot can do. Each tool is a fixed, parameterised query through the repository
layer - the AI chooses a tool name and simple arguments; it never writes SQL or code. Every promo in a
result carries its real episode and script times, so answers can cite them."""
from __future__ import annotations

import json

from database import repositories as R
from feedback.feedback_service import summary as feedback_summary
from story_intelligence.narrative_analyzer import promo_context


def fmt_t(s) -> str:
    s = int(round(s or 0))
    return f"{s // 60}:{s % 60:02d}"


def card(p: dict) -> dict:
    return {"promo_id": p["id"], "ranking": p["ranking_kind"], "rank": p["rank"], "episode": p["episode"],
            "cut": f"Ep{p['episode']} {fmt_t(p['ep_start'])}-{fmt_t(p['ep_end'])}", "duration_s": round(p["duration"] or 0),
            "hook": p["hook_text"], "cliffhanger": p["cliff_text"], "hook_score": p["hook_score"],
            "cliff_score": p["cliff_score"], "standalone_score": p["standalone_score"],
            "context_dependency": p.get("context_dependency"), "moment_type": p["archetype"],
            "verdict": p.get("verdict"), "score": p["score"], "why_rank": p["why_rank"],
            "why_it_works": p["why_it_works"], "why_it_might_fail": p.get("why_it_might_fail"),
            "characters": json.loads(p.get("characters_json") or "[]")}


def _kind(con, pid, kind):
    kinds = R.ranking_kinds(con, pid)
    return kind if kind in kinds else ("original" if "original" in kinds else (kinds[0] if kinds else "original"))


def get_top_ranked_promos(con, pid, limit: int = 5, ranking: str = "original"):
    k = _kind(con, pid, ranking)
    return {"ranking": k, "promos": [card(p) for p in R.get_promos(con, pid, k, limit=max(1, min(limit, 30)))]}


def search_promos(con, pid, query: str, ranking: str = "original", limit: int = 10):
    k = _kind(con, pid, ranking)
    words = [w for w in str(query).split() if len(w) > 2][:4] or [str(query)]
    seen, out = set(), []
    for w in words:
        for p in R.get_promos(con, pid, k, text=w, limit=50):
            if p["id"] not in seen:
                seen.add(p["id"]); out.append(p)
    for p in R.get_promos(con, pid, k, limit=100):           # also match by moment type (betrayal, threat...)
        if p["id"] not in seen and any(w.lower() in (p["archetype"] or "") for w in words):
            seen.add(p["id"]); out.append(p)
    out.sort(key=lambda p: p["rank"])
    return {"ranking": k, "query": query, "promos": [card(p) for p in out[:limit]]}


def get_episode_details(con, pid, episode: int):
    ep = next((e for e in R.get_episodes(con, pid) if e["number"] == int(episode)), None)
    if not ep:
        return {"error": f"Episode {episode} is not in this project."}
    promos = [card(p) for k in R.ranking_kinds(con, pid) for p in R.get_promos(con, pid, k, episode=int(episode))]
    chars = [c["name"] for c in R.get_characters(con, pid) if int(episode) in c["episodes"]]
    return {"episode": ep["number"], "logline": ep["logline"], "duration_s": ep["duration_s"],
            "characters": chars[:15], "events": R.get_events(con, pid, episode=int(episode))[:6], "promos": promos}


def get_character_episodes(con, pid, name: str):
    chars = R.get_characters(con, pid)
    key = str(name).upper().strip()
    c = next((c for c in chars if c["name"] == key or key in c["aliases"]), None) or \
        next((c for c in chars if key and key in c["name"]), None)
    if not c:
        return {"error": f"No character called '{name}' speaks in this script.",
                "known": [c["name"] for c in chars[:15]]}
    promos = [card(p) for k in R.ranking_kinds(con, pid) for p in R.get_promos(con, pid, k, limit=100)
              if c["name"] in (p.get("characters_json") or "") or any(a in (p.get("characters_json") or "") for a in c["aliases"])]
    return {"character": c["name"], "aliases": c["aliases"], "lines": c["n_lines"],
            "episodes": sorted(c["episodes"]), "events": R.get_events(con, pid, character=c["name"])[:8],
            "relationships": [r for r in R.get_relationships(con, pid, c["name"]) if r["relation"] != "appears_with"][:8],
            "promos": promos[:10]}


def compare_promos(con, pid, ranks: list[int] | None = None, ranking: str = "original", promo_ids: list[int] | None = None):
    k = _kind(con, pid, ranking)
    allp = R.get_promos(con, pid, k, limit=100)
    sel = [p for p in allp if (ranks and p["rank"] in [int(r) for r in ranks]) or
           (promo_ids and p["id"] in [int(i) for i in promo_ids])]
    if not sel:
        sel = allp[:5]
    return {"ranking": k, "promos": [{**card(p), "context": _ctx(con, pid, p)} for p in sel[:6]]}


def explain_promo(con, pid, rank: int | None = None, ranking: str = "original", episode: int | None = None):
    k = _kind(con, pid, ranking)
    allp = R.get_promos(con, pid, k, limit=100)
    p = next((p for p in allp if (rank and p["rank"] == int(rank)) or (episode and p["episode"] == int(episode))), None)
    if not p:
        return {"error": "No such promo in this ranking."}
    return {"ranking": k, "promo": card(p), "agent_reviews": R.get_agent_evals(con, p["id"]),
            "context": _ctx(con, pid, p), "lowest_ranked_score": allp[-1]["score"], "top_score": allp[0]["score"]}


def promos_by_context_dependency(con, pid, ranking: str = "original", limit: int = 10):
    k = _kind(con, pid, ranking)
    out = []
    for p in R.get_promos(con, pid, k, limit=100):
        ctx = _ctx(con, pid, p)
        if p.get("context_dependency") == "high" or (p["standalone_score"] is not None and p["standalone_score"] <= 1):
            out.append({**card(p), "depends_on_earlier_episodes": ctx["depends_on_earlier_episodes"]})
    return {"ranking": k, "promos": out[:limit], "total": len(out)}


def get_feedback_summary(con, pid):
    return feedback_summary(con, pid)


def _ctx(con, pid, p):
    c = promo_context(con, pid, p)
    return {"characters": [x["name"] for x in c["characters"]], "episode_logline": c["episode_logline"],
            "depends_on_earlier_episodes": c["depends_on_earlier_episodes"]}


# name -> (function, {arg: type}) - the copilot may only call these, with only these arguments
TOOLS = {
    "get_top_ranked_promos": (get_top_ranked_promos, {"limit": int, "ranking": str}),
    "search_promos": (search_promos, {"query": str, "ranking": str, "limit": int}),
    "get_episode_details": (get_episode_details, {"episode": int}),
    "get_character_episodes": (get_character_episodes, {"name": str}),
    "compare_promos": (compare_promos, {"ranks": list, "ranking": str, "promo_ids": list}),
    "explain_promo": (explain_promo, {"rank": int, "ranking": str, "episode": int}),
    "promos_by_context_dependency": (promos_by_context_dependency, {"ranking": str, "limit": int}),
    "get_feedback_summary": (get_feedback_summary, {}),
}

TOOL_DOCS = """get_top_ranked_promos(limit, ranking) - best promos in rank order
search_promos(query, ranking, limit) - promos whose lines/moment type match words (revenge, betrayal, poison...)
get_episode_details(episode) - logline, characters, events and promos of one episode
get_character_episodes(name) - a character's episodes, events, relationships and promos
compare_promos(ranks, ranking) - side-by-side details of promos by rank, e.g. ranks=[1,2]
explain_promo(rank, ranking, episode) - why one promo scored/ranked as it did (scores, agent reviews)
promos_by_context_dependency(ranking, limit) - promos that need earlier-episode context
get_feedback_summary() - editor approvals/rejections so far
ranking is "original" (pipeline) or "agents" (multi-agent), default "original"."""


def run_tool(con, pid, name: str, args: dict) -> dict:
    """Validate the tool name and arguments, then run it. Anything else is refused."""
    if name not in TOOLS:
        return {"error": f"unknown tool '{name}'"}
    fn, spec = TOOLS[name]
    clean = {}
    for k, v in (args or {}).items():
        if k not in spec or v in (None, ""):
            continue
        try:
            clean[k] = [int(x) for x in v][:10] if spec[k] is list else spec[k](v)
        except (TypeError, ValueError):
            continue
    try:
        return fn(con, pid, **clean)
    except TypeError as e:
        return {"error": f"bad arguments for {name}: {e}"}
