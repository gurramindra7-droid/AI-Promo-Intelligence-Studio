import json

import pandas as pd
import streamlit as st

from database import repositories as R
from database.database import session
from feedback import feedback_service as FS
from feedback import ranking_calibration as RC
from feedback.preference_learning import preferences
from frontend import ui


def render():
    p = ui.page_header("Feedback Center", "Editorial decisions, the reasons behind them, and what they change.")
    if not p:
        return
    pid = p["id"]
    with session() as con:
        kind = ui.ranking_switch(con, pid, "fb_kind")
        s = FS.summary(con, pid, kind)
        latest = R.latest_feedback(con, pid, kind)
        hist = R.feedback_history(con, pid)
        cal = RC.compute(con, pid, kind)
        pref = preferences(con, pid, kind)
        snaps = R.calibrations(con, pid)
        promos = {x["id"]: x for x in R.get_promos(con, pid, kind)}
    hist = [h for h in hist if h["promo_id"] in promos]

    c = st.columns(5)
    ui.kpi(c[0], f"{s['reviewed']} / {s['total_promos']}", "Reviewed", f"{s['pending']} pending")
    ui.kpi(c[1], s["approved"] if s["reviewed"] else None, "Approved")
    ui.kpi(c[2], s["needs_revision"] if s["reviewed"] else None, "Needs revision")
    ui.kpi(c[3], s["rejected"] if s["reviewed"] else None, "Rejected")
    ui.kpi(c[4], f"{s['approval_rate']:.0%}" if s["reviewed"] else None, "Approval rate",
           "share of reviewed promos" if s["reviewed"] else "no reviews yet")
    st.write("")

    if not s["reviewed"]:
        ui.empty_state("No reviews yet",
                       "Open a promo in Promo Discovery and choose Approve, Needs revision or Reject (with a reason). "
                       "Decisions appear here, and repeated rejection reasons can gently re-weight the ranking.")
        ui.link("promos", "Go to Promo Discovery")
    else:
        left, right = st.columns([1, 1.3], gap="large")
        with left, st.container(border=True):
            ui.section("Why editors reject", "latest decision per promo")
            if s["rejection_reasons"]:
                rr = pd.DataFrame({"Reason": list(s["rejection_reasons"]), "Promos": list(s["rejection_reasons"].values())})
                ui.bar_chart(rr, "Reason", "Promos", "Reason", "Promos", horizontal=True, height=max(140, 34 * len(rr)))
            else:
                st.caption("No rejections so far.")
        with right, st.container(border=True):
            ui.section("Latest decisions")
            rows = []
            for f in sorted(latest, key=lambda f: f["rank"] or 0):
                x = promos.get(f["promo_id"])
                if not x:
                    continue
                rows.append(f'<div class="row" style="grid-template-columns:34px 1fr auto"><div class="rk">#{x["rank"]}</div>'
                            f'<div><div class="q">{ui.esc(x["hook_text"])}</div><div class="m"><span class="cut">{ui.esc(ui.cut(x))}</span>'
                            f' &nbsp;{ui.esc(f.get("reason") or "")}{" · " + ui.esc(f["comment"]) if f.get("comment") else ""}</div></div>'
                            f'<div>{ui.tag(ui.DECISION_LABEL[f["decision"]], ui.DECISION_TONE[f["decision"]], True)}</div></div>')
            st.html("".join(rows))

    with st.container(border=True):
        ui.section("Ranking calibration", "transparent and conservative · never edits the original ranks")
        st.html(f'<div class="subtitle" style="margin-bottom:10px">A rule switches on only after ≥{cal["min_decisions"]} '
                f'reviews and ≥{cal["min_rejections"]} rejections citing the same reason on promos that share the feature. '
                f'Each active rule costs 10% of the score (25% at most). Calibrated ranks are shown beside the original.</div>')
        rules = "".join(
            f'<div class="row" style="grid-template-columns:1fr auto auto"><div><div class="q">{ui.esc(r["reason"])}</div>'
            f'<div class="m">applies to: {ui.esc(r["feature"])}</div></div><div class="m">{r["evidence"]} matching rejections</div>'
            f'<div>{ui.tag("Active · −10%" if r["active"] else "Inactive", "warn" if r["active"] else "", True)}</div></div>'
            for r in cal["rules"])
        st.html(rules)
        moved = [r for r in cal["rows"] if r["moved"] or r["applied"]]
        if moved:
            st.dataframe(pd.DataFrame(moved)[["rank", "calibrated_rank", "moved", "episode", "score", "calibrated_score",
                                              "applied", "decision"]], hide_index=True, width="stretch")
        else:
            st.caption(cal["note"])
        a, b = st.columns([1, 3], vertical_alignment="center")
        if a.button("Save audit snapshot", icon=":material/history:"):
            with session() as con:
                RC.save_snapshot(con, pid, kind)
            st.toast("Calibration snapshot saved", icon=":material/check:")
            st.rerun()
        b.caption(f"{len(snaps)} snapshot(s) saved" if snaps else "No snapshots yet.")
        if snaps:
            with st.expander("Audit trail"):
                st.dataframe(pd.DataFrame([{"Saved": x["created_at"], "Ranking": x["ranking_kind"],
                                            "Decisions": x["n_feedback"],
                                            "Active rules": ", ".join(r["rule"] for r in json.loads(x["rules_json"])["rules"]
                                                                      if r["active"]) or "none"} for x in snaps]),
                             hide_index=True, width="stretch")

    if s["reviewed"]:
        with st.container(border=True):
            ui.section("Approved vs rejected", pref["caveat"])
            if pref["averages"]:
                st.dataframe(pd.DataFrame(pref["averages"]).T.rename(index=ui.DECISION_LABEL).rename(columns=lambda c: c.replace("_", " ")),
                             width="stretch")
        with st.container(border=True):
            ui.section("Review history", f"{len(hist)} decisions")
            df = pd.DataFrame([{"When": h["created_at"].replace("T", " "), "Promo": f"#{promos[h['promo_id']]['rank']} "
                                f"{ui.cut(promos[h['promo_id']])}", "Decision": ui.DECISION_LABEL.get(h["decision"], h["decision"]),
                                "Reason": h["reason"] or "", "Comment": h["comment"] or ""} for h in hist])
            st.dataframe(df, hide_index=True, width="stretch")
            st.download_button("Download CSV", df.to_csv(index=False), file_name=f"feedback_{p['name']}.csv",
                               icon=":material/download:")
