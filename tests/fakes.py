"""MOCK LLM FOR TESTS ONLY - deterministic, made-up answers so the plumbing can be tested without
API calls. Its outputs are NOT model results and are never shown as such: its model name is
'mock/deterministic-test-llm', and it is only ever injected by tests."""
from __future__ import annotations

import hashlib
import json
import re

MOCK_MODEL = "mock/deterministic-test-llm"


def _h(s: str, mod: int) -> int:
    return int(hashlib.md5(s.encode()).hexdigest(), 16) % mod


class FakeLLM:
    def __init__(self, fail_first: bool = False, broken: bool = False):
        self.model = MOCK_MODEL
        self.calls: list[dict] = []
        self.fail_first = fail_first      # first reply malformed -> exercises the corrective retry
        self.broken = broken              # always malformed -> exercises failure handling

    def _reply(self, prompt: str, task: str):
        if task in ("agent_hook", "agent_cliffhanger"):
            ids = re.findall(r"^(L\d+) \[Ep", prompt, re.M)
            key = "hook" if task == "agent_hook" else "cliffhanger"
            return {"results": [{"line_id": i, f"{key}_score": _h(i + key, 6), f"{key}_type": "other",
                                 "reason": "mock reason", "confidence": 0.5} for i in ids]}
        if task == "agent_stranger":
            return {"standalone_score": _h(prompt, 6), "context_dependency": ["low", "medium", "high"][_h(prompt, 3)],
                    "missing_context": ["mock item"], "explanation": "mock explanation"}
        if task == "agent_critic":
            keys = re.findall(r"^cand_key: (\S+)", prompt, re.M)
            return {"reviews": [{"cand_key": k, "editorial_verdict": ["approve", "review", "reject"][_h(k, 3)],
                                 "strengths": ["mock strength"], "weaknesses": ["mock weakness"],
                                 "alternative_suggestion": "", "final_reasoning": "mock"} for k in keys]}
        if task == "story_events":
            eps = [int(e) for e in re.findall(r"^EPISODE (\d+):", prompt, re.M)]
            names = re.findall(r"KNOWN CHARACTERS: (.*)", prompt)
            first = names[0].split(", ")[0] if names and names[0] else "UNKNOWN"
            return {"episodes": [{"episode": e, "events": [{"description": f"mock event {e}", "event_type": "conflict",
                                                             "importance": 3, "characters_involved": [first, "NOBODY REAL"]}],
                                  "relationships": []} for e in eps]}
        if task == "story_aliases":
            return {"groups": []}
        if task == "copilot_plan":
            return {"tool": "get_top_ranked_promos", "args": {"limit": 3}}
        if task == "copilot_answer":
            return {"answer": "mock grounded answer", "promo_ids": []}
        return {}

    def call_json(self, prompt: str, system: str = "", task: str = "general", validate=None):
        self.calls.append({"task": task, "model": self.model, "cached": False, "prompt_tokens": len(prompt) // 4,
                           "completion_tokens": 50, "seconds": 0.0})
        if self.broken or (self.fail_first and len(self.calls) == 1):
            data = {"not": "the right shape"}
            if self.broken:
                from llm import LLMError
                if validate and validate(data) is not True:
                    raise LLMError(f"No valid JSON for task '{task}'. Last error: mock malformed")
        data = self._reply(prompt, task)
        if validate:
            v = validate(data)
            assert v is True, f"mock produced invalid data for {task}: {v}"
        return json.loads(json.dumps(data))
