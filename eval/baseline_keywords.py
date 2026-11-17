"""
baseline_keywords.py - the "no AI" version of the tool, to prove the AI adds value.

Fair comparison: it uses the SAME candidate builder (same 20-60s rules, same cuts on
line boundaries, same dedupe). The ONLY difference is who scores the lines:
    tool     -> the AI tagger + the AI stranger test
    baseline -> a keyword list (what a simple script or a rushed editor might search for)

Line scores:
    hook  = 2 points per dramatic keyword, +1 for "!" or [screaming]/[gasps], max 5
    cliff = 2 points per threat/suspense keyword, +2 if the line ends with "?" or "...", max 5
Promos are ranked by hook x cliff (no stranger test).

Run:  python eval/baseline_keywords.py data/screenplays/dragons_bride.txt
Out:  outputs/baseline_ranked_<name>.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from candidates import build_candidates   # noqa: E402
from llm import load_config               # noqa: E402
from parser import load_show, show_name  # noqa: E402

HOOK_WORDS = [
    "slap", "hit", "kill", "dead", "die", "blood", "monster", "pregnant", "divorce", "marry",
    "married", "wedding", "cheat", "affair", "secret", "liar", "lied", "betray", "fired", "kiss",
    "mate", "curse", "dragon", "wolf", "vampire", "billionaire", "revenge", "hate", "loser",
    "how dare", "get out", "who are you", "what the hell", "oh my god", "help", "stop",
]
CLIFF_WORDS = [
    "what", "who", "why", "wait", "no", "please", "don't", "you will", "i will", "or else",
    "never", "until", "tonight", "tomorrow", "finally", "truth", "found out", "know",
]
EXCITED = re.compile(r"!|\[(screaming|gasps?|crying|panting)\]", re.I)


def count(words: list[str], text: str) -> int:
    t = text.lower()
    return sum(1 for w in words if re.search(rf"\b{re.escape(w)}\b", t))


def score_line(l: dict) -> dict:
    t = l["text"]
    hook = min(5, 2 * count(HOOK_WORDS, t) + (1 if EXCITED.search(t) else 0))
    cliff = min(5, 2 * count(CLIFF_WORDS, t) + (2 if re.search(r"(\?|\.\.\.)\s*$", t.strip()) else 0))
    return {**l, "hook": hook, "cliff": cliff, "needs_context": 2,
            "archetype": "keyword", "reason": "keyword match"}


def run_baseline(script: str, cfg: dict) -> dict:
    tl = load_show(script)
    beats = [score_line(l) for l in tl["lines"] if l["type"] != "episode_marker"]
    res = build_candidates(beats, cfg["promo"])
    ranked = sorted(res["candidates"], key=lambda c: -c["pre_score"])
    for i, c in enumerate(ranked, 1):
        c["rank"] = i
    return {"meta": tl["meta"], "method": "keyword baseline (no AI)",
            "selection": res["thresholds_used"], "promos": ranked}


def main() -> None:
    script = sys.argv[1] if len(sys.argv) > 1 else "data/screenplays/dragons_bride.txt"
    cfg = load_config(ROOT / "config.yaml")
    out = run_baseline(script, cfg)
    p = ROOT / "outputs" / f"baseline_ranked_{show_name(script)}.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Baseline: {len(out['promos'])} promos (selection {out['selection']})")
    print("Saved:", p)


if __name__ == "__main__":
    main()
