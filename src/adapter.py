"""
adapter.py - turn ANY supported script format into simple raw lines.

Why a separate adapter?
  Kuku's real screenplays, YouTube transcripts and subtitle files all look different.
  The adapter's only job is: "find the time, the speaker and the text on each line".
  Everything after it (parser, tagger, ...) sees ONE standard format, so adding a new
  input format later means touching only this file.

Rule: this is all CODE (regular expressions), no AI. Timestamps must come from the
source text exactly, so the AI can never invent a time.

Supported formats (auto-detected):
  1. youtube_copy - pasted from YouTube "Show transcript":  "1:031 minute, 3 secondsHey loser."
  2. timestamped  - "1:03 Hey loser."  "[1:03] Hey loser."  "00:01:03 ..."  "(00:12.5) ..."
                    time ranges too: "[00:12 - 00:15] ..."  "00:12 --> 00:15 ..."
  3. screenplay   - a timestamped file WITH speaker names (Kuku's input pack: "a timestamp
                    for every scene, line of dialogue and key action"):
                        [00:00] SCENE 1 - INT. SCHOOL HALLWAY - DAY
                        [00:03] BELLA: I don't know how I got here.
                        [00:07] (Chloe slaps Bella)           <- stage direction = action
                        [00:09] ADAM (O.S.)                    <- speaker on its own line,
                        Step aside.                            <- dialogue on the next line
                    In a screenplay, a timed line with no speaker is treated as ACTION
                    (description of what we see).
  4. srt / vtt    - subtitle files: "00:01:03,000 --> 00:01:05,500" then text lines
Plus, in any format:
  - header lines   "SHOW: ...", "LANGUAGE: en"         -> metadata (top of file only)
  - action notes   "[4:27] ACTION: He grabs her"       -> type=action
  - scene headings "SCENE 3 ...", "INT. ...", "EXT. ..." -> type=scene (never a cut point)
  - episode marks  "EPISODE 2" / "EP 2" / "[0:00] Episode 2: Title" -> starts a new episode
"""

from __future__ import annotations

import re
import sys
from collections import Counter

# Windows consoles often use an old code page (cp1252) and crash when printing
# characters the AI writes (e.g. a non-breaking hyphen). Every script imports this
# module, so print unknown characters as "?" instead of crashing.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

# ---------- time helpers ----------

def to_seconds(t: str) -> float:
    """'1:03' -> 63, '1:02:03' -> 3723, '00:01:03,500' -> 63.5"""
    t = t.strip().replace(",", ".")
    parts = [float(p) for p in t.split(":")]
    secs = 0.0
    for p in parts:
        secs = secs * 60 + p
    return secs


def fmt_time(s: float) -> str:
    """63 -> '1:03' (same style YouTube uses, so editors can find it)."""
    s = int(round(s))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


# ---------- patterns ----------

TIME = r"\d{1,2}(?::\d{2}){1,2}"
TIMEF = TIME + r"(?:[.,]\d{1,3})?"            # optional fractions: 00:12.5 / 00:12,500
# YouTube copy glues an accessibility label after the time: "1:03" + "1 minute, 3 seconds"
SPOKEN = r"(?:\d+\s+(?:hours?|minutes?|seconds?)(?:,\s*\d+\s+(?:minutes?|seconds?))*)"

RE_HEADER = re.compile(r"^([A-Z][A-Z _]{1,20}):\s*(.*)$")
RE_YT = re.compile(rf"^({TIME}){SPOKEN}\s*(.*)$")
# leading time, optional range, optional brackets, optional separator, then the rest
RE_TS = re.compile(rf"^[\[(]?\s*({TIMEF})\s*(?:(?:-->|-|–|—|to)\s*({TIMEF})\s*)?[\])]?\s*(?:[:|\-–—]\s+)?(.*)$")
RE_SRT_TIME = re.compile(rf"^({TIMEF})\s*-->\s*({TIMEF})")

RE_EPISODE = re.compile(r"^(?:EPISODE|EP\.?)\s*(\d+)\b\s*[:\-–—.]?\s*(.{0,80})$", re.I)
RE_ACTION = re.compile(r"^ACTION\s*:\s*(.+)$", re.I)
RE_SCENE = re.compile(r"^(SCENE\b|INT\.|EXT\.|INT/EXT\.?|I/E\.?)", re.I)
RE_PAREN = re.compile(r"^\((.+)\)$")
# "BELLA: text" / "Bella (V.O.): text" - up to 3 capitalised words before the colon
RE_SPEAKER = re.compile(r"^([A-Z][A-Za-z'.\-]*(?:\s+[A-Z][A-Za-z'.\-]*){0,2})\s*(\([^)]*\))?\s*:\s*(.*)$")
# speaker cue alone on a line: "ADAM" / "ADAM (O.S.)" / "ADAM (CONT'D)"
RE_CUE = re.compile(r"^([A-Z][A-Z'.\-]*(?:\s+[A-Z][A-Z'.\-]*){0,2})\s*(\([^)]*\))?$")
RESERVED = {"ACTION", "SCENE", "EPISODE", "EP", "INT", "EXT", "NOTE", "CUT", "FADE", "SHOW",
            "SOURCE", "TYPE", "LANGUAGE", "TITLE", "THE END", "OK", "NO", "OH", "WHAT"}


RE_K_BLOCK = re.compile(r"^\*\*(.+?):\*\*$")
RE_K_TIME = re.compile(rf"^Start:\s*\(({TIMEF})\)\s*\|\s*End:\s*\(({TIMEF})\)")
K_TYPES = {"CAMERA": "camera", "ACTION": "action", "SOUND FX": "sfx", "SFX": "sfx", "MUSIC": "sfx"}


def detect_format(lines: list[str]) -> str:
    if sum(1 for l in lines[:400] if RE_K_BLOCK.match(l.strip())) >= 5 and \
            sum(1 for l in lines[:400] if RE_K_TIME.match(l.strip())) >= 5:
        return "kuku_screenplay"
    body = [l.strip() for l in lines if l.strip() and not RE_HEADER.match(l.strip())]
    sample = body[:80]
    if any(RE_SRT_TIME.match(l) for l in sample):
        return "srt"
    yt = sum(1 for l in sample if RE_YT.match(l))
    ts = sum(1 for l in sample if RE_TS.match(l))
    if yt >= max(3, len(sample) * 0.3):
        return "youtube_copy"
    if ts >= max(3, len(sample) * 0.3):
        return "timestamped"
    return "unknown"


def _label_seconds(rest: str) -> float | None:
    """Read YouTube's spoken label ('1 minute, 3 seconds') to double-check the time."""
    m = re.match(SPOKEN, rest)
    if not m:
        return None
    total = 0
    for num, unit in re.findall(r"(\d+)\s+(hour|minute|second)", m.group(0)):
        total += int(num) * {"hour": 3600, "minute": 60, "second": 1}[unit]
    return total


def _classify(rest: str) -> tuple[str, dict]:
    """What kind of line is this text (after its timestamp was removed)?"""
    if m := RE_EPISODE.match(rest):
        return "episode_marker", {"ep": int(m.group(1)), "text": f"EPISODE {m.group(1)}"
                                  + (f": {m.group(2).strip()}" if m.group(2).strip() else "")}
    if m := RE_ACTION.match(rest):
        return "action", {"text": m.group(1).strip()}
    if RE_SCENE.match(rest):
        return "scene", {"text": rest}
    if m := RE_PAREN.match(rest):
        return "action", {"text": m.group(1).strip(), "paren": True}
    return "dialogue", {"text": rest}


def _apply_speakers(rows: list[dict]) -> bool:
    """Find speaker names. If enough lines have them, this is a SCREENPLAY:
    split 'NAME: text' into speaker + text, and treat speaker-less timed lines as action."""
    dlg = [r for r in rows if r["type"] == "dialogue"]
    names = Counter()
    for r in dlg:
        if r.get("cue"):
            names[r["cue"]] += 1
        elif (m := RE_SPEAKER.match(r["text"])) and m.group(1).upper() not in RESERVED:
            names[m.group(1)] += 1
    ok = {n for n, c in names.items() if c >= 2 or (n.isupper() and len(n) > 1)}
    with_speaker = sum(1 for r in dlg if (r.get("cue") in ok) or
                       ((m := RE_SPEAKER.match(r["text"])) and m.group(1) in ok))
    screenplay = with_speaker >= 3 and with_speaker >= 0.2 * max(1, len(dlg))
    if not screenplay:
        return False
    # Once we know it's a screenplay, accept every "Name: line" (also one-off characters
    # like "Stranger:"), and write names in capitals so "Ethan" and "ETHAN" are one person.
    for r in dlg:
        if r.get("cue"):
            r["speaker"] = r["cue"].upper()
            r["text"] = r["text"][len(r["cue"]):].strip()
            r["text"] = re.sub(r"^\([^)]*\)\s*", "", r["text"])      # drop "(O.S.)" etc.
        elif (m := RE_SPEAKER.match(r["text"])) and m.group(1).upper() not in RESERVED:
            r["speaker"], r["text"] = m.group(1).upper(), m.group(3).strip()
        elif not re.fullmatch(r"(\s*\[[^\]]*\]\s*)+", r["text"] or ""):
            r["type"] = "action"     # screenplay description line ("Chloe slaps Bella.")
    return True


def _adapt_kuku(raw_lines: list[str]) -> dict:
    """Kuku's screenplay format (the input pack), one file per episode:

        EPISODE NUMBER: Episode 1
        EPISODE LOGLINE: ...                      <- header -> meta
        --- SCRIPT START ---
        SCENE 01
        Scene heading: INT. GRAND HOTEL BALLROOM – NIGHT
        Scene start: 00:00.00
        **CAMERA:** / **ACTION:** / **SOUND FX:** / **MAYA (Confused, Breathless):**
        Start: (00:13.50) | End: (00:14.30)
        "Why?"
        --- SCRIPT END ---

    Every block has an exact start AND end time, so no end times are guessed.
    """
    meta: dict = {}
    rows: list[dict] = []
    warnings: list[str] = []
    in_script = False
    scene: dict = {}
    i, n_lines = 0, len(raw_lines)
    while i < n_lines:
        s = raw_lines[i].strip()
        n = i + 1                                   # 1-based source line number
        i += 1
        if not s:
            continue
        if s.startswith("--- SCRIPT START"):
            in_script = True
            continue
        if s.startswith("--- SCRIPT END"):
            break
        if not in_script:
            if h := re.match(r"^([A-Z][A-Za-z _]{1,30}):\s*(.*)$", s):
                meta[h.group(1).strip().lower().replace(" ", "_")] = h.group(2).strip()
            continue
        if re.match(r"^SCENE\s+\d+\s*$", s, re.I):
            scene = {"num": s.upper(), "heading": "", "src_line": n}
            continue
        if m := re.match(r"^scene heading:\s*(.*)$", s, re.I):
            scene["heading"] = m.group(1).strip()
            continue
        if m := re.match(rf"^scene start:\s*({TIMEF})", s, re.I):
            rows.append(dict(start=to_seconds(m.group(1)), end=None, type="scene", speaker=None,
                             text=f"{scene.get('num', 'SCENE')} - {scene.get('heading', '')}".strip(" -"),
                             src_line=n))
            continue
        if re.match(r"^(scene end:|actions and dialogue:)", s, re.I):
            continue
        if m := RE_K_BLOCK.match(s):
            label = m.group(1).strip()
            base = re.sub(r"\s*\(.*$", "", label).strip()
            notes = [p.strip() for p in re.findall(r"\(([^)]*)\)", label)]
            t = RE_K_TIME.match(raw_lines[i].strip()) if i < n_lines else None
            if not t:
                warnings.append(f"line {n}: block {label!r} has no 'Start: (..) | End: (..)' line - skipped")
                continue
            time_line = i + 1
            i += 1
            text_lines = []
            while i < n_lines and raw_lines[i].strip() and not RE_K_BLOCK.match(raw_lines[i].strip()):
                text_lines.append(raw_lines[i].strip())
                i += 1
            text = " ".join(text_lines).strip()
            kind = K_TYPES.get(base.upper(), "dialogue")
            if kind == "dialogue":
                text = text.strip('"“”')
            start, end = to_seconds(t.group(1)), to_seconds(t.group(2))
            if end < start:
                warnings.append(f"line {time_line}: end before start - end ignored")
                end = None
            rows.append(dict(start=start, end=end, type=kind,
                             speaker=base.upper() if kind == "dialogue" else None,
                             delivery="; ".join(x for x in notes if x) or None if kind == "dialogue" else None,
                             text=text, src_line=time_line))
            continue
        warnings.append(f"line {n}: unrecognised line skipped: {s[:60]!r}")
    return {"meta": meta, "format": "kuku_screenplay", "rows": rows, "warnings": warnings}


def adapt(text: str) -> dict:
    """Return {"meta", "format", "rows": [{start, end|None, type, text, speaker, ep?, src_line}], "warnings"}.

    rows are in file order. `end` is known only for srt, time ranges or Kuku screenplays;
    the parser fills the rest.
    """
    raw_lines = text.splitlines()
    fmt = detect_format(raw_lines)
    if fmt == "kuku_screenplay":
        return _adapt_kuku(raw_lines)
    if fmt == "unknown":
        raise ValueError(
            "Unknown script format: no timestamps found. Supported: YouTube transcript copy, "
            "'M:SS text' lines, timestamped screenplays (SPEAKER: line), SRT/VTT subtitles."
        )

    meta: dict = {}
    rows: list[dict] = []
    warnings: list[str] = []
    in_header = True
    pending_srt: dict | None = None

    for n, line in enumerate(raw_lines, start=1):
        s = line.strip()
        if not s:
            in_header = in_header and not rows
            continue

        # header lines only at the top
        h = RE_HEADER.match(s)
        if in_header and h and h.group(1).strip() not in RESERVED - {"SHOW", "SOURCE", "TYPE", "LANGUAGE", "TITLE"}:
            meta[h.group(1).strip().lower()] = h.group(2).strip()
            continue
        in_header = False

        if fmt == "srt":
            if m := RE_SRT_TIME.match(s):
                pending_srt = dict(start=to_seconds(m.group(1)), end=to_seconds(m.group(2)),
                                   type="dialogue", text="", speaker=None, src_line=n)
                rows.append(pending_srt)
            elif s.isdigit() or s.upper().startswith("WEBVTT"):
                continue  # cue number / file header
            elif pending_srt is not None:
                pending_srt["text"] = (pending_srt["text"] + " " + s).strip()
            continue

        # 1. find the time (if any) and the rest of the line
        start = end = None
        rest = s
        if fmt == "youtube_copy" and (m := RE_YT.match(s)):
            start, rest = to_seconds(m.group(1)), m.group(2).strip()
            label = _label_seconds(s[len(m.group(1)):])
            if label is not None and abs(label - start) > 1:
                warnings.append(f"line {n}: time {m.group(1)} disagrees with label ({label}s)")
        elif m := RE_TS.match(s):
            start, rest = to_seconds(m.group(1)), m.group(3).strip()
            end = to_seconds(m.group(2)) if m.group(2) else None
            if end is not None and end < start:
                warnings.append(f"line {n}: range end before start - end ignored")
                end = None

        # 2. what kind of line is it?
        kind, info = _classify(rest)
        if start is None and kind not in ("episode_marker", "scene"):
            # plain text with no time -> continuation of the previous line
            if rows and rows[-1]["type"] in ("dialogue", "action") and not rows[-1].get("closed"):
                rows[-1]["text"] = (rows[-1]["text"] + " " + s).strip()
            else:
                warnings.append(f"line {n}: text with no timestamp skipped: {s[:60]!r}")
            continue
        row = dict(start=start, end=end, type=kind, speaker=None, src_line=n, **info)
        if kind == "dialogue" and (c := RE_CUE.match(rest)) and c.group(1) not in RESERVED:
            row["cue"] = c.group(1)              # speaker alone on the line; text follows
        if kind in ("episode_marker", "scene") or info.get("paren"):
            row["closed"] = True                 # never glue following text onto these
        rows.append(row)

    screenplay = _apply_speakers(rows) if fmt == "timestamped" else False
    for r in rows:
        r.pop("cue", None), r.pop("closed", None), r.pop("paren", None)
    return {"meta": meta, "format": "screenplay" if screenplay else fmt, "rows": rows, "warnings": warnings}
