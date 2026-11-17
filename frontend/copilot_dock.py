"""'Ask Studio' - the copilot as a round floating button (bottom-right of every workspace page) that opens a
full-height drawer on the right. Same grounded backend and the SAME conversation as the Editorial Copilot
page (st.session_state["chat_<project id>"])."""
from __future__ import annotations

import streamlit as st

from common.settings import get_settings
from copilot.assistant import chat
from database.database import session
from frontend import ui

SUGGESTED = ["Find the strongest promotional moments", "Which promos depend heavily on previous episodes?",
             "Explain promo #1", "Compare promos 1 and 2"]


def render(pid: int) -> None:
    with st.container(key="fab"):
        if st.button("", key="fab_btn", icon=":material/forum:", help="Ask Studio - the editorial copilot"):
            drawer(pid)


@st.dialog("Ask Studio", position="right", width="medium")
def drawer(pid: int) -> None:
    key = f"chat_{pid}"
    st.session_state.setdefault(key, {"session_id": None, "turns": []})
    state = st.session_state[key]
    ai = get_settings().ai_allowed
    st.html(f'<div class="subtitle" style="margin-top:-6px">Answers come only from this project\'s data and list the promos '
            f'they used. {ui.tag("AI" if ai else "Offline mode", "strong" if ai else "")}</div>')

    def _ask(text: str):
        st.session_state["_dr_q"] = (text or "").strip()

    def _submit():
        _ask(st.session_state.get("_dr_text", ""))
        st.session_state["_dr_text"] = ""

    question = st.session_state.pop("_dr_q", "")
    if question:                                   # answer first, so the panel below is already up to date
        with st.spinner("Looking it up…"), session() as con:
            r = chat(con, pid, question, state["session_id"], use_llm=ai)
        state["session_id"] = r["session_id"]
        state["turns"].append({"q": question, **r})

    with st.form("drawer_form", border=False):
        st.text_input("Question", key="_dr_text", placeholder="Ask about promos, episodes, characters…",
                      label_visibility="collapsed")
        st.form_submit_button("Ask", icon=":material/arrow_upward:", type="primary", width="stretch", on_click=_submit)
    if not state["turns"]:
        st.caption("Try one of these")
        for i, s in enumerate(SUGGESTED):
            st.button(s, key=f"dr_sg{i}", width="stretch", on_click=_ask, args=(s,))

    for t in reversed(state["turns"][-6:]):           # newest first
        st.html(f'<div class="dock-q">{ui.esc(t["q"])}</div>')
        st.markdown(t["answer"])
        data = t.get("data") or {}
        promos = data.get("promos") or ([data["promo"]] if data.get("promo") else [])
        if promos:
            st.html('<div class="dock-src">' + "".join(
                f'<span class="cut">#{c["rank"]} {ui.esc(c["cut"])}</span> ' for c in promos[:5]) + "</div>")
        st.divider()
    ui.link("copilot", "Open the full Editorial Copilot page", ":material/open_in_full:")
