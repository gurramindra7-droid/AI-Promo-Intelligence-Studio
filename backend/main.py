"""AI Promo Intelligence Studio - REST API (FastAPI).

    uvicorn backend.main:app --port 8000        (docs at http://localhost:8000/docs)

The API is a thin layer over the same services the Streamlit app uses. It never returns API keys,
and every promo time it returns comes from the parsed script (database), never from a model."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from collections import Counter
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

import common.paths  # noqa: F401  (adds src/ to sys.path)
from automation.webhook import WebhookError, check as webhook_check
from backend.services import processing_service as PS
from copilot.assistant import chat as copilot_chat
from database import repositories as R
from database.database import init_db, session
from feedback import feedback_service as FS
from feedback import ranking_calibration as RC
from feedback.preference_learning import preferences

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()            # create tables on startup (idempotent)
    yield


app = FastAPI(title="AI Promo Intelligence Studio", version="1.0", lifespan=lifespan,
              description="Multi-agent promo discovery, story intelligence, editorial copilot and feedback.")


# ---------- request bodies ----------

class UploadFile_(BaseModel):
    filename: str
    content: str = Field(max_length=2_000_000)


class ProjectIn(BaseModel):
    name: str
    title: str = ""
    files: list[UploadFile_] = []


class ProcessIn(BaseModel):
    mode: Literal["import", "pipeline", "agents", "story"] = "import"
    episodes: list[int] | None = None
    use_llm: bool = True


class FeedbackIn(BaseModel):
    decision: Literal["approve", "reject", "needs_revision"]
    reason: str | None = None
    comment: str | None = Field(default=None, max_length=2000)


class ChatIn(BaseModel):
    project_id: int
    message: str = Field(min_length=1, max_length=1000)
    session_id: str | None = None
    use_llm: bool = True


def _project(con, pid: int) -> dict:
    p = R.get_project(con, pid)
    if not p:
        raise HTTPException(404, "project not found")
    return p


def _promo_out(p: dict) -> dict:
    d = {k: v for k, v in p.items() if not k.endswith("_json")}
    d["characters"] = json.loads(p.get("characters_json") or "[]")
    d["segments"] = json.loads(p.get("segments_json") or "[]")
    return d


# ---------- endpoints ----------

@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/projects")
def list_projects():
    with session() as con:
        return [{k: v for k, v in p.items() if k != "meta_json"} for p in R.list_projects(con)]


@app.post("/api/projects", status_code=201)
def create_project(body: ProjectIn):
    with session() as con:
        try:
            return PS.create_project(con, body.name, body.title, [f.model_dump() for f in body.files])
        except ValueError as e:
            raise HTTPException(400, str(e))


@app.post("/api/projects/{pid}/process", status_code=202)
def process(pid: int, body: ProcessIn):
    with session() as con:
        _project(con, pid)
        try:
            jid = PS.start(con, pid, body.mode, body.episodes, body.use_llm)
        except ValueError as e:
            raise HTTPException(400, str(e))
    return {"job_id": jid, "status": "queued", "status_url": f"/api/projects/{pid}/status?job_id={jid}"}


@app.get("/api/projects/{pid}/status")
def status(pid: int, job_id: str | None = None):
    with session() as con:
        _project(con, pid)
        if job_id:
            j = R.get_job(con, job_id)
            if not j or j["project_id"] != pid:
                raise HTTPException(404, "job not found")
            jobs = [j]
        else:
            jobs = R.list_jobs(con, pid, limit=10)
        out = []
        for j in jobs:
            r = json.loads(j.get("result_json") or "null")
            if isinstance(r, dict):
                r.pop("trace", None)
            out.append({**{k: v for k, v in j.items() if k != "result_json"}, "result": r})
        return {"project_id": pid, "jobs": out, "ranking_kinds": R.ranking_kinds(con, pid)}


@app.get("/api/projects/{pid}/promos")
def promos(pid: int, ranking: str = "original", episode: int | None = None, verdict: str | None = None,
           q: str | None = None, limit: int = Query(50, ge=1, le=200)):
    with session() as con:
        _project(con, pid)
        if ranking not in R.ranking_kinds(con, pid):
            raise HTTPException(404, f"no '{ranking}' ranking for this project (have: {R.ranking_kinds(con, pid)})")
        return {"ranking": ranking, "promos": [_promo_out(p) for p in
                                               R.get_promos(con, pid, ranking, episode, verdict, q, limit)]}


@app.get("/api/projects/{pid}/story")
def story(pid: int, character: str | None = None):
    with session() as con:
        _project(con, pid)
        chars = R.get_characters(con, pid)
        rels = R.get_relationships(con, pid, character.upper() if character else None)
        events = R.get_events(con, pid, character=character.upper() if character else None)
        return {"characters": [{**{k: v for k, v in c.items() if k != "id"},
                                "episodes": sorted(c["episodes"])} for c in chars],
                "relationships": rels, "events": events,
                "counts": {"characters": len(chars), "relationships": len(rels), "events": len(events),
                           "unverified_events": sum(1 for e in events if not e.get("verified"))}}


@app.post("/api/promos/{promo_id}/feedback", status_code=201)
def feedback(promo_id: int, body: FeedbackIn):
    with session() as con:
        if not R.get_promo(con, promo_id):
            raise HTTPException(404, "promo not found")
        try:
            fid = FS.submit(con, promo_id, body.decision, body.reason, body.comment)
        except FS.FeedbackError as e:
            raise HTTPException(400, str(e))
    return {"feedback_id": fid, "promo_id": promo_id, "decision": body.decision}


@app.get("/api/projects/{pid}/feedback")
def get_feedback(pid: int, ranking: str = "original"):
    with session() as con:
        _project(con, pid)
        return {"summary": FS.summary(con, pid), "latest": R.latest_feedback(con, pid),
                "calibration": RC.compute(con, pid, ranking), "preferences": preferences(con, pid, ranking)}


@app.post("/api/copilot/chat")
def chat(body: ChatIn):
    with session() as con:
        _project(con, body.project_id)
        r = copilot_chat(con, body.project_id, body.message, body.session_id, body.use_llm)
    return r


@app.get("/api/projects/{pid}/analytics")
def analytics(pid: int):
    with session() as con:
        p = _project(con, pid)
        eps = R.get_episodes(con, pid)
        kinds = R.ranking_kinds(con, pid)
        per = {}
        for k in kinds:
            ps = R.get_promos(con, pid, k, limit=500)
            per[k] = {"promos": len(ps),
                      "avg_score": round(sum(x["score"] or 0 for x in ps) / max(1, len(ps)), 2),
                      "avg_duration": round(sum(x["duration"] or 0 for x in ps) / max(1, len(ps)), 1),
                      "by_episode": dict(sorted(Counter(x["episode"] for x in ps).items())),
                      "by_moment_type": dict(Counter(x["archetype"] or "?" for x in ps).most_common()),
                      "by_verdict": dict(Counter(x.get("verdict") or "-" for x in ps))}
        return {"project": p["name"], "title": p["show_title"], "episodes": len(eps),
                "blocks": sum(e["n_blocks"] or 0 for e in eps), "rankings": per,
                "feedback": FS.summary(con, pid), "model_usage": R.usage_summary(con, pid),
                "jobs": [{k: j[k] for k in ("id", "kind", "status", "created_at")} for j in R.list_jobs(con, pid, 5)]}


@app.post("/api/webhooks/n8n", status_code=202)
def n8n(payload: dict, x_webhook_secret: str | None = Header(default=None)):
    try:
        req = webhook_check(x_webhook_secret, payload)
    except WebhookError as e:
        raise HTTPException(e.status, str(e))
    with session() as con:
        p = R.get_project(con, req["project"])
        if not p:
            raise HTTPException(404, "project not found")
        try:
            jid = PS.start(con, p["id"], req["mode"], req["episodes"], req["use_llm"])
        except ValueError as e:
            raise HTTPException(400, str(e))
    return {"job_id": jid, "project_id": p["id"], "status": "queued"}
