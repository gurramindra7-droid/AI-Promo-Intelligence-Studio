"""Database schema. Unique keys make every import/processing step idempotent (re-running
updates rows instead of duplicating them). `ranking_kind` keeps the ORIGINAL pipeline ranking
and the new multi-agent ranking side by side - neither overwrites the other."""

DECISIONS = ("approve", "reject", "needs_revision")
REJECTION_REASONS = (
    "Weak opening",
    "Weak ending",
    "Too much context required",
    "Poor emotional impact",
    "Incorrect interpretation",
    "Better alternative exists",
    "Repetitive content",
)

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    show_title TEXT,
    source_path TEXT,
    meta_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    number INTEGER NOT NULL,
    logline TEXT,
    duration_s REAL,
    n_blocks INTEGER,
    n_dialogue INTEGER,
    n_action INTEGER,
    UNIQUE (project_id, number)
);

CREATE TABLE IF NOT EXISTS promos (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    ranking_kind TEXT NOT NULL,              -- 'original' | 'agents'
    cand_key TEXT NOT NULL,                  -- first_id..last_id of its segments (stable across runs)
    rank INTEGER,
    episode INTEGER,
    start_s REAL, end_s REAL,                -- show clock
    ep_start REAL, ep_end REAL,              -- time written in the episode's script
    duration REAL,
    hook_id TEXT, hook_text TEXT, hook_score REAL, hook_type TEXT,
    cliff_id TEXT, cliff_text TEXT, cliff_score REAL, cliff_type TEXT,
    standalone_score REAL,
    context_dependency TEXT,
    archetype TEXT,
    score REAL,
    verdict TEXT,                            -- critic: approve/review/reject (agents ranking)
    why_it_works TEXT,
    why_it_might_fail TEXT,
    why_rank TEXT,
    characters_json TEXT,
    segments_json TEXT,
    lines_json TEXT,
    UNIQUE (project_id, ranking_kind, cand_key)
);
CREATE INDEX IF NOT EXISTS ix_promos_rank ON promos(project_id, ranking_kind, rank);
CREATE INDEX IF NOT EXISTS ix_promos_episode ON promos(project_id, episode);

CREATE TABLE IF NOT EXISTS agent_line_scores (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    line_id TEXT NOT NULL,
    agent TEXT NOT NULL,                     -- 'hook' | 'cliffhanger'
    score REAL, kind TEXT, reason TEXT, confidence REAL, model TEXT,
    UNIQUE (project_id, line_id, agent)
);

CREATE TABLE IF NOT EXISTS agent_evaluations (
    id INTEGER PRIMARY KEY,
    promo_id INTEGER NOT NULL REFERENCES promos(id) ON DELETE CASCADE,
    agent TEXT NOT NULL,                     -- 'stranger' | 'critic'
    output_json TEXT NOT NULL,
    model TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (promo_id, agent)
);

CREATE TABLE IF NOT EXISTS characters (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    aliases_json TEXT DEFAULT '[]',
    role TEXT DEFAULT 'unknown',
    n_lines INTEGER DEFAULT 0,
    first_ep INTEGER, last_ep INTEGER,
    UNIQUE (project_id, name)
);

CREATE TABLE IF NOT EXISTS character_episodes (
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    episode INTEGER NOT NULL,
    n_lines INTEGER NOT NULL,
    PRIMARY KEY (character_id, episode)
);

CREATE TABLE IF NOT EXISTS story_events (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    episode INTEGER NOT NULL,
    description TEXT NOT NULL,
    event_type TEXT,
    importance INTEGER,
    characters_json TEXT DEFAULT '[]',
    source TEXT,                             -- e.g. 'logline:ep16' - where the fact came from
    confidence REAL,
    verified INTEGER DEFAULT 0,              -- 1 = every named character exists in the script
    UNIQUE (project_id, episode, description)
);

CREATE TABLE IF NOT EXISTS character_relationships (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    a TEXT NOT NULL, b TEXT NOT NULL,
    relation TEXT NOT NULL,                  -- 'appears_with' (code) or an LLM label
    evidence TEXT,
    episodes_json TEXT DEFAULT '[]',
    confidence REAL,
    source TEXT,                             -- 'co-occurrence' | 'llm:loglines'
    UNIQUE (project_id, a, b, relation)
);

CREATE TABLE IF NOT EXISTS editorial_feedback (
    id INTEGER PRIMARY KEY,
    promo_id INTEGER NOT NULL REFERENCES promos(id) ON DELETE CASCADE,
    decision TEXT NOT NULL,
    reason TEXT,
    comment TEXT,
    snapshot_json TEXT,                      -- promo scores + rank at decision time (audit)
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_feedback_promo ON editorial_feedback(promo_id);

CREATE TABLE IF NOT EXISTS ranking_calibrations (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    ranking_kind TEXT NOT NULL,
    n_feedback INTEGER,
    rules_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS copilot_conversations (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    tool_calls_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_copilot_session ON copilot_conversations(session_id);

CREATE TABLE IF NOT EXISTS processing_jobs (
    id TEXT PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,                    -- queued | running | done | error
    progress REAL DEFAULT 0,
    message TEXT,
    result_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS model_usage_logs (
    id INTEGER PRIMARY KEY,
    job_id TEXT,
    project_id INTEGER,
    task TEXT, model TEXT, cached INTEGER,
    prompt_tokens INTEGER, completion_tokens INTEGER, seconds REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""
