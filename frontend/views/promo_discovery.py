import json

import pandas as pd
import streamlit as st

from common.settings import get_settings
from database import repositories as R
from database.database import session
from feedback import feedback_service as FS
from frontend import ui
from story_intelligence.narrative_analyzer import promo_context

SORTS = {"Rank": ("rank", False), "Score": ("score", True), "Hook": ("hook_score", True),
         "Cliffhanger": ("cliff_score", True), "Standalone": ("standalone_score", True), "Episode": ("episode", False)}
STATUS_TEXT = {"approve": "● Approved", "needs_revision": "◐ Revision", "reject": "✕ Rejected", None: "○ Pending"}


def render():
    p = ui.page_header("Promo Discovery", "Candidate list on the left, inspection panel on the right. Times come from the script.")
    if not p:
        return
    pid = p["id"]
    with session() as con:
        kinds = R.ranking_kinds(con, pid)
    if not kinds:
        ui.empty_state("No promos yet", "Process this project in Settings → Workflow to discover promos.")
        return

    # ---- toolbar ----
    with st.container(border=True):
        a, b, f = st.columns([1.5, 3, 1.1], vertical_alignment="bottom")
        with a, session() as con:
            kind = ui.ranking_switch(con, pid, "disc_kind")
        with session() as con:
            promos = R.get_promos(con, pid, kind)
            latest = {x["promo_id"]: x["decision"] for x in R.latest_feedback(con, pid, kind)}
        q = b.text_input("Search", placeholder="Search hook, cliffhanger or reason…", label_visibility="collapsed")
        sort = f.selectbox("Sort by", list(SORTS), label_visibility="collapsed", format_func=lambda k: f"Sort: {k}")
        c, d, e, g = st.columns([1, 1.4, 1.4, 2.6], vertical_alignment="bottom")
        ep = c.selectbox("Episode", ["All"] + sorted({x["episode"] for x in promos}))
        ty = d.selectbox("Moment type", ["All"] + sorted({x["archetype"] or "other" for x in promos}),
                         format_func=lambda t: t.replace("_", " ").capitalize() if t != "All" else t)
        status = e.selectbox("Review status", ["All", "Pending", "approve", "needs_revision", "reject"],
                             format_func=lambda s: ui.DECISION_LABEL.get(s, s))
        opts = {x["id"]: f"#{x['rank']}  {ui.cut(x)}" for x in promos}
        cmp_ids = g.multiselect("Compare (pick 2–3)", list(opts), format_func=opts.get, max_selections=3,
                                key=f"cmp_{kind}", placeholder="Pick promos to compare")

    def keep(x):
        text = f"{x['hook_text']} {x['cliff_text']} {x['why_it_works']}".lower()
        dec = latest.get(x["id"])
        return ((not q or q.lower() in text) and (ep == "All" or x["episode"] == ep)
                and (ty == "All" or (x["archetype"] or "other") == ty)
                and (status == "All" or (status == "Pending" and dec is None) or dec == status))
    key, desc = SORTS[sort]
    shown = sorted([x for x in promos if keep(x)],
                   key=lambda x: (x[key] is None, -(x[key] or 0) if desc else (x[key] or 0), x["rank"]))

    l, r = st.columns([3, 1], vertical_alignment="center")
    l.html(f'<div class="subtitle">{len(shown)} of {len(promos)} candidates · {ui.RANKING_LABEL.get(kind, kind)} ranking'
           + ((" · demo show, real pipeline run" if get_settings().demo else " · submitted with the take-home, reproduced unchanged")
              if kind == "original" else
              " · agent scores are on their own scale; compare order and verdicts, not numbers") + "</div>")
    if len(cmp_ids) >= 2 and r.button("Compare side by side", icon=":material/compare_arrows:", type="primary", width="stretch"):
        compare_dialog([x for x in promos if x["id"] in cmp_ids])

    if not shown:
        ui.empty_state("No promos match these filters", "Clear the search or set a filter back to All.")
        return

    # ---- master / detail ----
    sel_key = f"sel_{pid}_{kind}"
    if st.session_state.get(sel_key) not in {x["id"] for x in shown}:
        st.session_state[sel_key] = shown[0]["id"]
    left, right = st.columns([1.15, 1], gap="medium")
    with left, st.container(border=True):
        ui.section("Candidates", "select a row to inspect")
        df = pd.DataFrame([{
            "id": x["id"], "#": x["rank"], "Cut": ui.cut(x), "Type": (x["archetype"] or "other").replace("_", " "),
            "Hook": x["hook_score"], "Cliff": x["cliff_score"], "Stand.": x["standalone_score"],
            "Critic": x.get("verdict") or "—", "Score": x["score"], "Status": STATUS_TEXT.get(latest.get(x["id"]))}
            for x in shown])
        ev = st.dataframe(df, hide_index=True, width="stretch", height=min(640, 38 + 35 * len(df)),
                          on_select="rerun", selection_mode="single-row", key=f"tbl_{pid}_{kind}",
                          column_order=["#", "Cut", "Type", "Hook", "Cliff", "Stand.", "Critic", "Score", "Status"],
                          column_config={"#": st.column_config.NumberColumn(width="small"),
                                         "Score": st.column_config.NumberColumn(format="%.1f"),
                                         "Hook": st.column_config.NumberColumn(format="%.1f", width="small"),
                                         "Cliff": st.column_config.NumberColumn(format="%.1f", width="small"),
                                         "Stand.": st.column_config.NumberColumn(format="%.1f", width="small")})
        rows = (ev.selection.rows if ev and getattr(ev, "selection", None) else [])
        tbl_sel = int(df.iloc[rows[0]]["id"]) if rows else None
        if tbl_sel is not None and tbl_sel != st.session_state.get(f"last_tbl_{sel_key}"):
            st.session_state[f"last_tbl_{sel_key}"] = tbl_sel        # a new table click wins over the picker
            st.session_state[sel_key] = tbl_sel
    with right:
        ids = [x["id"] for x in shown]
        label = {x["id"]: f"#{x['rank']}  ·  {ui.cut(x)}  ·  {(x['archetype'] or 'other').replace('_', ' ')}" for x in shown}
        st.session_state[f"insp_{sel_key}"] = st.session_state[sel_key]

        def _pick():
            st.session_state[sel_key] = st.session_state[f"insp_{sel_key}"]
        st.selectbox("Inspect", ids, key=f"insp_{sel_key}", format_func=label.get, on_change=_pick,
                     help="Or select a row in the candidate table")
        inspect_panel(pid, st.session_state[sel_key], latest.get(st.session_state[sel_key]))


def inspect_panel(pid: int, promo_id: int, decision: str | None):
    with session() as con:
        x = R.get_promo(con, promo_id)
        evals = R.get_agent_evals(con, promo_id)
        ctx = promo_context(con, pid, x)
        hist = [h for h in R.feedback_history(con, pid) if h["promo_id"] == promo_id]
    with st.container(border=True, key="inspect"):
        st.html('<div class="eyebrow" style="margin-bottom:10px">Inspection</div>' + ui.promo_card_html(x, decision))
        t1, t2, t3, t4 = st.tabs(["Overview", "Script", f"Agents ({len(evals)})", "Review"])
        with t1:
            segs = json.loads(x.get("segments_json") or "[]")
            cut_rows = "".join(f'<div class="k">Segment {i}</div><div class="v"><span class="cut">Ep{s.get("ep", x["episode"])} '
                               f'{ui.fmt_t(s.get("ep_start", s["start"]))}–{ui.fmt_t(s.get("ep_end", s["end"]))}</span>'
                               f' &nbsp;<span class="mono" style="color:#777">{ui.esc(s["first_id"])} → {ui.esc(s["last_id"])}</span></div>'
                               for i, s in enumerate(segs, 1))
            people = ", ".join(f"{c['name'].title()} ({'introduced earlier' if c['introduced_before_clip'] else 'new here'})"
                               for c in ctx["characters"]) or "—"
            st.html(f'<div class="kv" style="grid-template-columns:120px 1fr">{cut_rows}'
                    f'<div class="k">Duration</div><div class="v">{round(x["duration"] or 0)} s</div>'
                    f'<div class="k">Why it works</div><div class="v">{ui.esc(x.get("why_it_works") or "—")}</div>'
                    f'<div class="k">Why this rank</div><div class="v" style="color:#B3B3B3">{ui.esc(x.get("why_rank") or "—")}</div>'
                    f'<div class="k">Risk</div><div class="v" style="color:#B3B3B3">{ui.esc(x.get("why_it_might_fail") or "—")}</div>'
                    f'<div class="k">Logline</div><div class="v">{ui.esc(ctx["episode_logline"] or "—")}</div>'
                    f'<div class="k">A stranger meets</div><div class="v">{ui.esc(people)}</div></div>')
        with t2:
            show_cam = st.toggle("Show camera directions", value=st.session_state.get("pref_camera", False), key=f"cam_{promo_id}")
            ui.script_lines(x, show_camera=show_cam)
        with t3:
            if not evals:
                st.caption("Agent reviews exist only for the multi-agent ranking.")
            for name, out in evals.items():
                st.html(f'<div class="sec"><span class="t">{ui.esc(name.replace("_", " "))}</span>'
                        f'<span class="c mono">{ui.esc(out.get("_model", ""))}</span></div>')
                rows = "".join(f'<div class="k">{ui.esc(k.replace("_", " ").capitalize())}</div><div class="v">'
                               f'{ui.esc(", ".join(map(str, v)) if isinstance(v, list) else v)}</div>'
                               for k, v in out.items() if k != "_model" and v not in ("", [], None))
                st.html(f'<div class="kv" style="grid-template-columns:150px 1fr;margin-bottom:16px">{rows}</div>')
        with t4:
            with st.form(f"rev_{promo_id}", border=False):
                dec = st.segmented_control("Decision", ["approve", "needs_revision", "reject"], default=decision or "approve",
                                           format_func=ui.DECISION_LABEL.get, required=True)
                reason = st.selectbox("Reason (required to reject)", ["—"] + list(FS.REJECTION_REASONS))
                comment = st.text_area("Comment", placeholder="Optional note for the editor team", height=80)
                if st.form_submit_button("Save review", type="primary"):
                    try:
                        with session() as con:
                            FS.submit(con, promo_id, dec, None if reason == "—" else reason, comment or None)
                        st.toast("Review saved", icon=":material/check:")
                        st.rerun()
                    except FS.FeedbackError as e:
                        st.error("Choose a reason to reject this promo." if "reason" in str(e) else str(e))
            if hist:
                st.caption("History")
                st.dataframe(pd.DataFrame(hist)[["decision", "reason", "comment", "created_at"]], hide_index=True, width="stretch")


@st.dialog("Compare promos", width="large")
def compare_dialog(items: list[dict]):
    cols = st.columns(len(items))
    for c, x in zip(cols, sorted(items, key=lambda i: i["rank"])):
        with c, st.container(border=True):
            st.html(f'<div class="pc-head"><span class="pc-rank">{x["rank"]:02d}</span><span class="cut">{ui.esc(ui.cut(x))}</span>'
                    f'</div><div class="pc-score" style="text-align:left;margin-top:10px"><div class="n">{ui.num(x["score"])}</div>'
                    f'<div class="u">score</div></div>'
                    f'<div class="meters" style="flex-direction:column;gap:8px">{ui.meter("Hook", x["hook_score"])}'
                    f'{ui.meter("Cliffhanger", x["cliff_score"])}{ui.meter("Standalone", x["standalone_score"])}</div>'
                    f'<div class="pc-line" style="grid-template-columns:1fr"><div class="k">Hook</div>'
                    f'<div class="t">“{ui.esc(x["hook_text"])}”</div><div class="k">Cut on</div>'
                    f'<div class="t">“{ui.esc(x["cliff_text"])}”</div><div class="k">Why this rank</div>'
                    f'<div class="t" style="color:#B3B3B3;font-size:.82rem">{ui.esc(x["why_rank"])}</div></div>')
            if x.get("verdict"):
                st.html(ui.tag(f"Critic: {x['verdict']}", ui.VERDICT_TONE.get(x["verdict"], ""), True))
