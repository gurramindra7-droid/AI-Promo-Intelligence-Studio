"""Characters from the screenplay's own speaker labels - exact facts, no AI.

    who speaks, how often, in which episodes, and who shares scenes with whom.
Alias suggestions (e.g. LADY ANNA ~ ANNA) are marked with their source and confidence;
they are suggestions, not facts.
"""
from __future__ import annotations

from collections import Counter, defaultdict

TITLES = {"LADY", "LORD", "SIR", "MISS", "MRS", "MR", "DUKE", "DUCHESS", "THE", "YOUNG", "OLD", "FATHER", "MOTHER"}


def speakers_by_episode(lines: list[dict]) -> dict[str, Counter]:
    out: dict[str, Counter] = defaultdict(Counter)
    for l in lines:
        if l.get("speaker"):
            out[l["speaker"]][l["ep"]] += 1
    return out


def scenes(lines: list[dict]) -> list[tuple[int, set[str]]]:
    """(episode, speakers) per scene; a scene starts at each 'scene' line (or each episode)."""
    out, cur, ep = [], set(), None
    for l in lines:
        if l["type"] == "scene" or l["ep"] != ep:
            if cur:
                out.append((ep, cur))
            cur, ep = set(), l["ep"]
        if l.get("speaker"):
            cur.add(l["speaker"])
    if cur:
        out.append((ep, cur))
    return out


def co_occurrence(lines: list[dict]) -> dict[tuple[str, str], dict]:
    pairs: dict[tuple[str, str], dict] = {}
    for ep, who in scenes(lines):
        for a in who:
            for b in who:
                if a < b:
                    p = pairs.setdefault((a, b), {"scenes": 0, "episodes": set()})
                    p["scenes"] += 1
                    p["episodes"].add(ep)
    return pairs


def heuristic_aliases(names: list[str], counts: dict[str, int]) -> dict[str, list[str]]:
    """'LADY ANNA' -> alias of 'ANNA' when the name minus a title equals another speaker.
    The canonical name is the one with more lines."""
    groups: dict[str, set[str]] = defaultdict(set)
    name_set = set(names)
    for n in names:
        core = " ".join(w for w in n.split() if w not in TITLES)
        if core and core != n and core in name_set:
            canon, alias = (core, n) if counts.get(core, 0) >= counts.get(n, 0) else (n, core)
            groups[canon].add(alias)
    return {k: sorted(v) for k, v in groups.items()}
