"""
tagger.py - Step 3: the AI reads the script and scores every line ("beat").

For each line the AI gives:
    hook          0-5  would this stop a scrolling stranger in the first 3 seconds?
    cliff         0-5  is this a good place to CUT so the viewer needs to know what's next?
    needs_context 0-5  how much backstory a stranger needs to understand it (5 = lost)
    archetype          what kind of moment it is (slap, reveal, humiliation, ...)
    reason             a few words, so a human can check the AI's thinking

Why score lines and not ask "give me promos"?
  * The AI only judges meaning. It answers with line ids (L045), never times.
    Code (candidates.py) turns ids into start/end using the parser's timeline,
    so timestamps can't be invented.
  * Small, checkable judgements per line are easier to validate and evaluate than
    one big creative answer.

Chunking: one AI call per episode (or per ~4-minute window if the script has no
episode markers). The last few lines of the previous chunk are sent as read-only
context, so the AI knows what just happened. Every chunk is cached by llm.py.

Run:
    python src/tagger.py data/screenplays/dragons_bride.txt
(prints only a summary - use --show to print scores AFTER your answer key is written)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from adapter import fmt_time
from llm import LLM, LLMError
from parser import load_show, show_name

ARCHETYPES = [
    "slap_violence",        # physical hit, fight, grab
    "reveal_secret",        # hidden identity, secret exposed, shocking truth
    "humiliation",          # public shaming, bullying, insult
    "power_flip",           # underdog wins, revenge, status reversal
    "threat_danger",        # someone in danger, threat, attack
    "supernatural",         # transformation, powers, curse
    "romance_tension",      # kiss, jealousy, forbidden attraction, "mate"
    "betrayal",             # cheating, backstab, lie discovered
    "family_pregnancy",     # pregnancy, child, family shock
    "confession",           # love/guilt confession, ultimatum
    "setup",                # exposition, introductions, transitions
    "other",
]

WINDOW_SECONDS = 240      # chunk size when the script has no episode markers
CONTEXT_LINES = 6         # previous lines shown read-only
MAX_CHUNK_CHARS = 6000# episode-based scripts: max script text per AI call (free-tier token limits)

SYSTEM = """You are a senior promo editor for vertical microdramas (1-2 minute episodes, like ReelShort and DramaBox).
Your job: read a script and score each line as a possible START (hook) or END (cliffhanger) of a 20-60 second social media promo.

Definitions (from the brief):
- HOOK: something in the first 3 seconds that makes a scrolling stranger stop - a slap, a reveal, a shocking line, sudden danger.
- CLIFFHANGER: a moment to CUT on that is unresolved, so the viewer must know what happens next - a question, threat, reveal mid-sentence, someone about to act.
- A promo must make sense to someone who has never seen the show.

Scoring (integers 0-5):
- hook: 5 = instantly stops the scroll on its own; 3 = interesting; 0 = filler/exposition.
- cliff: 5 = perfect cut point, strong unresolved tension; 0 = resolved, calm or mid-thought filler.
- needs_context: 0 = a stranger understands it immediately; 5 = meaningless without backstory.

Rules:
- Score ONLY lines listed under SCORE THESE LINES, using their exact ids. Never invent ids. Never output times.
- Lines starting with ACTION are human notes of what happens on screen - trust them, they are often the strongest hooks.
- Captions may be auto-generated: no speaker names, some wrong words, tags like [music]. Judge the intended meaning.
- Be strict: most lines are 0-2. Reserve 4-5 for genuinely strong moments.
- archetype must be one of: {archetypes}
- reason: max 12 words.

Reply with JSON only:
{{"beats": [{{"id": "L001", "hook": 0, "cliff": 0, "needs_context": 0, "archetype": "setup", "reason": "..."}}, ...]}}"""

# Long screenplays (episode-based scripts, e.g. Kuku's 50-episode pack): same task, COMPACT
# reply - one short list per line, a reason only for strong lines. Cuts output tokens ~3x so
# a whole show fits a free tier's daily token budget. (YouTube compilations keep SYSTEM above,
# so their saved answers stay valid.)
SYSTEM_COMPACT = SYSTEM.split("Reply with JSON only:")[0].replace(
    "- Be strict: most lines are 0-2. Reserve 4-5 for genuinely strong moments.",
    "- Use the FULL 0-5 range within each part: its 2-3 strongest hook moments get hook 4-5 and its "
    "2-3 strongest cut points get cliff 4-5; filler and camera-like description get 0-1.").replace(
    "- reason: max 12 words.",
    "- reason: max 10 words, ONLY when hook >= 3 or cliff >= 3; otherwise an empty string.") + \
    """Reply with JSON only, one list per line in this exact order [id, hook, cliff, needs_context, archetype, reason]:
{{"b": [["L001", 0, 1, 2, "setup", ""], ["L002", 4, 1, 1, "slap_violence", "public slap in front of guests"], ...]}}"""


def normalize(data) -> dict:
    """Accept every reply shape the models use - {"b": [[...]]}, {"beats": [{...}]}, rows as
    lists or objects, or a bare list - and always return {"beats": [{id, hook, cliff, ...}]}.
    (A model once answered {"beats": [[...]]}, which crashed a strict reader.)"""
    if isinstance(data, list):
        data = {"b": data}
    if not isinstance(data, dict):
        return data
    rows = data.get("b") if isinstance(data.get("b"), list) else data.get("beats")
    if not isinstance(rows, list):
        return data
    beats = []
    for row in rows:
        if isinstance(row, dict):
            beats.append(row)
        elif isinstance(row, list) and len(row) >= 5:
            beats.append({"id": row[0], "hook": row[1], "cliff": row[2], "needs_context": row[3],
                          "archetype": row[4], "reason": row[5] if len(row) > 5 else ""})
        else:
            beats.append({"id": None})      # caught by the validator below
    return {"beats": beats}

def make_chunks(lines: list[dict], has_markers: bool) -> list[list[dict]]:
    """Group timeline lines: by episode if marked, else by time window."""
    # CAMERA lines (Kuku screenplays) describe shots, not moments: not scored, keeps prompts small.
    usable = [l for l in lines if l["type"] not in ("episode_marker", "camera")]
    chunks: list[list[dict]] = []
    for l in usable:
        if not chunks:
            chunks.append([l])
            continue
        first = chunks[-1][0]
        span = l["start"] - first["start"]
        if has_markers:
            # Kuku episodes are 1-2 min: group whole episodes into ~4-minute parts
            # (50 episodes -> ~20 calls, not 50); split a very long episode too.
            # Size cap: free tiers limit tokens per minute (Groq: 8,000), and one request
            # must fit under it. ~6,000 characters of script per call (~1,500 tokens) is safe;
            # prefer to cut at an episode boundary once a part is 3/4 full.
            size = sum(len(x["text"]) + 30 for x in chunks[-1])
            new = (l["ep"] != chunks[-1][-1]["ep"] and (span >= WINDOW_SECONDS or size >= 0.75 * MAX_CHUNK_CHARS)) \
                or span >= 2 * WINDOW_SECONDS or size >= MAX_CHUNK_CHARS
        else:
            new = span >= WINDOW_SECONDS
        if new:
            chunks.append([l])
        else:
            chunks[-1].append(l)
    return chunks


def _fmt_line(l: dict, show_ep: bool = False) -> str:
    ep = f"[Ep{l['ep']}] " if show_ep else ""
    who = ""
    if l.get("speaker"):   # Kuku screenplays also give the delivery: "MAYA (Desperate): ..."
        who = f"{l['speaker']} ({l['delivery']}): " if l.get("delivery") else f"{l['speaker']}: "
    if l["type"] == "action":
        return f"{l['id']} | {ep}ACTION: {l['text']}"
    if l["type"] == "scene":
        return f"{l['id']} | {ep}SCENE: {l['text']}"
    if l["type"] == "sfx":
        return f"{l['id']} | {ep}SOUND: {l['text']}"
    return f"{l['id']} | {ep}{who}{l['text']}"


def build_prompt(meta: dict, chunk: list[dict], context: list[dict], idx: int, total: int) -> str:
    marked = meta.get("has_episode_markers")
    if marked:
        eps = sorted({l["ep"] for l in chunk})
        span = f"episode {eps[0]}" if len(eps) == 1 else f"episodes {eps[0]}-{eps[-1]}"
        head = f"SHOW: {meta.get('show', 'unknown')}\nPART {idx + 1} of {total} ({span})\n"
        info = meta.get("episodes_info", {})
        summaries = [f"EPISODE {e} SUMMARY: {info[str(e)]['logline']}" for e in eps if str(e) in info]
        if summaries:   # the writers' loglines: context for the tagger only, never shown to the stranger
            head += "\n".join(summaries) + "\n"
    else:   # unchanged wording for compilations (keeps cached answers valid)
        head = (f"SHOW: {meta.get('show', 'unknown')}\n"
                f"PART {idx + 1} of {total} (episode {chunk[0]['ep']}, compilation - episode boundaries unknown)\n")
    ctx = ""
    if context:
        ctx = "\nPREVIOUS LINES (context only, do NOT score):\n" + "\n".join(_fmt_line(l, marked) for l in context) + "\n"
    body = "\nSCORE THESE LINES:\n" + "\n".join(_fmt_line(l, marked) for l in chunk)
    if any(l["type"] == "scene" for l in chunk):
        body += "\n\n(SCENE lines are scene headings, not moments: score them hook 0, cliff 0.)"
    return head + ctx + body


def _validator(chunk_ids: set[str]):
    def check(data) -> bool | str:
        data = normalize(data)
        if not isinstance(data, dict) or not isinstance(data.get("beats"), list):
            return 'Top level must be {"beats": [...]} (or {"b": [[...], ...]} in compact form).'
        bad_ids = [b.get("id") for b in data["beats"] if b.get("id") not in chunk_ids]
        if bad_ids:
            return f"These ids are not in SCORE THESE LINES: {bad_ids[:10]}. Use only listed ids."
        for b in data["beats"]:
            for k in ("hook", "cliff", "needs_context"):
                v = b.get(k)
                if not isinstance(v, (int, float)) or not 0 <= v <= 5:
                    return f"{b.get('id')}: '{k}' must be an integer 0-5."
        covered = {b["id"] for b in data["beats"]}
        if len(covered) < 0.9 * len(chunk_ids):
            missing = sorted(chunk_ids - covered)
            return f"You skipped {len(missing)} lines (e.g. {missing[:8]}). Score every listed line."
        return True
    return check


def tag_timeline(timeline: dict, llm: LLM, verbose: bool = True) -> dict:
    meta, lines = timeline["meta"], timeline["lines"]
    chunks = make_chunks(lines, meta.get("has_episode_markers", False))
    compact = bool(meta.get("has_episode_markers"))     # long screenplays -> compact replies
    system = (SYSTEM_COMPACT if compact else SYSTEM).format(archetypes=", ".join(ARCHETYPES))
    by_id: dict[str, dict] = {}
    notes: list[str] = []
    prev: list[dict] = []

    for i, chunk in enumerate(chunks):
        ids = {l["id"] for l in chunk}
        prompt = build_prompt(meta, chunk, prev[-CONTEXT_LINES:], i, len(chunks))
        if verbose:
            print(f"  tagging part {i + 1}/{len(chunks)}: {fmt_time(chunk[0]['start'])}-"
                  f"{fmt_time(chunk[-1]['end'])} ({len(chunk)} lines)")
        try:
            data = normalize(llm.call_json(prompt, system=system, task="tagger", validate=_validator(ids)))
        except LLMError:
            # A long part can get its reply cut off (skipped lines, broken JSON). Self-heal:
            # score the part again as two halves, each with a shorter reply.
            print(f"  [tagger] part {i + 1} failed - retrying as two halves")
            half = len(chunk) // 2
            beats_ok: list[dict] = []
            for j, piece in enumerate((chunk[:half], chunk[half:])):
                ctx = prev[-CONTEXT_LINES:] if j == 0 else chunk[:half][-CONTEXT_LINES:]
                p_ids = {l["id"] for l in piece}
                try:
                    part = normalize(llm.call_json(build_prompt(meta, piece, ctx, i, len(chunks)), system=system,
                                                   task="tagger", validate=_validator(p_ids)))
                    beats_ok += part["beats"]
                except LLMError as e:
                    # Still failing: these lines score 0 (never a guess) and the failure is
                    # written in the notes + run log, so a re-run can fill it.
                    notes.append(f"part {i + 1}.{j + 1} FAILED ({len(p_ids)} lines scored 0): {str(e)[:150]}")
                    print(f"  [tagger] part {i + 1}.{j + 1} FAILED - lines scored 0, see notes")
            data = {"beats": beats_ok}
        for b in data["beats"]:
            arch = b.get("archetype") if b.get("archetype") in ARCHETYPES else "other"
            by_id[b["id"]] = {
                "hook": int(round(b["hook"])), "cliff": int(round(b["cliff"])),
                "needs_context": int(round(b["needs_context"])),
                "archetype": arch, "reason": str(b.get("reason", ""))[:120],
            }
        missing = ids - set(by_id)
        if missing:
            notes.append(f"part {i + 1}: AI skipped {len(missing)} lines -> scored 0")
        prev = chunk

    # Merge scores into the timeline. Skipped lines get zeros (never a guess).
    beats = []
    for l in lines:
        if l["type"] == "episode_marker":
            continue
        s = by_id.get(l["id"], {"hook": 0, "cliff": 0, "needs_context": 5,
                                "archetype": "other", "reason": "not scored"})
        beats.append({**l, **s})
    failed = sum(1 for n in notes if "FAILED" in n)
    if failed > 0.3 * len(chunks):   # mostly zeros would look like a result but mean nothing
        raise RuntimeError(f"Tagger failed on {failed}/{len(chunks)} parts - stopping instead of ranking "
                           f"near-empty scores. First error: {next(n for n in notes if 'FAILED' in n)}")
    return {"meta": meta, "beats": beats, "notes": notes, "usage": llm.usage_summary()}


def main() -> None:
    ap = argparse.ArgumentParser(description="Score every line of a script with the LLM.")
    ap.add_argument("file")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--show", action="store_true",
                    help="print the top-scored lines (do this only AFTER writing my_picks.txt)")
    args = ap.parse_args()

    tl = load_show(args.file)
    llm = LLM(args.config)
    result = tag_timeline(tl, llm)

    out = Path(__file__).resolve().parent.parent / "outputs" / f"beats_{show_name(args.file)}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    b = result["beats"]
    print(f"\nScored {len(b)} lines. Strong hooks (>=4): {sum(x['hook'] >= 4 for x in b)}, "
          f"strong cliffs (>=4): {sum(x['cliff'] >= 4 for x in b)}")
    for n in result["notes"]:
        print("  note:", n)
    print("Usage:", result["usage"])
    print("Saved:", out)
    if args.show:
        print("\nTop hooks:")
        for x in sorted(b, key=lambda x: (-x["hook"], x["start"]))[:10]:
            print(f"  {x['id']} {fmt_time(x['start']):>5} H{x['hook']} C{x['cliff']} N{x['needs_context']} "
                  f"{x['archetype']:<16} {x['text'][:50]} | {x['reason']}")
    else:
        print("(Scores hidden. Write data/my_picks.txt first, then re-run with --show.)")


if __name__ == "__main__":
    main()
