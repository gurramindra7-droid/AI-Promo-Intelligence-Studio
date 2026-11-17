"""Outbound events to n8n (job started / completed / failed).

Off unless N8N_ENABLED=true AND N8N_CALLBACK_URL is set. Payloads carry ids, counts and status only -
never screenplay text, promo lines or API keys - so confidential scripts don't leave the machine."""
from __future__ import annotations

import hashlib
import hmac
import json
import urllib.request

from common.settings import get_settings, redact

EVENTS = ("job.started", "job.completed", "job.failed")
SAFE_KEYS = ("job_id", "project", "project_id", "kind", "status", "progress", "message", "summary")


def sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def build_body(event: str, payload: dict) -> bytes:
    safe = {k: v for k, v in payload.items() if k in SAFE_KEYS}
    return json.dumps({"event": event, **safe}, default=str).encode()


def notify(event: str, payload: dict, timeout: float = 5.0) -> dict:
    """Returns what happened (sent / skipped / error); never raises - automation must not break processing."""
    s = get_settings()
    if not s.n8n_enabled or not s.n8n_callback_url:
        return {"sent": False, "reason": "n8n disabled"}
    body = build_body(event, payload)
    headers = {"Content-Type": "application/json"}
    if s.n8n_secret:
        headers["X-Studio-Signature"] = sign(body, s.n8n_secret)
    req = urllib.request.Request(s.n8n_callback_url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return {"sent": True, "status": r.status}
    except Exception as e:
        return {"sent": False, "reason": redact(f"{type(e).__name__}: {e}")}
