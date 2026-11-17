"""Platform Overview - what the studio is, how the pieces fit, and live facts read from the running system."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from common.paths import ROOT
from common.settings import get_settings
from database import repositories as R
from database.database import session
from frontend import ui

LAYERS = [
    ("01", "Input", "CODE", "Screenplays, timestamped scripts, subtitles. Format detected automatically; every line gets an id and exact times."),
    ("02", "Line scoring", "AI", "Each line scored for hook and cliffhanger strength. The AI returns line ids only, never times."),
    ("03", "Clip builder", "CODE", "20–60 s clips that open on a hook and cut on a cliffhanger, whole lines, inside one episode."),
    ("04", "Four agents", "AI", "Hook, Cliffhanger, blind Stranger and Editorial Critic re-judge the shortlist (validated JSON)."),
    ("05", "Verification", "CODE", "Every clip re-checked against the parser: ids exist, times match, 20–60 s, no episode crossing."),
    ("06", "Ranking", "CODE", "Transparent score with written reasons; original and multi-agent rankings kept side by side."),
    ("07", "Story intelligence", "CODE + AI", "Characters and shared scenes from the script; events from loglines, grounded to real speakers."),
    ("08", "Editor in the loop", "HUMAN", "Approve, revise or reject with reasons; a cautious, audited re-ranking learns from it."),
]
MODULES = [
    ("Original pipeline", "src/", "parser, adapters, tagger, candidate builder, stranger test, ranker"),
    ("Agents", "agents/", "hook, cliffhanger, stranger, editorial critic, orchestrator"),
    ("Story intelligence", "story_intelligence/", "characters, aliases, events, relationship graph"),
    ("Copilot", "copilot/", "8 whitelisted read-only tools, grounded answers, offline mode"),
    ("Feedback", "feedback/", "reviews, conservative calibration, audit trail"),
    ("Backend", "backend/ · database/", "FastAPI REST API, background jobs, SQLite repositories"),
    ("Automation", "automation/", "n8n webhook with secret, signed job events"),
    ("Frontend", "frontend/", "Streamlit studio, Three.js intro and 3D charts"),
]


@st.cache_data(ttl=3600)
def _code_facts() -> dict:
    py = [p for p in ROOT.rglob("*.py") if not any(x in p.parts for x in (".venv", "venv", "archive", "site-packages", "__pycache__"))]
    js = list((ROOT / "frontend" / "static" / "js").glob("*.js"))
    lines = sum(len(p.read_text(encoding="utf-8", errors="ignore").splitlines()) for p in py + js)
    tests = sum(p.read_text(encoding="utf-8", errors="ignore").count("\ndef test_") for p in (ROOT / "tests").glob("test_*.py"))
    try:
        from backend.main import app
        endpoints = sum(1 for r in app.routes if getattr(r, "path", "").startswith("/api/"))
    except Exception:
        endpoints = None
    return {"files": len(py) + len(js), "lines": lines, "tests": tests, "endpoints": endpoints}


def render():
    ui.page_header("Platform Overview", "An editorial intelligence platform that finds, judges and explains promo moments "
                   "in microdrama screenplays.", project_select=False)
    s = get_settings()
    facts = _code_facts()
    with session() as con:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        rows = sum(con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables)
        projects = R.list_projects(con)
        promos = con.execute("SELECT COUNT(*) FROM promos").fetchone()[0]
        lines = con.execute("SELECT COALESCE(SUM(n_blocks),0) FROM episodes").fetchone()[0]
        calls = con.execute("SELECT COUNT(*) FROM model_usage_logs").fetchone()[0]

    st.html('<div style="margin:8px 0 18px;max-width:900px;font-size:1.02rem;line-height:1.6;color:#B3B3B3">'
            'A promo editor normally watches every episode to find 20–60 second moments that open on a hook and end on a '
            'cliffhanger. This studio reads the scripts instead: <b style="color:#fff">code</b> owns every timestamp, '
            '<b style="color:#fff">AI</b> makes the judgement calls, and the <b style="color:#fff">editor</b> makes the '
            'final decision.</div>')
    c = st.columns(6)
    ui.kpi(c[0], f"{facts['lines']:,}", "Lines of code", f"{facts['files']} source files")
    ui.kpi(c[1], facts["tests"], "Test functions", "pytest, offline, mock LLM")
    ui.kpi(c[2], facts["endpoints"], "REST endpoints", "FastAPI backend")
    ui.kpi(c[3], 4, "AI agents", "+ grounded copilot")
    ui.kpi(c[4], len(tables), "Database tables", f"{rows:,} rows live")
    ui.kpi(c[5], calls, "AI calls logged", "model, tokens, time")
    st.write("")

    ui.section("How it works", "eight stages, each owned by code, AI or the editor")
    cards = "".join(
        f'<div class="lay"><div class="n">{n}</div><div class="o">{o}</div><div class="h">{h}</div><div class="d">{d}</div></div>'
        for n, h, o, d in LAYERS)
    st.html(f"""<style>
.lay-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}}
@media (max-width:1000px){{.lay-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
@media (max-width:560px){{.lay-grid{{grid-template-columns:1fr}}}}
.lay{{background:#111;border:1px solid #303030;border-radius:8px;padding:16px;position:relative;min-height:150px}}
.lay .n{{font-family:'Archivo Black',sans-serif;font-size:1.5rem;color:#fff}}
.lay .o{{position:absolute;right:14px;top:16px;font-size:.6rem;letter-spacing:.16em;font-weight:700;color:#000;background:#fff;
 padding:2px 8px;border-radius:999px}}
.lay .h{{font-weight:700;letter-spacing:.08em;text-transform:uppercase;font-size:.8rem;color:#fff;margin-top:8px}}
.lay .d{{color:#B3B3B3;font-size:.84rem;line-height:1.5;margin-top:6px}}
</style><div class="lay-grid">{cards}</div>""")
    st.write("")

    left, right = st.columns([1.3, 1], gap="large")
    with left, st.container(border=True):
        ui.section("System modules", "all in this repository")
        st.html("".join(f'<div class="row" style="grid-template-columns:170px 1fr"><div class="q" style="font-weight:600">{ui.esc(a)}'
                        f'</div><div><div class="m" style="margin:0"><span class="cut">{ui.esc(b)}</span> &nbsp;{ui.esc(c)}</div></div></div>'
                        for a, b, c in MODULES))
    with right:
        with st.container(border=True):
            ui.section("Live data in this deployment")
            st.html('<div class="kv" style="grid-template-columns:150px 1fr">'
                    f'<div class="k">Mode</div><div class="v">{"Public demo · fictional show" if s.demo else "Full studio"}</div>'
                    f'<div class="k">Projects</div><div class="v">{len(projects)}</div>'
                    f'<div class="k">Script lines</div><div class="v">{int(lines):,}</div>'
                    f'<div class="k">Promos ranked</div><div class="v">{promos}</div>'
                    f'<div class="k">Live AI</div><div class="v">{"on" if s.ai_allowed else "off (offline answers)"}</div></div>')
        with st.container(border=True):
            ui.section("Built with")
            st.html('<div class="subtitle" style="line-height:1.9">Python · Streamlit · FastAPI · SQLite · LiteLLM '
                    '(Groq gpt-oss-120b / 20b, swappable in one line) · NetworkX · Three.js · Altair · pytest · n8n</div>')
        with st.container(border=True):
            ui.section("Try it")
            st.html('<div class="subtitle" style="line-height:1.7">Open <b style="color:#fff">Promo Discovery</b> to inspect '
                    'ranked clips, ask the round <b style="color:#fff">Ask Studio</b> button, or pick '
                    '<b style="color:#fff">＋ New project — custom input</b> in the project picker to analyse your own script.</div>')
