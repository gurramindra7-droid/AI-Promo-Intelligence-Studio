"""
verify_outputs.py - an INDEPENDENT check of the final promos against the raw script file.

It does not use parser.py. It re-reads the original file line by line and checks that
every ranked promo is correct, so a bug in the pipeline can't hide behind itself.

Checks for every promo:
  1. each segment's start time = the time written on that line of the raw file
  2. the hook text (first line) and cliffhanger text (last line) are really on those lines
  3. segments are in order and don't overlap; total length is 20-60 seconds
  4. the end of each segment is not past the next caption's start (cut doesn't spill over)
  5. no two promos overlap more than the allowed amount
  6. ranks are 1..N and the stranger test ran for every promo
  7. the stranger only saw promo text - no timestamps, no show name

Run:  python eval/verify_outputs.py data/screenplays/dragons_bride.txt
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from cold_viewer import promo_text   # noqa: E402  (only to rebuild what the stranger saw)
from llm import load_config          # noqa: E402
from parser import show_name         # noqa: E402  (only to find the output file names)

# a time at the very start of a raw line: 1:03 / [00:12] / (00:12.5) / [00:04.0 - 00:07.5]
RAW_TIME = re.compile(r"^(?:Start:\s*)?[\[(]?\s*(\d{1,2}(?::\d{2}){1,2}(?:[.,]\d{1,3})?)")


# an end time written on the line: "End: (01:55.70)" (Kuku) or "[00:04.0 - 00:07.5]" / "-->" (ranges, SRT)
RAW_END = re.compile(r"(?:End:\s*\(|(?:-->|\s-\s|–|—)\s*)(\d{1,2}(?::\d{2}){1,2}(?:[.,]\d{1,3})?)")


def secs(t: str) -> float:
    s = 0.0
    for p in t.replace(",", ".").split(":"):
        s = s * 60 + float(p)
    return s


def main(script: str) -> int:
    stem = show_name(script)
    promos = json.loads((ROOT / "outputs" / f"ranked_{stem}.json").read_text(encoding="utf-8"))["promos"]
    timeline = json.loads((ROOT / "outputs" / f"timeline_{stem}.json").read_text(encoding="utf-8"))
    by_id = {l["id"]: l for l in timeline["lines"]}
    cfg = load_config(ROOT / "config.yaml")
    show = timeline["meta"].get("show", "")
    starts_sorted = sorted({l["start"] for l in timeline["lines"] if l["type"] in ("dialogue", "sound")})

    files: dict[str, list[str]] = {}
    def raw_of(line: dict) -> list[str]:
        """The raw source file this line came from (episode files may differ)."""
        f = line.get("src_file") or script
        if f not in files:
            files[f] = Path(f).read_text(encoding="utf-8-sig").splitlines()
        return files[f]

    def text_on_raw(line: dict, text: str) -> bool:
        """Text must appear on its raw line (or the next few, for multi-line dialogue)."""
        raw = raw_of(line)
        window = " ".join(x.strip() for x in raw[line["src_line"] - 1: line["src_line"] + 3])
        return text[:40] in window

    errors: list[str] = []
    def err(msg): errors.append(msg)

    for c in promos:
        tag = f"#{c['rank']} {c['cand_id']}"
        prev_end = -1.0
        for s in c["segments"]:
            first, last = by_id[s["first_id"]], by_id[s["last_id"]]
            # 1. start time equals the time printed on the raw source line (episode time)
            raw_line = raw_of(first)[first["src_line"] - 1].strip()
            m = RAW_TIME.match(raw_line)
            ep_start = s.get("ep_start", s["start"])
            if not m or abs(secs(m.group(1)) - ep_start) > 0.01:
                err(f"{tag}: start {ep_start} != raw line {first['src_line']}: {raw_line[:40]!r}")
            if first["ep"] != last["ep"]:
                err(f"{tag}: segment runs across episodes {first['ep']}->{last['ep']}")
            # 4. the end time. If the script WRITES an end ("End: (01:55.70)", "[00:04 - 00:07]"),
            #    the cut must end exactly there (screenplay lines may overlap the next line).
            #    If it doesn't (captions), the cut must not spill past the next line's start.
            last_raw = raw_of(last)[last["src_line"] - 1]
            written_end = RAW_END.search(last_raw)
            ep_end = s.get("ep_end", s["end"])
            if written_end:
                if abs(secs(written_end.group(1)) - ep_end) > 0.01:
                    err(f"{tag}: end {ep_end} != end written in the script ({written_end.group(1)})")
            else:
                nxt = next((t for t in starts_sorted if t > last["start"]), None)
                if nxt is not None and s["end"] > nxt + 1e-6:
                    err(f"{tag}: segment end {s['end']} spills past next caption at {nxt}")
            # 3. order / no overlap
            if s["start"] < prev_end:
                err(f"{tag}: segments overlap or out of order")
            prev_end = s["end"]
        # 2. hook / cliff text really on those raw lines
        h, cl = by_id[c["hook_id"]], by_id[c["cliff_id"]]
        if not text_on_raw(h, c["hook_text"]):
            err(f"{tag}: hook text not found on raw line {h['src_line']}")
        if not text_on_raw(cl, c["cliff_text"]):
            err(f"{tag}: cliff text not found on raw line {cl['src_line']}")
        if c["hook_id"] != c["segments"][0]["first_id"] or c["cliff_id"] != c["segments"][-1]["last_id"]:
            err(f"{tag}: hook/cliff are not the first/last line")
        # 3. length
        d = sum(s["end"] - s["start"] for s in c["segments"])
        if not cfg["promo"]["min_seconds"] <= d <= cfg["promo"]["max_seconds"] or abs(d - c["duration"]) > 0.11:
            err(f"{tag}: duration {d:.1f}s (reported {c['duration']})")
        # 6. stranger test ran
        if not c["cold"].get("cold_ok"):
            err(f"{tag}: stranger test failed: {c['cold'].get('cold_error', '')[:80]}")
        # 7. stranger saw no times / show name
        seen = promo_text(c)
        if re.search(r"\b\d{1,2}:\d{2}\b", seen) or (show and show.lower() in seen.lower()):
            err(f"{tag}: stranger prompt leaks a timestamp or the show name")

    # 5. overlap between promos
    def ov(a, b):
        sh = sum(max(0, min(x["end"], y["end"]) - max(x["start"], y["start"])) for x in a for y in b)
        return sh / min(sum(x["end"] - x["start"] for x in a), sum(y["end"] - y["start"] for y in b))
    for i, a in enumerate(promos):
        for b in promos[i + 1:]:
            if ov(a["segments"], b["segments"]) > cfg["promo"]["max_overlap"] + 1e-6:
                err(f"{a['cand_id']} and {b['cand_id']} overlap more than {cfg['promo']['max_overlap']}")
    # 6. ranks
    if [c["rank"] for c in promos] != list(range(1, len(promos) + 1)):
        err("ranks are not 1..N")

    print(f"Checked {len(promos)} promos against the raw file {Path(script).name}")
    if errors:
        print(f"FAILED: {len(errors)} problem(s)")
        for e in errors:
            print("  -", e)
        return 1
    print("ALL CHECKS PASSED: times, texts, order, length, overlap, ranks, stranger blindness")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "data/screenplays/dragons_bride.txt"))
