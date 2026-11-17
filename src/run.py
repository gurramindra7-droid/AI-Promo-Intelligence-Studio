"""
run.py - ONE command runs the whole pipeline on a script file or a folder of them.

    python src/run.py --input data/screenplays --config config.yaml
    python src/run.py --input data/kuku/<show folder>                    # folder of episode files
    python src/run.py --input data/screenplays --model gemini/gemini-3.8-flash   # live model swap

Steps for each script file (each file = one show):
    1. parse      (code)  any supported format -> timeline with line ids
    2. tag        (AI)    hook / cliff / needs_context score for every line
    3. candidates (code)  20-60s promos: start on hook, end on cliffhanger, verified times
    4. cold view  (AI)    blind "stranger" test for each promo
    5. rank       (code)  score + rules + variety -> ranked_<name>.json / .csv / .md
    + run log: model, which model actually answered, calls, tokens, cost, seconds per step

Every step's output is saved in outputs/, unedited (the brief asks for raw outputs).
AI answers are cached, so running again is free unless the script or prompt changed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from candidates import build_candidates          # noqa: E402
from cold_viewer import run_cold_viewer           # noqa: E402
from llm import LLM, load_config                  # noqa: E402
from parser import discover_shows, parse_show    # noqa: E402
from ranker import rank, write_outputs            # noqa: E402
from tagger import tag_timeline                   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def save(name: str, data: dict) -> Path:
    p = ROOT / "outputs" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def run_one(name: str, files: list[Path], cfg: dict, config_path: str, model: str | None,
            use_cache: bool = True, cold_model: str | None = None) -> dict:
    stem = name
    llm = LLM(config_path, model_override=model, use_cache=use_cache)
    # Optional: a different (e.g. cheaper) model for the stranger test - a simpler task.
    cold_llm = LLM(config_path, model_override=cold_model, use_cache=use_cache) if cold_model else llm
    times: dict[str, float] = {}
    label = files[0].name if len(files) == 1 else f"{name}/ ({len(files)} episode files)"
    print(f"\n=== {label}  (model: {llm.model}) ===")

    t = time.time()
    tl = parse_show(name, files)
    save(f"timeline_{stem}.json", tl)
    times["1_parse"] = time.time() - t
    m = tl["meta"]
    print(f"[1/5] parsed {len(tl['lines'])} lines, {m['duration_seconds']:.0f}s, format={m['format']}, "
          f"episodes={len(m['episodes'])}" + (f", speakers={len(m['speakers'])}" if m.get("speakers") else ""))

    t = time.time()
    tagged = tag_timeline(tl, llm)
    save(f"beats_{stem}.json", tagged)
    times["2_tag"] = time.time() - t
    print(f"[2/5] tagged {len(tagged['beats'])} lines")

    t = time.time()
    cands = build_candidates(tagged["beats"], cfg["promo"])
    cands["meta"] = m
    save(f"candidates_{stem}.json", cands)
    times["3_candidates"] = time.time() - t
    print(f"[3/5] {len(cands['candidates'])} candidate promos "
          f"(raw {cands['raw_before_dedupe']}, widened: {cands['relaxed'] or 'no'})")
    if not cands["candidates"]:
        print("      no candidates - stopping for this show")
        return {"show": stem, "error": "no candidates"}

    t = time.time()
    judged = run_cold_viewer(cands["candidates"], cold_llm, workers=cfg.get("cold_viewer", {}).get("workers", 4))
    cands["candidates"] = judged
    save(f"cold_{stem}.json", cands)
    times["4_cold_viewer"] = time.time() - t
    ok = [c["cold"] for c in judged if c["cold"]["cold_ok"]]
    print(f"[4/5] stranger test: {len(ok)}/{len(judged)} judged, "
          f"avg standalone {sum(c['standalone'] for c in ok) / max(1, len(ok)):.2f}")

    t = time.time()
    ranked = rank(judged, m.get("duration_seconds", 0), cfg["promo"], cfg["ranking"])
    usage = llm.usage_summary()
    if cold_llm is not llm:   # add the stranger-test model's calls into one run summary
        cu = cold_llm.usage_summary()
        usage["cold_viewer_model"] = cold_llm.model
        for k in ("calls_total", "calls_cached", "prompt_tokens", "completion_tokens", "cost_usd", "seconds"):
            usage[k] = round(usage[k] + cu[k], 5)
        for model_name, n in cu["answered_by"].items():   # (not `m`: that name holds the show's meta)
            usage["answered_by"][model_name] = usage["answered_by"].get(model_name, 0) + n
        usage["calls_by_task"].update(cu["calls_by_task"])
    run_info = {"model": llm.model, "selection": cands["thresholds_used"], "relaxed": cands["relaxed"],
                "usage": usage}
    paths = write_outputs(ranked, m, stem, run_info)
    times["5_rank"] = time.time() - t
    print(f"[5/5] ranked -> {', '.join(p.name for p in paths)}")

    log = {
        "show": m.get("show", stem), "name": stem, "files": [f.name for f in files], "run_at": datetime.now().isoformat(timespec="seconds"),
        "model": llm.model, "fallback_model": llm.fallback_model, "config_file": str(config_path),
        "allow_joins": cfg["promo"].get("allow_joins", True),
        "lines": len(tl["lines"]), "duration_seconds": m["duration_seconds"],
        "candidates": len(judged), "top_n": sum(c["in_top"] for c in ranked),
        "selection": cands["thresholds_used"], "widened": cands["relaxed"],
        "parser_warnings": len(tl["warnings"]), "tagger_notes": tagged["notes"],
        "seconds_per_step": {k: round(v, 1) for k, v in times.items()},
        "seconds_total": round(sum(times.values()), 1),
        "usage": usage,
    }
    save(f"run_log_{stem}.json", log)
    a = usage["answered_by"]
    print(f"Done in {log['seconds_total']}s | calls {usage['calls_total']} (cached {usage['calls_cached']}) | "
          f"tokens {usage['prompt_tokens'] + usage['completion_tokens']} | cost ${usage['cost_usd']} | answered_by {a}")
    if len(a) > 1:
        print("WARNING: more than one model answered - scores may be inconsistent (see run log)")
    return log


def main() -> None:
    ap = argparse.ArgumentParser(description="AI Promo Finder - run the full pipeline.")
    ap.add_argument("--input", required=True, help="a script file, or a folder of script files")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--model", help="override llm.model from config.yaml, e.g. openai/gpt-4.1")
    ap.add_argument("--cold-model", help="use a different model for the stranger test, e.g. groq/openai/gpt-oss-20b")
    ap.add_argument("--no-cache", action="store_true", help="ignore saved AI answers")
    args = ap.parse_args()

    cfg = load_config(args.config)
    # A file = one show. A folder of episode files (ep01.txt, ep02.txt...) = one show.
    # A folder of show files or show sub-folders = several shows.
    shows = discover_shows(args.input)
    if not shows:
        raise SystemExit(f"No script files (.txt/.srt/.vtt/.md) found in {args.input}")

    logs = []
    for name, files in shows:
        try:
            logs.append(run_one(name, files, cfg, args.config, args.model, use_cache=not args.no_cache,
                                cold_model=args.cold_model))
        except Exception as e:   # one bad show shouldn't stop the others
            print(f"FAILED on {name}: {e}")
            logs.append({"show": name, "error": str(e)})

    print("\n=== Summary ===")
    for lg in logs:
        if "error" in lg:
            print(f"  {lg['show']}: ERROR {lg['error']}")
        else:
            print(f"  {lg['show']}: {lg['candidates']} promos ranked in {lg['seconds_total']}s, "
                  f"cost ${lg['usage']['cost_usd']} -> outputs/ranked_{lg['name']}.md")


if __name__ == "__main__":
    main()
