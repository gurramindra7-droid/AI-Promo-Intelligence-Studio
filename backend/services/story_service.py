"""Run the Story Intelligence Engine for a project and store the results."""
from __future__ import annotations

from typing import Callable

from agents.base import make_llm
from backend.services.import_service import load_timeline
from database import repositories as R
from story_intelligence import character_extractor as CE
from story_intelligence import event_extractor as EE


def run_story(con, project_id: int, show: str, use_llm: bool = True, llm=None, job_id: str | None = None,
              progress: Callable[[float, str], None] = lambda p, m: None, episodes: list[int] | None = None) -> dict:
    tl = load_timeline(show)
    lines = [l for l in tl["lines"] if episodes is None or l["ep"] in episodes]

    # 1. Characters + appearances (script facts)
    progress(0.1, "Characters from speaker labels")
    per_ep = CE.speakers_by_episode(lines)
    counts = {n: sum(c.values()) for n, c in per_ep.items()}
    for name, c in per_ep.items():
        cid = R.upsert_character(con, project_id, name, counts[name], min(c), max(c))
        R.set_character_episodes(con, cid, dict(c))
    aliases = CE.heuristic_aliases(list(per_ep), counts)
    for canon, al in aliases.items():
        R.set_character_aliases(con, project_id, canon, al)

    # 2. Co-appearance (script facts)
    progress(0.3, "Shared scenes")
    pairs = CE.co_occurrence(lines)
    for (a, b), p in pairs.items():
        R.upsert_relationship(con, project_id, a, b, "appears_with", f"shared {p['scenes']} scenes",
                              sorted(p["episodes"]), 1.0, "co-occurrence")

    result = {"characters": len(per_ep), "alias_groups": len(aliases), "appears_with_pairs": len(pairs),
              "events": 0, "llm_relationships": 0, "unverified_events": 0, "llm_used": False}

    # 3. Events + stated relationships from the writers' loglines (AI, grounded in code)
    if use_llm:
        llm = llm or make_llm("story")
        eps = [e for e in R.get_episodes(con, project_id) if episodes is None or e["number"] in episodes]
        known = [n for n, _ in sorted(counts.items(), key=lambda kv: -kv[1])][:40]
        progress(0.5, f"Events from {len(eps)} loglines")
        events, rels = EE.extract(llm, eps, EE.NameMatcher(list(per_ep), aliases), known)
        for e in events:
            R.upsert_event(con, project_id, e["episode"], e["description"], e["event_type"], e["importance"],
                           e["characters"], e["source"], e["confidence"], e["verified"])
        for r in rels:
            R.upsert_relationship(con, project_id, r["a"], r["b"], r["relation"], r["evidence"], [r["episode"]],
                                  r["confidence"], r["source"])
        R.log_usage(con, job_id, project_id, llm.calls)
        result.update(events=len(events), llm_relationships=len(rels),
                      unverified_events=sum(1 for e in events if not e["verified"]), llm_used=True,
                      calls=len(llm.calls))
    progress(1.0, "Done")
    return result
