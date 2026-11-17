"""
app.py - the promo editor's screen (human in the loop).

    streamlit run app.py

Two modes:
  1. Review results : pick a show already processed (outputs/ranked_*.json), see each promo as
                      a card, WATCH the clip (YouTube sources play at the exact start/end),
                      and Approve / Reject with a note. Decisions are saved to
                      outputs/feedback_<show>.json - the AI suggests, the editor decides.
  2. Run new script : upload a script file (YouTube transcript copy, screenplay, SRT...) and
                      run the whole pipeline on it. Needs an API key in .env (or Streamlit secrets).
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from adapter import fmt_time        # noqa: E402
from llm import load_config         # noqa: E402

OUT = ROOT / "outputs"
UPLOADS = ROOT / "data" / "uploads"   # data/ is git-ignored: uploaded scripts stay private

st.set_page_config(page_title="AI Promo Finder", page_icon="🎬", layout="wide")


# ---------- helpers ----------

def youtube_url(meta: dict) -> str | None:
    m = re.search(r"(https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w\-]+)", meta.get("source", ""))
    return m.group(1) if m else None


def load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def feedback_path(show: str) -> Path:
    return OUT / f"feedback_{show}.json"


def load_feedback(show: str) -> dict:
    p = feedback_path(show)
    return load_json(p) if p.exists() else {}


def save_feedback(show: str, fb: dict) -> None:
    feedback_path(show).write_text(json.dumps(fb, ensure_ascii=False, indent=1), encoding="utf-8")


def cut_label(s: dict) -> str:
    return f"Ep{s.get('ep', 1)} {fmt_time(s.get('ep_start', s['start']))}-{fmt_time(s.get('ep_end', s['end']))}"


# ---------- sidebar ----------

st.sidebar.title("🎬 AI Promo Finder")
st.sidebar.caption("Ranked, ready-to-cut promos from microdrama scripts")
mode = st.sidebar.radio("Mode", ["Review results", "Run on a new script"])


# ---------- mode 2: run the pipeline on an uploaded script ----------

if mode == "Run on a new script":
    st.header("Run on a new script")
    st.write("Upload a timestamped script: a YouTube transcript copy, a screenplay "
             "(`[00:12] NAME: line`), or an SRT/VTT subtitle file. One file = one show.")
    cfg = load_config(ROOT / "config.yaml")
    model = st.text_input("Model (LiteLLM name)", cfg["llm"]["model"],
                          help="Swap the model here, e.g. gemini/gemini-3.8-flash or openai/gpt-4.1")
    up = st.file_uploader("Script file", type=["txt", "srt", "vtt", "md"])
    if up and st.button("Find promos", type="primary"):
        UPLOADS.mkdir(parents=True, exist_ok=True)
        path = UPLOADS / up.name
        path.write_bytes(up.getvalue())
        from run import run_one   # imported here: only needed in this mode
        with st.status(f"Running the pipeline on {up.name} (a few minutes on free tiers)...", expanded=True) as status:
            t0 = time.time()
            try:
                log = run_one(path.stem, [path], cfg, str(ROOT / "config.yaml"),
                              model if model != cfg["llm"]["model"] else None)
            except Exception as e:   # show the error instead of a blank page
                status.update(label="Failed", state="error")
                st.error(f"{type(e).__name__}: {e}")
                st.stop()
            status.update(label=f"Done in {time.time() - t0:.0f}s", state="complete")
        if "error" in log:
            st.error(log["error"])
        else:
            st.success(f"{log['candidates']} promos ranked. Switch to **Review results** and pick "
                       f"**{path.stem}** to see them.")
    st.stop()


# ---------- mode 1: review results ----------

shows = sorted(p.stem.removeprefix("ranked_") for p in OUT.glob("ranked_*.json"))
if not shows:
    st.info("No results yet. Run `python src/run.py --input <script>` or use **Run on a new script**.")
    st.stop()

show = st.sidebar.selectbox("Show", shows)
data = load_json(OUT / f"ranked_{show}.json")
meta, promos = data["meta"], data["promos"]
run_log_p = OUT / f"run_log_{show}.json"
run_log = load_json(run_log_p) if run_log_p.exists() else {}
yt = youtube_url(meta)

st.sidebar.divider()
only_top = st.sidebar.checkbox("Only the top list", value=False)
kinds = st.sidebar.multiselect("Clip kind", ["single", "joined"], default=["single", "joined"])
show_video = st.sidebar.checkbox("Show video players", value=bool(yt), disabled=not yt,
                                  help="Only for YouTube sources (times map 1:1 to the video)")
fb = load_feedback(show)

# header + run summary
st.title(meta.get("show", show))
cols = st.columns(5)
cols[0].metric("Promos", len(promos))
cols[1].metric("Script length", fmt_time(meta.get("duration_seconds", 0)))
if run_log:
    u = run_log.get("usage", {})
    cols[2].metric("AI calls", u.get("calls_total", "-"))
    cached = u.get("calls_total") and u.get("calls_cached") == u.get("calls_total")
    cols[3].metric("Last run", "cached" if cached else f"{run_log.get('seconds_total', 0):.0f}s",
                   help="'cached' = every AI answer was reused from an earlier run (free, instant)")
    cols[4].metric("Approved", sum(1 for v in fb.values() if v.get("verdict") == "approve"))
    st.caption(f"Model: `{run_log.get('model')}` · format: `{meta.get('format')}` · "
               f"episodes: {len(meta.get('episodes', [1]))} · joins allowed: {run_log.get('allow_joins', '?')} · "
               f"source: {meta.get('source', meta.get('source_file', ''))}")
st.info("Times are **episode + time in that episode's script** (for a YouTube compilation: the video time). "
        "The AI suggests; you approve or reject. Decisions are saved for the next run.", icon="✂️")

# cards
for p in promos:
    if only_top and not p.get("in_top"):
        continue
    if p["kind"] not in kinds:
        continue
    cid = p["cand_id"]
    verdict = fb.get(cid, {}).get("verdict")
    badge = {"approve": "✅ approved", "reject": "❌ rejected"}.get(verdict, "")
    segs = " + ".join(cut_label(s) for s in p["segments"])
    with st.container(border=True):
        top = st.columns([3, 1])
        top[0].subheader(f"#{p['rank']} · {segs}")
        top[0].caption(f"{p['archetype']} · {p['kind']} · {p['duration']:.0f}s · score {p['score']} {badge}")
        left, right = st.columns([3, 2]) if show_video else (st.container(), None)
        with left:
            st.markdown(f"**Hook (first 3s):** “{p['hook_text']}”")
            st.markdown(f"**Cliffhanger (last line):** “{p['cliff_text']}”")
            st.markdown(f"**Why it works:** {p['why_it_works']}")
            with st.expander("Why this rank · stranger test · full lines"):
                st.write(f"**Score:** {p['score_parts']}")
                cold = p.get("cold", {})
                st.write(f"**A stranger saw:** {cold.get('what_happens', '')}")
                if cold.get("question_left"):
                    st.write(f"**…and wants to know:** {cold['question_left']}")
                if cold.get("confusing"):
                    st.write("**Confused by:** " + "; ".join(cold["confusing"]))
                st.write(f"Stranger scores - standalone {cold.get('standalone')}/5, "
                         f"hook {cold.get('hook_3s')}/5, want next {cold.get('want_next')}/5")
                for l in p.get("lines", []):
                    who = f"**{l['speaker']}:** " if l.get("speaker") else ""
                    tag = "*(action)* " if l["type"] == "action" else ""
                    st.markdown(f"`{l['id']}` {tag}{who}{l['text']}")
        if show_video and right is not None:
            with right:
                for s in p["segments"]:
                    st.video(yt, start_time=int(s["start"]), end_time=int(s["end"]) + 1)
        b = st.columns([1, 1, 2])
        note = b[2].text_input("Note", fb.get(cid, {}).get("note", ""), key=f"note_{show}_{cid}",
                               label_visibility="collapsed", placeholder="Optional note (why?)")
        for col, (label, v) in zip(b[:2], [("✅ Approve", "approve"), ("❌ Reject", "reject")]):
            if col.button(label, key=f"{v}_{show}_{cid}", type="primary" if verdict == v else "secondary"):
                fb[cid] = {"verdict": v, "note": note, "rank": p["rank"], "cut": segs,
                           "at": datetime.now().isoformat(timespec="seconds")}
                save_feedback(show, fb)
                st.rerun()

if fb:
    st.sidebar.download_button("Download my decisions (JSON)", json.dumps(fb, indent=1),
                               file_name=f"feedback_{show}.json")
