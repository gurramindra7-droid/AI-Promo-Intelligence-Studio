"""Five-second cinematic introduction (Three.js, monochrome).

The scene lives in frontend/static/js/intro3d.js and is served locally from /app/static/ (no CDN).
This module only injects one <script type="module" src=...> tag through st.html - an empty script with a
src attribute, so Streamlit's DOMPurify sanitiser keeps it.

  - shown once per browser: localStorage key 'apis.intro.v2'
  - Settings -> Appearance & intro -> "Replay introduction", or open /?intro=1
  - Skip button / Esc; prefers-reduced-motion -> one composed still frame
  - no WebGL or Three.js -> CSS fallback; any error removes the overlay, the app always loads
"""
from __future__ import annotations

import uuid

import streamlit as st

KEY = "apis.intro.v2"
SCRIPT_URL = "app/static/js/intro3d.js"   # relative: Streamlit Cloud serves the app under /~/+/


def tag(force: bool) -> str:
    # a fresh nonce per render: the module runs once per URL, and a re-mounted element can never replay
    return f'<script type="module" src="{SCRIPT_URL}?force={1 if force else 0}&n={uuid.uuid4().hex[:12]}"></script>'


def render(force: bool = False) -> None:
    with st.container(key="intro_host"):
        st.html(tag(force), unsafe_allow_javascript=True)


def maybe_render() -> None:
    """Called on every app run; injects at most once per browser session (plus on explicit replay)."""
    if st.query_params.get("intro") == "1":
        st.query_params.pop("intro")
        st.session_state.replay_intro = True
    if st.session_state.pop("replay_intro", False):
        render(force=True)
        st.session_state.intro_checked = True
    elif not st.session_state.get("intro_checked"):
        render(force=False)
        st.session_state.intro_checked = True
