"""Interactive 3D bar charts (Three.js) for Streamlit.

Each chart is a small, isolated HTML document rendered with st.iframe. It loads the vendored Three.js
and frontend/static/js/chart3d.js from /app/static/ (no CDN). Data goes in as JSON; every value comes
from the database. Callers always pair a chart with a Table view (the accessible alternative)."""
from __future__ import annotations

import html as _html
import json
from pathlib import Path

import streamlit as st

TEMPLATE = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;height:100%;background:#111;font-family:Inter,'Segoe UI',system-ui,sans-serif;overflow:hidden}
#wrap{position:relative;width:100%;height:100%}
#wrap canvas{display:block;width:100%;height:100%;touch-action:none}
#labels{position:absolute;inset:0;pointer-events:none}
.lb{position:absolute;left:0;top:0;white-space:nowrap;font-size:11px;color:#B3B3B3;font-variant-numeric:tabular-nums}
.lb.cat{font-size:11px;color:#B3B3B3;transform-origin:100% 0;text-transform:capitalize}
.lb.y{color:#777;font-size:10px}.lb.t{color:#777;font-size:10px;letter-spacing:.14em;text-transform:uppercase;font-weight:600}
.lb.s{color:#fff;font-size:10px;letter-spacing:.1em;text-transform:uppercase;font-weight:600}
#tip{position:absolute;left:0;top:0;pointer-events:none;opacity:0;transition:opacity .12s;background:#000;color:#fff;
 border:1px solid #444;border-radius:6px;padding:8px 10px;font-size:12px;line-height:1.45;max-width:240px;box-shadow:0 8px 24px rgba(0,0,0,.6)}
#tip b{font-weight:600}
.ctl{position:absolute;right:10px;top:10px;display:flex;gap:6px;align-items:center}
.hint{color:#777;font-size:10px;letter-spacing:.08em;text-transform:uppercase}
#reset{background:#181818;color:#fff;border:1px solid #303030;border-radius:6px;font:500 11px Inter,sans-serif;letter-spacing:.08em;
 text-transform:uppercase;padding:6px 10px;cursor:pointer}#reset:hover{background:#292929;border-color:#444}
#fallback{position:absolute;inset:0;display:none;align-items:center;justify-content:center;color:#B3B3B3;font-size:13px;text-align:center;padding:24px}
</style></head><body><div id="wrap"><div id="labels"></div><div id="tip"></div>
<div class="ctl"><span class="hint">Drag to rotate · scroll to zoom</span><button id="reset" type="button">Reset view</button></div>
<div id="fallback"></div></div>
<script type="application/json" id="cfg">__CFG__</script>
<script type="module">
import { mount } from "/app/static/js/chart3d.js?v=__V__";
mount(JSON.parse(document.getElementById("cfg").textContent));
</script></body></html>"""

JS = Path(__file__).resolve().parent / "static" / "js" / "chart3d.js"


def _version() -> str:
    """Cache-buster: the chart script's modification time, so browsers never run a stale copy."""
    try:
        return str(int(JS.stat().st_mtime))
    except OSError:
        return "0"


SHADES = [0xBDBDBD, 0x6E6E6E, 0x9A9A9A, 0x4A4A4A]   # light gray, mid gray ... (series identity via depth row + label)


def bars3d(categories: list[str], series: list[dict], x_title: str = "", y_title: str = "", height: int = 380,
           label_every: int = 1, tooltips: list[list[str]] | None = None) -> None:
    """series = [{"name": str, "values": [numbers], "shade": optional int}] - one depth row per series."""
    for i, s in enumerate(series):
        s.setdefault("shade", SHADES[i % len(SHADES)])
    cfg = {"categories": [str(c) for c in categories], "series": series, "xTitle": x_title, "yTitle": y_title,
           "labelEvery": label_every, "tooltips": tooltips}
    blob = json.dumps(cfg).replace("</", "<\\/")
    st.iframe(TEMPLATE.replace("__CFG__", blob).replace("__V__", _version()), height=height)


def tip(*rows: tuple[str, object]) -> str:
    """Tooltip HTML: first row bold title, the rest 'label: value'."""
    head, *rest = rows
    return f"<b>{_html.escape(str(head[1]))}</b>" + "".join(f"<br>{_html.escape(str(k))}: {_html.escape(str(v))}" for k, v in rest)
