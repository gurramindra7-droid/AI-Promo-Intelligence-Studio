"""Load the ORIGINAL pipeline's saved results (outputs/*.json) into the studio database.
Read-only on the pipeline side: no AI calls, no files changed. The original 30 promos land
as ranking_kind='original' exactly as ranked by src/ranker.py."""
from __future__ import annotations

import json
from pathlib import Path

from common.paths import OUTPUTS
from database import repositories as R


def cand_key(segments: list[dict]) -> str:
    return "+".join(f"{s['first_id']}..{s['last_id']}" for s in segments)


def speakers(lines: list[dict]) -> list[str]:
    return sorted({l["speaker"] for l in lines if l.get("speaker")})


def promo_row(p: dict, rank: int) -> dict:
    segs = p["segments"]
    cold = p.get("cold", {})
    confusing = cold.get("confusing") or []
    return {
        "rank": rank,
        "episode": segs[0].get("ep", 1),
        "start_s": segs[0]["start"], "end_s": segs[-1]["end"],
        "ep_start": segs[0].get("ep_start", segs[0]["start"]), "ep_end": segs[-1].get("ep_end", segs[-1]["end"]),
        "duration": p["duration"],
        "hook_id": p["hook_id"], "hook_text": p["hook_text"], "hook_score": p.get("hook_score"),
        "cliff_id": p["cliff_id"], "cliff_text": p["cliff_text"], "cliff_score": p.get("cliff_score"),
        "standalone_score": cold.get("standalone"),
        "archetype": p.get("archetype"),
        "score": p.get("score", p.get("pre_score")),
        "why_it_works": p.get("why_it_works", ""),
        "why_it_might_fail": ("A stranger was confused by: " + "; ".join(confusing)) if confusing else "",
        "why_rank": p.get("score_parts", ""),
        "characters_json": json.dumps(speakers(p.get("lines", []))),
        "segments_json": json.dumps(segs),
        "lines_json": json.dumps(p.get("lines", [])),
    }


def import_show(con, show: str, outputs_dir: Path = OUTPUTS) -> dict:
    """show = output name, e.g. 'the_last_reel'. Returns counts."""
    tl_p, rk_p = outputs_dir / f"timeline_{show}.json", outputs_dir / f"ranked_{show}.json"
    if not tl_p.exists() or not rk_p.exists():
        raise FileNotFoundError(f"No pipeline outputs for '{show}' in {outputs_dir}. Run: python src/run.py --input <script>")
    tl = json.loads(tl_p.read_text(encoding="utf-8"))
    ranked = json.loads(rk_p.read_text(encoding="utf-8"))
    meta = tl["meta"]
    prev = R.get_project(con, show)
    pid = R.upsert_project(con, show, meta.get("show", show), (prev or {}).get("source_path") or meta.get("source_file", ""),
                           {k: meta.get(k) for k in ("format", "duration_seconds", "counts", "episodes")})
    info = meta.get("episodes_info", {})
    lines = tl["lines"]
    for ep in meta.get("episodes", [1]):
        el = [l for l in lines if l["ep"] == ep]
        R.upsert_episode(con, pid, ep, logline=info.get(str(ep), {}).get("logline", ""),
                         duration_s=max((l.get("ep_end", l["end"]) for l in el), default=0),
                         n_blocks=len(el), n_dialogue=sum(l["type"] == "dialogue" for l in el),
                         n_action=sum(l["type"] == "action" for l in el))
    keys = []
    for p in ranked["promos"]:
        k = cand_key(p["segments"]); keys.append(k)
        R.upsert_promo(con, pid, "original", k, promo_row(p, p["rank"]))
    R.delete_promos_not_in(con, pid, "original", keys)
    return {"project_id": pid, "episodes": len(meta.get("episodes", [1])), "blocks": len(lines),
            "promos": len(keys)}


def available_shows(outputs_dir: Path = OUTPUTS) -> list[str]:
    return sorted(p.stem.removeprefix("ranked_") for p in outputs_dir.glob("ranked_*.json"))


def load_timeline(show: str, outputs_dir: Path = OUTPUTS) -> dict:
    return json.loads((outputs_dir / f"timeline_{show}.json").read_text(encoding="utf-8"))


def load_beats(show: str, outputs_dir: Path = OUTPUTS) -> dict | None:
    p = outputs_dir / f"beats_{show}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
