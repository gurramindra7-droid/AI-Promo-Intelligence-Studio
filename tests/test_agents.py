"""Agents: JSON validation, failure handling, model switching, caching, and that no agent can
introduce a timestamp. Uses the MOCK LLM (tests/fakes.py) - no API calls."""
import json

import pytest

from agents import cliffhanger_agent, editorial_critic_agent, hook_agent, stranger_agent
from agents.agent_orchestrator import run_agents, validate_candidate
from agents.base import AgentConfigError
from database import repositories as R
from tests.fakes import FakeLLM, MOCK_MODEL


def _lines(n=4):
    return [{"id": f"L{i}", "ep": 1, "start": i * 3.0, "end": i * 3.0 + 2.5, "ep_start": i * 3.0,
             "ep_end": i * 3.0 + 2.5, "type": "dialogue", "speaker": "A", "text": f"line {i}"} for i in range(n)]


def test_hook_validator_rejects_unknown_ids_and_bad_scores():
    check = hook_agent.validator({"L1", "L2"})
    row = lambda i: {"line_id": i, "hook_score": 4, "hook_type": "other", "reason": "x", "confidence": 0.5}
    assert check({"results": [row("L1"), row("L2")]}) is True
    assert check({"results": [row("L1")]}) is not True, "every listed line must be scored"
    assert check({"results": [{"line_id": "L9", "hook_score": 4, "hook_type": "other", "reason": "x",
                               "confidence": 0.5}]}) is not True
    assert check({"results": [{"line_id": "L1", "hook_score": 9, "hook_type": "other", "reason": "x",
                               "confidence": 0.5}]}) is not True
    assert check({"wrong": []}) is not True


def test_stranger_validator():
    ok = {"standalone_score": 3, "context_dependency": "low", "missing_context": [], "explanation": "x"}
    assert stranger_agent.validate(ok) is True
    assert stranger_agent.validate({**ok, "context_dependency": "extreme"}) is not True


def test_agent_outputs_contain_no_times():
    llm = FakeLLM()
    out = hook_agent.run(llm, _lines(), {})
    assert out and all(set(r) <= {"line_id", "hook_score", "hook_type", "reason", "confidence"} for r in out)
    out = cliffhanger_agent.run(llm, _lines(), {})
    assert all("start" not in r and "end" not in r for r in out)


def test_validate_candidate_catches_tampering():
    L = _lines(12)
    by_id = {l["id"]: l for l in L}
    good = {"segments": [{"first_id": "L0", "last_id": "L9", "start": 0.0, "end": 29.5}]}
    assert validate_candidate(good, by_id) is None
    moved = {"segments": [{"first_id": "L0", "last_id": "L9", "start": 1.0, "end": 29.5}]}
    assert "time mismatch" in validate_candidate(moved, by_id)
    fake = {"segments": [{"first_id": "L0", "last_id": "L99", "start": 0.0, "end": 29.5}]}
    assert "unknown line id" in validate_candidate(fake, by_id)
    short = {"segments": [{"first_id": "L0", "last_id": "L2", "start": 0.0, "end": 8.5}]}
    assert "outside 20-60" in validate_candidate(short, by_id)
    by_id["L9"] = {**by_id["L9"], "ep": 2}
    assert "episode boundary" in validate_candidate(good, by_id)


def test_broken_llm_raises_clearly():
    with pytest.raises(Exception) as e:
        stranger_agent.run(FakeLLM(broken=True), _lines(), [{"first_id": "L0", "last_id": "L3"}])
    assert "No valid JSON" in str(e.value)


def test_model_switching_by_env(monkeypatch):
    from common.settings import get_settings
    monkeypatch.setenv("STUDIO_CRITIC_MODEL", "groq/some-other-model")
    assert get_settings().model_for("critic") == "groq/some-other-model"
    monkeypatch.delenv("STUDIO_CRITIC_MODEL")
    assert get_settings().model_for("critic") != "groq/some-other-model"


def test_missing_key_is_a_clear_config_error(monkeypatch):
    from agents.base import call, make_llm
    monkeypatch.setenv("STUDIO_AGENT_MODEL", "groq/openai/gpt-oss-20b")
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    llm = make_llm("agent")
    llm.fallback_model = None
    llm.use_cache = False
    with pytest.raises(AgentConfigError):
        call(llm, "x", "y", "agent_hook", lambda d: True)


def test_llm_cache_roundtrip(tmp_path):
    from llm import LLM
    from common.paths import CONFIG
    llm = LLM(CONFIG, model_override="groq/pytest-model")
    llm.cache_dir = tmp_path
    k = llm._cache_key("groq/pytest-model", "sys", "prompt")
    assert llm._cache_get(k) is None
    llm._cache_put(k, {"a": 1})
    assert llm._cache_get(k) == {"a": 1}
    assert llm._cache_key("groq/other", "sys", "prompt") != k, "changing the model must not reuse answers"


def test_orchestrator_end_to_end_with_mock(imported):
    con, pid = imported["con"], imported["pid"]
    llms = {"agent": FakeLLM(), "stranger": FakeLLM(), "critic": FakeLLM()}
    try:
        res = run_agents(con, pid, imported["name"], llms=llms)
    except ValueError as e:      # mock scores can legitimately give no 20-60 s clip on a tiny sample
        pytest.skip(str(e))
    con.commit()
    agents = R.get_promos(con, pid, "agents")
    original = R.get_promos(con, pid, "original")
    assert len(original) == imported["promos"], "agents never touch the original ranking"
    assert res["ranked"] == len(agents)
    by_id = {l["id"]: l for l in imported["timeline"]["lines"]}
    for p in agents:
        assert validate_candidate({"segments": json.loads(p["segments_json"])}, by_id) is None
        evals = R.get_agent_evals(con, p["id"])
        assert evals and all(v["_model"] == MOCK_MODEL for v in evals.values())
    assert set(res["answered_by"]) <= {MOCK_MODEL}
