"""
blind_review.py - a fair human check of the AI tool against a no-AI method, on the real input.

Why: there is no answer key for Kuku's show, and an answer key written after seeing the tool's
output would be biased. So instead a person rates promos WITHOUT knowing who picked them.

    1. make : takes the AI tool's top N and the keyword baseline's top N (outputs/), merges promos
              that are the same moment (>= 50% time overlap), shuffles them with a fixed seed and
              writes a rating sheet with codes P01, P02... and each promo's script text.
              The key (which code came from which method) is saved separately and NOT shown.
    2. You  : read each promo and write  rating: good | average | bad  and a short why.
    3. score: reveals the key and counts good / average / bad for each method.

The sheet and key quote the script, so they live in data/ (private, never in the repo).

    python eval/blind_review.py make  data/<your_show_folder>
    python eval/blind_review.py score data/<your_show_folder>
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from adapter import fmt_time       # noqa: E402
from parser import show_name       # noqa: E402

PRIVATE = ROOT / "data" / "reviews"


def overlap(a: list[dict], b: list[dict]) -> float:
    shared = sum(max(0.0, min(x["end"], y["end"]) - max(x["start"], y["start"])) for x in a for y in b)
    la, lb = sum(s["end"] - s["start"] for s in a), sum(s["end"] - s["start"] for s in b)
    return shared / max(1e-6, min(la, lb))


def cut(p: dict) -> str:
    return " + ".join(f"Episode {s.get('ep', 1)}, {fmt_time(s.get('ep_start', s['start']))} to "
                      f"{fmt_time(s.get('ep_end', s['end']))}" for s in p["segments"])


def script_text(p: dict) -> list[str]:
    out = []
    for l in p.get("lines", []):
        if l["type"] in ("camera", "scene", "episode_marker"):
            continue
        if l["type"] == "action":
            out.append(f"   (action) {l['text']}")
        elif l["type"] in ("sfx", "sound"):
            out.append(f"   (sound) {l['text']}")
        else:
            who = l.get("speaker") or ""
            how = f" ({l['delivery']})" if l.get("delivery") else ""
            out.append(f"   {who}{how}: {l['text']}" if who else f"   {l['text']}")
    return out


def make(inp: str, n: int, seed: int) -> None:
    stem = show_name(inp)
    tool = json.loads((ROOT / "outputs" / f"ranked_{stem}.json").read_text(encoding="utf-8"))["promos"][:n]
    base = json.loads((ROOT / "outputs" / f"baseline_ranked_{stem}.json").read_text(encoding="utf-8"))["promos"][:n]
    items: list[dict] = []
    for method, promos in (("ai_tool", tool), ("keyword", base)):
        for p in promos:
            rank = promos.index(p) + 1
            same = next((it for it in items if overlap(it["promo"]["segments"], p["segments"]) >= 0.5), None)
            if same:                                   # the same moment picked by both methods
                same["methods"].append(method)
                same["rank"][method] = rank
            else:
                items.append({"promo": p, "methods": [method], "rank": {method: rank}})
    random.Random(seed).shuffle(items)
    PRIVATE.mkdir(parents=True, exist_ok=True)
    key, sheet = {}, [
        f"# BLIND REVIEW - {stem}  ({len(items)} promos, order shuffled)",
        "# For each promo write:  rating: good | average | bad   and a short why.",
        "# good = you would post it: strong hook in the first 3 s, ends unresolved, a stranger gets it.",
        "# Don't try to guess which method picked it - judge the promo only.", ""]
    for i, it in enumerate(items, 1):
        code = f"P{i:02d}"
        p = it["promo"]
        key[code] = {"methods": it["methods"], "segments": p["segments"], "rank": it["rank"]}
        sheet += [f"{code}  |  {cut(p)}  ({p['duration']:.0f}s)", *script_text(p), "rating: ", "why: ", ""]
    (PRIVATE / f"blind_review_{stem}.txt").write_text("\n".join(sheet), encoding="utf-8")
    (PRIVATE / f"blind_key_{stem}.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
    both = sum(1 for it in items if len(it["methods"]) == 2)
    print(f"Sheet: data/reviews/blind_review_{stem}.txt  ({len(items)} promos; {both} picked by both methods)")
    print("Fill in 'rating:' for each, save, then run:  python eval/blind_review.py score " + inp)


def score(inp: str, n: int) -> None:
    stem = show_name(inp)
    key = json.loads((PRIVATE / f"blind_key_{stem}.json").read_text(encoding="utf-8"))
    text = (PRIVATE / f"blind_review_{stem}.txt").read_text(encoding="utf-8")
    ratings, whys, cur = {}, {}, None
    for line in text.splitlines():
        if m := re.match(r"^(P\d{2})\s*\|", line):
            cur = m.group(1)
        elif cur and (m := re.match(r"^rating:\s*(good|average|avg|bad)\b", line.strip(), re.I)):
            ratings[cur] = {"avg": "average"}.get(m.group(1).lower(), m.group(1).lower())
        elif cur and line.startswith("why:"):
            whys[cur] = line[4:].strip()
    missing = [c for c in key if c not in ratings]
    if missing:
        print(f"Not rated yet: {', '.join(missing)}  (write 'rating: good', 'average' or 'bad')")
        if len(missing) == len(key):
            return
    res = {}
    for method in ("ai_tool", "keyword"):
        codes = [c for c, k in key.items() if method in k["methods"] and c in ratings]
        cnt = {v: sum(1 for c in codes if ratings[c] == v) for v in ("good", "average", "bad")}
        res[method] = {"rated": len(codes), **cnt,
                       "good_share": round(cnt["good"] / max(1, len(codes)), 2),
                       "good_in_top5": sum(1 for c in codes if ratings[c] == "good" and (k := key[c])["rank"].get(method, 99) <= 5)}
    lines = [f"# Blind review - {stem}", "",
             f"Top {n} of the AI tool and top {n} of a keyword method (no AI), shuffled; rated by a person "
             "without knowing which method picked which promo. Promos both methods picked count for both.", "",
             "| Method | Rated | Good | Average | Bad | Good share | Good in its top 5 |",
             "|---|---|---|---|---|---|---|"]
    for method, label in (("ai_tool", "AI tool"), ("keyword", "Keyword method (no AI)")):
        r = res[method]
        lines.append(f"| {label} | {r['rated']} | {r['good']} | {r['average']} | {r['bad']} | {r['good_share']:.0%} | {r['good_in_top5']} |")
    lines += ["", "## Reasons given (code - method - rating - why)"]
    for c in sorted(ratings):
        lines.append(f"- {c} - {'+'.join(key[c]['methods'])} - {ratings[c]} - {whys.get(c, '')}")
    out = ROOT / "eval" / f"results_blind_{stem}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[4:8]))
    print(f"\nSaved {out.relative_to(ROOT)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["make", "score"])
    ap.add_argument("input")
    ap.add_argument("--n", type=int, default=10, help="top N promos from each method")
    ap.add_argument("--seed", type=int, default=7, help="shuffle seed (fixed, so the sheet is reproducible)")
    a = ap.parse_args()
    make(a.input, a.n, a.seed) if a.action == "make" else score(a.input, a.n)
