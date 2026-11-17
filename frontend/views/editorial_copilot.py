import json
import os

import streamlit as st

from common.settings import get_settings
from copilot.assistant import chat
from database import repositories as R
from database.database import session
from frontend import ui

SUGGESTED = ["Find the strongest promotional moments", "Show the best revenge-related promos",
             "Which promos depend heavily on previous episodes?", "Explain promo #1",
             "Compare promos 1 and 2", "How is the editor feedback going?"]
TOOL_LABEL = {"get_top_ranked_promos": "Top-ranked promos", "search_promos": "Promo search",
              "get_episode_details": "Episode details", "get_character_episodes": "Character lookup",
              "compare_promos": "Promo comparison", "explain_promo": "Rank explanation",
              "promos_by_context_dependency": "Context-dependency check", "get_feedback_summary": "Feedback summary"}


def _load_turns(session_id: str) -> list[dict]:
    with session() as con:
        msgs = R.get_messages(con, session_id, limit=60)
    turns, q = [], None
    for m in msgs:
        if m["role"] == "user":
            q = m["content"]
        else:
            t = json.loads(m.get("tool_calls_json") or "{}")
            turns.append({"q": q, "answer": m["content"], "tool": t.get("tool"), "args": t.get("args", {}),
                          "data": t.get("data") or {}, "mode": "saved", "note": ""})
    return turns


def render():
    p = ui.page_header("Editorial Copilot", "Ask about promos, episodes and characters. Answers come only from this project's data.")
    if not p:
        return
    pid = p["id"]
    key = f"chat_{pid}"
    st.session_state.setdefault(key, {"session_id": None, "turns": []})
    state = st.session_state[key]
    model = get_settings().model_for("copilot") or "config.yaml llm.model"
    has_key = get_settings().ai_allowed

    side, main = st.columns([1, 2.6], gap="large")
    clicked = None
    with side:
        with st.container(border=True):
            ui.section("Conversations")
            if st.button("New conversation", icon=":material/add:", width="stretch"):
                st.session_state[key] = {"session_id": None, "turns": []}
                st.rerun()
            with session() as con:
                sessions = R.list_chat_sessions(con, pid, 12)
            for s in sessions:
                label = (s["title"] or "Conversation")[:46]
                active = s["session_id"] == state["session_id"]
                if st.button(label, key=f"s_{s['session_id']}", width="stretch", type="primary" if active else "tertiary",
                             help=f"{s['n'] // 2} questions · {s['last'][:16].replace('T', ' ')}"):
                    st.session_state[key] = {"session_id": s["session_id"], "turns": _load_turns(s["session_id"])}
                    st.rerun()
            if not sessions:
                st.caption("No conversations yet.")
        with st.container(border=True):
            ui.section("Suggested questions")
            for i, s in enumerate(SUGGESTED):
                if st.button(s, key=f"sg{i}", width="stretch", type="secondary"):
                    clicked = s
        with st.container(border=True):
            ui.section("Answering mode")
            use_llm = st.toggle("Use AI", value=has_key, disabled=not has_key,
                                help="Off: rule-based routing and a plain summary of the same data (no API call).")
            st.html(f'<div class="kv" style="grid-template-columns:70px 1fr;font-size:.8rem">'
                    f'<div class="k">Model</div><div class="v mono">{ui.esc(model)}</div>'
                    f'<div class="k">Key</div><div class="v">{"available" if has_key else ("off in the public demo" if get_settings().demo else "missing: offline mode only")}</div>'
                    f'<div class="k">Tools</div><div class="v">8 fixed read-only tools · no SQL, no code</div></div>')

    with main:
        box = st.container(height=600, border=True)
        with box:
            if not state["turns"]:
                st.html('<div class="empty" style="margin-top:40px"><div class="t">Ask the copilot</div><div class="b">'
                        'It picks one of eight read-only tools, runs it on the database, and answers only from what the tool '
                        'returned, citing promos as #rank (Ep m:ss–m:ss). The data it used is listed under every answer.'
                        '</div></div>')
            for t in state["turns"]:
                _turn(t)
        msg = st.chat_input("Ask about promos, episodes, characters or feedback…") or clicked
        if msg:
            with box:
                with st.chat_message("user", avatar=":material/person:"):
                    st.markdown(msg)
                with st.chat_message("assistant", avatar=":material/edit_note:"), st.spinner("Looking it up…"):
                    with session() as con:
                        r = chat(con, pid, msg, state["session_id"], use_llm=use_llm)
            state["session_id"] = r["session_id"]
            state["turns"].append({"q": msg, **r})
            st.rerun()


def _turn(t: dict):
    with st.chat_message("user", avatar=":material/person:"):
        st.markdown(t["q"] or "")
    with st.chat_message("assistant", avatar=":material/edit_note:"):
        st.markdown(t["answer"])
        mode = {"llm": "AI answer", "offline": "Offline answer (rule-based)", "saved": "Saved answer"}.get(t["mode"], t["mode"])
        st.html(f'<div style="margin-top:6px">{ui.tag(mode, "accent" if t["mode"] == "llm" else "")}'
                f'{ui.tag("Source: " + TOOL_LABEL.get(t["tool"], t["tool"] or "—"))}'
                + (f'<span class="subtitle" style="font-size:.76rem">{ui.esc(t["note"])}</span>' if t.get("note") else "")
                + "</div>")
        data = t.get("data") or {}
        promos = data.get("promos") or ([data["promo"]] if data.get("promo") else [])
        if promos:
            rows = "".join(
                f'<div class="row"><div class="rk">#{c["rank"]}</div><div><div class="q">{ui.esc(c.get("hook") or "")}</div>'
                f'<div class="m"><span class="cut">{ui.esc(c["cut"])}</span> &nbsp;{ui.esc(ui.RANKING_LABEL.get(c["ranking"], c["ranking"]))}'
                f' · {ui.esc((c.get("moment_type") or "").replace("_", " "))}</div></div><div class="sc">{ui.num(c["score"])}</div></div>'
                for c in promos[:6])
            with st.expander(f"Promos referenced ({len(promos)})"):
                st.html(rows)
