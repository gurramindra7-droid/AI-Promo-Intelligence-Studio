import pandas as pd
import streamlit as st

from database import repositories as R
from database.database import session
from frontend import ui
from story_intelligence.relationship_graph import build_graph, character_subgraph, character_view, to_pyvis_html


def render():
    p = ui.page_header("Story Intelligence", "Who is who, who meets whom, and what happens, with the source of every fact.")
    if not p:
        return
    pid = p["id"]
    with session() as con:
        chars = R.get_characters(con, pid)
        if not chars:
            ui.empty_state("No story data yet", "Run the story job in Settings → Workflow. Script facts need no AI; "
                           "events from episode loglines use one AI call per 10 episodes.")
            return
        g = build_graph(con, pid)
        events = R.get_events(con, pid)
        rels_all = R.get_relationships(con, pid)
        eps = R.get_episodes(con, pid)
    stated = [r for r in rels_all if r["relation"] != "appears_with"]
    verified = sum(1 for e in events if e["verified"])

    c = st.columns(4)
    ui.kpi(c[0], len(chars), "Speaking characters", "script speaker labels · certain")
    ui.kpi(c[1], sum(1 for r in rels_all if r["relation"] == "appears_with"), "Shared-scene pairs", "script scenes · certain")
    ui.kpi(c[2], len(stated) or None, "Stated relationships", "from loglines (AI) · grounded" if stated else "AI step not run")
    ui.kpi(c[3], f"{verified} / {len(events)}" if events else None, "Events verified",
           "names matched to real speakers" if events else "AI step not run")
    st.html('<div class="subtitle" style="margin:10px 0 4px">'
            + ui.tag("Confirmed", "good", True) + " from the script itself &nbsp; "
            + ui.tag("Grounded", "accent", True) + " AI fact whose names all match real speakers &nbsp; "
            + ui.tag("Unverified", "bad", True) + " AI fact naming someone who never speaks</div>")

    t1, t2, t3, t4 = st.tabs(["Relationship network", "Characters", "Events", "Episode progression"])
    main = [ch["name"] for ch in chars if ch["n_lines"] >= 3]

    with t1:
        left, right = st.columns([2.2, 1], gap="large")
        with right:
            focus = st.selectbox("Focus character", ["Whole cast"] + main,
                                 format_func=lambda n: n if n == "Whole cast" else n.title())
            focus = None if focus == "Whole cast" else focus
            if focus:
                v = character_view(g, focus)
                st.html(f'<div class="kv" style="grid-template-columns:110px 1fr;margin-top:6px">'
                        f'<div class="k">Lines</div><div class="v">{v["n_lines"]}</div>'
                        f'<div class="k">Episodes</div><div class="v">{v["first_ep"]}–{v["last_ep"]} '
                        f'({len(v["episodes"])} episodes)</div><div class="k">Aliases</div>'
                        f'<div class="v">{ui.esc(", ".join(a.title() for a in v["aliases"]) or "—")}</div></div>')
                ui.section("Strongest connections")
                rows = "".join(f'<div class="row" style="grid-template-columns:1fr auto"><div><div class="q">{ui.esc(k.title())}</div>'
                               f'<div class="m">{ui.esc(", ".join(r["relation"] for r in d["relations"]) or "shared scenes only")}'
                               f'</div></div><div class="sc">{d["shared_scenes"]}</div></div>'
                               for k, d in list(v["connections"].items())[:8])
                st.html(rows or '<div class="subtitle">No connections.</div>')
            else:
                st.html('<div class="subtitle">Node size = lines spoken. Edge thickness = shared scenes. Dashed edge = a '
                        'conflict relation stated in a logline. Pick a character to centre the network.</div>')
        with left:
            st.iframe(to_pyvis_html(character_subgraph(g, focus, max_chars=25), focus, height="500px"), height=520)

    with t2:
        df = pd.DataFrame([{"Character": ch["name"].title(), "Lines": ch["n_lines"], "First ep": ch["first_ep"],
                            "Last ep": ch["last_ep"], "Episodes": len(ch["episodes"]),
                            "Aliases": ", ".join(a.title() for a in ch["aliases"])} for ch in chars])
        st.dataframe(df, hide_index=True, width="stretch", height=460, column_config={
            "Lines": st.column_config.ProgressColumn("Lines", min_value=0, max_value=int(df.Lines.max()), format="%d"),
            "Episodes": st.column_config.NumberColumn("Episodes", help="episodes in which the character speaks")})
        if stated:
            ui.section("Stated relationships", "AI reading of episode loglines, names grounded to real speakers")
            st.dataframe(pd.DataFrame([{"Between": f"{r['a'].title()} – {r['b'].title()}", "Relation": r["relation"],
                                        "Evidence": r["evidence"], "Episodes": ", ".join(map(str, r["episodes"])),
                                        "Confidence": r["confidence"], "Source": r["source"]} for r in stated]),
                         hide_index=True, width="stretch", column_config={
                             "Confidence": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.1f")})

    with t3:
        if not events:
            ui.empty_state("No events yet", "Run the story job with AI on to extract events from the episode loglines.")
        else:
            f1, f2, f3 = st.columns([1.2, 1.4, 2])
            imp = f1.select_slider("Minimum importance", options=[1, 2, 3, 4, 5], value=3)
            only = f2.segmented_control("Show", ["All", "Grounded", "Unverified"], default="All", required=True)
            who = f3.selectbox("Character", ["Everyone"] + main, format_func=lambda n: n if n == "Everyone" else n.title())
            sel = [e for e in events if e["importance"] >= imp and (only == "All" or (only == "Grounded") == bool(e["verified"]))
                   and (who == "Everyone" or who in e["characters"])]
            st.caption(f"{len(sel)} of {len(events)} events")
            by_ep: dict[int, list] = {}
            for e in sorted(sel, key=lambda e: (e["episode"], -e["importance"])):
                by_ep.setdefault(e["episode"], []).append(e)
            html = []
            for ep, es in by_ep.items():
                html.append(f'<div class="row" style="grid-template-columns:64px 1fr;align-items:start">'
                            f'<div class="cut" style="text-align:center">Ep {ep}</div><div>')
                for e in es:
                    html.append(f'<div style="margin-bottom:8px"><div class="q" style="-webkit-line-clamp:3">{ui.esc(e["description"])}</div>'
                                f'<div class="m">{ui.tag(e["event_type"])}{ui.tag("Grounded" if e["verified"] else "Unverified", "accent" if e["verified"] else "bad", True)}'
                                f' importance {e["importance"]}/5 · {ui.esc(", ".join(c.title() for c in e["characters"]) or "—")}'
                                f' · <span class="mono">{ui.esc(e["source"])}</span></div></div>')
                html.append("</div></div>")
            st.html("".join(html) or '<div class="subtitle">No events match.</div>')

    with t4:
        top = [ch for ch in chars if ch["n_lines"] >= 3][:12]
        rows = [{"Character": ch["name"].title(), "Episode": ep, "Lines": n} for ch in top for ep, n in ch["episodes"].items()]
        ui.section("Who carries each episode", "lines spoken per episode · 12 most active characters · from the script")
        if rows:
            ui.heatmap(pd.DataFrame(rows), "Episode", "Character", "Lines", "Episode", "Character",
                       height=34 * len(top) + 40, y_sort=[ch["name"].title() for ch in top])
        if eps:
            with st.expander("Episode loglines (writers' one-line summaries)"):
                st.dataframe(pd.DataFrame([{"Episode": e["number"], "Logline": e["logline"]} for e in eps]),
                             hide_index=True, width="stretch", height=320)
