"""All reads/writes go through these functions - no other module writes SQL. This is also what
keeps the copilot safe: it can only call these fixed, parameterised queries, never its own SQL."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from typing import Any

J = json.dumps


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


# ---------- projects / episodes ----------

def upsert_project(con, name: str, show_title: str = "", source_path: str = "", meta: dict | None = None) -> int:
    con.execute("""INSERT INTO projects (name, show_title, source_path, meta_json) VALUES (?,?,?,?)
                   ON CONFLICT(name) DO UPDATE SET show_title=excluded.show_title,
                   source_path=excluded.source_path, meta_json=excluded.meta_json""",
                (name, show_title, source_path, J(meta or {})))
    return con.execute("SELECT id FROM projects WHERE name=?", (name,)).fetchone()["id"]


def get_project(con, key: int | str) -> dict | None:
    q = "SELECT * FROM projects WHERE id=?" if str(key).isdigit() else "SELECT * FROM projects WHERE name=?"
    r = con.execute(q, (int(key) if str(key).isdigit() else key,)).fetchone()
    return dict(r) if r else None


def list_projects(con) -> list[dict]:
    return rows(con.execute("SELECT * FROM projects ORDER BY id"))


def upsert_episode(con, project_id: int, number: int, **f) -> None:
    con.execute("""INSERT INTO episodes (project_id, number, logline, duration_s, n_blocks, n_dialogue, n_action)
                   VALUES (?,?,?,?,?,?,?) ON CONFLICT(project_id, number) DO UPDATE SET
                   logline=excluded.logline, duration_s=excluded.duration_s, n_blocks=excluded.n_blocks,
                   n_dialogue=excluded.n_dialogue, n_action=excluded.n_action""",
                (project_id, number, f.get("logline"), f.get("duration_s"), f.get("n_blocks"),
                 f.get("n_dialogue"), f.get("n_action")))


def get_episodes(con, project_id: int) -> list[dict]:
    return rows(con.execute("SELECT * FROM episodes WHERE project_id=? ORDER BY number", (project_id,)))


# ---------- promos ----------

PROMO_FIELDS = ("rank", "episode", "start_s", "end_s", "ep_start", "ep_end", "duration", "hook_id", "hook_text",
                "hook_score", "hook_type", "cliff_id", "cliff_text", "cliff_score", "cliff_type", "standalone_score",
                "context_dependency", "archetype", "score", "verdict", "why_it_works", "why_it_might_fail",
                "why_rank", "characters_json", "segments_json", "lines_json")


def upsert_promo(con, project_id: int, kind: str, cand_key: str, data: dict) -> int:
    cols = [c for c in PROMO_FIELDS if c in data]
    con.execute(f"""INSERT INTO promos (project_id, ranking_kind, cand_key, {", ".join(cols)})
                    VALUES (?,?,?,{",".join("?" * len(cols))})
                    ON CONFLICT(project_id, ranking_kind, cand_key) DO UPDATE SET
                    {", ".join(f"{c}=excluded.{c}" for c in cols)}""",
                (project_id, kind, cand_key, *[data[c] for c in cols]))
    return con.execute("SELECT id FROM promos WHERE project_id=? AND ranking_kind=? AND cand_key=?",
                       (project_id, kind, cand_key)).fetchone()["id"]


def delete_promos_not_in(con, project_id: int, kind: str, keep_keys: list[str]) -> None:
    """After a re-run, remove promos of that ranking that no longer exist (keeps feedback of kept ones)."""
    q = ",".join("?" * len(keep_keys)) or "''"
    con.execute(f"DELETE FROM promos WHERE project_id=? AND ranking_kind=? AND cand_key NOT IN ({q})",
                (project_id, kind, *keep_keys))


def get_promos(con, project_id: int, kind: str = "original", episode: int | None = None,
               verdict: str | None = None, text: str | None = None, limit: int = 200) -> list[dict]:
    q, a = "SELECT * FROM promos WHERE project_id=? AND ranking_kind=?", [project_id, kind]
    if episode is not None:
        q += " AND episode=?"; a.append(episode)
    if verdict:
        q += " AND verdict=?"; a.append(verdict)
    if text:
        q += " AND (hook_text LIKE ? OR cliff_text LIKE ? OR why_it_works LIKE ? OR characters_json LIKE ? OR lines_json LIKE ?)"
        a += [f"%{text}%"] * 5
    q += " ORDER BY rank LIMIT ?"; a.append(limit)
    return rows(con.execute(q, a))


def get_promo(con, promo_id: int) -> dict | None:
    r = con.execute("SELECT * FROM promos WHERE id=?", (promo_id,)).fetchone()
    return dict(r) if r else None


def ranking_kinds(con, project_id: int) -> list[str]:
    return [r["ranking_kind"] for r in con.execute(
        "SELECT DISTINCT ranking_kind FROM promos WHERE project_id=? ORDER BY ranking_kind", (project_id,))]


# ---------- agent outputs ----------

def upsert_line_score(con, project_id: int, line_id: str, agent: str, score: float, kind: str, reason: str,
                      confidence: float, model: str) -> None:
    con.execute("""INSERT INTO agent_line_scores (project_id, line_id, agent, score, kind, reason, confidence, model)
                   VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(project_id, line_id, agent) DO UPDATE SET
                   score=excluded.score, kind=excluded.kind, reason=excluded.reason,
                   confidence=excluded.confidence, model=excluded.model""",
                (project_id, line_id, agent, score, kind, reason, confidence, model))


def get_line_scores(con, project_id: int, agent: str) -> dict[str, dict]:
    return {r["line_id"]: dict(r) for r in con.execute(
        "SELECT * FROM agent_line_scores WHERE project_id=? AND agent=?", (project_id, agent))}


def upsert_agent_eval(con, promo_id: int, agent: str, output: dict, model: str) -> None:
    con.execute("""INSERT INTO agent_evaluations (promo_id, agent, output_json, model) VALUES (?,?,?,?)
                   ON CONFLICT(promo_id, agent) DO UPDATE SET output_json=excluded.output_json,
                   model=excluded.model, created_at=CURRENT_TIMESTAMP""", (promo_id, agent, J(output), model))


def get_agent_evals(con, promo_id: int) -> dict[str, dict]:
    return {r["agent"]: {**json.loads(r["output_json"]), "_model": r["model"]} for r in con.execute(
        "SELECT * FROM agent_evaluations WHERE promo_id=?", (promo_id,))}


# ---------- story ----------

def upsert_character(con, project_id: int, name: str, n_lines: int, first_ep: int, last_ep: int,
                     aliases: list[str] | None = None, role: str = "unknown") -> int:
    con.execute("""INSERT INTO characters (project_id, name, aliases_json, role, n_lines, first_ep, last_ep)
                   VALUES (?,?,?,?,?,?,?) ON CONFLICT(project_id, name) DO UPDATE SET
                   n_lines=excluded.n_lines, first_ep=excluded.first_ep, last_ep=excluded.last_ep""",
                (project_id, name, J(aliases or []), role, n_lines, first_ep, last_ep))
    return con.execute("SELECT id FROM characters WHERE project_id=? AND name=?", (project_id, name)).fetchone()["id"]


def set_character_aliases(con, project_id: int, name: str, aliases: list[str], role: str | None = None) -> None:
    con.execute("UPDATE characters SET aliases_json=?, role=COALESCE(?, role) WHERE project_id=? AND name=?",
                (J(sorted(set(aliases))), role, project_id, name))


def set_character_episodes(con, character_id: int, counts: dict[int, int]) -> None:
    con.execute("DELETE FROM character_episodes WHERE character_id=?", (character_id,))
    con.executemany("INSERT INTO character_episodes VALUES (?,?,?)",
                    [(character_id, ep, n) for ep, n in sorted(counts.items())])


def get_characters(con, project_id: int) -> list[dict]:
    out = rows(con.execute("SELECT * FROM characters WHERE project_id=? ORDER BY n_lines DESC", (project_id,)))
    for c in out:
        c["aliases"] = json.loads(c["aliases_json"] or "[]")
        c["episodes"] = {r["episode"]: r["n_lines"] for r in con.execute(
            "SELECT episode, n_lines FROM character_episodes WHERE character_id=? ORDER BY episode", (c["id"],))}
    return out


def upsert_event(con, project_id: int, episode: int, description: str, event_type: str, importance: int,
                 characters: list[str], source: str, confidence: float, verified: bool) -> None:
    con.execute("""INSERT INTO story_events (project_id, episode, description, event_type, importance,
                   characters_json, source, confidence, verified) VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(project_id, episode, description) DO UPDATE SET event_type=excluded.event_type,
                   importance=excluded.importance, characters_json=excluded.characters_json,
                   source=excluded.source, confidence=excluded.confidence, verified=excluded.verified""",
                (project_id, episode, description, event_type, importance, J(characters), source, confidence,
                 int(verified)))


def get_events(con, project_id: int, character: str | None = None, episode: int | None = None) -> list[dict]:
    q, a = "SELECT * FROM story_events WHERE project_id=?", [project_id]
    if episode is not None:
        q += " AND episode=?"; a.append(episode)
    if character:
        q += " AND characters_json LIKE ?"; a.append(f"%{character}%")
    out = rows(con.execute(q + " ORDER BY episode, importance DESC", a))
    for e in out:
        e["characters"] = json.loads(e["characters_json"] or "[]")
    return out


def upsert_relationship(con, project_id: int, a: str, b: str, relation: str, evidence: str,
                        episodes: list[int], confidence: float, source: str) -> None:
    a, b = sorted([a, b]) if relation == "appears_with" else (a, b)
    con.execute("""INSERT INTO character_relationships (project_id, a, b, relation, evidence, episodes_json,
                   confidence, source) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(project_id, a, b, relation)
                   DO UPDATE SET evidence=excluded.evidence, episodes_json=excluded.episodes_json,
                   confidence=excluded.confidence, source=excluded.source""",
                (project_id, a, b, relation, evidence, J(sorted(set(episodes))), confidence, source))


def get_relationships(con, project_id: int, character: str | None = None) -> list[dict]:
    q, a = "SELECT * FROM character_relationships WHERE project_id=?", [project_id]
    if character:
        q += " AND (a=? OR b=?)"; a += [character, character]
    out = rows(con.execute(q + " ORDER BY confidence DESC", a))
    for r in out:
        r["episodes"] = json.loads(r["episodes_json"] or "[]")
    return out


# ---------- feedback ----------

def add_feedback(con, promo_id: int, decision: str, reason: str | None, comment: str | None, snapshot: dict) -> int:
    cur = con.execute("INSERT INTO editorial_feedback (promo_id, decision, reason, comment, snapshot_json, created_at)"
                      " VALUES (?,?,?,?,?,?)", (promo_id, decision, reason, comment, J(snapshot), _now()))
    return cur.lastrowid


def latest_feedback(con, project_id: int, kind: str | None = None) -> list[dict]:
    """The most recent decision per promo (an editor can change their mind; history is kept)."""
    q = """SELECT f.*, p.ranking_kind, p.rank, p.episode, p.ep_start, p.ep_end, p.cand_key
           FROM editorial_feedback f JOIN promos p ON p.id=f.promo_id
           WHERE p.project_id=? AND f.id IN (SELECT MAX(id) FROM editorial_feedback GROUP BY promo_id)"""
    a: list[Any] = [project_id]
    if kind:
        q += " AND p.ranking_kind=?"; a.append(kind)
    return rows(con.execute(q + " ORDER BY f.id DESC", a))


def feedback_history(con, project_id: int) -> list[dict]:
    return rows(con.execute("""SELECT f.*, p.ranking_kind, p.rank, p.episode FROM editorial_feedback f
                               JOIN promos p ON p.id=f.promo_id WHERE p.project_id=? ORDER BY f.id DESC""",
                            (project_id,)))


def add_calibration(con, project_id: int, kind: str, n: int, rules: dict) -> None:
    con.execute("INSERT INTO ranking_calibrations (project_id, ranking_kind, n_feedback, rules_json, created_at)"
                " VALUES (?,?,?,?,?)", (project_id, kind, n, J(rules), _now()))


def calibrations(con, project_id: int) -> list[dict]:
    return rows(con.execute("SELECT * FROM ranking_calibrations WHERE project_id=? ORDER BY id DESC", (project_id,)))


# ---------- jobs / usage / chat ----------

def create_job(con, project_id: int | None, kind: str) -> str:
    jid = uuid.uuid4().hex[:12]
    con.execute("INSERT INTO processing_jobs (id, project_id, kind, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                (jid, project_id, kind, "queued", _now(), _now()))
    return jid


def update_job(con, jid: str, status: str | None = None, progress: float | None = None,
               message: str | None = None, result: dict | None = None) -> None:
    con.execute("""UPDATE processing_jobs SET status=COALESCE(?, status), progress=COALESCE(?, progress),
                   message=COALESCE(?, message), result_json=COALESCE(?, result_json), updated_at=? WHERE id=?""",
                (status, progress, message, J(result) if result is not None else None, _now(), jid))


def get_job(con, jid: str) -> dict | None:
    r = con.execute("SELECT * FROM processing_jobs WHERE id=?", (jid,)).fetchone()
    return dict(r) if r else None


def list_jobs(con, project_id: int | None = None, limit: int = 20) -> list[dict]:
    if project_id is None:
        return rows(con.execute("SELECT * FROM processing_jobs ORDER BY created_at DESC LIMIT ?", (limit,)))
    return rows(con.execute("SELECT * FROM processing_jobs WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
                            (project_id, limit)))


def log_usage(con, job_id: str | None, project_id: int | None, calls: list[dict]) -> None:
    con.executemany("""INSERT INTO model_usage_logs (job_id, project_id, task, model, cached, prompt_tokens,
                       completion_tokens, seconds, created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                    [(job_id, project_id, c.get("task"), c.get("model"), int(bool(c.get("cached"))),
                      c.get("prompt_tokens", 0), c.get("completion_tokens", 0), c.get("seconds", 0), _now())
                     for c in calls])


def usage_summary(con, project_id: int | None = None) -> list[dict]:
    q = """SELECT task, model, COUNT(*) calls, SUM(cached) cached, SUM(prompt_tokens) prompt_tokens,
           SUM(completion_tokens) completion_tokens, ROUND(SUM(seconds),1) seconds FROM model_usage_logs"""
    a: list[Any] = []
    if project_id is not None:
        q += " WHERE project_id=?"; a.append(project_id)
    return rows(con.execute(q + " GROUP BY task, model ORDER BY task", a))


def add_message(con, project_id: int | None, session_id: str, role: str, content: str, tools: Any = None) -> None:
    con.execute("INSERT INTO copilot_conversations (project_id, session_id, role, content, tool_calls_json, created_at)"
                " VALUES (?,?,?,?,?,?)", (project_id, session_id, role, content, J(tools) if tools else None, _now()))


def get_messages(con, session_id: str, limit: int = 20) -> list[dict]:
    out = rows(con.execute("SELECT * FROM copilot_conversations WHERE session_id=? ORDER BY id DESC LIMIT ?",
                           (session_id, limit)))
    return list(reversed(out))


def list_chat_sessions(con, project_id: int, limit: int = 20) -> list[dict]:
    """One row per copilot conversation: id, first question, number of messages, last activity."""
    return rows(con.execute("""SELECT session_id, MIN(created_at) started, MAX(created_at) last, COUNT(*) n,
                               (SELECT content FROM copilot_conversations c2 WHERE c2.session_id=c.session_id
                                AND c2.role='user' ORDER BY id LIMIT 1) title
                               FROM copilot_conversations c WHERE project_id=? GROUP BY session_id
                               ORDER BY last DESC LIMIT ?""", (project_id, limit)))
