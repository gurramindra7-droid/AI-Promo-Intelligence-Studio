"""Command line for the studio (same services as the UI and the API).

    python -m studio_cli import  the_last_reel
    python -m studio_cli story   the_last_reel [--no-llm] [--episodes 1-5]
    python -m studio_cli agents  the_last_reel --episodes 1-3
    python -m studio_cli status  the_last_reel
"""
from __future__ import annotations

import argparse
import json
import sys

import common.paths  # noqa: F401
from backend.services import processing_service as PS
from database import repositories as R
from database.database import init_db, session


def eps(t: str | None):
    if not t:
        return None
    out: list[int] = []
    for part in t.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="AI Promo Intelligence Studio CLI")
    ap.add_argument("command", choices=["import", "story", "agents", "pipeline", "status"])
    ap.add_argument("project")
    ap.add_argument("--episodes", help="e.g. 1-3 or 1,4,7")
    ap.add_argument("--no-llm", action="store_true", help="story: script facts only, no AI")
    a = ap.parse_args()
    init_db()
    with session() as con:
        if a.command != "status":
            if not R.get_project(con, a.project):
                PS.create_project(con, a.project)
        p = R.get_project(con, a.project)
        if not p:
            sys.exit(f"unknown project {a.project}")
        if a.command == "status":
            for j in R.list_jobs(con, p["id"], 10):
                print(j["id"], j["kind"], j["status"], j["progress"], j["message"])
            return
        con.commit()
        jid = PS.start(con, p["id"], a.command, eps(a.episodes), not a.no_llm, background=False)
        job = R.get_job(con, jid)
    res = json.loads(job["result_json"] or "{}")
    res.pop("trace", None) if isinstance(res, dict) else None
    print(job["status"], json.dumps(res, indent=1, ensure_ascii=False))
    if job["status"] != "completed":
        sys.exit(1)


if __name__ == "__main__":
    main()
