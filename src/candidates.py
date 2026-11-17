"""
candidates.py - Step 4: turn scored lines into possible promos. 100% CODE, no AI.

Input : beats from tagger.py (every line has hook / cliff / needs_context scores)
Output: candidate promos, each = 1 or more segments of whole lines, in order.

Rules (from the brief + config.yaml):
  1. START on a strong hook line (hook >= hook_threshold). The promo starts exactly at
     that line, so the hook lands in the first 3 seconds.
  2. END on a strong cliffhanger line (cliff >= cliff_threshold). We cut at the END of
     that line, so the unresolved moment is the last thing the viewer sees.
  3. Total length 20-60 seconds.
  4. Cuts always snap to line boundaries (start/end copied from the timeline), so no
     cut lands mid-sentence and every time is traceable to the source.
  5. Two kinds:
       single : one continuous stretch, hook ... cliff
       joined : hook moment (a few seconds) + a later stretch ending on the cliff,
                when the cliff is too far away for one 60s clip. The brief allows
                joining moments. Whether the join still makes sense is checked later
                by the cold-viewer step (Step 5).
  6. Remove near-duplicates: if two candidates overlap > max_overlap, keep the better one.
  7. Which lines count as "strong" (config `selection`):
       relative (default): the top X% of this show's lines by hook / cliff score.
                Works the same whatever model is plugged in (models use 0-5 differently).
       absolute: fixed cut-offs (hook >= 4, cliff >= 4).
     If too few candidates come out, the pool is widened (relative) or the cut-off
     lowered (absolute), and that is recorded in the output, so nothing is hidden.

Run:
    python src/candidates.py data/screenplays/dragons_bride.txt
(needs outputs/beats_<name>.json from tagger.py; prints a summary only - use --show
 AFTER writing your answer key)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from adapter import fmt_time
from parser import show_name
from llm import load_config

ROOT = Path(__file__).resolve().parent.parent
CUTTABLE = ("dialogue", "action")   # a promo should not start/end on a bare "[music]"


# ---------- helpers ----------

def seg(lines: list[dict], i: int, j: int) -> dict:
    """Segment = lines[i..j] inclusive. Times are copied from those lines."""
    # start/end = show clock (for maths); ep_start/ep_end = time written in that episode's
    # script (what the editor cuts from). Same numbers for a single video.
    return {"first_id": lines[i]["id"], "last_id": lines[j]["id"], "ep": lines[i]["ep"],
            "start": lines[i]["start"], "end": lines[j]["end"],
            "ep_start": lines[i].get("ep_start", lines[i]["start"]),
            "ep_end": lines[j].get("ep_end", lines[j]["end"]), "_i": i, "_j": j}


def seg_len(s: dict) -> float:
    return s["end"] - s["start"]


def total_len(segs: list[dict]) -> float:
    return sum(seg_len(s) for s in segs)


def overlap_ratio(a: list[dict], b: list[dict]) -> float:
    """Shared seconds / length of the shorter promo."""
    shared = 0.0
    for x in a:
        for y in b:
            shared += max(0.0, min(x["end"], y["end"]) - max(x["start"], y["start"]))
    return shared / max(1e-6, min(total_len(a), total_len(b)))


def length_bonus(d: float, p: dict) -> float:
    """Small preference for the editor's sweet spot (USER DECISION in config)."""
    return 1.0 if p["preferred_min_seconds"] <= d <= p["preferred_max_seconds"] else 0.9


# ---------- builders ----------

def single_candidates(L: list[dict], h: int, p: dict, is_cliff) -> list[list[dict]]:
    out = []
    for j in range(h, len(L)):
        if L[j]["ep"] != L[h]["ep"]:
            break   # a continuous clip never runs across an episode boundary
        d = L[j]["end"] - L[h]["start"]
        if d > p["max_seconds"]:
            break
        if d >= p["min_seconds"] and is_cliff(L[j]):
            out.append([seg(L, h, j)])
    return out


def joined_candidates(L: list[dict], h: int, p: dict, is_cliff) -> list[list[dict]]:
    """Hook moment + later stretch that ends on a cliff (the cliff is > 60s away)."""
    # Segment A: the hook line plus following lines until it is ~hook_segment_seconds long.
    a_end = h
    while (a_end + 1 < len(L) and L[a_end + 1]["start"] - L[h]["start"] < p["hook_segment_seconds"]):
        a_end += 1
    A = seg(L, h, a_end)
    out = []
    for c in range(a_end + 1, len(L)):
        if L[c]["start"] - A["end"] > p["max_join_gap_seconds"] or L[c]["ep"] != L[h]["ep"]:
            break   # too far away / different episode -> likely a different storyline
        if not is_cliff(L[c]):
            continue
        # Segment B: walk back from the cliff, adding whole lines while it fits.
        budget_max = p["max_seconds"] - seg_len(A)
        target = p["preferred_min_seconds"] - seg_len(A)
        b = c
        while b - 1 > a_end and (L[c]["end"] - L[b - 1]["start"]) <= budget_max \
                and (L[c]["end"] - L[b]["start"]) < target:
            b -= 1
        B = seg(L, b, c)
        if B["start"] - A["end"] < p["min_join_gap_seconds"]:
            continue                       # basically continuous -> the single builder covers it
        if p["min_seconds"] <= seg_len(A) + seg_len(B) <= p["max_seconds"]:
            out.append([A, B])
    # Keep only the best join per hook: strongest cliff, then the closest one
    # (closer = more likely the same storyline). Otherwise joins flood the list.
    out.sort(key=lambda s: (-L[s[1]["_j"]]["cliff"], s[1]["start"] - s[0]["end"]))
    return out[:1]


def describe(L: list[dict], segs: list[dict]) -> dict:
    """Attach scores + text so later steps (and humans) can judge the candidate."""
    first, last = L[segs[0]["_i"]], L[segs[-1]["_j"]]
    inside = [L[k] for s in segs for k in range(s["_i"], s["_j"] + 1)]
    d = total_len(segs)
    return {
        "segments": [{k: v for k, v in s.items() if not k.startswith("_")} for s in segs],
        "kind": "single" if len(segs) == 1 else "joined",
        "duration": round(d, 1),
        "hook_id": first["id"], "hook_text": first["text"], "hook_score": first["hook"],
        "cliff_id": last["id"], "cliff_text": last["text"], "cliff_score": last["cliff"],
        "archetype": first["archetype"],
        "hook_reason": first["reason"], "cliff_reason": last["reason"],
        "max_needs_context": max(x["needs_context"] for x in inside),
        "avg_needs_context": round(sum(x["needs_context"] for x in inside) / len(inside), 2),
        # hook x cliff, small bonus for the preferred length, small penalty for joins
        # (the brief: a promo is "usually one continuous stretch").
        "pre_score": round(first["hook"] * last["cliff"] * length_bonus(d, PROMO)
                           * (1.0 if len(segs) == 1 else PROMO.get("join_penalty", 0.85)), 2),
        "lines": [{"id": x["id"], "start": x["start"], "type": x["type"], "text": x["text"],
                   "speaker": x.get("speaker"), "delivery": x.get("delivery")} for x in inside],
    }


def dedupe(cands: list[dict], max_overlap: float) -> list[dict]:
    kept: list[dict] = []
    for c in sorted(cands, key=lambda c: (-c["pre_score"], c["kind"] != "single", c["duration"])):
        if all(overlap_ratio(c["segments"], k["segments"]) <= max_overlap for k in kept):
            kept.append(c)
    return kept


def verify(cands: list[dict], L: list[dict]) -> None:
    """Non-negotiable rule: every time must equal a line time in the source timeline."""
    by_id = {x["id"]: x for x in L}
    for c in cands:
        prev_end = -1.0
        for s in c["segments"]:
            assert by_id[s["first_id"]]["start"] == s["start"], f"bad start {s}"
            assert by_id[s["last_id"]]["end"] == s["end"], f"bad end {s}"
            assert s["start"] >= prev_end, "segments out of order"
            prev_end = s["end"]
        assert PROMO["min_seconds"] <= c["duration"] <= PROMO["max_seconds"], c["duration"]


PROMO: dict = {}


def top_ids(L: list[dict], key: str, tie: str, pct: float) -> set[str]:
    """RELATIVE selection: the top `pct`% of cuttable lines by `key` (ties broken by
    `tie`). Why: each model uses the 0-5 scale differently (Gemini gave 5 lines hook>=4,
    Groq gave 1), so a fixed cut-off breaks when the model is swapped. "Best 10% of
    this show" means the same thing for every model. Lines scored 0 are never picked."""
    pool = [x for x in L if x["type"] in CUTTABLE and x[key] > 0]
    pool.sort(key=lambda x: (-x[key], -x[tie], x["needs_context"]))
    n = max(1, round(len([x for x in L if x["type"] in CUTTABLE]) * pct / 100))
    return {x["id"] for x in pool[:n]}


def _collect(L: list[dict], p: dict, is_hook, is_cliff) -> tuple[list[dict], int]:
    raw = []
    for h, line in enumerate(L):
        if is_hook(line):
            raw += single_candidates(L, h, p, is_cliff)
            if p.get("allow_joins", True):
                raw += joined_candidates(L, h, p, is_cliff)
    return dedupe([describe(L, s) for s in raw], p["max_overlap"]), len(raw)


def build_candidates(beats: list[dict], promo_cfg: dict) -> dict:
    PROMO.clear()
    PROMO.update(promo_cfg)
    p = promo_cfg
    L = beats
    relaxed: list[str] = []
    mode = p.get("selection", "relative")

    if mode == "relative":
        hook_pct, cliff_pct = p["hook_top_pct"], p["cliff_top_pct"]
        while True:
            hooks = top_ids(L, "hook", "cliff", hook_pct)
            cliffs = top_ids(L, "cliff", "hook", cliff_pct)
            cands, n_raw = _collect(L, p, lambda x: x["id"] in hooks, lambda x: x["id"] in cliffs)
            if len(cands) >= p["min_candidates"] or (hook_pct >= p["max_top_pct"] and cliff_pct >= p["max_top_pct"]):
                break
            # Too few: widen both pools by 5 percentage points, and record it.
            hook_pct = min(p["max_top_pct"], hook_pct + 5)
            cliff_pct = min(p["max_top_pct"], cliff_pct + 5)
            relaxed.append(f"top % widened -> hooks {hook_pct}%, cliffs {cliff_pct}%")
        used = {"mode": "relative", "hook_top_pct": hook_pct, "cliff_top_pct": cliff_pct,
                "hook_lines": len(hooks), "cliff_lines": len(cliffs),
                "lowest_hook_score_used": min(x["hook"] for x in L if x["id"] in hooks),
                "lowest_cliff_score_used": min(x["cliff"] for x in L if x["id"] in cliffs)}
    else:  # "absolute": fixed score cut-offs, relaxed by 1 if too few
        hook_t, cliff_t = p["hook_threshold"], p["cliff_threshold"]
        while True:
            cands, n_raw = _collect(L, p, lambda x: x["type"] in CUTTABLE and x["hook"] >= hook_t,
                                    lambda x: x["type"] in CUTTABLE and x["cliff"] >= cliff_t)
            if len(cands) >= p["min_candidates"] or (hook_t <= p["relax_floor"] and cliff_t <= p["relax_floor"]):
                break
            if hook_t >= cliff_t and hook_t > p["relax_floor"]:
                hook_t -= 1
                relaxed.append(f"hook_threshold -> {hook_t}")
            elif cliff_t > p["relax_floor"]:
                cliff_t -= 1
                relaxed.append(f"cliff_threshold -> {cliff_t}")
        used = {"mode": "absolute", "hook": hook_t, "cliff": cliff_t}

    cands = cands[: p["max_candidates"]]
    verify(cands, L)
    for n, c in enumerate(cands, 1):
        c["cand_id"] = f"C{n:02d}"
    return {"candidates": cands, "thresholds_used": used, "relaxed": relaxed,
            "raw_before_dedupe": n_raw}


def main() -> None:
    ap = argparse.ArgumentParser(description="Build candidate promos from tagged beats.")
    ap.add_argument("file", help="the script file (used to find outputs/beats_<name>.json)")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--show", action="store_true", help="print candidates (only AFTER my_picks.txt)")
    args = ap.parse_args()

    stem = show_name(args.file)
    beats_path = ROOT / "outputs" / f"beats_{stem}.json"
    if not beats_path.exists():
        raise SystemExit(f"Missing {beats_path}. Run: python src/tagger.py {args.file}")
    tagged = json.loads(beats_path.read_text(encoding="utf-8"))
    cfg = load_config(args.config)

    res = build_candidates(tagged["beats"], cfg["promo"])
    res["meta"] = tagged["meta"]
    out = ROOT / "outputs" / f"candidates_{stem}.json"
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    c = res["candidates"]
    print(f"Raw windows: {res['raw_before_dedupe']}  ->  after dedupe/cap: {len(c)}")
    print(f"Thresholds used: {res['thresholds_used']}  relaxed: {res['relaxed'] or 'no'}")
    print(f"Single: {sum(x['kind'] == 'single' for x in c)}  Joined: {sum(x['kind'] == 'joined' for x in c)}")
    if c:
        ds = [x["duration"] for x in c]
        print(f"Durations: min {min(ds)}s  max {max(ds)}s  avg {sum(ds) / len(ds):.1f}s")
    print("All timestamps verified against the source timeline: OK")
    print("Saved:", out)
    if args.show:
        for x in c:
            segs = " + ".join(f"{fmt_time(s['start'])}-{fmt_time(s['end'])}" for s in x["segments"])
            print(f"\n{x['cand_id']} [{x['kind']}] {segs} ({x['duration']}s) pre={x['pre_score']} {x['archetype']}")
            print(f"   HOOK  ({x['hook_score']}): {x['hook_text'][:80]}")
            print(f"   CLIFF ({x['cliff_score']}): {x['cliff_text'][:80]}")
    else:
        print("(Candidates hidden. Write data/my_picks.txt first, then re-run with --show.)")


if __name__ == "__main__":
    main()
