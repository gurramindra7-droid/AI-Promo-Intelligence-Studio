from collections import Counter

import pandas as pd
import streamlit as st

from database import repositories as R
from database.database import session
from feedback.feedback_service import summary as fb_summary
from frontend import charts3d, ui


def _chart_card(title: str, caption: str, key: str, draw_3d, table: pd.DataFrame):
    """A chart card with a 3D view and an accessible table view of the same data."""
    with st.container(border=True):
        h1, h2 = st.columns([1.7, 1], vertical_alignment="top")
        h1.html(f'<div class="sec" style="display:block;margin-bottom:10px"><div class="t">{ui.esc(title)}</div>'
                f'<div class="c" style="margin-top:4px">{ui.esc(caption)}</div></div>')
        with h2, st.container(horizontal=True, horizontal_alignment="right"):
            view = st.segmented_control("View", ["Table", "3D"], default="Table", key=key, label_visibility="collapsed",
                                        required=True)
        if view == "Table":
            st.dataframe(table, hide_index=True, width="stretch", height=min(380, 38 + 35 * len(table)))
        else:
            draw_3d()


def render():
    p = ui.page_header("Executive Dashboard", "Where the show's promo shortlist stands today.")
    if not p:
        return
    pid = p["id"]
    with session() as con:
        eps = R.get_episodes(con, pid)
        kinds = R.ranking_kinds(con, pid)
        orig = R.get_promos(con, pid, "original") if "original" in kinds else []
        agents = R.get_promos(con, pid, "agents") if "agents" in kinds else []
        fb = fb_summary(con, pid)
        usage = R.usage_summary(con, pid)
        chars = R.get_characters(con, pid)
        jobs = R.list_jobs(con, pid, 5)

    blocks = sum(e["n_blocks"] or 0 for e in eps)
    st.html(f'<div class="eyebrow" style="margin:6px 0 14px">{ui.esc(p["show_title"])} &nbsp;·&nbsp; {len(eps)} episodes'
            f' &nbsp;·&nbsp; {blocks:,} script blocks</div>')
    c = st.columns(5)
    agent_eps = sorted({x["episode"] for x in agents})
    from common.settings import get_settings
    from backend.services.processing_service import from_upload
    submitted = not get_settings().demo and not from_upload(p.get("source_path") or "")
    ui.kpi(c[0], len(orig) or None, "Original pipeline promos",
           "submitted ranking, unchanged" if submitted else "pipeline ranking")
    ui.kpi(c[1], len(agents) or None, "Multi-agent promos",
           f"episodes {agent_eps[0]}–{agent_eps[-1]}" if agent_eps else "not run yet")
    ui.kpi(c[2], len(chars) or None, "Speaking characters", "from script speaker labels" if chars else "story not built yet")
    ui.kpi(c[3], f"{fb['reviewed']}/{fb['total_promos']}" if fb["total_promos"] else None, "Promos reviewed",
           f"{fb['pending']} pending" if fb["total_promos"] else "")
    ui.kpi(c[4], f"{fb['approval_rate']:.0%}" if fb["reviewed"] else None, "Approval rate",
           f"{fb['approved']} approved · {fb['rejected']} rejected" if fb["reviewed"] else "no reviews yet")
    st.write("")

    # ---- top 5 ----
    with st.container(border=True):
        h1, h2 = st.columns([2, 1.2], vertical_alignment="center")
        with h1:
            ui.section("Post first", "top 5 recommendations")
        with h2, session() as con:
            kind = ui.ranking_switch(con, pid, "dash_kind")
        top = (orig if kind == "original" else agents)[:5]
        if top:
            st.html("".join(ui.promo_row(x) for x in top))
            ui.link("promos", "Open Promo Discovery")
        else:
            ui.empty_state("No promos in this ranking", "Process the project in Settings → Workflow.")

    # ---- 3D: promos per episode ----
    if orig:
        cnt = Counter(x["episode"] for x in orig)
        best = {}
        for x in orig:
            best.setdefault(x["episode"], x)
        n = len(eps) or max(cnt)
        cats = list(range(1, n + 1))
        vals = [cnt.get(e, 0) for e in cats]
        tips = [[charts3d.tip(("", f"Episode {e}"), ("Promos", cnt.get(e, 0)),
                              *((("Best", f"#{best[e]['rank']} · {ui.cut(best[e])}"),) if e in best else ()))
                 for e in cats]]
        _chart_card("Promos per episode", f"original pipeline · {n} episodes", "v_eps",
                    lambda: charts3d.bars3d(cats, [{"name": "Promos", "values": vals}], "Episode", "Promos",
                                            height=400, label_every=5, tooltips=tips),
                    pd.DataFrame({"Episode": cats, "Promos": vals}).query("Promos > 0"))

    left = right = st.container()                 # full-width rows: category labels need the room
    with left:
        if orig:
            mt = Counter((x["archetype"] or "other") for x in orig)
            order = [k for k, _ in mt.most_common()]
            labels = [k.replace("_", " ") for k in order]
            share = {k: v / len(orig) for k, v in mt.items()}
            tips = [[charts3d.tip(("", lab.capitalize()), ("Promos", mt[k]), ("Share", f"{share[k]:.0%}"))
                     for k, lab in zip(order, labels)]]
            _chart_card("Moment types", "original pipeline", "v_types",
                        lambda: charts3d.bars3d(labels, [{"name": "Promos", "values": [mt[k] for k in order]}],
                                                "Moment type", "Promos", height=380, tooltips=tips),
                        pd.DataFrame({"Moment type": labels, "Promos": [mt[k] for k in order],
                                      "Share": [f"{share[k]:.0%}" for k in order]}))
    with right:
        if usage:
            df = pd.DataFrame(usage)
            by = df.groupby("task", as_index=False)[["calls", "cached", "prompt_tokens", "completion_tokens"]].sum()
            tasks = [t.replace("_", " ") for t in by.task]
            tips = [[charts3d.tip(("", t), ("Prompt tokens", f"{int(pt):,}"), ("Calls", int(cl)), ("Cached", int(ca)))
                     for t, pt, cl, ca in zip(tasks, by.prompt_tokens, by.calls, by.cached)],
                    [charts3d.tip(("", t), ("Completion tokens", f"{int(ct):,}"), ("Calls", int(cl)))
                     for t, ct, cl in zip(tasks, by.completion_tokens, by.calls)]]
            _chart_card("Studio AI usage", "tokens by task · front row prompt, back row completion", "v_usage",
                        lambda: charts3d.bars3d(tasks, [{"name": "Prompt", "values": [int(v) for v in by.prompt_tokens]},
                                                        {"name": "Completion", "values": [int(v) for v in by.completion_tokens]}],
                                                "Task", "Tokens", height=400, tooltips=tips),
                        by.rename(columns={"task": "Task", "calls": "Calls", "cached": "Cached",
                                           "prompt_tokens": "Prompt tokens", "completion_tokens": "Completion tokens"}))
            st.caption(f"{int(by.calls.sum())} studio calls recorded · models: "
                       + ", ".join(sorted(m.split('/')[-1] for m in df.model.unique()))
                       + ". The original pipeline's usage is in outputs/run_log_<show>.json.")
        else:
            with st.container(border=True):
                ui.section("Studio AI usage")
                ui.empty_state("No studio AI calls yet", "Agent, story and copilot runs are logged here with model and tokens.")

    if jobs:
        with st.container(border=True):
            ui.section("Recent processing jobs")
            st.dataframe(pd.DataFrame(jobs)[["kind", "status", "progress", "message", "updated_at"]], hide_index=True,
                         width="stretch", column_config={
                             "kind": "Job", "status": "Status", "message": "Last message", "updated_at": "Updated",
                             "progress": st.column_config.ProgressColumn("Progress", min_value=0, max_value=1, format="percent")})
