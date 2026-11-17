"""Events and relationships extracted by the AI from the writers' EPISODE LOGLINES (one short summary
per episode in Kuku's screenplays) - 10 episodes per call, so 50 episodes cost ~5 calls.

Grounding rules, enforced in code after the AI answers:
  * every event keeps its source episode;
  * character names are matched against the script's real speakers (and aliases); unknown names are
    removed and the event is marked unverified with lower confidence - never added as new characters;
  * relationships are kept only when both people are real speakers.
"""
from __future__ import annotations

import re

from agents.base import call, clamp

EVENT_TYPES = ["conflict", "revelation", "betrayal", "romance", "alliance", "threat", "rescue",
               "transformation", "decision", "other"]
RELATIONS = ["family", "romantic", "rivals", "allies", "conflict", "employer", "unknown"]

SYSTEM = f"""You extract story facts for a promo team. You get the writers' one-line summary (logline) of each
episode of a microdrama, plus the list of KNOWN CHARACTERS (speaker names from the script).
For each episode give its main events and any relationship the logline STATES. Do not guess or infer
relationships that are not stated. Use character names exactly as in KNOWN CHARACTERS when you can.

event_type: one of {EVENT_TYPES}. importance: integer 1-5. relation: one of {RELATIONS}.
evidence: the logline words that state the relationship.
Reply with JSON only: {{"episodes": [{{"episode": 1, "events": [{{"description": "...", "event_type": "conflict",
"importance": 3, "characters_involved": ["NAME"]}}], "relationships": [{{"a": "NAME", "b": "NAME",
"relation": "rivals", "evidence": "..."}}]}}]}}"""


def build_prompt(batch: list[dict], known: list[str]) -> str:
    out = ["KNOWN CHARACTERS: " + ", ".join(known), ""]
    out += [f"EPISODE {e['number']}: {e['logline']}" for e in batch]
    return "\n".join(out)


def validator(eps: set[int]):
    def check(d):
        if not isinstance(d, dict) or not isinstance(d.get("episodes"), list):
            return 'Top level must be {"episodes": [...]}.'
        got = {e.get("episode") for e in d["episodes"] if isinstance(e, dict)}
        if not got <= eps:
            return f"Only use the listed episode numbers {sorted(eps)}."
        return True
    return check


class NameMatcher:
    """Map a name the AI wrote ('Anna', 'Lady Anna') to a real speaker ('ANNA')."""

    def __init__(self, speakers: list[str], aliases: dict[str, list[str]]):
        self.map: dict[str, str] = {}
        for s in speakers:
            self.map[self.key(s)] = s
        for canon, al in aliases.items():
            for a in al:
                self.map[self.key(a)] = canon

    @staticmethod
    def key(n: str) -> str:
        return re.sub(r"[^A-Z ]", "", str(n).upper()).strip()

    def match(self, name: str) -> str | None:
        k = self.key(name)
        if k in self.map:
            return self.map[k]
        words = k.split()
        hits = {v for kk, v in self.map.items() if words and kk.split()[-1:] == words[-1:]}
        return hits.pop() if len(hits) == 1 else None


def extract(llm, episodes: list[dict], matcher: NameMatcher, known: list[str], batch_size: int = 10):
    """Yields (episode, event_dict) and (episode, relationship_dict) records, already grounded."""
    events, rels = [], []
    usable = [e for e in episodes if (e.get("logline") or "").strip()]
    for i in range(0, len(usable), batch_size):
        batch = usable[i:i + batch_size]
        d = call(llm, build_prompt(batch, known), SYSTEM, "story_events", validator({e["number"] for e in batch}))
        for ep in d["episodes"]:
            n = ep["episode"]
            for ev in ep.get("events", []) or []:
                raw = [str(c) for c in ev.get("characters_involved", []) or []]
                matched = [m for m in (matcher.match(c) for c in raw) if m]
                verified = len(matched) == len(raw)
                events.append({"episode": n, "description": str(ev.get("description", ""))[:240],
                               "event_type": ev.get("event_type") if ev.get("event_type") in EVENT_TYPES else "other",
                               "importance": int(clamp(ev.get("importance", 3), 1, 5)),
                               "characters": sorted(set(matched)), "verified": verified,
                               "confidence": 0.7 if verified else 0.4, "source": f"logline:ep{n}"})
            for r in ep.get("relationships", []) or []:
                a, b = matcher.match(r.get("a", "")), matcher.match(r.get("b", ""))
                if a and b and a != b:
                    rels.append({"episode": n, "a": a, "b": b,
                                 "relation": r.get("relation") if r.get("relation") in RELATIONS else "unknown",
                                 "evidence": str(r.get("evidence", ""))[:200], "confidence": 0.6,
                                 "source": f"llm:logline:ep{n}"})
    return events, rels
