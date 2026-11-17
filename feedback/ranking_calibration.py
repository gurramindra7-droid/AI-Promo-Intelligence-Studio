"""Feedback-driven ranking calibration - deliberately simple, transparent and conservative.

This is NOT machine learning and does not retrain any model. It turns repeated, explicit editor
rejection reasons into small, visible score penalties:

    reason "Too much context required"  -> promos with standalone <= 1 or high context dependency
    reason "Weak opening"               -> promos with hook score < 3
    reason "Weak ending"                -> promos with cliffhanger score < 3

A rule switches on only with enough evidence (>= MIN_DECISIONS reviews in the ranking AND
>= MIN_REJECTIONS rejections citing that reason on promos that have the feature). Each active rule
costs 10% of the score, at most 25% in total. The original ranking is never changed: calibrated ranks
are computed alongside it, every adjustment is explained, and snapshots are saved for audit.
"""
from __future__ import annotations

from functools import cmp_to_key

from database import repositories as R

MIN_DECISIONS = 5
MIN_REJECTIONS = 3
PENALTY = 0.10
MAX_PENALTY = 0.25

RULES = {
    "Too much context required": ("needs_context", "standalone <= 1 or high context dependency",
                                  lambda p: (p.get("standalone_score") is not None and p["standalone_score"] <= 1)
                                  or p.get("context_dependency") == "high"),
    "Weak opening": ("weak_hook", "hook score < 3", lambda p: (p.get("hook_score") or 0) < 3),
    "Weak ending": ("weak_cliff", "cliffhanger score < 3", lambda p: (p.get("cliff_score") or 0) < 3),
}


def compute(con, project_id: int, kind: str = "original") -> dict:
    promos = R.get_promos(con, project_id, kind)
    latest = {f["promo_id"]: f for f in R.latest_feedback(con, project_id, kind)}
    by_id = {p["id"]: p for p in promos}
    rules = []
    for reason, (name, desc, has) in RULES.items():
        hits = [f for f in latest.values() if f["decision"] == "reject" and f["reason"] == reason
                and f["promo_id"] in by_id and has(by_id[f["promo_id"]])]
        active = len(latest) >= MIN_DECISIONS and len(hits) >= MIN_REJECTIONS
        rules.append({"rule": name, "reason": reason, "feature": desc, "evidence": len(hits),
                      "decisions": len(latest), "active": active, "penalty": PENALTY if active else 0.0})
    rows = []
    for p in promos:
        applied = [r for r in rules if r["active"] and RULES[r["reason"]][2](p)]
        pen = min(MAX_PENALTY, sum(r["penalty"] for r in applied))
        rows.append({"promo_id": p["id"], "rank": p["rank"], "episode": p["episode"], "score": p["score"],
                     "calibrated_score": round((p["score"] or 0) * (1 - pen), 2), "penalty": pen,
                     "applied": [r["rule"] for r in applied],
                     "decision": latest.get(p["id"], {}).get("decision")})
    # Two promos swap only if their penalties DIFFER and the penalised one now scores lower.
    # Equal penalties keep the original order (which includes the original variety rule).
    def order(a, b):
        if a["penalty"] != b["penalty"] and a["calibrated_score"] != b["calibrated_score"]:
            return -1 if a["calibrated_score"] > b["calibrated_score"] else 1
        return a["rank"] - b["rank"]
    for i, r in enumerate(sorted(rows, key=cmp_to_key(order)), 1):
        r["calibrated_rank"] = i
        r["moved"] = r["rank"] - i
    return {"ranking": kind, "decisions": len(latest), "min_decisions": MIN_DECISIONS,
            "min_rejections": MIN_REJECTIONS, "rules": rules, "rows": sorted(rows, key=lambda r: r["rank"]),
            "note": ("Not enough feedback yet - ranking unchanged." if not any(r["active"] for r in rules)
                     else "Active rules shown above; the original ranking is kept unchanged.")}


def save_snapshot(con, project_id: int, kind: str = "original") -> dict:
    res = compute(con, project_id, kind)
    R.add_calibration(con, project_id, kind, res["decisions"], {"rules": res["rules"],
                      "moves": [{k: r[k] for k in ("promo_id", "rank", "calibrated_rank", "applied")} for r in res["rows"]]})
    return res
