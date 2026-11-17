"""
ranker.py - Step 6: put the promos in the order an editor should post them, and say why.
100% CODE + simple rules (every rule below is a USER DECISION in config.yaml).

1. Three scores, each 0-5, mixing the tagger (reads the whole show) and the
   cold viewer (a stranger who sees only the promo):
       hook       = average of tagger hook  and stranger's hook_3s
       cliff      = average of tagger cliff and stranger's want_next
       standalone = stranger's standalone
2. base = (hook+1) x (cliff+1) x (standalone+1), scaled to 0-100.
       Multiply, because a promo needs ALL three: a great hook with no cliffhanger
       is weak. "+1" so one 0 doesn't wipe out everything else.
3. Rules (multipliers):
       joined promo                 x join_penalty      (brief: "usually one continuous stretch")
       length outside 25-45s        x outside_length_factor
       early in the show            x early_bonus       (viewer who clicks starts at episode 1)
       last part of the show        x spoiler_penalty   (spoiler guard: don't give away late twists)
4. Diversity: at most `max_per_archetype_in_top` promos of one type (slap, reveal, ...)
   in the top N, so the posting plan isn't five copies of the same moment.
5. Every promo gets a plain-English "why it works" and "why this rank" line.

Run:
    python src/ranker.py data/screenplays/dragons_bride.txt
Outputs: outputs/ranked_<name>.json / .csv / .md
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from adapter import fmt_time
from parser import show_name
from llm import load_config

ROOT = Path(__file__).resolve().parent.parent


def score_promo(c: dict, show_len: float, p: dict, r: dict) -> dict:
    cold = c["cold"]
    hook = (c["hook_score"] + cold["hook_3s"]) / 2
    cliff = (c["cliff_score"] + cold["want_next"]) / 2
    stand = cold["standalone"]
    base = (hook + 1) * (cliff + 1) * (stand + 1) / 216 * 100      # 216 = 6*6*6 -> 0..100

    mult, why = 1.0, []
    if c["kind"] == "joined":
        mult *= p.get("join_penalty", 0.85)
        why.append(f"joined clip x{p.get('join_penalty', 0.85)}")
    if not p["preferred_min_seconds"] <= c["duration"] <= p["preferred_max_seconds"]:
        mult *= r["outside_length_factor"]
        why.append(f"{c['duration']:.0f}s is outside {p['preferred_min_seconds']}-{p['preferred_max_seconds']}s x{r['outside_length_factor']}")
    pos = c["segments"][0]["start"] / max(1.0, show_len)
    if r.get("prefer_early_episodes") and pos <= r["early_portion"]:
        mult *= r["early_bonus"]
        why.append(f"early in show x{r['early_bonus']}")
    if r.get("spoiler_guard") and c["segments"][-1]["end"] / max(1.0, show_len) >= 1 - r["spoiler_tail"]:
        mult *= r["spoiler_penalty"]
        why.append(f"late in show (spoiler risk) x{r['spoiler_penalty']}")
    if not cold.get("cold_ok", True):
        why.append("stranger check FAILED - treat with care")

    final = round(base * mult, 1)
    parts = (f"hook {hook:.1f}, cliffhanger {cliff:.1f}, standalone {stand}/5 -> base {base:.0f}"
             + (f"; {'; '.join(why)}" if why else ""))
    return {"score": final, "hook_mix": round(hook, 2), "cliff_mix": round(cliff, 2),
            "standalone": stand, "score_parts": parts}


def why_it_works(c: dict) -> str:
    """One line built from the AI's own reasons - no extra AI call."""
    q = c["cold"].get("question_left") or c.get("cliff_reason", "")
    hook = (c.get("hook_reason") or "a strong opening line").rstrip(".")
    return f"Opens on {hook[0].lower() + hook[1:] if hook else hook}; ends leaving a stranger asking: {q}".strip()


def rank(cands: list[dict], show_len: float, p: dict, r: dict) -> list[dict]:
    for c in cands:
        c.update(score_promo(c, show_len, p, r))
        c["why_it_works"] = why_it_works(c)
    ordered = sorted(cands, key=lambda c: -c["score"])

    # Diversity: fill the top N, skipping a promo if its type is already used too often.
    top, rest, per_type = [], [], {}
    for c in ordered:
        a = c["archetype"]
        if len(top) < r["top_n"] and per_type.get(a, 0) < r["max_per_archetype_in_top"]:
            top.append(c)
            per_type[a] = per_type.get(a, 0) + 1
        else:
            rest.append(c)
    # Variety is a preference, not a wall: if there are too few types to fill the
    # top N, fill the empty slots with the best remaining promos (by score).
    while len(top) < r["top_n"] and rest:
        c = rest.pop(0)
        c["score_parts"] += f"; let in after variety pass (only {len(per_type)} promo types available)"
        top.append(c)
    for c in rest:
        a = c["archetype"]
        if per_type.get(a, 0) >= r["max_per_archetype_in_top"] and c["score"] > top[-1]["score"]:
            c["score_parts"] += f"; moved down: already {r['max_per_archetype_in_top']} '{a}' promos in top {r['top_n']}"
    final = top + rest
    for i, c in enumerate(final, 1):
        c["rank"] = i
        c["in_top"] = i <= len(top)
    return final


# ---------- writers ----------

def seg_str(c: dict) -> str:
    """Episode + the time written in THAT episode's script (what the editor cuts from)."""
    return " + ".join(f"Ep{s['ep']} {fmt_time(s.get('ep_start', s['start']))}-{fmt_time(s.get('ep_end', s['end']))}"
                      for s in c["segments"])


def write_outputs(ranked: list[dict], meta: dict, stem: str, run_info: dict) -> list[Path]:
    out = ROOT / "outputs"
    paths = []

    j = out / f"ranked_{stem}.json"
    j.write_text(json.dumps({"meta": meta, "run": run_info, "promos": ranked}, ensure_ascii=False, indent=1),
                 encoding="utf-8")
    paths.append(j)

    cpath = out / f"ranked_{stem}.csv"
    with open(cpath, "w", newline="", encoding="utf-8-sig") as f:   # utf-8-sig opens cleanly in Excel
        w = csv.writer(f)
        w.writerow(["rank", "score", "segments (episode start-end, in order)", "duration_s", "kind",
                    "type", "hook", "cliffhanger", "why it works", "why this rank",
                    "stranger: what happens", "stranger: confused by"])
        for c in ranked:
            w.writerow([c["rank"], c["score"], seg_str(c), c["duration"], c["kind"], c["archetype"],
                        c["hook_text"], c["cliff_text"], c["why_it_works"], c["score_parts"],
                        c["cold"]["what_happens"], "; ".join(c["cold"]["confusing"])])
    paths.append(cpath)

    m = out / f"ranked_{stem}.md"
    lines = [f"# Ranked promos - {meta.get('show', stem)}", "",
             f"Source: {meta.get('source', '')}  ",
             f"Model: {run_info.get('model')} | promos: {len(ranked)} | "
             f"note: timestamps are relative to the source video/script", ""]
    for c in ranked:
        if c["rank"] == len([x for x in ranked if x["in_top"]]) + 1:
            lines += ["---", "## Other candidates (below the top list)", ""]
        lines += [f"### #{c['rank']} - score {c['score']} - {c['archetype']} ({c['kind']}, {c['duration']:.0f}s)",
                  f"- **Cut:** {seg_str(c)}",
                  f"- **Hook (first 3s):** \"{c['hook_text']}\"",
                  f"- **Cliffhanger (last line):** \"{c['cliff_text']}\"",
                  f"- **Why it works:** {c['why_it_works']}",
                  f"- **Why this rank:** {c['score_parts']}",
                  f"- **Stranger test:** {c['cold']['what_happens']}"
                  + (f" _Confused by: {'; '.join(c['cold']['confusing'])}_" if c["cold"]["confusing"] else ""),
                  ""]
    m.write_text("\n".join(lines), encoding="utf-8")
    paths.append(m)
    return paths


def main() -> None:
    ap = argparse.ArgumentParser(description="Rank the judged promos and write final outputs.")
    ap.add_argument("file")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--show", action="store_true", help="print the ranking (only AFTER my_picks.txt)")
    args = ap.parse_args()

    stem = show_name(args.file)
    cold_path = ROOT / "outputs" / f"cold_{stem}.json"
    if not cold_path.exists():
        raise SystemExit(f"Missing {cold_path}. Run: python src/cold_viewer.py {args.file}")
    data = json.loads(cold_path.read_text(encoding="utf-8"))
    cfg = load_config(args.config)
    meta = data["meta"]

    ranked = rank(data["candidates"], meta.get("duration_seconds", 0), cfg["promo"], cfg["ranking"])
    run_info = {"model": cfg["llm"]["model"], "selection": data.get("thresholds_used"),
                "relaxed": data.get("relaxed"), "cold_usage": data.get("cold_usage")}
    paths = write_outputs(ranked, meta, stem, run_info)

    top = [c for c in ranked if c["in_top"]]
    print(f"Ranked {len(ranked)} promos; top list = {len(top)} "
          f"(types: {sorted({c['archetype'] for c in top})})")
    print(f"Scores: best {ranked[0]['score']}  worst {ranked[-1]['score']}" if ranked else "No promos.")
    for pth in paths:
        print("Saved:", pth)
    if args.show:
        for c in ranked:
            print(f"\n#{c['rank']} {c['score']:>5}  {seg_str(c)}  [{c['kind']}, {c['archetype']}]")
            print(f"     hook:  {c['hook_text'][:80]}")
            print(f"     cliff: {c['cliff_text'][:80]}")
            print(f"     why rank: {c['score_parts']}")
    else:
        print("(Ranking hidden - don't open outputs/ranked_* until data/my_picks.txt is written.)")


if __name__ == "__main__":
    main()
