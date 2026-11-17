"""Simple, honest view of what editors seem to prefer - descriptive statistics over their decisions,
shown in the Feedback Center. No model is trained; with a handful of reviews these are hints, not facts."""
from __future__ import annotations

from collections import defaultdict
from statistics import mean

from database import repositories as R


def preferences(con, project_id: int, kind: str | None = None) -> dict:
    latest = R.latest_feedback(con, project_id, kind)
    promos = {p["id"]: p for k in R.ranking_kinds(con, project_id) for p in R.get_promos(con, project_id, k)}
    groups: dict[str, list[dict]] = defaultdict(list)
    for f in latest:
        if f["promo_id"] in promos:
            groups[f["decision"]].append(promos[f["promo_id"]])

    def avg(ps, key):
        vals = [p[key] for p in ps if p.get(key) is not None]
        return round(mean(vals), 2) if vals else None

    by_type: dict[str, dict] = defaultdict(lambda: {"approve": 0, "reject": 0, "needs_revision": 0})
    for f in latest:
        p = promos.get(f["promo_id"])
        if p:
            by_type[p.get("archetype") or "other"][f["decision"]] += 1
    return {"n": len(latest),
            "averages": {d: {k: avg(ps, k) for k in ("hook_score", "cliff_score", "standalone_score", "duration")}
                         for d, ps in groups.items()},
            "by_moment_type": dict(by_type),
            "caveat": "Descriptive only. Fewer than ~20 reviews is too few to draw conclusions."}
