"""Inbound n8n webhook: n8n (or any automation tool) asks the studio to process a project.

Security: disabled unless N8N_ENABLED=true; requires N8N_WEBHOOK_SECRET, sent in the
X-Webhook-Secret header and compared in constant time. Only a fixed set of actions is accepted."""
from __future__ import annotations

import hmac

from common.settings import get_settings

ACTIONS = {"process"}
MODES = {"import", "pipeline", "agents", "story"}


class WebhookError(Exception):
    def __init__(self, status: int, msg: str):
        super().__init__(msg)
        self.status = status


def check(secret_header: str | None, payload: dict) -> dict:
    s = get_settings()
    if not s.n8n_enabled:
        raise WebhookError(403, "n8n integration is disabled (set N8N_ENABLED=true)")
    if not s.n8n_secret:
        raise WebhookError(503, "N8N_WEBHOOK_SECRET is not set")
    if not secret_header or not hmac.compare_digest(secret_header.encode(), s.n8n_secret.encode()):
        raise WebhookError(401, "bad or missing X-Webhook-Secret")
    action, mode = payload.get("action", "process"), payload.get("mode", "import")
    if action not in ACTIONS:
        raise WebhookError(400, f"action must be one of {sorted(ACTIONS)}")
    if mode not in MODES:
        raise WebhookError(400, f"mode must be one of {sorted(MODES)}")
    if not payload.get("project"):
        raise WebhookError(400, "project (name or id) is required")
    eps = payload.get("episodes")
    if eps is not None and not (isinstance(eps, list) and all(isinstance(e, int) for e in eps)):
        raise WebhookError(400, "episodes must be a list of integers")
    return {"project": payload["project"], "mode": mode, "episodes": eps,
            "use_llm": bool(payload.get("use_llm", True))}
