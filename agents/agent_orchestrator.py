"""Multi-agent promo evaluation.

    Screenplay timeline (original parser)  +  original line scores (original tagger, reused - not re-paid)
      -> shortlist: each show's top N% lines
      -> Hook agent  (re-judges shortlisted openings: score, type, reason, confidence)
      -> Cliffhanger agent (re-judges shortlisted endings)
      -> Candidate generator  (ORIGINAL src/candidates.py: 20-60 s, whole lines, one episode)
      -> Stranger agent (blind, per clip)
      -> Editorial critic (batches, spots repetition)
      -> Deterministic validation (every cut re-checked against the parser's timeline)
      -> Agent ranking  (stored as ranking_kind='agents'; the original ranking is never touched)

No agent ever writes a timestamp: agents return line ids / candidate keys only.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

import common.paths  # noqa: F401
from candidates import CUTTABLE, build_candidates  # noqa: E402  (original, unchanged)
from llm import load_config  # noqa: E402

from agents import cliffhanger_agent, editorial_critic_agent, hook_agent, stranger_agent
from agents.base import AgentConfigError, make_llm
from backend.services.import_service import cand_key, load_beats, load_timeline
from common.settings import get_settings
from database import repositories as R

VERDICT_FACTOR = {"approve": 1.0, "review": 0.85, "reject": 0.6}


def _chunks(xs: list, n: int):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def shortlist(lines: list[dict], key: str, tie: str, pct: float) -> list[dict]:
    pool = [l for l in lines if l["type"] in CUTTABLE]
    n = max(5, round(len(pool) * pct / 100))
    return sorted(pool, key=lambda l: (-l.get(key, 0), -l.get(tie, 0), l["start"]))[:n]


def validate_candidate(c: dict, by_id: dict[str, dict]) -> str | None:
    """Deterministic check: every segment's times are exactly the parser's line times, one episode, 20-60 s."""
    total = 0.0
    for s in c["segments"]:
        a, b = by_id.get(s["first_id"]), by_id.get(s["last_id"])
        if a is None or b is None:
            return f"unknown line id in {s}"
        if a["start"] != s["start"] or b["end"] != s["end"]:
            return f"time mismatch in {s['first_id']}..{s['last_id']}"
        if a["ep"] != b["ep"]:
            return "segment crosses an episode boundary"
        total += s["end"] - s["start"]
    if not 20 <= round(total, 1) <= 60:
        return f"duration {total:.1f}s outside 20-60 s"
    return None


def run_agents(con, project_id: int, show: str, episodes: list[int] | None = None, job_id: str | None = None,
               progress: Callable[[float, str], None] = lambda p, m: None, llms: dict | None = None) -> dict:
    st = get_settings().studio
    beats_file = load_beats(show)
    if not beats_file:
        raise AgentConfigError(f"No original line scores for '{show}'. Run the original pipeline first: "
                               f"python src/run.py --input <script>")
    tl = load_timeline(show)
    by_id = {l["id"]: l for l in tl["lines"]}
    L = [b for b in beats_file["beats"] if episodes is None or b["ep"] in episodes]
    if not L:
        raise ValueError(f"No lines for episodes {episodes}")
    readable = [l for l in L if l["type"] != "camera"]
    pos = {l["id"]: i for i, l in enumerate(readable)}

    llms = llms or {}
    llm_a = llms.get("agent") or make_llm("agent")
    llm_s = llms.get("stranger") or make_llm("stranger")
    llm_c = llms.get("critic") or make_llm("critic")
    notes: list[str] = []

    # 1-2. Hook + cliffhanger agents on the shortlist
    pct = st["shortlist_pct"]
    hooks_in, cliffs_in = shortlist(L, "hook", "cliff", pct), shortlist(L, "cliff", "hook", pct)
    hook_res: dict[str, dict] = {}
    for i, batch in enumerate(_chunks(hooks_in, st["agent_batch"])):
        progress(0.05 + 0.25 * i / max(1, len(hooks_in) / st["agent_batch"]), f"Hook agent: batch {i + 1}")
        ctx = {l["id"]: readable[max(0, pos[l["id"]] - 2):pos[l["id"]]] for l in batch if l["id"] in pos}
        for r in hook_agent.run(llm_a, batch, ctx):
            hook_res[r["line_id"]] = r
            R.upsert_line_score(con, project_id, r["line_id"], "hook", r["hook_score"], r["hook_type"],
                                r["reason"], r["confidence"], llm_a.calls[-1]["model"] if llm_a.calls else llm_a.model)
    cliff_res: dict[str, dict] = {}
    for i, batch in enumerate(_chunks(cliffs_in, st["agent_batch"])):
        progress(0.30 + 0.20 * i / max(1, len(cliffs_in) / st["agent_batch"]), f"Cliffhanger agent: batch {i + 1}")
        after = {l["id"]: readable[pos[l["id"]] + 1:pos[l["id"]] + 3] for l in batch if l["id"] in pos}
        for r in cliffhanger_agent.run(llm_a, batch, after):
            cliff_res[r["line_id"]] = r
            R.upsert_line_score(con, project_id, r["line_id"], "cliffhanger", r["cliffhanger_score"],
                                r["cliffhanger_type"], r["reason"], r["confidence"],
                                llm_a.calls[-1]["model"] if llm_a.calls else llm_a.model)

    # 3. Candidate generator = the ORIGINAL deterministic builder, fed the agents' scores
    agent_beats = [{**l, "hook": hook_res.get(l["id"], {}).get("hook_score", 0),
                    "cliff": cliff_res.get(l["id"], {}).get("cliffhanger_score", 0)} for l in L]
    promo_cfg = dict(load_config(common.paths.CONFIG)["promo"])
    promo_cfg["max_candidates"] = st["max_candidates"]
    promo_cfg["min_candidates"] = min(promo_cfg["min_candidates"], st["max_candidates"])
    progress(0.5, "Building candidate clips (code)")
    cands = build_candidates(agent_beats, promo_cfg)["candidates"]
    if not cands:
        raise ValueError("The agents' scores produced no 20-60 s candidate clips for these episodes.")

    # 4. Stranger agent, one blind call per clip
    progress(0.55, f"Stranger agent: {len(cands)} clips")
    with ThreadPoolExecutor(max_workers=2) as ex:
        stranger = list(ex.map(lambda c: stranger_agent.run(llm_s, c["lines"], c["segments"]), cands))

    # 5. Editorial critic in batches
    items = []
    for c, sres in zip(cands, stranger):
        h, cl = hook_res.get(c["hook_id"], {}), cliff_res.get(c["cliff_id"], {})
        items.append({"cand_key": cand_key(c["segments"]), "episode": c["segments"][0]["ep"],
                      "duration": c["duration"], "hook_score": h.get("hook_score", c["hook_score"]),
                      "hook_type": h.get("hook_type"), "cliff_score": cl.get("cliffhanger_score", c["cliff_score"]),
                      "cliff_type": cl.get("cliffhanger_type"), "standalone_score": sres["standalone_score"],
                      "text": stranger_agent.clip_text(c["lines"], c["segments"]), "cand": c, "stranger": sres,
                      "hook": h, "cliff": cl})
    others = [f"Ep{it['episode']}: {it['cand']['hook_text'][:60]} ... {it['cand']['cliff_text'][:50]}" for it in items]
    critic: dict[str, dict] = {}
    for i, batch in enumerate(_chunks(items, st["critic_batch"])):
        progress(0.75 + 0.15 * i / max(1, len(items) / st["critic_batch"]), f"Editorial critic: batch {i + 1}")
        critic.update(editorial_critic_agent.run(llm_c, batch, others))

    # 6. Deterministic validation + 7. ranking
    progress(0.92, "Validating cuts and ranking")
    scored = []
    for it in items:
        err = validate_candidate(it["cand"], by_id)
        if err:
            notes.append(f"dropped {it['cand_key']}: {err}")
            continue
        cv = critic.get(it["cand_key"], {"editorial_verdict": "review", "strengths": [], "weaknesses": [
            "critic gave no review"], "alternative_suggestion": "", "final_reasoning": ""})
        h, cl, s = it["hook_score"], it["cliff_score"], it["standalone_score"]
        base = (h + 1) * (cl + 1) * (s + 1) / 216 * 100
        f = VERDICT_FACTOR[cv["editorial_verdict"]]
        scored.append((round(base * f, 1), base, f, it, cv))
    scored.sort(key=lambda x: -x[0])

    keys = []
    for rank, (score, base, f, it, cv) in enumerate(scored, 1):
        c, sres = it["cand"], it["stranger"]
        works = "; ".join(x for x in [it["hook"].get("reason"), it["cliff"].get("reason")] + cv["strengths"] if x)
        fails = "; ".join(cv["weaknesses"] + [f"needs context: {m}" for m in sres["missing_context"]])
        segs = c["segments"]
        row = {
            "rank": rank, "episode": it["episode"], "start_s": segs[0]["start"], "end_s": segs[-1]["end"],
            "ep_start": segs[0].get("ep_start", segs[0]["start"]), "ep_end": segs[-1].get("ep_end", segs[-1]["end"]),
            "duration": c["duration"], "hook_id": c["hook_id"], "hook_text": c["hook_text"],
            "hook_score": it["hook_score"], "hook_type": it["hook_type"], "cliff_id": c["cliff_id"],
            "cliff_text": c["cliff_text"], "cliff_score": it["cliff_score"], "cliff_type": it["cliff_type"],
            "standalone_score": it["standalone_score"], "context_dependency": sres["context_dependency"],
            "archetype": c.get("archetype"), "score": score, "verdict": cv["editorial_verdict"],
            "why_it_works": works, "why_it_might_fail": fails,
            "why_rank": (f"hook {it['hook_score']} ({it['hook_type']}), cliffhanger {it['cliff_score']} "
                         f"({it['cliff_type']}), standalone {it['standalone_score']} -> base {base:.0f}; "
                         f"critic '{cv['editorial_verdict']}' x{f}"),
            "characters_json": json.dumps(sorted({l["speaker"] for l in c["lines"] if l.get("speaker")})),
            "segments_json": json.dumps(segs), "lines_json": json.dumps(c["lines"]),
        }
        pid = R.upsert_promo(con, project_id, "agents", it["cand_key"], row)
        R.upsert_agent_eval(con, pid, "stranger", sres, _model(llm_s))
        R.upsert_agent_eval(con, pid, "critic", cv, _model(llm_c))
        keys.append(it["cand_key"])
    R.delete_promos_not_in(con, project_id, "agents", keys)

    calls = llm_a.calls + ([] if llm_s is llm_a else llm_s.calls) + \
        ([] if llm_c in (llm_a, llm_s) else llm_c.calls)
    R.log_usage(con, job_id, project_id, calls)
    answered = {}
    for c in calls:
        answered[c["model"]] = answered.get(c["model"], 0) + 1
    progress(1.0, "Done")
    return {"episodes": sorted({l["ep"] for l in L}), "hook_shortlist": len(hooks_in),
            "cliff_shortlist": len(cliffs_in), "candidates": len(cands), "ranked": len(keys), "notes": notes,
            "calls": len(calls), "cached": sum(1 for c in calls if c.get("cached")), "answered_by": answered,
            "tokens": sum(c.get("prompt_tokens", 0) + c.get("completion_tokens", 0) for c in calls)}


def _model(llm) -> str:
    return llm.calls[-1]["model"] if getattr(llm, "calls", None) else llm.model
