"""Shared test fixtures.

Everything here runs OFFLINE: no API keys, no network. The synthetic show is built from the public
sample scripts in samples/ (not Kuku's confidential files) by the REAL parser, candidate builder and
ranker; only the AI scores are replaced by deterministic MOCK numbers (tests/fakes.py)."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import common.paths  # noqa: E402,F401  (adds src/ to sys.path)

SHOW = "zz_pytest_synthetic"           # written to outputs/ during the test session, removed after
SAMPLE = ROOT / "samples" / "kuku_style_show"
ARCH = ["slap_violence", "reveal_secret", "threat_danger", "power_flip", "romance_tension"]


def _h(s: str, mod: int) -> int:
    return int(hashlib.md5(s.encode()).hexdigest(), 16) % mod


def mock_beats(lines: list[dict]) -> list[dict]:
    return [{**l, "hook": _h(l["id"] + "h", 6), "cliff": _h(l["id"] + "c", 6), "needs_context": _h(l["id"] + "n", 6),
             "archetype": ARCH[_h(l["id"], len(ARCH))], "reason": "MOCK score"} for l in lines]


def mock_cold(c: dict) -> dict:
    k = c["segments"][0]["first_id"]
    return {"cold_ok": True, "understood": True, "standalone": _h(k + "s", 6), "hook_3s": _h(k + "3", 6),
            "want_next": _h(k + "w", 6), "what_happens": "MOCK", "question_left": "MOCK question?",
            "confusing": []}


@pytest.fixture(autouse=True)
def _not_demo(monkeypatch):
    """Tests run the full studio, not the public demo, unless a test opts in."""
    monkeypatch.setenv("STUDIO_DEMO", "0")


@pytest.fixture(scope="session")
def synthetic_show():
    from candidates import build_candidates
    from llm import load_config
    from parser import discover_shows, parse_show
    from ranker import rank

    cfg = load_config(ROOT / "config.yaml")
    name, files = discover_shows(SAMPLE)[0]
    tl = parse_show(SHOW, files)
    beats = mock_beats(tl["lines"])
    p = {**cfg["promo"], "min_candidates": 3}
    cands = build_candidates(beats, p)["candidates"]
    for c in cands:
        c["cold"] = mock_cold(c)
    ranked = rank(cands, tl["meta"]["duration_seconds"], p, cfg["ranking"])
    out = ROOT / "outputs"
    paths = {"timeline": out / f"timeline_{SHOW}.json", "beats": out / f"beats_{SHOW}.json",
             "ranked": out / f"ranked_{SHOW}.json"}
    paths["timeline"].write_text(json.dumps(tl), encoding="utf-8")
    paths["beats"].write_text(json.dumps({"meta": tl["meta"], "beats": beats, "notes": ["MOCK"]}), encoding="utf-8")
    paths["ranked"].write_text(json.dumps({"meta": tl["meta"], "run": {"model": "MOCK"}, "promos": ranked}),
                               encoding="utf-8")
    yield {"name": SHOW, "timeline": tl, "beats": beats, "ranked": ranked, "cfg": cfg}
    for pth in paths.values():
        pth.unlink(missing_ok=True)


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """A fresh, empty studio database for one test."""
    monkeypatch.setenv("STUDIO_DB", str(tmp_path / "studio_test.db"))
    from database.database import init_db, session
    init_db()
    with session() as con:
        yield con


@pytest.fixture()
def imported(db, synthetic_show):
    from backend.services.import_service import import_show
    r = import_show(db, synthetic_show["name"])
    db.commit()
    return {"con": db, "pid": r["project_id"], **r, **synthetic_show}
