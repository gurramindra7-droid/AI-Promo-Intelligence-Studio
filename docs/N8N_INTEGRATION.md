# n8n integration (optional, disabled by default)

The studio can be driven by n8n, for example: *"when a new episode pack lands in a folder, process it and
post the top promos to the editors' channel."* The integration is **off** unless you switch it on, and it never
sends screenplay text or API keys anywhere.

## 1. Switch it on (`.env`)

```
N8N_ENABLED=true
N8N_WEBHOOK_SECRET=<a long random string>
N8N_CALLBACK_URL=https://<your-n8n>/webhook/promo-studio-events   # optional
```

Restart the API: `.venv\Scripts\python -m uvicorn backend.main:app --port 8000`

## 2. Inbound: n8n → studio (start a job)

n8n **HTTP Request** node:

| Field | Value |
|---|---|
| Method | `POST` |
| URL | `http://<studio-host>:8000/api/webhooks/n8n` |
| Header | `X-Webhook-Secret: <N8N_WEBHOOK_SECRET>` |
| Body (JSON) | `{"action": "process", "project": "my_show", "mode": "agents", "episodes": [1, 2, 3]}` |

* `project`: a project name or id (create it first with `POST /api/projects`).
* `mode`: `import` | `pipeline` | `agents` | `story`.
* The reply is `202 {"job_id": "...", "status": "queued"}`. Poll `GET /api/projects/{id}/status?job_id=...`
  or wait for the callback below.

Security: a wrong or missing secret returns `401` (constant-time comparison). Integration disabled returns `403`.
A missing secret returns `503`. Only the fixed actions and modes above are accepted (`400` otherwise).

## 3. Outbound: studio → n8n (job events)

If `N8N_CALLBACK_URL` is set, the studio POSTs these events:

```json
{"event": "job.completed", "job_id": "a1b2c3", "project": "my_show", "kind": "agents",
 "status": "completed", "summary": {"agents": {"candidates": 12, "ranked": 12, "calls": 19}}}
```

Events are `job.started`, `job.completed` and `job.failed`. Payloads contain **only** ids, counts, status
and error messages (with keys redacted). They never contain script lines, promo text or keys. When
`N8N_WEBHOOK_SECRET` is set, every event carries an `X-Studio-Signature` header: an HMAC-SHA256 of the
body, which n8n can verify. A failing callback never breaks processing.

## 4. Example workflow

1. **Trigger:** schedule or folder watch, then **HTTP Request** `POST /api/projects` (upload the scripts).
2. **HTTP Request** `POST /api/webhooks/n8n` with `mode: "pipeline"`.
3. **Webhook** node receives `job.completed`, then **HTTP Request** `GET /api/projects/{id}/promos?limit=5`.
4. **Slack/Email** node posts the top 5 to editors. Editors review them in the Streamlit Feedback Center.

This was tested with the API test client (secret checks, disabled state, job start). It was **not** tested
against a live n8n instance.
