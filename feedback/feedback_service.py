"""Approve / reject / needs-revision decisions on promos. Every decision is stored with a snapshot of
the promo's scores and rank at that moment (audit trail); later decisions on the same promo are kept
as history and the latest one counts."""
from __future__ import annotations

from collections import Counter

from database import repositories as R
from database.models import DECISIONS, REJECTION_REASONS


class FeedbackError(ValueError):
    pass


def submit(con, promo_id: int, decision: str, reason: str | None = None, comment: str | None = None) -> int:
    decision = (decision or "").lower().replace(" ", "_")
    if decision not in DECISIONS:
        raise FeedbackError(f"decision must be one of {DECISIONS}")
    if decision == "reject" and reason not in REJECTION_REASONS:
        raise FeedbackError(f"a rejection needs a reason, one of {REJECTION_REASONS}")
    if reason and reason not in REJECTION_REASONS:
        raise FeedbackError(f"unknown reason '{reason}'")
    p = R.get_promo(con, promo_id)
    if not p:
        raise FeedbackError(f"promo {promo_id} not found")
    snap = {k: p[k] for k in ("ranking_kind", "rank", "episode", "ep_start", "ep_end", "hook_score", "cliff_score",
                              "standalone_score", "context_dependency", "verdict", "score")}
    return R.add_feedback(con, promo_id, decision, reason, (comment or "").strip()[:1000] or None, snap)


def summary(con, project_id: int, kind: str | None = None) -> dict:
    latest = R.latest_feedback(con, project_id, kind)
    total = len(R.get_promos(con, project_id, kind)) if kind else sum(
        len(R.get_promos(con, project_id, k)) for k in R.ranking_kinds(con, project_id))
    by = Counter(f["decision"] for f in latest)
    reviewed = len(latest)
    return {"total_promos": total, "reviewed": reviewed, "approved": by.get("approve", 0),
            "rejected": by.get("reject", 0), "needs_revision": by.get("needs_revision", 0),
            "pending": max(0, total - reviewed),
            "approval_rate": round(by.get("approve", 0) / reviewed, 2) if reviewed else None,
            "rejection_reasons": Counter(f["reason"] for f in latest if f["decision"] == "reject").most_common()}
