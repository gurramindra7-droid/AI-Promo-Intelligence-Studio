"""The ORIGINAL pipeline's deterministic parts: parsing, timestamps, candidates, durations, episode
boundaries, ranking - plus a check that the submitted Kuku outputs are byte-for-byte unchanged."""
import hashlib
import json
from pathlib import Path

import pytest

from tests.conftest import ROOT, SAMPLE, mock_beats

from adapter import detect_format, to_seconds  # noqa: E402
from candidates import build_candidates  # noqa: E402
from parser import discover_shows, parse_file, parse_show  # noqa: E402

# Private, git-ignored list {output file name: sha256} recorded before the studio was built. The names
# identify a confidential show, so the list lives in data/ and this test runs only where that data exists.
HASH_FILE = ROOT / "data" / "baseline_hashes.json"


def test_time_parsing():
    assert to_seconds("01:02.50") == pytest.approx(62.5)
    assert to_seconds("0:03") == 3


def test_parse_sample_episode_folder():
    shows = discover_shows(SAMPLE)
    assert len(shows) == 1, "a folder of episode files is ONE show"
    tl = parse_show("s", shows[0][1])
    assert tl["meta"]["episodes"] == [1, 2, 3]
    assert all("gap" in w for w in tl["warnings"]), "only informational gap notes on the sample"
    ids = [l["id"] for l in tl["lines"]]
    assert len(ids) == len(set(ids)), "line ids must be unique"


def test_timestamps_monotonic_and_episode_local():
    tl = parse_show("s", discover_shows(SAMPLE)[0][1])
    for l in tl["lines"]:
        assert l["end"] >= l["start"]
        assert l["ep_end"] - l["ep_start"] == pytest.approx(l["end"] - l["start"], abs=0.01)
    starts = [l["start"] for l in tl["lines"]]
    assert starts == sorted(starts), "show clock must not go backwards across episodes"


def test_single_file_format_detected():
    tl = parse_file(ROOT / "samples" / "kuku_style_single_file.txt")
    assert tl["lines"] and tl["meta"]["format"]


def test_candidates_respect_duration_and_episode_boundaries(synthetic_show):
    tl = synthetic_show["timeline"]
    by_id = {l["id"]: l for l in tl["lines"]}
    p = {**synthetic_show["cfg"]["promo"], "min_candidates": 3}
    cands = build_candidates(mock_beats(tl["lines"]), p)["candidates"]
    assert cands
    for c in cands:
        assert p["min_seconds"] <= c["duration"] <= p["max_seconds"]
        for s in c["segments"]:
            a, b = by_id[s["first_id"]], by_id[s["last_id"]]
            assert a["start"] == s["start"] and b["end"] == s["end"], "times come from the parser, exactly"
            assert a["ep"] == b["ep"], "a clip never crosses an episode boundary"


def test_ranking_is_deterministic(synthetic_show):
    from ranker import rank
    from tests.conftest import mock_cold
    cfg = synthetic_show["cfg"]
    p = {**cfg["promo"], "min_candidates": 3}
    runs = []
    for _ in range(2):
        cands = build_candidates(mock_beats(synthetic_show["timeline"]["lines"]), p)["candidates"]
        for c in cands:
            c["cold"] = mock_cold(c)
        runs.append([(c["rank"], c["score"]) for c in rank(cands, 243.3, p, cfg["ranking"])])
    assert runs[0] == runs[1]
    assert [r for r, _ in runs[0]] == list(range(1, len(runs[0]) + 1))


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.mark.skipif(not HASH_FILE.exists(), reason="private baseline (confidential outputs) not on this machine")
def test_original_outputs_unchanged():
    """The submitted promos must stay reproducible: every recorded output file is byte-for-byte unchanged."""
    expected = json.loads(HASH_FILE.read_text())
    assert expected
    for name, h in expected.items():
        p = ROOT / "outputs" / name
        assert p.exists(), name
        assert _sha(p) == h, f"{name} changed!"
