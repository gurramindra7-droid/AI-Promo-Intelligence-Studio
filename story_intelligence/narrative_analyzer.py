"""Connect promos to the story: who is in each clip, whether they are recurring characters, and what the
writers' logline says happens in that episode. Context-dependence is reported, not punished - some
promos deliberately open a mystery."""
from __future__ import annotations

import json

from database import repositories as R


def promo_context(con, project_id: int, promo: dict) -> dict:
    chars = {c["name"]: c for c in R.get_characters(con, project_id)}
    alias_of = {a: c["name"] for c in chars.values() for a in c["aliases"]}
    names = set(json.loads(promo.get("characters_json") or "[]"))
    text = " ".join(l.get("text", "") for l in json.loads(promo.get("lines_json") or "[]")).upper()
    for n in list(chars) + list(alias_of):          # names mentioned in action lines too
        if len(n) > 3 and n in text:
            names.add(alias_of.get(n, n))
    names = {alias_of.get(n, n) for n in names}
    ep = promo.get("episode")
    people = []
    for n in sorted(names):
        c = chars.get(n)
        if not c:
            continue
        people.append({"name": n, "episodes_present": len(c["episodes"]), "first_ep": c["first_ep"],
                       "recurring": len(c["episodes"]) >= 5, "introduced_before_clip": (c["first_ep"] or ep) < ep})
    episode = next((e for e in R.get_episodes(con, project_id) if e["number"] == ep), {})
    return {"characters": people, "episode_logline": episode.get("logline", ""),
            "episode_events": R.get_events(con, project_id, episode=ep),
            "depends_on_earlier_episodes": any(p["introduced_before_clip"] for p in people)}
