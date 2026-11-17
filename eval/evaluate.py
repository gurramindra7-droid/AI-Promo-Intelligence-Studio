"""
evaluate.py - Step 8: how good are the picks? Compare against YOUR answer key.

1. Reads data/my_picks.txt (written by hand BEFORE seeing any tool output) and saves it
   as eval/gold_labels.json. Format, one block per pick:

        PICK 1
        start: 5:13
        end: 5:45
        hook: "You. Waitress. You spilled wine on my dress."
        cliffhanger: "Are you calling me a liar?" - cut before her answer
        why: public humiliation + a question a stranger wants answered

   For a promo that joins moments use instead:   segments: 1:03-1:20, 4:27-4:52
   For a show split into episodes add a line      episode: 3   (times = that episode's times)

2. A tool promo MATCHES a pick if they share at least `--min-overlap` (default 50%) of the
   shorter one's length. Each pick can be matched once.

3. Metrics (for the AI tool AND the keyword baseline, side by side):
     precision@10   of the tool's top 10, how many match one of my picks
     recall@10      of my picks, how many are found in the tool's top 10
     recall@all     of my picks, how many are found anywhere in the tool's list
     start / end error   for matched pairs, how many seconds the cut points are off

4. Lists the misses and false alarms - the raw material for "where the tool picks badly".

Run:  python eval/evaluate.py data/screenplays/dragons_bride.txt
Out:  eval/results_<name>.json  and  eval/results_<name>.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from adapter import fmt_time, to_seconds   # noqa: E402
from parser import show_name               # noqa: E402

TIME = r"\d{1,2}(?::\d{2}){1,2}"


# ---------- answer key ----------

def parse_picks(text: str) -> list[dict]:
    picks, cur = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if re.match(r"^PICK\b", line, re.I):
            cur = {"name": line, "segments": [], "_start": None, "_end": None}
            picks.append(cur)
            continue
        if cur is None:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip().lower(), val.strip()
        if key in ("start", "end"):
            t = re.search(TIME, val)
            if t:   # blank template lines are simply left empty
                cur["_" + key] = to_seconds(t.group(0))
        elif key in ("episode", "ep") and re.search(r"\d+", val):
            cur["ep"] = int(re.search(r"\d+", val).group(0))   # times below are that episode's times
        elif key == "segments":
            for a, b in re.findall(rf"({TIME})\s*-\s*({TIME})", val):
                cur["segments"].append({"start": to_seconds(a), "end": to_seconds(b)})
        elif key in ("hook", "cliffhanger", "cliff", "why"):
            cur["cliffhanger" if key == "cliff" else key] = val.strip('"')
    out = []
    for p in picks:
        if not p["segments"] and p["_start"] is not None and p["_end"] is not None:
            p["segments"] = [{"start": p["_start"], "end": p["_end"]}]
        p.pop("_start"), p.pop("_end")
        if not p["segments"]:
            print(f"  warning: {p['name']} has no start/end - skipped")
            continue
        bad = [s for s in p["segments"] if s["end"] <= s["start"]]
        if bad:
            print(f"  warning: {p['name']} has end before start - skipped")
            continue
        out.append(p)
    return out


# ---------- matching ----------

def length(segs: list[dict]) -> float:
    return sum(s["end"] - s["start"] for s in segs)


def overlap(a: list[dict], b: list[dict]) -> float:
    shared = sum(max(0.0, min(x["end"], y["end"]) - max(x["start"], y["start"])) for x in a for y in b)
    return shared / max(1e-6, min(length(a), length(b)))


def match(promos: list[dict], gold: list[dict], min_ov: float) -> dict:
    """Greedy one-to-one matching, best overlaps first."""
    pairs = sorted(((overlap(p["segments"], g["segments"]), i, j)
                    for i, p in enumerate(promos) for j, g in enumerate(gold)), reverse=True)
    used_p, used_g, matched = set(), set(), {}
    for ov, i, j in pairs:
        if ov < min_ov:
            break
        if i in used_p or j in used_g:
            continue
        used_p.add(i), used_g.add(j)
        matched[i] = (j, ov)
    return matched


def metrics(promos: list[dict], gold: list[dict], min_ov: float, k: int = 10) -> dict:
    m_all = match(promos, gold, min_ov)
    m_top = match(promos[:k], gold, min_ov)
    errs_s = [abs(promos[i]["segments"][0]["start"] - gold[j]["segments"][0]["start"]) for i, (j, _) in m_all.items()]
    errs_e = [abs(promos[i]["segments"][-1]["end"] - gold[j]["segments"][-1]["end"]) for i, (j, _) in m_all.items()]
    avg = lambda xs: round(sum(xs) / len(xs), 1) if xs else None
    return {
        "promos": len(promos),
        f"precision@{k}": round(len(m_top) / max(1, min(k, len(promos))), 2),
        f"recall@{k}": round(len(m_top) / max(1, len(gold)), 2),
        "recall@all": round(len(m_all) / max(1, len(gold)), 2),
        "avg_start_error_s": avg(errs_s),
        "avg_end_error_s": avg(errs_e),
        "matched": {promos[i].get("cand_id", f"#{promos[i]['rank']}"): gold[j]["name"] for i, (j, _) in m_all.items()},
        "missed_picks": [g["name"] for j, g in enumerate(gold) if j not in {jj for jj, _ in m_all.values()}],
        "false_alarms_top": [f"#{p['rank']} {segs(p)}" for i, p in enumerate(promos[:k]) if i not in m_top],
    }


def segs(p: dict) -> str:
    return " + ".join(f"Ep{s.get('ep', 1)} {fmt_time(s.get('ep_start', s['start']))}-{fmt_time(s.get('ep_end', s['end']))}"
                      for s in p["segments"])


def to_show_clock(gold: list[dict], timeline: dict) -> None:
    """Picks written as 'episode: 3' + that episode's times -> the pipeline's show clock."""
    offsets: dict[int, float] = {}
    for l in timeline["lines"]:
        offsets.setdefault(l["ep"], l["start"] - l.get("ep_start", l["start"]))
    for g in gold:
        if g.get("ep") is not None:
            if g["ep"] not in offsets:
                print(f"  warning: {g['name']} - episode {g['ep']} not in the script")
                continue
            for s in g["segments"]:
                s["start"] += offsets[g["ep"]]
                s["end"] += offsets[g["ep"]]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("--picks", default=str(ROOT / "data" / "my_picks.txt"))
    ap.add_argument("--min-overlap", type=float, default=0.5)
    ap.add_argument("--k", type=int, default=10)
    args = ap.parse_args()

    stem = show_name(args.script)
    picks_path = Path(args.picks)
    if not picks_path.exists():
        raise SystemExit(f"No answer key at {picks_path}. Write your picks first (see the format at the top of this file).")
    gold = parse_picks(picks_path.read_text(encoding="utf-8-sig"))
    if not gold:
        raise SystemExit("No valid picks found in the answer key.")
    tl_path = ROOT / "outputs" / f"timeline_{stem}.json"
    if tl_path.exists():
        to_show_clock(gold, json.loads(tl_path.read_text(encoding="utf-8")))
    (ROOT / "eval" / "gold_labels.json").write_text(json.dumps(gold, ensure_ascii=False, indent=1), encoding="utf-8")

    tool = json.loads((ROOT / "outputs" / f"ranked_{stem}.json").read_text(encoding="utf-8"))["promos"]
    base_p = ROOT / "outputs" / f"baseline_ranked_{stem}.json"
    base = json.loads(base_p.read_text(encoding="utf-8"))["promos"] if base_p.exists() else None

    res = {"answer_key": str(picks_path.name), "picks": len(gold), "min_overlap": args.min_overlap,
           "tool": metrics(tool, gold, args.min_overlap, args.k)}
    if base is not None:
        res["baseline"] = metrics(base, gold, args.min_overlap, args.k)
    (ROOT / "eval" / f"results_{stem}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    k = args.k
    rows = ["promos", f"precision@{k}", f"recall@{k}", "recall@all", "avg_start_error_s", "avg_end_error_s"]
    md = [f"# Evaluation - {stem}", "",
          f"Answer key: {len(gold)} picks from {picks_path.name}. Match = at least {int(args.min_overlap * 100)}% time overlap.", "",
          "| Metric | AI tool | Keyword baseline |", "|---|---|---|"]
    for r in rows:
        md.append(f"| {r} | {res['tool'][r]} | {res['baseline'][r] if base is not None else '-'} |")
    md += ["", "## AI tool: picks it missed", *[f"- {x}" for x in res["tool"]["missed_picks"] or ["(none)"]],
           "", f"## AI tool: top-{k} promos that match none of my picks",
           *[f"- {x}" for x in res["tool"]["false_alarms_top"] or ["(none)"]]]
    (ROOT / "eval" / f"results_{stem}.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md[4:4 + len(rows) + 2]))
    print(f"\nSaved eval/results_{stem}.json and .md")


if __name__ == "__main__":
    main()
