"""AI Promo Intelligence Studio - Streamlit frontend.

    streamlit run frontend/app.py          (theme: .streamlit/config.toml)

The original single-page reviewer (app.py at the repo root) is unchanged and still works."""
import mimetypes
import sys
from pathlib import Path

# Static files (Three.js, intro, charts) are served from frontend/static by Streamlit, which takes the type
# from Python's mimetypes table. On Windows the registry can map .js to text/plain, which browsers refuse
# for ES modules, so register the correct type in this (server) process.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("font/woff2", ".woff2")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

st.set_page_config(page_title="AI Promo Intelligence Studio", page_icon=str(ROOT / "frontend" / "assets" / "icon.svg"),
                   layout="wide", initial_sidebar_state="auto")

from frontend import copilot_dock, intro, ui  # noqa: E402
from frontend.views import (dashboard, editorial_copilot, feedback_center, overview, promo_discovery,  # noqa: E402
                            settings_page, story_intelligence)

ui.setup()
intro.maybe_render()
st.logo(str(ui.ASSETS / "logo.svg"), size="large", icon_image=str(ui.ASSETS / "icon.svg"))

pages = {
    "Workspace": [
        st.Page(overview.render, title="Platform Overview", icon=":material/account_tree:", url_path="overview",
                default=True),
        st.Page(dashboard.render, title="Executive Dashboard", icon=":material/space_dashboard:", url_path="dashboard"),
        st.Page(promo_discovery.render, title="Promo Discovery", icon=":material/movie_filter:", url_path="promos"),
        st.Page(story_intelligence.render, title="Story Intelligence", icon=":material/hub:", url_path="story"),
        st.Page(editorial_copilot.render, title="Editorial Copilot", icon=":material/forum:", url_path="copilot"),
        st.Page(feedback_center.render, title="Feedback Center", icon=":material/fact_check:", url_path="feedback"),
    ],
    "System": [
        st.Page(settings_page.render, title="Settings", icon=":material/settings:", url_path="settings"),
    ],
}
st.session_state["_pages"] = {pg.url_path: pg for group in pages.values() for pg in group}
page = st.navigation(pages, expanded=True)
if page.url_path not in ("copilot",):                  # round 'Ask Studio' button on every other page
    proj = ui.current_project()
    if proj:
        copilot_dock.render(proj["id"])
page.run()
