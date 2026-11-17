"""Custom input: create a project from your own scripts and run the real backend pipeline on it.

Opened from the project picker in the top bar ("+ New project - custom input"). Files are saved under
data/uploads/<name>/ and processed by the ORIGINAL pipeline (parse -> AI tagging -> candidates ->
stranger test -> ranking), then imported and given a character map. Progress is read live from the job
table. On the public demo this works only when the owner has enabled an AI key; limits apply."""
from __future__ import annotations

import json
import time

import streamlit as st

from backend.services import processing_service as PS
from common.settings import get_settings
from database import repositories as R
from database.database import session
from frontend import ui

EXAMPLE = """EPISODE 1: The Contract
[00:00] SCENE 1 - INT. OFFICE - NIGHT
[00:02] (Maya slams a contract on the desk)
[00:05] MAYA: You lied to me about everything.
[00:09] ETHAN: Sign it, or your brother loses his job tomorrow."""


@st.dialog("New project - custom input", width="large")
def dialog() -> None:
    s = get_settings()
    jid = st.session_state.get("np_job")
    if jid:
        _progress(jid)
        return
    st.html('<div class="subtitle" style="margin-top:-4px">Upload the script or subtitles of any microdrama. The real '
            'backend runs the full pipeline and ranks its promos. Times always come from your file.</div>')
    if not s.ai_allowed:
        st.warning(PS.DEMO_MSG + " The bundled demo show still shows every feature with real saved results.",
                   icon=":material/lock:")
    name = st.text_input("Project name", placeholder="e.g. my_new_show (letters, digits, _)")
    t1, t2 = st.tabs(["Upload files", "Paste script"])
    with t1:
        files = st.file_uploader("Script or subtitle files: one file, or one per episode", type=["txt", "srt", "vtt", "md"],
                                 accept_multiple_files=True)
    with t2:
        pasted = st.text_area("Script text", height=180, placeholder=EXAMPLE)
    with st.expander("Which inputs work?"):
        st.markdown(
            "- **Screenplays** in the input-pack format (EPISODE LOGLINE, SCENE blocks, Start/End times)\n"
            "- **Timestamped scripts** like the example in the paste box (`[mm:ss] SPEAKER: line`, `ACTION:` notes)\n"
            "- **Subtitles** `.srt` / `.vtt`, and transcripts copied from YouTube\n"
            "- **Video files are not analysed directly.** Upload the video's script or subtitles instead.\n"
            f"- Public demo limits: up to {PS.MAX_UPLOAD_FILES} files and {PS.MAX_UPLOAD_BYTES // 1000} KB per project, "
            "one analysis at a time.")
    payload = [{"filename": f.name, "content": f.getvalue().decode("utf-8", errors="replace")} for f in files or []]
    if (pasted or "").strip():
        payload.append({"filename": "pasted_script.txt", "content": pasted})
    ready = bool(name.strip()) and bool(payload) and s.ai_allowed
    if st.button("Analyze", type="primary", icon=":material/play_arrow:", disabled=not ready, width="stretch"):
        try:
            with session() as con:
                r = PS.create_project(con, name, name, payload)
                st.session_state["np_job"] = PS.start(con, r["project_id"], "pipeline")
                st.session_state["np_name"] = r["name"]
            st.rerun(scope="fragment")
        except (ValueError, LookupError) as e:
            st.error(str(e))


def _progress(jid: str) -> None:
    with session() as con:
        j = R.get_job(con, jid)
    if not j:
        st.error("Job not found.")
        return
    name = st.session_state.get("np_name", "")
    st.html(f'<div class="eyebrow">Analyzing · {ui.esc(name)}</div>')
    st.progress(float(j["progress"] or 0), text=j["message"] or j["status"])
    st.caption("Steps: parse your file (code) → AI scores every line → build 20–60 s clips (code) → blind stranger "
               "test (AI) → rank (code) → character map (code). Usually 1–3 minutes.")
    if j["status"] == "completed":
        res = json.loads(j["result_json"] or "{}")
        imp, pipe = res.get("import", {}), res.get("pipeline", {})
        st.success(f"Done: {imp.get('promos', 0)} promos from {imp.get('episodes', 0)} episode(s), "
                   f"{imp.get('blocks', 0)} script lines · {pipe.get('calls', 0)} AI calls in {pipe.get('seconds', 0)} s.")
        if st.button("Open the dashboard", type="primary", icon=":material/space_dashboard:"):
            st.session_state["_project"] = name
            st.session_state.pop("np_job", None)
            st.rerun()
    elif j["status"] == "failed":
        st.error(f"The analysis failed: {j['message']}")
        if st.button("Try again"):
            st.session_state.pop("np_job", None)
            st.rerun(scope="fragment")
    else:                                    # still running: redraw the whole window in 2 s
        time.sleep(2)
        st.rerun(scope="fragment")
