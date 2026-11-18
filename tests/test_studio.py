"""Studio features: import, story graph, copilot retrieval and tool safety, feedback persistence,
calibration, n8n webhook security, API endpoints and a frontend smoke test. Offline (MOCK LLM)."""
import json

import pytest
from fastapi.testclient import TestClient

from database import repositories as R
from tests.fakes import FakeLLM


# ---------- import ----------

def test_import_is_idempotent(imported):
    from backend.services.import_service import import_show
    con, pid = imported["con"], imported["pid"]
    n1 = len(R.get_promos(con, pid))
    import_show(con, imported["name"])
    assert len(R.get_promos(con, pid)) == n1 == len(imported["ranked"])
    top = R.get_promos(con, pid)[0]
    assert top["rank"] == 1 and top["episode"] in imported["timeline"]["meta"]["episodes"]


# ---------- story ----------

def test_story_graph_code_only(imported):
    from backend.services.story_service import run_story
    from story_intelligence.relationship_graph import build_graph, character_view
    con, pid = imported["con"], imported["pid"]
    res = run_story(con, pid, imported["name"], use_llm=False)
    assert res["characters"] > 0 and not res["llm_used"]
    g = build_graph(con, pid, min_lines=1)
    kinds = {d["kind"] for _, d in g.nodes(data=True)}
    assert {"character", "episode"} <= kinds
    name = R.get_characters(con, pid)[0]["name"]
    v = character_view(g, name)
    assert v["episodes"]


def test_story_llm_facts_are_grounded(imported):
    """The MOCK LLM names a character that does not exist ('NOBODY REAL'); it must be dropped and the
    events stored as unverified/verified by code, never trusted blindly."""
    from backend.services.story_service import run_story
    con, pid = imported["con"], imported["pid"]
    run_story(con, pid, imported["name"], use_llm=True, llm=FakeLLM())
    real = {c["name"] for c in R.get_characters(con, pid)}
    for e in R.get_events(con, pid):
        assert "NOBODY REAL" not in e["characters"]
        assert set(e["characters"]) <= real
    for r in R.get_relationships(con, pid):
        assert r["a"] in real and r["b"] in real


# ---------- copilot ----------

def test_copilot_tools_are_whitelisted(imported):
    from copilot.tools import run_tool
    con, pid = imported["con"], imported["pid"]
    assert "error" in run_tool(con, pid, "DROP TABLE promos", {})
    assert "error" in run_tool(con, pid, "__import__('os')", {})
    r = run_tool(con, pid, "get_top_ranked_promos", {"limit": "2", "evil": "x; DROP TABLE promos"})
    assert len(r["promos"]) <= 2
    assert R.get_promos(con, pid), "table still there"


def test_copilot_retrieval_offline(imported):
    from copilot.assistant import chat
    con, pid = imported["con"], imported["pid"]
    r = chat(con, pid, "Find the strongest promotional moments", use_llm=False)
    assert r["tool"] == "get_top_ranked_promos" and r["mode"] == "offline"
    first = r["data"]["promos"][0]
    assert first["cut"].startswith(f"Ep{first['episode']} ")
    r2 = chat(con, pid, "How is the feedback going?", session_id=r["session_id"], use_llm=False)
    assert r2["tool"] == "get_feedback_summary"
    assert len(R.get_messages(con, r["session_id"])) == 4


def test_copilot_llm_mode_drops_invented_ids(imported):
    from copilot.assistant import chat

    class Inventing(FakeLLM):
        def _reply(self, prompt, task):
            if task == "copilot_answer":
                return {"answer": "see #1", "promo_ids": [999999]}
            return super()._reply(prompt, task)
    con, pid = imported["con"], imported["pid"]
    r = chat(con, pid, "best promos?", use_llm=True, llm=Inventing())
    assert r["mode"] == "llm" and 999999 not in r["promo_ids"]


# ---------- feedback + calibration ----------

def test_feedback_persistence_and_rules(imported):
    from feedback import feedback_service as FS
    con, pid = imported["con"], imported["pid"]
    p = R.get_promos(con, pid)[0]
    with pytest.raises(FS.FeedbackError):
        FS.submit(con, p["id"], "reject")                     # reason required
    with pytest.raises(FS.FeedbackError):
        FS.submit(con, p["id"], "maybe")
    FS.submit(con, p["id"], "needs revision", comment="tighten the end")
    FS.submit(con, p["id"], "approve")
    latest = R.latest_feedback(con, pid)
    assert len(latest) == 1 and latest[0]["decision"] == "approve"
    hist = R.feedback_history(con, pid)
    assert len(hist) == 2 and json.loads(hist[0]["snapshot_json"])["rank"] == p["rank"]
    s = FS.summary(con, pid)
    assert s["approved"] == 1 and s["reviewed"] == 1


def test_calibration_is_conservative(imported):
    from feedback import feedback_service as FS
    from feedback import ranking_calibration as RC
    con, pid = imported["con"], imported["pid"]
    before = [p["rank"] for p in R.get_promos(con, pid)]
    res = RC.compute(con, pid)
    assert not any(r["active"] for r in res["rules"])
    assert all(r["moved"] == 0 for r in res["rows"])
    for p in R.get_promos(con, pid):
        FS.submit(con, p["id"], "reject", "Weak opening")
    res = RC.compute(con, pid)
    assert len(res["rows"]) == len(before)
    assert [p["rank"] for p in R.get_promos(con, pid)] == before, "original ranks never change"
    for r in res["rows"]:
        assert 0 <= r["penalty"] <= RC.MAX_PENALTY


# ---------- n8n ----------

def test_webhook_security(monkeypatch):
    from automation.webhook import WebhookError, check
    monkeypatch.setenv("N8N_ENABLED", "false")
    with pytest.raises(WebhookError) as e:
        check("s", {"project": "x"})
    assert e.value.status == 403
    monkeypatch.setenv("N8N_ENABLED", "true")
    monkeypatch.setenv("N8N_WEBHOOK_SECRET", "right-secret")
    with pytest.raises(WebhookError) as e:
        check("wrong", {"project": "x"})
    assert e.value.status == 401
    with pytest.raises(WebhookError):
        check("right-secret", {"project": "x", "mode": "rm -rf"})
    assert check("right-secret", {"project": "x", "mode": "agents", "episodes": [1, 2]})["mode"] == "agents"


def test_outbound_payload_has_no_script_text():
    from automation.n8n_integration import build_body, notify
    body = json.loads(build_body("job.completed", {"job_id": "j", "status": "completed",
                                                   "lines_json": "SECRET SCRIPT", "api_key": "gsk_x"}))
    assert "lines_json" not in body and "api_key" not in body
    assert notify("job.completed", {})["sent"] is False      # disabled by default


def test_redact_keys():
    from common.settings import redact
    assert "abcdefgh1234" not in redact("key gsk_abcdefgh1234567 failed")


# ---------- API ----------

def test_api_endpoints(imported, monkeypatch):
    from backend.main import app
    pid = imported["pid"]
    with TestClient(app) as c:
        assert c.get("/api/health").json()["ok"]
        assert any(p["id"] == pid for p in c.get("/api/projects").json())
        r = c.get(f"/api/projects/{pid}/promos", params={"limit": 2})
        assert r.status_code == 200 and len(r.json()["promos"]) <= 2
        assert c.get(f"/api/projects/{pid}/promos", params={"ranking": "nope"}).status_code == 404
        assert c.get("/api/projects/99999/promos").status_code == 404
        promo = r.json()["promos"][0]
        assert "lines_json" not in promo and promo["segments"]
        assert c.post(f"/api/promos/{promo['id']}/feedback", json={"decision": "reject"}).status_code == 400
        assert c.post(f"/api/promos/{promo['id']}/feedback", json={"decision": "approve"}).status_code == 201
        assert c.get(f"/api/projects/{pid}/feedback").json()["summary"]["approved"] == 1
        a = c.get(f"/api/projects/{pid}/analytics").json()
        assert a["rankings"]["original"]["promos"] == imported["promos"]
        ch = c.post("/api/copilot/chat", json={"project_id": pid, "message": "top promos", "use_llm": False}).json()
        assert ch["promos" if "promos" in ch else "data"]
        job = c.post(f"/api/projects/{pid}/process", json={"mode": "import"}).json()
        import time
        for _ in range(50):
            st = c.get(f"/api/projects/{pid}/status", params={"job_id": job["job_id"]}).json()["jobs"][0]
            if st["status"] in ("completed", "failed"):
                break
            time.sleep(0.1)
        assert st["status"] == "completed", st
        assert c.get(f"/api/projects/{pid}/story").status_code == 200
        assert c.post("/api/webhooks/n8n", json={"project": "x"}).status_code in (403, 503, 401)
        assert c.post("/api/projects", json={"name": "!"}).status_code == 400
        bad = {"name": "upload_test", "files": [{"filename": "../../evil.py", "content": "x"}]}
        assert c.post("/api/projects", json=bad).status_code == 400
        txt = json.dumps(c.get(f"/api/projects/{pid}/analytics").json())
        assert "gsk_" not in txt and "AIza" not in txt


def test_saved_outputs_are_protected(imported):
    """Imported pipeline outputs (not uploads) can never be re-processed or overwritten by an upload."""
    from backend.services import processing_service as PS
    con, pid, name = imported["con"], imported["pid"], imported["name"]
    assert PS.is_protected(name)
    with pytest.raises(ValueError):
        PS.start(con, pid, "pipeline", background=False)
    with pytest.raises(ValueError):
        PS.create_project(con, name, files=[{"filename": "a.txt", "content": "x"}])


def test_demo_mode_is_safe(monkeypatch, tmp_path):
    """Public demo: bundled fictional database, no processing, no live AI even if a key is configured."""
    from common import settings as S
    from backend.services import processing_service as PS
    from database.database import session
    monkeypatch.delenv("STUDIO_DB", raising=False)
    monkeypatch.setenv("STUDIO_DEMO", "1")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_not_real_000000")
    monkeypatch.setattr(S.tempfile, "gettempdir", lambda: str(tmp_path))
    s = S.get_settings()
    assert s.demo and not s.ai_allowed and not s.processing_allowed
    assert s.db_path.startswith(str(tmp_path)) and S.DEMO_DB.exists()
    with session() as con:
        p = R.list_projects(con)[0]
        assert R.get_promos(con, p["id"]), "demo database ships real promos"
        with pytest.raises(ValueError, match="public demo"):
            PS.start(con, p["id"], "agents", background=False)
    monkeypatch.setenv("STUDIO_DEMO_ALLOW_AI", "true")
    assert S.get_settings().ai_allowed
    with session() as con:                     # AI enabled: only NEW custom-input projects may be processed
        with pytest.raises(ValueError, match="uploaded"):
            PS.start(con, p["id"], "agents", background=False)
        with pytest.raises(ValueError, match="KB"):
            PS.create_project(con, "too_big", files=[{"filename": "a.txt", "content": "x" * (PS.MAX_UPLOAD_BYTES + 1)}])


# ---------- frontend ----------

@pytest.mark.parametrize("page", ["overview", "dashboard", "promo_discovery", "story_intelligence", "editorial_copilot",
                                  "feedback_center", "settings_page"])
def test_frontend_pages_render(imported, page):
    from streamlit.testing.v1 import AppTest
    from tests.conftest import ROOT
    src = f"""
import sys; sys.path.insert(0, r'{ROOT}')
from frontend import ui
from frontend.views import {page}
ui.setup()
{page}.render()
"""
    at = AppTest.from_string(src, default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.title


def test_frontend_empty_state(db):
    from streamlit.testing.v1 import AppTest
    from tests.conftest import ROOT
    src = f"""
import sys; sys.path.insert(0, r'{ROOT}')
from frontend import ui
from frontend.views import dashboard
ui.setup()
dashboard.render()
"""
    at = AppTest.from_string(src, default_timeout=60).run()
    assert not at.exception
    html = " ".join(str(e.proto) for e in at.get("html"))
    assert "No project yet" in html, "the empty state must explain what to do"


def test_intro_script_survives_sanitiser():
    """st.html sanitises with DOMPurify: the intro is injected as an EMPTY module script with a src, the 3D
    scene lives in a local static file, and it must offer Skip, remember completion, respect reduced motion
    and fall back when WebGL is missing."""
    import re
    from unittest import mock
    import streamlit as st
    from frontend import intro
    from tests.conftest import ROOT
    cap = {}
    with mock.patch.object(st, "html", lambda b, **k: cap.update(b=b, k=k)), mock.patch.object(st, "container"):
        intro.render(force=True)
    assert re.fullmatch(r'<script type="module" src="app/static/js/intro3d\.js\?force=1&n=[0-9a-f]{12}"></script>', cap["b"])
    assert cap["k"].get("unsafe_allow_javascript") is True
    js = (ROOT / "frontend" / "static" / "js" / "intro3d.js").read_text(encoding="utf-8")
    for must in ("Enter Studio", "Skip intro", "prefers-reduced-motion", "WebGLRenderer", "INTELLIGENCE STUDIO",
                 "../vendor/three/three.module.js"):
        assert must in js, must
    assert "http://" not in js and "https://" not in js, "no CDN: everything is served locally"
    assert (ROOT / "frontend" / "static" / "vendor" / "three" / "three.core.js").exists()


def test_frontend_is_monochrome():
    """The design system allows black, white and gray only: every hex colour must have R == G == B."""
    import re
    from tests.conftest import ROOT
    files = [ROOT / ".streamlit" / "config.toml", *(ROOT / "frontend").rglob("*.py"),
             *(ROOT / "frontend" / "static" / "js").glob("*.js"), *(ROOT / "frontend" / "assets").glob("*.svg"),
             ROOT / "story_intelligence" / "relationship_graph.py"]
    bad = []
    for f in files:
        for m in re.finditer(r"(?:#|0x)([0-9A-Fa-f]{6})", f.read_text(encoding="utf-8")):
            h = m.group(1).lower()
            if not (h[0:2] == h[2:4] == h[4:6]):
                bad.append(f"{f.name}: {m.group(0)}")
    assert not bad, bad
