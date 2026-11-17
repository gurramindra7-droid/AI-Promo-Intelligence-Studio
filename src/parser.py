"""
parser.py - raw rows from the adapter  ->  the STANDARD TIMELINE every later step uses.

Each timeline line:
    {"id": "L007", "ep": 1, "start": 33.0, "end": 40.0, "ep_start": 33.0, "ep_end": 40.0,
     "type": "dialogue", "speaker": "BELLA", "text": "Excuse me...", "src_file": ..., "src_line": 12}

Two kinds of time:
    ep_start / ep_end : the time written in the script for that episode (what an editor uses)
    start / end       : one continuous show clock (episode 2 starts after episode 1 ends).
                        Used inside the pipeline for lengths, overlaps and ordering, so
                        episodes whose times restart at 0:00 never get mixed up.
For a single video/compilation the two are the same.

Why ids?  Later the AI answers with line ids ("hook is L045"), never with times.
Code then looks the id up here to get the times. So every timestamp in the final
output is copied from the source file - the AI cannot invent one.

Types:  dialogue | sound ("[music]" alone) | action | scene | episode_marker

Shows can be:
    one file                    -> one show (episodes inside marked "EPISODE 2", or a compilation)
    a folder of episode files   -> one show, e.g. kuku_show/ep01.txt, ep02.txt ... (ep from filename)
    a folder of show files      -> each file is a show
    a folder of show folders    -> each sub-folder is a show

Run on its own to check a file or folder:
    python src/parser.py data/screenplays/dragons_bride.txt
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from adapter import adapt, fmt_time

MAX_LINE_SECONDS = 12.0   # a caption rarely lasts longer; a longer gap is silence/action
WORDS_PER_SECOND = 2.5    # to estimate how long the last line lasts
ACTION_SECONDS = 2.0      # an action note marks a moment, not a span
SCRIPT_EXT = {".txt", ".srt", ".vtt", ".md"}
RE_EP_NAME = re.compile(r"(?:^|[^a-z])(?:ep|episode|e)[\s_\-.]*0*(\d{1,3})(?!\d)", re.I)

RE_ONLY_TAGS = re.compile(r"^(\s*\[[^\]]*\]\s*)+$")


def _speech_seconds(text: str) -> float:
    return max(1.5, len(text.split()) / WORDS_PER_SECOND)


def _fill_group(rows: list[dict], warnings: list[str]) -> list[dict]:
    """Sort one episode's rows by time and fill in missing end times (episode-local)."""
    order = {"episode_marker": 0, "scene": 1, "camera": 2, "dialogue": 2, "sound": 2, "sfx": 2, "action": 3}
    rows = sorted(rows, key=lambda r: (r["start"], order.get(r["type"], 2)))   # stable sort
    for r in rows:
        if r["type"] == "dialogue":
            if not r["text"]:
                warnings.append(f"src line {r['src_line']}: empty line dropped")
                r["type"] = "_drop"
            elif RE_ONLY_TAGS.match(r["text"]):
                r["type"] = "sound"
    rows = [r for r in rows if r["type"] != "_drop"]

    # A line ends when the next spoken line starts (capped). Actions are short moments.
    timed = [r for r in rows if r["type"] in ("dialogue", "sound", "action")]
    spoken = [r for r in rows if r["type"] in ("dialogue", "sound")]
    for i, r in enumerate(spoken):
        if r.get("end") is not None:
            continue
        nxt = spoken[i + 1]["start"] if i + 1 < len(spoken) else None
        est = r["start"] + _speech_seconds(r["text"])
        if nxt is None:
            r["end"] = est
        else:
            r["end"] = min(nxt, r["start"] + MAX_LINE_SECONDS)
            if nxt - r["start"] > MAX_LINE_SECONDS:
                warnings.append(f"gap {fmt_time(r['start'])}->{fmt_time(nxt)} "
                                f"({nxt - r['start']:.0f}s with no caption; likely action/music)")
    for r in rows:
        if r.get("end") is None:
            if r["type"] == "action":
                nxt = next((x["start"] for x in timed if x["start"] > r["start"]), None)
                r["end"] = r["start"] + ACTION_SECONDS if nxt is None else min(nxt, r["start"] + ACTION_SECONDS)
                r["end"] = max(r["end"], r["start"])
            else:   # scene headings / episode markers are points in time
                r["end"] = r["start"]
    return rows


def build_timeline(text: str, source: str = "", default_ep: int = 1, clock_offset: float = 0.0) -> dict:
    a = adapt(text)
    rows = a["rows"]
    warnings = list(a["warnings"])
    # Kuku files say "EPISODE NUMBER: Episode 7" in their header - trust that over the file name.
    if m := re.search(r"\d+", a["meta"].get("episode_number", "")):
        default_ep = int(m.group(0))

    # Untimed markers / scene headings take the time of the next timed row.
    for i, r in enumerate(rows):
        if r["start"] is None:
            nxt = next((x["start"] for x in rows[i + 1:] if x["start"] is not None), None)
            r["start"] = nxt if nxt is not None else (rows[i - 1]["start"] if i else 0.0)

    # Split into episodes in FILE order (an "EPISODE n" line starts a new one).
    groups: list[dict] = [{"ep": default_ep, "rows": []}]
    for r in rows:
        if r["type"] == "episode_marker":
            if groups[-1]["rows"]:
                groups.append({"ep": r["ep"], "rows": [r]})
            else:
                groups[-1] = {"ep": r["ep"], "rows": [r]}
        else:
            groups[-1]["rows"].append(r)
    groups = [g for g in groups if g["rows"]]

    # Each episode: sort + fill ends. If an episode's times restart (e.g. every episode
    # starts at 0:00), move it onto the show clock after the previous episode.
    lines: list[dict] = []
    offset, prev_max_start, prev_end_clock = clock_offset, None, clock_offset
    restarts = False
    for g in groups:
        grows = _fill_group(g["rows"], warnings)
        if not grows:
            continue
        first = min(r["start"] for r in grows)
        if prev_max_start is not None and first < prev_max_start:
            offset = prev_end_clock       # times restarted -> continue after previous episode
            restarts = True
        for r in grows:
            lines.append({
                "id": "", "ep": g["ep"],
                "start": round(r["start"] + offset, 2), "end": round(r["end"] + offset, 2),
                "ep_start": round(r["start"], 2), "ep_end": round(r["end"], 2),
                "type": r["type"], "speaker": r.get("speaker"), "text": r["text"],
                **({"delivery": r["delivery"]} if r.get("delivery") else {}),
                "src_file": source, "src_line": r["src_line"],
            })
        prev_max_start = max(r["start"] for r in grows)
        prev_end_clock = max(x["end"] for x in lines)

    for i, x in enumerate(lines, 1):
        x["id"] = f"L{i:03d}"

    # Sanity checks - fail loudly rather than produce wrong timestamps later.
    for x in lines:
        assert x["end"] >= x["start"], f"{x['id']} ends before it starts"
    starts = [x["start"] for x in lines]
    assert starts == sorted(starts), "timeline not in time order"

    meta = dict(a["meta"])
    meta.update(source_file=Path(source).name if source else "", format=a["format"],
                has_episode_markers=len(groups) > 1 or any(x["type"] == "episode_marker" for x in lines),
                episodes=sorted({x["ep"] for x in lines}), times_restart_per_episode=restarts,
                duration_seconds=round(max((x["end"] for x in lines), default=0) - clock_offset, 1),
                counts={t: sum(1 for x in lines if x["type"] == t)
                        for t in ("dialogue", "sound", "action", "scene", "camera", "sfx", "episode_marker")},
                speakers=sorted({x["speaker"] for x in lines if x["speaker"]}))
    if a["meta"].get("episode_logline"):
        meta["episodes_info"] = {str(g["ep"]): {"logline": a["meta"].get("episode_logline", ""),
                                                "continuity_notes": a["meta"].get("continuity_notes", "")}
                                 for g in groups[:1]}
    return {"meta": meta, "lines": lines, "warnings": warnings}


def parse_file(path: str | Path) -> dict:
    path = Path(path)
    m = RE_EP_NAME.search(path.stem)
    return build_timeline(path.read_text(encoding="utf-8-sig"), source=str(path),
                          default_ep=int(m.group(1)) if m else 1)


# ---------- shows: one file, or a folder of episode files ----------

def _is_episode_set(files: list[Path]) -> bool:
    """All file names carry an episode number (ep01.txt, Episode_2.txt, 03.txt ...)."""
    return len(files) >= 2 and all(RE_EP_NAME.search(f.stem) or re.fullmatch(r"\d{1,3}", f.stem) for f in files)


def _ep_num(f: Path) -> int:
    m = RE_EP_NAME.search(f.stem)
    return int(m.group(1)) if m else int(re.fullmatch(r"\d{1,3}", f.stem).group(0))


def discover_shows(inp: str | Path) -> list[tuple[str, list[Path]]]:
    """Return [(show_name, [script files in episode order])]."""
    inp = Path(inp)
    if inp.is_file():
        return [(inp.stem, [inp])]
    files = sorted(f for f in inp.iterdir() if f.is_file() and f.suffix.lower() in SCRIPT_EXT)
    subdirs = sorted(d for d in inp.iterdir() if d.is_dir() and not d.name.startswith("."))
    shows: list[tuple[str, list[Path]]] = []
    if _is_episode_set(files):
        shows.append((inp.name, sorted(files, key=_ep_num)))
    else:
        shows += [(f.stem, [f]) for f in files]
    for d in subdirs:
        sub = sorted(f for f in d.iterdir() if f.is_file() and f.suffix.lower() in SCRIPT_EXT)
        if sub:
            shows.append((d.name, sorted(sub, key=_ep_num) if _is_episode_set(sub) else sub))
    return shows


def parse_show(name: str, files: list[Path]) -> dict:
    """Parse one show. Several files = episodes, joined onto one show clock."""
    if len(files) == 1:
        tl = parse_file(files[0])
        tl["meta"].setdefault("show", name)
        return tl
    lines, warnings, meta, clock, ep_info = [], [], {}, 0.0, {}
    for f in files:
        m = RE_EP_NAME.search(f.stem)
        ep = int(m.group(1)) if m else _ep_num(f)
        tl = build_timeline(f.read_text(encoding="utf-8-sig"), source=str(f), default_ep=ep, clock_offset=clock)
        if not meta:
            meta = {k: v for k, v in tl["meta"].items()
                    if k not in ("episode_number", "episode_logline", "continuity_notes", "episodes_info")}
        ep_info.update(tl["meta"].get("episodes_info", {}))
        warnings += [f"{f.name}: {w}" for w in tl["warnings"]]
        lines += tl["lines"]
        clock = max((x["end"] for x in lines), default=clock)
    for i, x in enumerate(lines, 1):
        x["id"] = f"L{i:03d}"
    # Optional show_info.yaml next to the episodes, e.g.  show: "My Show Title"
    info_p = files[0].parent / "show_info.yaml"
    if info_p.exists():
        import yaml
        meta.update(yaml.safe_load(info_p.read_text(encoding="utf-8")) or {})
    meta.update(show=meta.get("show", name), source_file=f"{len(files)} episode files",
                has_episode_markers=True, episodes=sorted({x["ep"] for x in lines}),
                times_restart_per_episode=True, duration_seconds=round(clock, 1),
                counts={t: sum(1 for x in lines if x["type"] == t)
                        for t in ("dialogue", "sound", "action", "scene", "camera", "sfx", "episode_marker")},
                speakers=sorted({x["speaker"] for x in lines if x["speaker"]}))
    if ep_info:
        meta["episodes_info"] = ep_info
    return {"meta": meta, "lines": lines, "warnings": warnings}


def show_name(inp: str | Path) -> str:
    """Name used for output files: file stem, or folder name for a folder of episodes."""
    return discover_shows(inp)[0][0]


def load_show(inp: str | Path) -> dict:
    """Parse the (first) show found at a file or folder path."""
    return parse_show(*discover_shows(inp)[0])


def find_line(timeline: dict, line_id: str) -> dict | None:
    """Look up a line by id. Later steps use this to turn AI-chosen ids into real times."""
    for x in timeline["lines"]:
        if x["id"] == line_id:
            return x
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description="Parse a script (file or folder) into the standard timeline.")
    ap.add_argument("input")
    ap.add_argument("--show", type=int, default=8, help="how many lines to print")
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    for name, files in discover_shows(args.input):
        tl = parse_show(name, files)
        m = tl["meta"]
        print(f"\nShow:     {m.get('show', name)}   ({m.get('language', '?')})   files: {len(files)}")
        print(f"Format:   {m['format']}   episodes: {m['episodes'][:10]}{'...' if len(m['episodes']) > 10 else ''}"
              f"   times restart per episode: {m['times_restart_per_episode']}")
        print(f"Length:   {fmt_time(m['duration_seconds'])}   lines: {m['counts']}")
        if m["speakers"]:
            print(f"Speakers: {', '.join(m['speakers'][:12])}")
        print(f"Warnings: {len(tl['warnings'])}")
        for w in tl["warnings"][:6]:
            print("   -", w)
        for x in tl["lines"][: args.show]:
            who = f"{x['speaker']}: " if x["speaker"] else ""
            print(f"   {x['id']} ep{x['ep']} {fmt_time(x['ep_start']):>6}-{fmt_time(x['ep_end']):<6} "
                  f"{x['type']:<9} {who}{x['text'][:60]}")
        out = root / "outputs" / f"timeline_{name}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(tl, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Saved:    {out}")


if __name__ == "__main__":
    main()
