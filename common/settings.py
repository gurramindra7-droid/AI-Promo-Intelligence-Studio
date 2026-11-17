"""Studio settings: config.yaml `studio:` section, overridable by environment variables.
API keys are never stored here - LiteLLM reads them from the environment (.env or host secrets).

Demo mode (public deployment): when no private database exists (no STUDIO_DB and no data/studio.db) and
the bundled demo database demo/studio_demo.db is present - or when STUDIO_DEMO=1 - the studio runs on a
fresh copy of the demo database (an original fictional show). Processing jobs are disabled and the
copilot answers offline unless STUDIO_DEMO_ALLOW_AI=true, so a public link can never spend AI quota."""
from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

from common.paths import CONFIG, DATA, ROOT

load_dotenv(ROOT / ".env")

DEMO_DB = ROOT / "demo" / "studio_demo.db"

DEFAULTS = {
    "agent_model": None,            # None -> llm.model from config.yaml
    "stranger_model": "groq/openai/gpt-oss-20b",
    "critic_model": None,
    "story_model": None,
    "copilot_model": None,
    "shortlist_pct": 15,            # agents re-judge the top 15% lines from the original tagger
    "max_candidates": 20,           # candidates sent to the stranger + critic agents
    "critic_batch": 5,
    "agent_batch": 25,
}


def is_demo() -> bool:
    flag = os.getenv("STUDIO_DEMO", "").lower()
    if flag in ("1", "true", "yes"):
        return True
    if flag in ("0", "false", "no"):
        return False
    return not os.getenv("STUDIO_DB") and not (DATA / "studio.db").exists() and DEMO_DB.exists()


def _demo_db_path() -> str:
    """A writable per-process copy of the bundled demo database (reviews made in the demo stay local)."""
    target = Path(tempfile.gettempdir()) / "apis_demo" / "studio_demo.db"
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(DEMO_DB, target)
    return str(target)


def _db_path() -> str:
    if os.getenv("STUDIO_DB"):
        return os.environ["STUDIO_DB"]
    return _demo_db_path() if is_demo() else str(DATA / "studio.db")


@dataclass
class Settings:
    db_path: str = field(default_factory=_db_path)
    demo: bool = field(default_factory=is_demo)
    demo_allow_ai: bool = field(default_factory=lambda: os.getenv("STUDIO_DEMO_ALLOW_AI", "false").lower() == "true")
    n8n_enabled: bool = field(default_factory=lambda: os.getenv("N8N_ENABLED", "false").lower() == "true")
    n8n_secret: str = field(default_factory=lambda: os.getenv("N8N_WEBHOOK_SECRET", ""))
    n8n_callback_url: str = field(default_factory=lambda: os.getenv("N8N_CALLBACK_URL", ""))
    studio: dict = field(default_factory=dict)

    def model_for(self, role: str) -> str | None:
        """role: agent | stranger | critic | story | copilot. None = use config.yaml llm.model."""
        env = os.getenv(f"STUDIO_{role.upper()}_MODEL")
        return env or self.studio.get(f"{role}_model") or self.studio.get("agent_model")

    @property
    def ai_allowed(self) -> bool:
        """May the UI make live AI calls? Needs a key, and in demo mode an explicit opt-in."""
        has_key = bool(os.getenv("GROQ_API_KEY") or os.getenv("GEMINI_API_KEY"))
        return has_key and (not self.demo or self.demo_allow_ai)

    @property
    def processing_allowed(self) -> bool:
        return not self.demo


def get_settings() -> Settings:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    s = Settings()
    s.studio = {**DEFAULTS, **(cfg.get("studio") or {})}
    return s


def redact(text: str) -> str:
    """Remove anything that looks like an API key before logging or showing an error."""
    import re
    return re.sub(r"(gsk_|sk-|AIza)[A-Za-z0-9_\-]{8,}", r"\1***", str(text))
