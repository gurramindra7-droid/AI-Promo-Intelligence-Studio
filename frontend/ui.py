"""Design system + shared UI for the studio - strict monochrome (black / white / gray only).

Tokens live here and in .streamlit/config.toml. Hierarchy comes from brightness, weight and material,
never from hue. Status is shown with a glyph + word (never colour alone):
    ● Approved   ◐ Needs revision   ✕ Rejected   ○ Pending
Pages call the service layer directly (same code as the FastAPI backend); every number comes from the
database, and missing data shows an empty state instead of a placeholder value."""
from __future__ import annotations

import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

import common.paths  # noqa: F401
from database import repositories as R
from database.database import init_db, session

VERSION = "2.0.0"
ASSETS = Path(__file__).resolve().parent / "assets"

# ---------- design tokens (the brief's palette, nothing else) ----------
T = {
    "bg": "#000000", "surface": "#111111", "surface2": "#181818", "surface3": "#222222",
    "border": "#303030", "border2": "#444444", "text": "#FFFFFF", "text2": "#B3B3B3", "muted": "#777777",
    "hover": "#292929",
}
FONT = "Inter, 'Segoe UI', system-ui, sans-serif"
DISPLAY = "'Archivo Black', Inter, 'Segoe UI', sans-serif"
MONO = "'Cascadia Mono', Consolas, ui-monospace, monospace"

CSS = f"""
<style>
:root {{
  --background:{T['bg']}; --surface-primary:{T['surface']}; --surface-secondary:{T['surface2']};
  --surface-tertiary:{T['surface3']}; --border-primary:{T['border']}; --border-secondary:{T['border2']};
  --text-primary:{T['text']}; --text-secondary:{T['text2']}; --text-muted:{T['muted']}; --hover-background:{T['hover']};
  --r:8px; --r-sm:6px;
}}
/* ---- shell ---- */
.stApp {{ background: var(--background); }}
.block-container {{ padding-top: 1.4rem !important; padding-bottom: 3rem !important; max-width: 1360px; }}
header[data-testid="stHeader"] {{ background: transparent; }}
@media (min-width: 640px) {{ section[data-testid="stSidebar"] {{ width: 248px !important; min-width: 248px !important; }} }}
section[data-testid="stSidebar"] > div {{ padding-top: .3rem; }}
[data-testid="stSidebarNav"] a {{ border-radius: var(--r-sm); margin: 1px 0; border-left: 2px solid transparent;
   transition: background .15s ease, border-color .15s ease; }}
[data-testid="stSidebarNav"] a:hover {{ background: var(--hover-background); }}
[data-testid="stSidebarNav"] a span {{ color: var(--text-secondary) !important; }}
[data-testid="stSidebarNav"] a[aria-current="page"] {{ background: var(--surface-tertiary); border-left-color: #FFFFFF; }}
[data-testid="stSidebarNav"] a[aria-current="page"] span {{ color: #FFFFFF !important; font-weight: 600; }}
[data-testid="stSidebarNavSeparator"] {{ display: none; }}
[data-testid="stNavSectionHeader"] {{ font-size: .66rem !important; letter-spacing: .16em; text-transform: uppercase;
   color: var(--text-muted) !important; margin-top: .9rem; font-weight: 600; }}
[data-testid="stLogo"] {{ height: 2.6rem !important; max-width: 100%; }}
@media (prefers-reduced-motion: no-preference) {{
  .block-container {{ animation: pageIn .26s ease-out both; }}
  @keyframes pageIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}   /* opacity only: a transform would break position:fixed */
}}
/* ---- type ---- */
h1 {{ font-family: {DISPLAY} !important; text-transform: uppercase; letter-spacing: .01em; margin: 0 !important;
   padding: 0 !important; line-height: 1.1 !important; }}
h2, h3 {{ letter-spacing: -.005em; }}
.crumb {{ font-size: .7rem; color: var(--text-muted); letter-spacing: .14em; text-transform: uppercase; margin-bottom: 6px; }}
.crumb b {{ color: var(--text-secondary); font-weight: 600; }}
.subtitle {{ color: var(--text-secondary); font-size: .9rem; margin-top: 6px; }}
.eyebrow {{ font-size: .68rem; letter-spacing: .16em; text-transform: uppercase; color: var(--text-muted); font-weight: 600; }}
.sec {{ display:flex; align-items: baseline; justify-content: space-between; gap: 12px; margin: 2px 0 12px; }}
.sec .t {{ font-weight: 700; font-size: .78rem; letter-spacing: .14em; text-transform: uppercase; color: #FFFFFF; }}
.sec .c {{ color: var(--text-muted); font-size: .78rem; }}
.mono {{ font-family: {MONO}; font-size: .8rem; }}
/* ---- top bar ---- */
.st-key-topbar {{ border-bottom: 1px solid var(--border-primary); padding-bottom: 16px; margin-bottom: 10px; }}
.status {{ display:inline-flex; align-items:center; gap:7px; font-size:.74rem; color: var(--text-secondary); letter-spacing:.04em;
   border:1px solid var(--border-primary); border-radius: 999px; padding: 4px 11px; white-space: nowrap; }}
.status i {{ width:7px; height:7px; border-radius:50%; border:1px solid var(--text-muted); display:inline-block; }}
.status.busy i {{ background:#FFFFFF; border-color:#FFFFFF; }}
@media (prefers-reduced-motion: no-preference) {{ .status.busy i {{ animation: pulse 1.6s ease-in-out infinite; }}
  @keyframes pulse {{ 50% {{ opacity: .3; }} }} }}
/* ---- surfaces ---- */
.kpi {{ background: var(--surface-primary); border: 1px solid var(--border-primary); border-radius: var(--r); padding: 16px 18px;
   height: 100%; min-height: 112px; position: relative; overflow: hidden; }}
.kpi:before {{ content:""; position:absolute; left:0; top:0; right:0; height:1px; background: linear-gradient(90deg,#444,transparent); }}
.kpi .l {{ color: var(--text-muted); font-size: .68rem; font-weight: 600; letter-spacing: .14em; text-transform: uppercase; }}
.kpi .v {{ font-family: {DISPLAY}; font-size: 1.9rem; color: #FFFFFF; line-height: 1.2; margin-top: 10px; font-variant-numeric: tabular-nums; }}
.kpi .v.none {{ color: var(--border-secondary); }}
.kpi .h {{ color: var(--text-secondary); font-size: .76rem; margin-top: 4px; }}
div[data-testid="stVerticalBlockBorderWrapper"] {{ border-color: var(--border-primary) !important; background: var(--surface-primary);
   transition: border-color .15s ease; }}
div[data-testid="stVerticalBlockBorderWrapper"]:hover {{ border-color: var(--border-secondary) !important; }}
/* ranked rows (editorial list) */
.row {{ display:grid; grid-template-columns: 44px 1fr auto; gap: 14px; align-items: center; padding: 12px 2px;
   border-bottom: 1px solid var(--surface-tertiary); }}
.row:last-child {{ border-bottom: none; }}
.row .rk {{ font-family: {DISPLAY}; color: #FFFFFF; font-size: 1.15rem; text-align: left; }}
.row .q {{ color: #FFFFFF; font-size: .9rem; line-height: 1.38; overflow: hidden; text-overflow: ellipsis;
   display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; }}
.row .m {{ color: var(--text-muted); font-size: .76rem; margin-top: 4px; }}
.row .sc {{ font-weight: 600; color: #FFFFFF; font-size: .95rem; font-variant-numeric: tabular-nums; }}
.cut {{ font-family: {MONO}; font-size: .76rem; color: #FFFFFF; background: var(--surface-tertiary);
   border: 1px solid var(--border-primary); border-radius: 4px; padding: 1px 7px; white-space: nowrap; }}
.tag {{ display:inline-flex; align-items:center; gap:6px; font-size:.7rem; color: var(--text-secondary); letter-spacing:.03em;
   border:1px solid var(--border-primary); border-radius: 999px; padding: 1px 9px; margin-right: 4px; white-space: nowrap; }}
.tag.solid {{ background:#FFFFFF; color:#000000; border-color:#FFFFFF; font-weight:600; }}
.tag.strong {{ color:#FFFFFF; border-color: var(--border-secondary); }}
.tag.dim {{ color: var(--text-muted); border-style: dashed; }}
.tag .g {{ font-size: .8rem; line-height: 1; }}
/* promo card */
.pc-head {{ display:flex; align-items:center; gap: 10px; flex-wrap: wrap; }}
.pc-rank {{ font-family: {DISPLAY}; font-size: 1.35rem; color: #FFFFFF; min-width: 44px; }}
.pc-score {{ margin-left:auto; text-align:right; }}
.pc-score .n {{ font-family: {DISPLAY}; font-size: 1.5rem; color: #FFFFFF; font-variant-numeric: tabular-nums; line-height: 1; }}
.pc-score .u {{ font-size: .62rem; color: var(--text-muted); letter-spacing: .16em; text-transform: uppercase; margin-top: 4px; }}
.pc-line {{ margin-top: 12px; display:grid; grid-template-columns: 78px 1fr; gap: 6px 12px; font-size: .9rem; }}
.pc-line .k {{ color: var(--text-muted); font-size: .64rem; letter-spacing: .16em; text-transform: uppercase; padding-top: 4px; font-weight: 600; }}
.pc-line .t {{ color: #FFFFFF; line-height: 1.42; }}
.meters {{ display:flex; gap: 22px; flex-wrap: wrap; margin-top: 14px; }}
.meter {{ display:flex; align-items:center; gap: 8px; font-size: .72rem; color: var(--text-muted); letter-spacing: .06em; text-transform: uppercase; }}
.meter .cells {{ display:flex; gap: 2px; }}
.meter .cells span {{ width: 14px; height: 5px; border-radius: 1px; background: var(--surface-tertiary); }}
.meter .cells span.on {{ background: #FFFFFF; }}
.meter b {{ color: #FFFFFF; font-weight: 600; font-variant-numeric: tabular-nums; letter-spacing: 0; }}
/* empty state */
.empty {{ border: 1px dashed var(--border-secondary); border-radius: var(--r); padding: 30px 22px; text-align: center; background: var(--surface-primary); }}
.empty .t {{ font-weight: 700; color: #FFFFFF; margin-bottom: 6px; letter-spacing: .1em; text-transform: uppercase; font-size: .8rem; }}
.empty .b {{ color: var(--text-secondary); font-size: .86rem; max-width: 540px; margin: 0 auto; }}
/* key-value */
.kv {{ display:grid; grid-template-columns: 180px 1fr; gap: 9px 16px; font-size: .88rem; }}
.kv .k {{ color: var(--text-muted); }} .kv .v {{ color: #FFFFFF; overflow-wrap: anywhere; }}
/* widgets */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {{ min-height: 2.25rem; font-weight: 500;
   background: var(--surface-secondary); border-color: var(--border-primary); color: #FFFFFF;
   transition: background .15s ease, border-color .15s ease, transform .05s ease; }}
.stButton > button:hover, .stDownloadButton > button:hover, .stFormSubmitButton > button:hover {{
   background: var(--hover-background); border-color: var(--border-secondary); color: #FFFFFF; }}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primaryFormSubmit"] {{ background: #FFFFFF; color: #000000; border-color: #FFFFFF; }}
.stButton > button[kind="primary"] p, .stFormSubmitButton > button[kind="primaryFormSubmit"] p {{ color: #000000; }}
.stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primaryFormSubmit"]:hover {{ background: #D9D9D9; color:#000; border-color:#D9D9D9; }}
.stButton > button[kind="tertiary"] {{ background: transparent; border-color: transparent; }}
.stButton > button:active {{ transform: translateY(1px); }}
[data-testid="stTabs"] button[role="tab"] {{ font-size: .8rem; letter-spacing: .08em; text-transform: uppercase; }}
[data-testid="stTabs"] [data-baseweb="tab-highlight"] {{ background: #FFFFFF !important; }}
[data-testid="stChatMessage"] {{ background: transparent; }}
[data-testid="stExpander"] details {{ border-color: var(--border-primary) !important; background: var(--surface-primary); }}
[data-testid="stDialog"] div[role="dialog"] {{ border: 1px solid var(--border-secondary); background: #0B0B0B; }}
.st-key-intro_host {{ position:absolute !important; width:0; height:0; overflow:hidden; margin:0 !important; }}
iframe {{ border: none !important; border-radius: var(--r); }}
[class*="st-key-s_"] button, [class*="st-key-sg"] button {{ justify-content: flex-start; text-align: left; }}
[class*="st-key-s_"] button p, [class*="st-key-sg"] button p {{ text-align: left; }}
/* sidebar copilot dock */
.st-key-fab {{ position: fixed !important; right: 28px; bottom: 26px; z-index: 999; width: auto !important; }}
.st-key-fab button {{ width: 58px; height: 58px; min-height: 58px !important; border-radius: 50% !important;
   background: #FFFFFF !important; border: 1px solid #FFFFFF !important; box-shadow: 0 10px 30px rgba(0,0,0,.6), 0 0 0 6px rgba(255,255,255,.06);
   transition: transform .15s ease, box-shadow .15s ease; }}
.st-key-fab button:hover {{ transform: translateY(-2px); box-shadow: 0 14px 34px rgba(0,0,0,.7), 0 0 0 8px rgba(255,255,255,.08); }}
.st-key-fab button span, .st-key-fab button p {{ color: #000000 !important; font-size: 1.5rem !important; }}
.st-key-fab:after {{ content: "ASK STUDIO"; position: absolute; right: 70px; top: 18px; white-space: nowrap; font-size: .62rem;
   letter-spacing: .16em; font-weight: 700; color: #000; background: #FFFFFF; padding: 4px 9px; border-radius: 999px; pointer-events: none; }}
[data-testid="stDialog"] .dock-q, .st-key-dock .dock-q {{ color: #FFFFFF; font-weight: 600; font-size: .86rem; border-left: 2px solid #FFFFFF;
   padding-left: 9px; margin: 6px 0 4px; }}
[data-testid="stDialog"] .dock-src .cut {{ font-size: .7rem; display: inline-block; margin: 2px 2px 0 0; }}
.st-key-dock {{ background: var(--surface-primary) !important; margin-top: 18px; }}
.st-key-dock .dock-h {{ display:flex; justify-content:space-between; align-items:center; }}
.st-key-dock .dock-h span {{ font-weight:700; font-size:.68rem; letter-spacing:.16em; text-transform:uppercase; color:#FFFFFF; }}
.st-key-dock .dock-h em {{ font-style:normal; font-size:.62rem; letter-spacing:.12em; text-transform:uppercase; color: var(--text-muted);
   border:1px solid var(--border-primary); border-radius:999px; padding:0 7px; }}
.st-key-dock .dock-q {{ color: var(--text-secondary); font-size:.76rem; border-left:2px solid #FFFFFF; padding-left:8px; margin-top:4px; }}
.st-key-dock [data-testid="stMarkdownContainer"] p, .st-key-dock [data-testid="stMarkdownContainer"] li {{ font-size:.8rem; line-height:1.45; }}
.st-key-dock .dock-src .cut {{ font-size:.68rem; display:inline-block; margin:2px 2px 0 0; }}
.st-key-dock input {{ font-size:.82rem; }}
.st-key-dock [data-testid="InputInstructions"] {{ display:none; }}
a {{ color: #FFFFFF; }}
::selection {{ background: #FFFFFF; color: #000000; }}
@media (max-width: 900px) {{ .kv {{ grid-template-columns: 1fr; }} .pc-line {{ grid-template-columns: 1fr; }} }}
</style>
"""


def setup():
    st.html(CSS)
    if "db_ready" not in st.session_state:
        init_db()
        st.session_state.db_ready = True


def esc(s) -> str:
    return str(s if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def fmt_t(s) -> str:
    s = int(round(s or 0))
    return f"{s // 60}:{s % 60:02d}"


def cut(p: dict) -> str:
    return f"Ep{p['episode']} {fmt_t(p['ep_start'])}–{fmt_t(p['ep_end'])}"


def num(v, d=1) -> str:
    return "—" if v is None else (f"{v:.{d}f}" if isinstance(v, float) and v != int(v) else f"{int(v)}" if isinstance(v, (int, float)) else str(v))


# ---------- project + top bar ----------

def projects() -> list[dict]:
    with session() as con:
        return R.list_projects(con)


def current_project() -> dict | None:
    ps = projects()
    if not ps:
        return None
    names = [p["name"] for p in ps]
    if st.session_state.get("_project") not in names:
        st.session_state["_project"] = names[0]
    return next(p for p in ps if p["name"] == st.session_state["_project"])


def _active_jobs() -> int:
    with session() as con:
        return sum(1 for j in R.list_jobs(con, None, 20) if j["status"] in ("queued", "running"))


def page_header(title: str, subtitle: str = "", project_select: bool = True) -> dict | None:
    """Breadcrumb + title on the left; project selector and real processing status on the right."""
    ps = projects()
    with st.container(key="topbar"):
        left, right = st.columns([1.6, 1.4], vertical_alignment="bottom")
        with left:
            from common.settings import get_settings
            demo = ' &nbsp;<span class="tag strong">Public demo · fictional show</span>' if get_settings().demo else ""
            st.html(f'<div class="crumb">Studio &nbsp;/&nbsp; <b>{esc(title)}</b>{demo}</div>')
            st.title(title, anchor=False)
            if subtitle:
                st.html(f'<div class="subtitle">{esc(subtitle)}</div>')
        with right:
            if project_select and ps:
                NEW = "__new__"
                names = [p["name"] for p in ps]
                cur = current_project()["name"]          # kept in "_project" so it survives pages without the picker

                def _pick():
                    v = st.session_state["_project_sel"]
                    if v == NEW:                         # "custom input" opens the new-project window
                        st.session_state["_open_new_project"] = True
                    else:
                        st.session_state["_project"] = v
                st.session_state["_project_sel"] = cur
                c1, c2 = st.columns([3, 1.1], vertical_alignment="bottom")
                c1.selectbox("Project · input", names + [NEW], key="_project_sel", on_change=_pick,
                             format_func=lambda n: "＋ New project — custom input" if n == NEW
                             else next(p["show_title"] for p in ps if p["name"] == n))
                n = _active_jobs()
                c2.html(f'<div style="padding-bottom:6px;text-align:right"><span class="status {"busy" if n else ""}">'
                        f'<i></i>{f"Processing · {n}" if n else "Idle"}</span></div>')
    if st.session_state.pop("_open_new_project", False):
        from frontend import new_project
        new_project.dialog()
    if project_select and not ps:
        empty_state("No project yet", "Open Settings → Project to import a processed show or upload a script.")
        return None
    return current_project() if project_select else None


# ---------- building blocks ----------

def link(page_key: str, label: str, icon: str = ":material/arrow_forward:"):
    """Link to another studio page (Page objects are registered by frontend/app.py)."""
    pg = (st.session_state.get("_pages") or {}).get(page_key)
    if pg is not None:
        st.page_link(pg, label=label, icon=icon)


def section(title: str, caption: str = ""):
    st.html(f'<div class="sec"><span class="t">{esc(title)}</span><span class="c">{esc(caption)}</span></div>')


def kpi(col, value, label: str, hint: str = ""):
    empty = value in (None, "", "—")
    col.html(f'<div class="kpi"><div class="l">{esc(label)}</div>'
             f'<div class="v {"none" if empty else ""}">{esc("—" if empty else value)}</div>'
             f'<div class="h">{esc(hint)}</div></div>')


def empty_state(title: str, body: str):
    st.html(f'<div class="empty"><div class="t">{esc(title)}</div><div class="b">{esc(body)}</div></div>')


# Monochrome tones: solid (white chip), strong (white outline), "" (gray), dim (dashed). Glyphs carry meaning.
GLYPH = {"approve": "●", "needs_revision": "◐", "reject": "✕", None: "○", "review": "◐"}


def tag(text: str, tone: str = "", glyph: str | bool = "", dot: bool = False) -> str:
    """Monochrome chip. Semantic tones map to brightness: good -> solid white, warn/accent -> white outline,
    bad -> dashed gray. glyph=True picks the matching shape (● ◐ ○) so meaning never relies on colour."""
    tone = {"good": "solid", "warn": "strong", "bad": "dim", "accent": "strong"}.get(tone, tone)
    if glyph is True or dot:
        glyph = {"solid": "●", "strong": "◐", "dim": "○"}.get(tone, "·")
    g = f'<span class="g">{glyph}</span>' if glyph else ""
    return f'<span class="tag {tone}">{g}{esc(text)}</span>'


VERDICT_TONE = {"approve": "solid", "review": "strong", "reject": "dim"}
DECISION_TONE = {"approve": "solid", "needs_revision": "strong", "reject": "dim"}
DECISION_LABEL = {"approve": "Approved", "needs_revision": "Needs revision", "reject": "Rejected"}
RANKING_LABEL = {"original": "Original pipeline", "agents": "Multi-agent"}


def status_tag(decision: str | None) -> str:
    return tag(DECISION_LABEL.get(decision, "Pending review"), DECISION_TONE.get(decision, ""), GLYPH.get(decision, "○"))


def meter(label: str, v) -> str:
    n = 0 if v is None else int(round(v))
    cells = "".join(f'<span class="{"on" if i < n else ""}"></span>' for i in range(5))
    return f'<div class="meter">{esc(label)} <div class="cells">{cells}</div><b>{num(v)}</b></div>'


def promo_row(p: dict) -> str:
    return (f'<div class="row"><div class="rk">{p["rank"]:02d}</div>'
            f'<div><div class="q">{esc(p["hook_text"])}</div>'
            f'<div class="m"><span class="cut">{esc(cut(p))}</span> &nbsp;{esc((p["archetype"] or "moment").replace("_", " ").upper())}'
            f' · {round(p["duration"] or 0)} s</div></div><div class="sc">{num(p["score"])}</div></div>')


def promo_card_html(p: dict, decision: str | None) -> str:
    tags = [tag((p["archetype"] or "moment").replace("_", " "))]
    if p.get("verdict"):
        tags.append(tag(f"Critic: {p['verdict']}", VERDICT_TONE.get(p["verdict"], ""), GLYPH.get(p["verdict"], "")))
    if p.get("context_dependency"):
        tags.append(tag(f"Context: {p['context_dependency']}", {"low": "strong", "medium": "", "high": "dim"}.get(p["context_dependency"], "")))
    tags.append(status_tag(decision))
    return f"""<div class="pc-head"><span class="pc-rank">{p['rank']:02d}</span><span class="cut">{esc(cut(p))}</span>
<span class="tag">{round(p['duration'] or 0)} s</span>{''.join(tags)}
<div class="pc-score"><div class="n">{num(p['score'])}</div><div class="u">score</div></div></div>
<div class="pc-line"><div class="k">Hook</div><div class="t">“{esc(p['hook_text'])}”</div>
<div class="k">Cut on</div><div class="t">“{esc(p['cliff_text'])}”</div></div>
<div class="meters">{meter('Hook', p['hook_score'])}{meter('Cliffhanger', p['cliff_score'])}{meter('Standalone', p['standalone_score'])}</div>"""


def ranking_switch(con, pid: int, key: str) -> str:
    kinds = R.ranking_kinds(con, pid) or ["original"]
    if len(kinds) == 1:
        return kinds[0]
    v = st.segmented_control("Ranking", ["original"] + [k for k in kinds if k != "original"],
                             default="original" if "original" in kinds else kinds[0], label_visibility="collapsed",
                             format_func=lambda k: RANKING_LABEL.get(k, k), key=key, required=True)
    return v or kinds[0]


def script_lines(p: dict, show_camera: bool = False):
    rows = []
    for l in json.loads(p.get("lines_json") or "[]"):
        if l.get("type") == "camera" and not show_camera:
            continue
        who = (l.get("speaker") or "").title() or l.get("type", "").upper()
        rows.append(f'<div style="display:grid;grid-template-columns:52px 130px 1fr;gap:12px;padding:6px 0;'
                    f'border-bottom:1px solid #222;font-size:.86rem">'
                    f'<span class="mono" style="color:#777">{fmt_t(l.get("ep_start", l["start"]))}</span>'
                    f'<span style="color:#B3B3B3">{esc(who)}</span><span>{esc(l.get("text", ""))}</span></div>')
    st.html("".join(rows) or '<div class="subtitle">No lines.</div>')


# ---------- 2D charts (grayscale) - used for table-adjacent views and small summaries ----------

def _style(ch: alt.Chart, height: int) -> alt.Chart:
    return (ch.properties(height=height, background="transparent")
            .configure_view(stroke=None)
            .configure_axis(labelColor=T["text2"], titleColor=T["muted"], labelFont=FONT, titleFont=FONT,
                            labelFontSize=11, titleFontSize=10, titleFontWeight=600, gridColor=T["surface3"],
                            gridWidth=1, domain=False, tickColor=T["surface3"], tickSize=4)
            .configure_legend(labelColor=T["text2"], titleColor=T["muted"], labelFont=FONT, titleFont=FONT))


def bar_chart(df: pd.DataFrame, cat: str, val: str, cat_title: str, val_title: str, horizontal=False,
              height=240, sort=None, tooltip=None):
    tip = tooltip or [alt.Tooltip(cat, title=cat_title), alt.Tooltip(val, title=val_title)]
    if horizontal:
        enc = dict(y=alt.Y(f"{cat}:N", title=None, sort=sort or "-x", axis=alt.Axis(labelLimit=200, ticks=False)),
                   x=alt.X(f"{val}:Q", title=val_title, axis=alt.Axis(tickMinStep=1, grid=True)))
        mark = alt.Chart(df).mark_bar(color="#D9D9D9", cornerRadiusTopRight=2, cornerRadiusBottomRight=2, size=12)
    else:
        enc = dict(x=alt.X(f"{cat}:O", title=cat_title, sort=sort, axis=alt.Axis(labelAngle=0, ticks=False)),
                   y=alt.Y(f"{val}:Q", title=val_title, axis=alt.Axis(tickMinStep=1, grid=True)))
        mark = alt.Chart(df).mark_bar(color="#D9D9D9", cornerRadiusTopLeft=2, cornerRadiusTopRight=2, size=14)
    st.altair_chart(_style(mark.encode(**enc, tooltip=tip), height), width="stretch", theme=None)


def heatmap(df: pd.DataFrame, x: str, y: str, val: str, x_title: str, y_title: str, height=320, y_sort=None):
    ch = alt.Chart(df).mark_rect(cornerRadius=1, stroke=T["bg"], strokeWidth=2).encode(
        x=alt.X(f"{x}:O", title=x_title, axis=alt.Axis(labelAngle=0, ticks=False, labelOverlap=True)),
        y=alt.Y(f"{y}:N", title=None, sort=y_sort, axis=alt.Axis(ticks=False, labelLimit=170)),
        color=alt.Color(f"{val}:Q", title="Lines", scale=alt.Scale(range=["#1C1C1C", "#FFFFFF"])),
        tooltip=[alt.Tooltip(y, title=y_title), alt.Tooltip(x, title=x_title), alt.Tooltip(val, title="Lines")])
    st.altair_chart(_style(ch, height), width="stretch", theme=None)
