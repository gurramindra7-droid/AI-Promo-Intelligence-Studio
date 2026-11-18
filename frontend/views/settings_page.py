import json
import os
import platform
import sqlite3
import urllib.request
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

from backend.services import processing_service as PS
from backend.services.import_service import available_shows
from common.paths import CONFIG, ROOT
from common.settings import get_settings
from database import repositories as R
from database.database import session
from frontend import ui

ROLES = {"agent": "Hook + cliffhanger agents", "stranger": "Stranger agent", "critic": "Editorial critic",
         "story": "Story events", "copilot": "Editorial copilot"}
KEY_ENV = {"groq": "GROQ_API_KEY", "gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}


def render():
    ui.page_header("Settings", "Configuration and status. Values shown are read live; keys are never displayed.",
                   project_select=False)
    t = st.tabs(["General", "Project", "AI configuration", "Workflow", "System information", "Appearance & intro"])
    with t[0]:
        _general()
    with t[1]:
        _project()
    with t[2]:
        _ai()
    with t[3]:
        _workflow()
    with t[4]:
        _system()
    with t[5]:
        _appearance()


def _kv(rows: list[tuple[str, str]]):
    st.html('<div class="kv">' + "".join(f'<div class="k">{ui.esc(k)}</div><div class="v">{v}</div>' for k, v in rows) + "</div>")


def _general():
    with st.container(border=True):
        ui.section("Product")
        _kv([("Name", "AI Promo Intelligence Studio"), ("Version", ui.VERSION),
             ("Purpose", "Find, evaluate and select promo moments from microdrama screenplays."),
             ("Workspace", "Executive Dashboard · Promo Discovery · Story Intelligence · Editorial Copilot · Feedback Center")])


def _appearance():
    with st.container(border=True):
        ui.section("Introduction", "5-second Three.js opening, plays each time the studio opens")
        a, b = st.columns([1, 3], vertical_alignment="center")
        if a.button("Replay introduction", icon=":material/replay:", type="primary"):
            st.session_state.replay_intro = True
            st.rerun()
        b.caption("Ends on an Enter Studio button; Skip (button or Esc) jumps to that screen. With reduced motion turned on in your system, one still "
                  "frame is shown instead; without WebGL a simple CSS version plays.")
    with st.container(border=True):
        ui.section("Theme", "fixed by design")
        _kv([("Palette", "Monochrome: black, white and gray only"), ("Display font", "Archivo Black (bundled)"),
             ("Text font", "Inter (bundled)"), ("Charts", "Interactive Three.js 3D, each with a Table view"),
             ("Defined in", '<span class="mono">.streamlit/config.toml</span> and <span class="mono">frontend/ui.py</span>')])
    with st.container(border=True):
        ui.section("Display")
        st.session_state.pref_camera = st.toggle("Show camera directions in script views by default",
                                                 value=st.session_state.get("pref_camera", False))


def _project():
    p = ui.current_project()
    if p:
        with session() as con:
            eps = R.get_episodes(con, p["id"])
            kinds = {k: len(R.get_promos(con, p["id"], k)) for k in R.ranking_kinds(con, p["id"])}
            chars = len(R.get_characters(con, p["id"]))
        with st.container(border=True):
            ui.section("Current project", "change it with the project picker on any workspace page")
            _kv([("Title", ui.esc(p["show_title"])), ("Name", f'<span class="mono">{ui.esc(p["name"])}</span>'),
                 ("Source", ui.esc(p["source_path"] or "—")), ("Created", ui.esc(p["created_at"])),
                 ("Episodes", str(len(eps))), ("Script blocks", f'{sum(e["n_blocks"] or 0 for e in eps):,}'),
                 ("Rankings", ", ".join(f"{ui.RANKING_LABEL.get(k, k)}: {n}" for k, n in kinds.items()) or "—"),
                 ("Characters", str(chars) if chars else "story not built"),
                 ("Protected", "yes: saved outputs are never re-processed" if PS.is_protected(p["name"], p["source_path"] or "") else "no")])
    if get_settings().demo:
        st.info("This is the public demo: an original fictional show, preloaded. Importing and uploading are "
                "turned off here; run the studio locally to process your own scripts.", icon=":material/lock:")
        return
    with st.container(border=True):
        ui.section("Import processed shows", "load saved pipeline outputs, no AI")
        have = {x["name"] for x in ui.projects()}
        for sh in available_shows():
            c1, c2 = st.columns([4, 1], vertical_alignment="center")
            c1.html(f'<span class="mono">{ui.esc(sh)}</span> ' + (ui.tag("in studio", "good", True) if sh in have else ""))
            if c2.button("Re-import" if sh in have else "Import", key=f"imp_{sh}", width="stretch"):
                with session() as con:
                    PS.create_project(con, sh)
                    PS.start(con, R.get_project(con, sh)["id"], "import", background=False)
                st.toast(f"Imported {sh}", icon=":material/check:")
                st.rerun()
    with st.container(border=True):
        ui.section("New project from scripts", "saved under data/uploads/ (git-ignored)")
        with st.form("upload", border=False):
            name = st.text_input("Project name", placeholder="letters, digits and _")
            files = st.file_uploader("Script files: one file, or one per episode", type=["txt", "srt", "vtt", "md"],
                                     accept_multiple_files=True)
            if st.form_submit_button("Create project", type="primary"):
                try:
                    with session() as con:
                        r = PS.create_project(con, name, name, [{"filename": f.name, "content": f.getvalue().decode(
                            "utf-8", errors="replace")} for f in files or []])
                    st.success(f"Created {r['name']} with {r['files']} file(s). Run the 'pipeline' job in Workflow next.")
                except ValueError as e:
                    st.error(str(e))


def _ai():
    s = get_settings()
    llm = (yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}).get("llm", {})
    with st.container(border=True):
        ui.section("Models by role", "config.yaml studio: section, overridable with STUDIO_<ROLE>_MODEL")
        rows = []
        for role, label in ROLES.items():
            m = s.model_for(role) or llm.get("model", "")
            prov = m.split("/")[0] if "/" in m else "—"
            env = KEY_ENV.get(prov)
            rows.append({"Role": label, "Model": m, "Provider": prov,
                         "API key": ("present" if os.getenv(env) else "missing") if env else "—",
                         "Override": f"STUDIO_{role.upper()}_MODEL" + (" (set)" if os.getenv(f"STUDIO_{role.upper()}_MODEL") else "")})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption("'present' means the key exists in .env. It is not a live connection test, and no call is made here.")
    with st.container(border=True):
        ui.section("Shared model settings", "config.yaml llm: section")
        _kv([("Main model", f'<span class="mono">{ui.esc(llm.get("model"))}</span>'),
             ("Fallback model", f'<span class="mono">{ui.esc(llm.get("fallback_model") or "off")}</span>'),
             ("Temperature", ui.esc(llm.get("temperature"))), ("Reasoning effort", ui.esc(llm.get("reasoning_effort") or "—")),
             ("JSON retries", ui.esc(llm.get("json_retries"))), ("Cache", "on" if llm.get("use_cache", True) else "off"),
             ("Agent shortlist", f'top {s.studio["shortlist_pct"]}% of lines · max {s.studio["max_candidates"]} clips')])


def _workflow():
    s = get_settings()
    ps = ui.projects()
    if s.demo:
        st.info(PS.DEMO_MSG + " Every result shown comes from real runs saved in the demo database.", icon=":material/lock:")
    with st.container(border=True):
        ui.section("Processing", "jobs run in the background; status updates live in the top bar")
        if not ps:
            st.caption("Import or create a project first.")
        else:
            names = [x["name"] for x in ps]
            cur = ui.current_project()
            c1, c2, c3, c4 = st.columns([1.6, 1.2, 1.2, 0.8], vertical_alignment="bottom")
            name = c1.selectbox("Project", names, index=names.index(cur["name"]) if cur else 0, key="proc_proj")
            mode = c2.selectbox("Job", list(PS.MODES), help="import: load saved outputs (no AI) · pipeline: original "
                                "pipeline on uploaded files · agents: multi-agent ranking · story: story graph")
            eps = c3.text_input("Episodes", "1-3" if mode == "agents" else "", placeholder="e.g. 1-5, blank = all")
            use_llm = c4.toggle("AI", value=True, help="story without AI = script facts only")
            sel = next(x for x in ps if x["name"] == name)
            if mode == "pipeline" and PS.is_protected(name, sel.get("source_path") or ""):
                st.warning("This show's saved outputs are protected: the pipeline only re-runs uploaded projects.")
            if mode == "agents":
                st.caption("Agents make real model calls (about 5 per episode on the free tier). Start small.")
            if st.button("Start job", type="primary", icon=":material/play_arrow:", disabled=s.demo):
                try:
                    with session() as con:
                        jid = PS.start(con, R.get_project(con, name)["id"], mode, _parse_eps(eps), use_llm)
                    st.toast(f"Job {jid} started", icon=":material/play_arrow:")
                except ValueError as e:
                    st.error(str(e))
            with session() as con:
                jobs = R.list_jobs(con, None, 10)
            if jobs:
                st.button("Refresh status", icon=":material/refresh:", type="tertiary")
                st.dataframe(pd.DataFrame(jobs)[["id", "kind", "status", "progress", "message", "updated_at"]],
                             hide_index=True, width="stretch", column_config={
                                 "progress": st.column_config.ProgressColumn("Progress", min_value=0, max_value=1,
                                                                             format="percent")})
    with st.container(border=True):
        ui.section("AI answer cache", "saved replies make re-runs free and reproducible")
        cache = ROOT / "cache"
        files = list(cache.glob("*.json")) if cache.exists() else []
        _kv([("Location", '<span class="mono">cache/</span> (git-ignored)'), ("Saved replies", f"{len(files):,}"),
             ("Size", f"{sum(f.stat().st_size for f in files) / 1e6:.1f} MB")])
    with st.container(border=True):
        ui.section("n8n automation", "off by default · see docs/N8N_INTEGRATION.md")
        _kv([("Status", ui.tag("Enabled", "good", True) if s.n8n_enabled else ui.tag("Disabled", "", True)),
             ("Webhook secret", "set" if s.n8n_secret else "not set"),
             ("Callback URL", "set" if s.n8n_callback_url else "not set"),
             ("Inbound endpoint", '<span class="mono">POST /api/webhooks/n8n</span> (header X-Webhook-Secret)'),
             ("Tested", "with the API test client; not against a live n8n instance")])


def _system():
    s = get_settings()
    dbp = Path(s.db_path)
    try:
        with sqlite3.connect(dbp) as c:
            ok = c.execute("PRAGMA quick_check").fetchone()[0]
        db_status = ui.tag("OK", "good", True) if ok == "ok" else ui.tag(f"Problem: {ok}", "bad", True)
    except Exception as e:
        db_status = ui.tag(f"Unavailable: {type(e).__name__}", "bad", True)
    api = os.getenv("STUDIO_API_URL", "http://localhost:8000")
    try:
        with urllib.request.urlopen(f"{api}/api/health", timeout=0.8) as r:
            api_status = ui.tag("Running", "good", True) if json.loads(r.read()).get("ok") else ui.tag("Unexpected reply", "warn", True)
    except Exception:
        api_status = ui.tag("Not running", "", True) + ' <span class="subtitle">optional: this app talks to the database directly</span>'
    import streamlit
    with st.container(border=True):
        ui.section("System information", "checked when this page loads")
        _kv([("Studio version", ui.VERSION), ("Python", platform.python_version()), ("Streamlit", streamlit.__version__),
             ("Database", f'<span class="mono">{ui.esc(dbp)}</span>'),
             ("Database size", f"{dbp.stat().st_size / 1e6:.1f} MB" if dbp.exists() else "—"),
             ("Database check", db_status), ("REST API", f'{api_status} <span class="mono">{ui.esc(api)}</span>')])
    if st.button("Re-check", icon=":material/refresh:", type="tertiary"):
        st.rerun()


def _parse_eps(t: str):
    t = (t or "").strip()
    if not t:
        return None
    out = []
    for part in t.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return out
