"""Processing jobs (run in a background thread, status stored in processing_jobs).

Modes
  import    load the original pipeline's saved outputs into the database (no AI)
  pipeline  run the ORIGINAL pipeline (src/run.py run_one) on an uploaded project, then import
  agents    multi-agent re-ranking (ranking_kind='agents'); original ranking untouched
  story     characters/relationships (code) + events from loglines (AI, optional)

The Kuku show's original outputs are protected: the API will not re-run the pipeline over them."""
from __future__ import annotations

import json
import re
import threading
import traceback
from pathlib import Path

from automation.n8n_integration import notify
from backend.services.import_service import available_shows, import_show
from common.paths import CONFIG, DATA, OUTPUTS
from common.settings import get_settings, redact
from database import repositories as R
from database.database import session

UPLOADS = DATA / "uploads"
DEMO_MSG = ("Live analysis is turned off on this public demo (the owner has not enabled an AI key), "
            "so it can't spend anyone's AI quota.")
MAX_UPLOAD_BYTES = 400_000          # public demo: total script size per custom project
MAX_UPLOAD_FILES = 30


def from_upload(source_path: str) -> bool:
    return bool(source_path) and Path(source_path).resolve().is_relative_to(UPLOADS.resolve())


def is_protected(name: str, source_path: str = "") -> bool:
    """Saved pipeline outputs that did not come from an upload (e.g. the submitted results) are never
    re-processed or overwritten by the API/UI - only uploaded projects can run the pipeline."""
    return name in available_shows() and not from_upload(source_path)
MODES = ("import", "pipeline", "agents", "story")
NAME_RE = re.compile(r"^[a-z0-9_]{2,60}$")
FILE_RE = re.compile(r"^[\w\- .]{1,120}\.(txt|srt|vtt|md)$")


def safe_name(name: str) -> str:
    n = re.sub(r"[^a-z0-9_]+", "_", str(name).lower()).strip("_")[:60]
    if not NAME_RE.match(n):
        raise ValueError("project name must have 2-60 letters/digits")
    return n


def create_project(con, name: str, title: str = "", files: list[dict] | None = None) -> dict:
    """files = [{"filename": "ep01.txt", "content": "..."}] -> saved under data/uploads/<name>/ (git-ignored).
    With no files, the name must match existing pipeline outputs (e.g. the_last_reel)."""
    s = get_settings()
    if s.demo and not (files and s.ai_allowed):           # public demo: only new custom-input projects
        raise ValueError(DEMO_MSG)
    if s.demo and files:
        size = sum(len(str(f.get("content", "")).encode("utf-8")) for f in files)
        if len(files) > MAX_UPLOAD_FILES or size > MAX_UPLOAD_BYTES:
            raise ValueError(f"The public demo accepts up to {MAX_UPLOAD_FILES} files and "
                             f"{MAX_UPLOAD_BYTES // 1000} KB of script per project.")
    n = safe_name(name)
    src = ""
    if files:
        if is_protected(n):
            raise ValueError(f"'{n}' is protected; choose another name for uploads")
        d = UPLOADS / n
        for f in files:
            if not FILE_RE.match(Path(str(f.get("filename", ""))).name):
                raise ValueError(f"bad file name '{f.get('filename')}' (allowed: .txt .srt .vtt .md)")
        d.mkdir(parents=True, exist_ok=True)
        for f in files:
            (d / Path(str(f["filename"])).name).write_text(str(f.get("content", "")), encoding="utf-8")
        src = str(d)
    elif n not in available_shows():
        raise ValueError(f"No uploaded files and no pipeline outputs for '{n}'")
    prev = R.get_project(con, n)
    pid = R.upsert_project(con, n, title or (prev or {}).get("show_title") or n, src or (prev or {}).get("source_path") or "",
                           json.loads((prev or {}).get("meta_json") or "{}"))
    return {"project_id": pid, "name": n, "files": len(files or []), "source_path": src}


def _run_pipeline(name: str, src: str, progress) -> dict:
    if is_protected(name, src):
        raise ValueError(f"'{name}' is protected: its original outputs are kept as they are")
    from llm import load_config          # src/ is on sys.path (common.paths)
    from parser import discover_shows
    from run import run_one
    if not src:
        raise ValueError("this project has no uploaded script files")
    shows = discover_shows(src)
    if not shows:
        raise ValueError(f"No script files in {src}")
    cfg = load_config(str(CONFIG))
    files = [f for _, fs in shows for f in fs]
    progress(0.1, f"Original pipeline on {len(files)} file(s)")
    log = run_one(name, files, cfg, str(CONFIG), None)
    if log.get("error"):
        raise RuntimeError(log["error"])
    return {"calls": log["usage"]["calls_total"], "cached": log["usage"]["calls_cached"],
            "seconds": log["seconds_total"], "promos": log["candidates"]}


def execute(job_id: str, project_id: int, mode: str, episodes: list[int] | None, use_llm: bool) -> dict:
    with session() as con:
        p = R.get_project(con, project_id)
        R.update_job(con, job_id, status="running", progress=0.02, message=f"{mode} started")
    notify("job.started", {"job_id": job_id, "project": p["name"], "kind": mode, "status": "running"})

    work: dict = {}          # the open work connection, if any (SQLite allows one writer at a time)

    def progress(f: float, msg: str):
        """Progress is written on the SAME connection as the work and committed, so other readers see it
        and we never block on our own open transaction."""
        c = work.get("con")
        if c is not None:
            R.update_job(c, job_id, progress=round(f, 3), message=str(msg)[:300])
            c.commit()
        else:
            with session() as c2:
                R.update_job(c2, job_id, progress=round(f, 3), message=str(msg)[:300])

    try:
        out: dict = {}
        if mode == "pipeline":
            out["pipeline"] = _run_pipeline(p["name"], p["source_path"], progress)
        with session() as con:
            work["con"] = con
            if mode in ("import", "pipeline"):
                out["import"] = import_show(con, p["name"])
                if mode == "pipeline":                   # characters + shared scenes from the script (code, no AI)
                    from backend.services.story_service import run_story
                    progress(0.95, "Building the character map")
                    out["story"] = run_story(con, project_id, p["name"], use_llm=False)
            elif mode == "agents":
                from agents.agent_orchestrator import run_agents
                out["agents"] = run_agents(con, project_id, p["name"], episodes=episodes, job_id=job_id,
                                           progress=progress)
            elif mode == "story":
                from backend.services.story_service import run_story
                out["story"] = run_story(con, project_id, p["name"], use_llm=use_llm, job_id=job_id,
                                         progress=progress, episodes=episodes)
            R.update_job(con, job_id, status="completed", progress=1.0, message="done", result=out)
        work.pop("con", None)
        summary = {k: {kk: vv for kk, vv in v.items() if isinstance(vv, (int, float))}
                   for k, v in out.items() if isinstance(v, dict)}
        notify("job.completed", {"job_id": job_id, "project": p["name"], "kind": mode, "status": "completed",
                                 "summary": summary})
        return out
    except Exception as e:
        work.pop("con", None)
        msg = redact(f"{type(e).__name__}: {e}")
        with session() as con:
            R.update_job(con, job_id, status="failed", message=msg[:500],
                         result={"error": msg, "trace": redact(traceback.format_exc())[-1500:]})
        notify("job.failed", {"job_id": job_id, "project": p["name"], "kind": mode, "status": "failed",
                              "message": msg})
        return {"error": msg}


def start(con, project_id: int, mode: str, episodes: list[int] | None = None, use_llm: bool = True,
          background: bool = True) -> str:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    p = R.get_project(con, project_id)
    if not p:
        raise LookupError("project not found")
    s = get_settings()
    if s.demo:
        if not s.ai_allowed:
            raise ValueError(DEMO_MSG)
        if not from_upload(p["source_path"] or ""):
            raise ValueError("On the public demo only your own uploaded (custom input) projects can be processed.")
        if any(j["status"] in ("queued", "running") for j in R.list_jobs(con, None, 20)):
            raise ValueError("Another analysis is running on this demo. Please try again in a minute.")
    if mode == "pipeline" and is_protected(p["name"], p["source_path"] or ""):
        raise ValueError(f"'{p['name']}' is protected: use mode 'import' to load its original outputs")
    if mode in ("agents", "story") and not (OUTPUTS / f"timeline_{p['name']}.json").exists():
        raise ValueError("run mode 'pipeline' (or 'import') first")
    jid = R.create_job(con, project_id, mode)
    con.commit()
    if background:
        threading.Thread(target=execute, args=(jid, project_id, mode, episodes, use_llm), daemon=True).start()
    else:
        execute(jid, project_id, mode, episodes, use_llm)
    return jid
