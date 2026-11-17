"""
cold_viewer.py - Step 5: the "stranger test". Makes rule 3 of the brief measurable:
"a good promo makes sense on its own to someone who has never seen the show".

How: for EACH candidate promo, a fresh AI call gets ONLY the promo's lines - no show
name, no story summary, no other promos. It plays a stranger scrolling TikTok and says:

    understood      true/false  could I follow what is going on?
    what_happens    1 sentence  (lets a human check it really understood)
    question_left   the question I'd need answered -> proves there is a cliffhanger
    confusing       things that made no sense without backstory
    standalone      0-5  makes sense on its own
    hook_3s         0-5  would the FIRST line alone stop my scroll?
    want_next       0-5  how badly do I want to watch the next episode?

Why one call per promo (not all in one call)?
  If the AI saw several promos together it would learn the story from the others
  and stop being a "stranger". Separate calls keep each judgement blind.
  Calls run a few at a time in parallel, and every answer is cached.

Run:
    python src/cold_viewer.py data/screenplays/dragons_bride.txt
(needs outputs/candidates_<name>.json; prints a summary only - use --show AFTER my_picks.txt)
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from adapter import fmt_time
from parser import show_name
from llm import LLM, LLMError, load_config

ROOT = Path(__file__).resolve().parent.parent

SYSTEM = """You are an ordinary person scrolling TikTok/Instagram Reels in the US. You have NEVER seen this show and know nothing about its characters or story.
You are shown the transcript of one short promo clip (20-60 seconds) cut from a vertical microdrama.
Lines are in the order they play. "[CUT]" means the clip jumps to a later moment. "ACTION:" lines describe what you see on screen.
Captions are auto-generated: no speaker names, some words may be wrong.

Judge honestly as a stranger - do not invent backstory to fill gaps. If something only makes sense with knowledge you don't have, it is confusing.

Scores are integers 0-5:
- standalone: 5 = I fully get who/what/why from the clip alone; 0 = I'm lost.
- hook_3s: 5 = the FIRST line alone would make me stop scrolling; 0 = I'd scroll past.
- want_next: 5 = I must know what happens next; 0 = I don't care / it felt finished.

Reply with JSON only:
{"understood": true, "what_happens": "<one sentence>", "question_left": "<the question I want answered, or empty if none>", "confusing": ["<short item>", ...], "standalone": 0, "hook_3s": 0, "want_next": 0}"""

KEYS = ("standalone", "hook_3s", "want_next")


def promo_text(c: dict) -> str:
    """Only the promo's own lines. Segments joined by [CUT]. No times, no show info."""
    out, seg_i = [], 0
    bounds = [(s["first_id"], s["last_id"]) for s in c["segments"]]
    for l in c["lines"]:
        if seg_i + 1 < len(bounds) and l["id"] == bounds[seg_i + 1][0]:
            out.append("[CUT]")
            seg_i += 1
        if l["type"] == "action":
            out.append(f"ACTION: {l['text']}")
        elif l["type"] == "scene":
            out.append(f"SCENE: {l['text']}")
        elif l["type"] == "camera":   # what a viewer would SEE (Kuku screenplays)
            out.append(f"SHOT: {l['text']}")
        elif l["type"] == "sfx":
            out.append(f"SOUND: {l['text']}")
        elif l.get("speaker") and l.get("delivery"):
            out.append(f"{l['speaker']} ({l['delivery']}): {l['text']}")
        else:   # speaker names (screenplays) help a stranger follow who is talking
            out.append(f"{l['speaker']}: {l['text']}" if l.get("speaker") else l["text"])
    return "\n".join(out)


def validate(d) -> bool | str:
    if not isinstance(d, dict):
        return "Reply must be a JSON object."
    if not isinstance(d.get("understood"), bool):
        return "'understood' must be true or false."
    for k in KEYS:
        v = d.get(k)
        if not isinstance(v, (int, float)) or not 0 <= v <= 5:
            return f"'{k}' must be an integer 0-5."
    if not isinstance(d.get("confusing", []), list):
        return "'confusing' must be a list of strings."
    return True


def judge_one(llm: LLM, c: dict) -> dict:
    prompt = "PROMO CLIP TRANSCRIPT:\n" + promo_text(c)
    try:
        d = llm.call_json(prompt, system=SYSTEM, task="cold_viewer", validate=validate)
    except LLMError as e:
        # Never guess: a failed check is recorded as a failure and ranks low.
        return {"cold_ok": False, "cold_error": str(e)[:200], "understood": False,
                "what_happens": "", "question_left": "", "confusing": ["cold-viewer check failed"],
                "standalone": 0, "hook_3s": 0, "want_next": 0}
    # The AI's own yes/no was too loose (it said "understood" while scoring standalone 1).
    # So code decides: understood = standalone >= 3. The AI's answer is kept for the doc.
    return {"cold_ok": True, "understood": int(round(d["standalone"])) >= 3,
            "ai_said_understood": d["understood"],
            "what_happens": str(d.get("what_happens", ""))[:250],
            "question_left": str(d.get("question_left", ""))[:200],
            "confusing": [str(x)[:120] for x in d.get("confusing", [])][:5],
            **{k: int(round(d[k])) for k in KEYS}}


def run_cold_viewer(cands: list[dict], llm: LLM, workers: int = 4, verbose: bool = True) -> list[dict]:
    if verbose:
        print(f"  cold-viewer: judging {len(cands)} promos ({workers} at a time)...")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(lambda c: judge_one(llm, c), cands))
    return [{**c, "cold": r} for c, r in zip(cands, results)]


def main() -> None:
    ap = argparse.ArgumentParser(description="Stranger test for each candidate promo.")
    ap.add_argument("file")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--show", action="store_true", help="print verdicts (only AFTER my_picks.txt)")
    args = ap.parse_args()

    stem = show_name(args.file)
    cpath = ROOT / "outputs" / f"candidates_{stem}.json"
    if not cpath.exists():
        raise SystemExit(f"Missing {cpath}. Run: python src/candidates.py {args.file}")
    data = json.loads(cpath.read_text(encoding="utf-8"))
    cfg = load_config(args.config)
    llm = LLM(args.config)

    judged = run_cold_viewer(data["candidates"], llm, workers=cfg.get("cold_viewer", {}).get("workers", 4))
    data["candidates"] = judged
    data["cold_usage"] = llm.usage_summary()
    out = ROOT / "outputs" / f"cold_{stem}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    cs = [c["cold"] for c in judged]
    ok = [c for c in cs if c["cold_ok"]]
    print(f"Judged {len(cs)} promos. Check failed: {len(cs) - len(ok)}. "
          f"Understood by stranger: {sum(c['understood'] for c in ok)}/{len(ok)}")
    if ok:
        avg = lambda k: sum(c[k] for c in ok) / len(ok)
        print(f"Average standalone {avg('standalone'):.2f}  hook_3s {avg('hook_3s'):.2f}  want_next {avg('want_next'):.2f}")
        for kind in ("single", "joined"):
            sub = [c["cold"] for c in judged if c["kind"] == kind and c["cold"]["cold_ok"]]
            if sub:
                print(f"  {kind:<6}: {len(sub)} promos, understood {sum(x['understood'] for x in sub)}, "
                      f"avg standalone {sum(x['standalone'] for x in sub) / len(sub):.2f}")
    print("Usage:", data["cold_usage"])
    print("Saved:", out)
    if args.show:
        for c in judged:
            v = c["cold"]
            segs = " + ".join(f"{fmt_time(s['start'])}-{fmt_time(s['end'])}" for s in c["segments"])
            print(f"\n{c['cand_id']} {segs} [{c['kind']}] understood={v['understood']} "
                  f"S{v['standalone']} H{v['hook_3s']} W{v['want_next']}")
            print(f"   sees: {v['what_happens']}")
            print(f"   asks: {v['question_left']}")
            if v["confusing"]:
                print(f"   confused by: {'; '.join(v['confusing'])}")
    else:
        print("(Verdicts hidden. Write data/my_picks.txt first, then re-run with --show.)")


if __name__ == "__main__":
    main()
