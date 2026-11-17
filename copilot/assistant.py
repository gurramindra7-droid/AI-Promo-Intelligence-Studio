"""Editorial copilot.

    question -> intent (AI picks ONE tool from a fixed list; validated) -> run the tool on the database
             -> AI writes the answer using ONLY that data -> answer + the promos it used

Grounding rules: the answer may cite only promos/episodes/times present in the tool result; if the data
does not contain the answer, it must say so. Without an API key the copilot still works in OFFLINE mode
(rule-based routing + a plain summary of the same data), clearly labelled.
"""
from __future__ import annotations

import json
import uuid

from agents.base import AgentConfigError, call, make_llm
from copilot import retrieval
from copilot.tools import TOOL_DOCS, TOOLS, run_tool
from database import repositories as R

PLAN_SYSTEM = f"""You route an editor's question about a microdrama's promo shortlist to ONE tool.
Tools:
{TOOL_DOCS}
Use the recent conversation to resolve follow-ups ("that one", "the second promo").
Reply with JSON only: {{"tool": "<name>", "args": {{...}}}}"""

ANSWER_SYSTEM = """You are an editorial copilot for a microdrama promo team. Answer the editor's question using ONLY
the DATA provided (results from the project's database). Always cite promos as "#rank (EpN m:ss-m:ss)".
Explain reasoning with the scores and reviews in the data. If the data does not answer the question,
say so plainly - never invent promos, episodes, times, characters or numbers. Be concise (<= 150 words).
Reply with JSON only: {"answer": "...", "promo_ids": [ids of promos you referred to]}"""


def _plan_valid(d):
    if not isinstance(d, dict) or d.get("tool") not in TOOLS:
        return f"tool must be one of {list(TOOLS)}"
    if not isinstance(d.get("args", {}), dict):
        return "args must be an object"
    return True


def _answer_valid(d):
    return True if isinstance(d, dict) and isinstance(d.get("answer"), str) else 'Reply {"answer": "...", "promo_ids": []}'


def _offline_answer(tool: str, data: dict) -> str:
    if data.get("error"):
        return data["error"]
    if tool == "get_feedback_summary":
        d = data
        return (f"{d['reviewed']} of {d['total_promos']} promos reviewed: {d['approved']} approved, "
                f"{d['rejected']} rejected, {d['needs_revision']} need revision, {d['pending']} pending.")
    if tool == "get_character_episodes":
        return (f"{data['character']} speaks {data['lines']} lines across {len(data['episodes'])} episodes "
                f"({data['episodes'][:12]}...). Promos featuring them: " +
                (", ".join(f"#{p['rank']} ({p['cut']})" for p in data["promos"][:6]) or "none in the shortlist") + ".")
    if tool == "get_episode_details":
        return (f"Episode {data['episode']}: {data['logline'] or 'no logline'} Promos in this episode: " +
                (", ".join(f"#{p['rank']} {p['ranking']} ({p['cut']})" for p in data["promos"]) or "none") + ".")
    if tool == "explain_promo":
        p = data["promo"]
        return f"#{p['rank']} ({p['cut']}): {p['why_rank']}. Why it works: {p['why_it_works']}"
    promos = data.get("promos") or []
    if not promos:
        return "No promos in the data match that."
    return "\n".join(f"- #{p['rank']} ({p['cut']}, score {p['score']}): \"{(p['hook'] or '')[:70]}\" -> "
                     f"\"{(p['cliffhanger'] or '')[:60]}\"" for p in promos[:6])


def chat(con, project_id: int, message: str, session_id: str | None = None, use_llm: bool = True,
         llm=None) -> dict:
    session_id = session_id or uuid.uuid4().hex[:10]
    history = R.get_messages(con, session_id, limit=8)
    last_data = next((json.loads(h["tool_calls_json"]).get("data") for h in reversed(history)
                      if h["role"] == "assistant" and h.get("tool_calls_json")), None)
    R.add_message(con, project_id, session_id, "user", message)
    mode, note = "offline", ""
    tool, args = retrieval.route(con, project_id, message, last_data)
    if use_llm:
        try:
            llm = llm or make_llm("copilot")
            convo = "\n".join(f"{h['role']}: {h['content'][:300]}" for h in history[-6:])
            plan = call(llm, f"RECENT CONVERSATION:\n{convo}\n\nQUESTION: {message}", PLAN_SYSTEM, "copilot_plan",
                        _plan_valid)
            tool, args = plan["tool"], plan.get("args", {})
            mode = "llm"
        except AgentConfigError as e:
            note = str(e)
        except Exception as e:  # invalid plan after retry -> keep the rule-based route
            note = f"AI routing failed ({type(e).__name__}); used rule-based routing."
    data = run_tool(con, project_id, tool, args)
    if data.get("error") and tool != "get_top_ranked_promos" and "known" not in data:
        tool, args = retrieval.route(con, project_id, message, last_data)
        data = run_tool(con, project_id, tool, args)
    answer = _offline_answer(tool, data)
    used = [p["promo_id"] for p in (data.get("promos") or [])][:6]
    if mode == "llm":
        try:
            blob = json.dumps(data, ensure_ascii=False, default=str)[:12000]
            a = call(llm, f"QUESTION: {message}\n\nDATA (tool {tool}):\n{blob}", ANSWER_SYSTEM, "copilot_answer",
                     _answer_valid)
            answer = a["answer"]
            valid_ids = {p["promo_id"] for p in (data.get("promos") or [])} | (
                {data["promo"]["promo_id"]} if data.get("promo") else set())
            used = [i for i in a.get("promo_ids", []) if i in valid_ids] or used   # drop ids not in the data
            if data.get("promos") and "#" not in answer:      # grounding check: the AI cited nothing
                answer += "\n\nPromos in the data:\n\n" + _offline_answer(tool, data)
        except Exception as e:
            mode, note = "offline", f"AI answer failed ({type(e).__name__}); showing the data summary."
    R.add_message(con, project_id, session_id, "assistant", answer, {"tool": tool, "args": args, "data": data})
    if mode == "llm":
        R.log_usage(con, None, project_id, llm.calls[-2:])
    return {"session_id": session_id, "answer": answer, "tool": tool, "args": args, "data": data,
            "promo_ids": used, "mode": mode, "note": note}
