# AI Promo Finder

**Ranked, ready-to-cut promos from microdrama scripts.**

AI Promo Finder reads a microdrama's scripts and gives the promo editor a ranked list of
ready-to-cut promos: the episode and exact start/end time of every segment, the hook,
the cliffhanger, one line on why it works, and why it is ranked where it is.

Built for the Kuku AI Generalist assignment, Problem 1 ("Find the Promos").

---

## What a promo is (from the brief)

A 20-60 second clip from the show itself that:

1. **opens on a hook**: something in the first 3 seconds that stops a scrolling viewer
2. **ends on a cliffhanger**: it cuts at an unresolved moment
3. **makes sense on its own** to someone who has never seen the show

The tool only finds moments and cut points. No editing, music or overlays.

---

## How it works

```
script(s) ──► 1. PARSE (code) ──► 2. TAG (AI) ──► 3. CANDIDATES (code) ──► 4. STRANGER TEST (AI) ──► 5. RANK (code) ──► editor (app)
```

| Step | Who | What it does | Why this way |
|---|---|---|---|
| 1. Parse | code | Reads any supported format into one timeline: each line gets an id, episode, start/end time, type (dialogue / action / scene / sound / camera), speaker | Timestamps come **only** from the script, never from the AI |
| 2. Tag | AI | Scores every line: `hook` 0-5, `cliff` 0-5, `needs_context` 0-5, moment type, short reason. Answers with **line ids only** | Small, checkable judgements; the AI cannot invent a time |
| 3. Candidates | code | Builds 20-60s clips that **start on a strong hook line** and **end on a strong cliffhanger line**, cut on whole lines, never across episodes; removes near-duplicates | Rules from the brief, fully explainable |
| 4. Stranger test | AI | A **fresh, blind** AI call per promo sees only that promo's lines (no show name, no story): what happens? what question is left? what is confusing? `standalone` 0-5 | Makes "makes sense on its own" measurable |
| 5. Rank | code | `score = (hook+1)(cliff+1)(standalone+1)`, then rules: early-episode bonus, spoiler guard, preferred 25-45s, variety in the top 10 | Every rank comes with a plain-English "why this rank" |
| App | human | Editor watches/reads each promo and clicks Approve / Reject (saved) | The AI suggests, the editor decides |

"Strong" hook/cliff lines are the **top X% of each show** (not a fixed score), because
different models use the 0-5 scale differently. That keeps results stable when the model is swapped.

---

## Quick start

Python 3.10+ (tested on 3.14, Windows 11).

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt        # macOS/Linux: .venv/bin/python
cp .env.example .env                                            # then paste your API key(s) into .env
.venv/Scripts/python src/llm.py --test                          # checks the key works
```

Free keys: Groq (https://console.groq.com/keys) and/or Gemini (https://aistudio.google.com/apikey).

### Run on a script, a folder of episodes, or many shows

```bash
.venv/Scripts/python src/run.py --input samples/kuku_style_show          # folder of episode files = one show
.venv/Scripts/python src/run.py --input path/to/script.txt               # one file = one show
.venv/Scripts/python src/run.py --input path/to/folder_of_shows          # each file / sub-folder = one show
```

Results land in `outputs/`:

| File | Content |
|---|---|
| `ranked_<show>.md` / `.csv` / `.json` | **The answer**: ranked promos with cuts, hook, cliffhanger, why it works, why this rank |
| `run_log_<show>.json` | model used, which model actually answered, AI calls, tokens, time per step, settings |
| `timeline_`, `beats_`, `candidates_`, `cold_<show>.json` | raw output of every step (unedited) |

### Swap the model (one line)

In `config.yaml` change `llm.model`, or override on the command line:

```bash
.venv/Scripts/python src/run.py --input samples/kuku_style_show --model gemini/gemini-3.8-flash
.venv/Scripts/python src/run.py --input samples/kuku_style_show --model openai/gpt-4.1          # needs OPENAI_API_KEY
.venv/Scripts/python src/run.py --input samples/kuku_style_show --model anthropic/claude-sonnet-5-5   # needs ANTHROPIC_API_KEY
```

Any [LiteLLM](https://docs.litellm.ai/docs/providers) model name works. All AI calls go through
`src/llm.py`, which validates JSON, retries, waits as long as the provider asks on rate limits,
gives up at once on a used-up daily quota, falls back to a backup model, caches answers, and logs
which model really answered (`answered_by` in the run log).

A cheaper model for the simpler stranger test: `--cold-model groq/openai/gpt-oss-20b`.

**Free-tier note.** A 50-episode screenplay needs roughly 200,000 tokens, about one Groq model's
free daily budget. To fit it, long screenplays use compact AI replies, `reasoning_effort: low`,
and each AI call is sized by characters (a part whose reply gets cut off is retried as two halves).
A paid key removes all of this.

### Editor app

```bash
.venv/Scripts/python -m streamlit run app.py
```

- **Review results**: promo cards in rank order; for YouTube sources the clip plays at the exact
  start/end; Approve / Reject + note, saved to `outputs/feedback_<show>.json`.
- **Run on a new script**: upload a script, pick a model, get ranked promos.

---

## Supported input formats (auto-detected)

| Format | Example |
|---|---|
| **Kuku screenplay** (the assignment's input pack) | `**MAYA (Desperate):**` / `Start: (00:13.50) \| End: (00:14.30)` / `"Why me?"`, plus `**CAMERA:**`, `**ACTION:**`, `**SOUND FX:**`, scene headings, episode logline header |
| Timestamped screenplay | `[00:12] BELLA: line`, `[00:16] (Victoria slaps Maya)`, `SCENE 2 - INT. ...`, `NAME (O.S.)` on its own line, ranges `[00:04.0 - 00:07.5]` |
| YouTube transcript copy | `1:031 minute, 3 secondsHey loser.` (as pasted from "Show transcript") |
| Plain timestamps / subtitles | `1:03 Hey loser.`, SRT / VTT |

Episodes: one file per episode (`ep01.txt`, `episode-001-...txt`) or `EPISODE n` lines inside one
file. Times may restart at 0:00 every episode; output cuts are always **episode + time in that
episode's script**.

`samples/` contains a small **synthetic** 3-episode screenplay (written for testing, not a real
show) so the tool can be tried without any private data.

---

## Checking quality

```bash
.venv/Scripts/python eval/verify_outputs.py <input>          # independent check of every timestamp vs the raw script
.venv/Scripts/python eval/baseline_keywords.py <input>       # no-AI keyword baseline, same candidate rules
.venv/Scripts/python eval/evaluate.py <input>                # precision@10, recall, cut-point error vs an answer key
.venv/Scripts/python eval/blind_review.py make <input>       # blind human review: AI top 10 vs keyword top 10, shuffled
.venv/Scripts/python eval/blind_review.py score <input>      # ...then reveal which method picked what
```

- **`verify_outputs.py`** re-reads the original files (without the parser) and checks that every
  start time, hook and cliffhanger is really in the script, each end equals the script's written
  `End:` time (or doesn't spill into the next caption when none is written), lengths are 20-60s,
  and the stranger never saw timestamps or the show name. It was itself tested by planting errors
  (all caught).
- **`blind_review.py`** is for shows with no answer key: a person rates both methods' promos
  without knowing which method picked which. The sheet and key quote the script, so they are
  written to `data/reviews/` (private).
- **`evaluate.py`** compares the ranked list with an answer key (`data/my_picks.txt`, format in the
  file's docstring) and with the keyword baseline, and lists misses and false alarms.

---

## Key settings (`config.yaml`)

| Setting | Value | Reason |
|---|---|---|
| `llm.model` | `groq/openai/gpt-oss-120b` | free tier with ~1,000 requests/day (Gemini Flash free = 20/day) |
| `llm.fallback_model` | `groq/openai/gpt-oss-20b` | separate daily budget, used when the main model is limited |
| `llm.max_tokens` / `reasoning_effort` | 4200 / `low` | prompt + reply must fit Groq's free 8,000 tokens per minute |
| `promo.min/max_seconds` | 20 / 60 | the brief |
| `promo.selection` | `relative`, top 10% (widens to 25% if too few) | model-independent |
| `promo.allow_joins` | `false` | in testing, joined clips mostly mixed unrelated scenes |
| `ranking.*` | early bonus x1.05, spoiler guard x0.9, 25-45s preferred | posting strategy; all editable |

---

## Known limitations

- The AI reads **text**: a moment that is only visual and not described in the script can be missed.
  Kuku screenplays describe actions and shots, so this matters far less than on auto-captions.
- AI scores vary slightly run to run; the cache makes a saved run reproducible.
- Free tiers are slow (rate-limit waits); a paid key removes the waiting.
- The stranger test is still an AI imitating a viewer, not a real audience.

---

## Project layout

```
src/        adapter.py (formats) · parser.py (timeline, episodes) · tagger.py (AI scores)
            candidates.py (clips) · cold_viewer.py (stranger test) · ranker.py · llm.py (model wrapper) · run.py
eval/       verify_outputs.py · baseline_keywords.py · evaluate.py · blind_review.py
samples/    synthetic screenplay for trying the tool
app.py      Streamlit editor app
config.yaml settings (model in one line)
ai_notes.txt  AI tools used + places where AI (and my design) got it wrong
```

**Data policy:** scripts, transcripts, the Kuku input pack, AI caches and outputs are **not** in this
repository (`data/`, `cache/`, `outputs/` are git-ignored). The Kuku material is confidential.

---

# AI Promo Intelligence Studio (multi-agent editorial copilot)

> Branch `feature/promo-intelligence-studio`. This **extends** the tool above and does not replace it:
> `python src/run.py`, `app.py`, `eval/` and the 30 submitted Kuku promos are unchanged. A test checks the
> submitted output files' SHA-256 hashes.

## 1. Overview
The pipeline finds promos once. The studio turns that into a working tool for the promo team:
- **four specialised AI agents** re-judge the shortlist
- a **story graph** shows who is who and what happens
- a **copilot** answers editors' questions from the data
- an **editor feedback loop** and a **REST API** with **n8n** hooks support automation

## 2. Problem it solves
Editors need more than a list. They ask why one clip beats another, whether a stranger will follow it, which promos feature a given character, and what is left to review. Each answer used to mean reading the scripts again.

## 3. Features
| Area | What it does |
|---|---|
| Multi-agent ranking | Hook, Cliffhanger, Stranger and Editorial Critic agents. Results are stored as a **separate** `agents` ranking, so the original ranking is never touched |
| Story Intelligence | Characters, aliases, episodes and shared scenes come from speaker labels (code). Events and stated relationships come from the writers' episode loglines (AI), are grounded against real speaker names, and carry confidence and source. An interactive NetworkX/pyvis graph shows the result |
| Editorial Copilot | Chat over **8 fixed read-only tools**. The AI picks a tool, code runs it, and the AI answers only from that data, citing `#rank (EpN m:ss-m:ss)`. If it cites nothing, code attaches the data. An offline rule-based mode works without a key |
| Feedback Center | Approve / Reject (reason required) / Needs revision, plus a comment. Each review stores a snapshot. A conservative, transparent calibration (rules turn on only with enough evidence) keeps an audit trail and never edits the original ranks |
| API + automation | FastAPI with background jobs and job status. An n8n webhook (secret, off by default) sends job events |

## 4. Architecture
```
   Streamlit studio (frontend/)      FastAPI (backend/main.py)  <-- n8n webhook (automation/)
                 |                              |
                 +-------------+----------------+
                    service layer (backend/services, studio_cli.py)
     +-------------+--------------+------------------+----------------+
 import_service  agents/ (4 agents  story_intelligence/  copilot/ (tools,  feedback/ (reviews,
 (loads original  + orchestrator)   (characters, events,  routing, grounded calibration,
  outputs/)            |             NetworkX graph)      answers)          preferences)
     |                 v
     |     ORIGINAL src/: candidates.build_candidates + validate_candidate (code)
     v                                                     LiteLLM wrapper (src/llm.py): cache, JSON
 SQLite (database/): projects, episodes, promos(original|agents), agent outputs,   validation, retry,
 characters, events, relationships, feedback, calibrations, jobs, usage, chat      fallback, usage log
```
**Rule kept from the original:** no AI ever writes a timestamp. Agents return line ids and scores only. Clips are built by the original `build_candidates`, and each one is re-checked by `validate_candidate`: the ids exist, the times equal the parser's times, the clip stays inside one episode, and it lasts 20–60 s.

## 5. The agents
| Agent | Sees | Returns (validated JSON) |
|---|---|---|
| Hook | shortlisted lines + 2 lines of lead-in | `line_id, hook_score 0-5, hook_type, reason, confidence` |
| Cliffhanger | shortlisted lines + what follows | `line_id, cliffhanger_score 0-5, cliffhanger_type, reason, confidence` |
| Stranger | only the clip text (blind, fresh call) | `standalone_score, context_dependency low/medium/high, missing_context, explanation` |
| Editorial Critic | a batch of clips (to spot repetition) | `editorial_verdict approve/review/reject, strengths, weaknesses, alternative_suggestion, final_reasoning` |

The orchestrator re-uses the original tagger's top 15% lines as the shortlist, so the full script is not paid for twice. Agent score = `(hook+1)(cliff+1)(standalone+1)/216x100` multiplied by the critic factor (approve 1.0, review 0.85, reject 0.6). Every stored output records which model answered it.

## 6. Tech stack
Python 3.14 · Streamlit 1.67 + Altair (charts) · FastAPI + Uvicorn · SQLite (WAL) · NetworkX + pyvis · LiteLLM (Groq `openai/gpt-oss-120b` and `gpt-oss-20b`; Gemini optional) · pandas · pytest.

## 7. Folder structure
```
agents/             hook_agent, cliffhanger_agent, stranger_agent, editorial_critic_agent, agent_orchestrator, base
story_intelligence/ character_extractor, event_extractor, relationship_graph, narrative_analyzer
copilot/            tools (whitelist), retrieval (offline routing), assistant (grounded chat)
feedback/           feedback_service, ranking_calibration, preference_learning
database/           models (schema), database (connections), repositories (all SQL lives here)
backend/            main.py (FastAPI), services/ (import, processing jobs, story)
automation/         webhook (inbound n8n), n8n_integration (outbound events)
frontend/           app.py (shell + navigation), ui.py (design system), intro.py (5-s opening), assets/, views/ (6 pages)
common/             paths, settings (config + env, key redaction)
studio_cli.py       command line for the same services
tests/              36 offline tests (mock LLM, clearly labelled)
docs/               N8N_INTEGRATION.md, STUDIO_EVALUATION.md
```

## 8. Setup (Windows PowerShell)
```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env        # open .env and paste GROQ_API_KEY yourself (never in chat)
.venv\Scripts\python src\llm.py --test
```

## 9. Environment variables
| Variable | Default | Purpose |
|---|---|---|
| `GROQ_API_KEY`, `GEMINI_API_KEY` | none | model keys (read by LiteLLM, never shown or logged) |
| `STUDIO_DB` | `data/studio.db` | SQLite file (git-ignored) |
| `STUDIO_<ROLE>_MODEL` | config.yaml `studio:` | per-role model: AGENT, STRANGER, CRITIC, STORY, COPILOT |
| `N8N_ENABLED` | `false` | turn the n8n integration on |
| `N8N_WEBHOOK_SECRET` | none | required header secret for the inbound webhook |
| `N8N_CALLBACK_URL` | none | where job events are sent |

## 10. Run it
```powershell
# 1) (optional) the ORIGINAL pipeline, unchanged
.venv\Scripts\python src\run.py --input data\<your_show_folder>
# 2) load its results into the studio, then build the story graph
.venv\Scripts\python -m studio_cli import <show>
.venv\Scripts\python -m studio_cli story <show>            # add --no-llm for script facts only
# 3) multi-agent ranking on a small subset (real AI calls, cached afterwards)
.venv\Scripts\python -m studio_cli agents <show> --episodes 1-3
# 4) the studio UI  -> http://localhost:8501
.venv\Scripts\python -m streamlit run frontend\app.py        # theme: .streamlit\config.toml
# 5) the API  -> http://localhost:8000/docs
.venv\Scripts\python -m uvicorn backend.main:app --port 8000
```
Steps 2–3 can also be run from **Settings → Projects & processing** in the UI.

### Studio interface (monochrome, 3D)
- **Palette:** black, white and gray only (`--background #000`, surfaces `#111/#181818/#222`, borders `#303030/#444`, text `#FFF/#B3B3B3/#777`). A test (`test_frontend_is_monochrome`) fails if any hex colour in the frontend has R≠G≠B. Status uses shape + word, never hue: ● Approved · ◐ Needs revision · ✕ Rejected · ○ Pending.
- **Type:** Archivo Black (display, uppercase page titles and product name) and Inter (text), both bundled in `frontend/static/fonts` (OFL).
- **Intro (`frontend/static/js/intro3d.js`):** a 5-second Three.js scene:
  - a brushed-metal film reel (extruded flanges with cut-outs, a matte film coil and a hub) revealed by a white key light
  - a sprocketed film strip flowing along a 3D curve, with three frames lifted out as the promo
  - textured screenplay pages and an editorial timeline with clip markers, under real shadows and a camera dolly
  - large **AI PROMO / INTELLIGENCE STUDIO** title
  - Behaviour: Skip / Esc; shown once (localStorage); replay from Settings → Appearance & intro or `/?intro=1`; reduced motion shows one still frame; with no WebGL a CSS version plays; any error removes the overlay.
- **3D charts (`frontend/static/js/chart3d.js`):** Three.js bars with real depth and shadows. You can drag to rotate, scroll to zoom, use Reset view, and hover for real-data tooltips. Dashboard charts: promos per episode, moment types, and studio AI usage (prompt and completion tokens as two depth rows). Every chart has a **Table** view as the accessible alternative.
- **Local only:** Three.js 0.187 (MIT) and fonts are vendored under `frontend/static` (see `THIRD_PARTY.txt`) and served by Streamlit static serving. The app makes no CDN requests.
- **Pages:**
  - Dashboard: KPIs, top 5, and the 3D charts
  - Promo Discovery: candidate table plus an inspection panel with overview, script, agents and review, and side-by-side compare
  - Story Intelligence: grayscale network with dashed conflict edges, directory, grounded/unverified events, and an episode heatmap
  - Copilot: conversations, suggestions, and sources
  - Feedback Center
  - Settings: General, Project, AI configuration, Workflow, System information, Appearance & intro

## 11. API
| Method | Path | |
|---|---|---|
| POST | `/api/projects` | create with uploads (`{"name","title","files":[{"filename","content"}]}`), or register existing outputs |
| POST | `/api/projects/{id}/process` | start a job: `mode` import / pipeline / agents / story, `episodes`, `use_llm`. Returns 202 + job id |
| GET | `/api/projects/{id}/status` | job status, progress, result |
| GET | `/api/projects/{id}/promos` | `ranking=original/agents`, `episode`, `verdict`, `q`, `limit` |
| GET | `/api/projects/{id}/story` | characters, relationships, events (+ verified counts) |
| POST | `/api/promos/{promo_id}/feedback` | `decision`, `reason`, `comment` |
| GET | `/api/projects/{id}/feedback` | summary, latest decisions, calibration, preferences |
| POST | `/api/copilot/chat` | `project_id`, `message`, `session_id`, `use_llm` |
| GET | `/api/projects/{id}/analytics` | counts, distributions, model usage, jobs |
| POST | `/api/webhooks/n8n` | header `X-Webhook-Secret` (see docs/N8N_INTEGRATION.md) |

## 12. Tests
```powershell
.venv\Scripts\python -m pytest tests -q
```
The 36 tests run offline and cover:
- parsing, timestamps, episode boundaries, durations, candidates and ranking determinism
- agent JSON validation, timestamp-tamper detection, broken-model handling, missing-key errors, model switching and cache keys
- the orchestrator end to end, story graph grounding, and copilot tool whitelisting, retrieval and invented-id dropping
- feedback persistence, conservative calibration, webhook security, outbound payload safety and key redaction
- every API endpoint, every frontend page, the empty state, protection of the submitted show, and the unchanged hashes of the submitted outputs

The **mock LLM** (`tests/fakes.py`, model name `mock/deterministic-test-llm`) exists only in tests and is never shown as a model result. The synthetic test show is built from the public `samples/`, not from Kuku files.

## 13. Security and confidentiality
- Keys are read only from `.env` and redacted from errors and job logs. The API never returns them.
- The copilot cannot run SQL or code: it has 8 whitelisted tools with typed arguments and parameterised queries, and it drops promo ids that aren't in its data.
- Uploads accept only `.txt/.srt/.vtt/.md` with safe names and are stored in git-ignored `data/uploads/`.
- The submitted show is **protected**: the API/UI refuse to re-run the pipeline over it.
- n8n is off by default. Its payloads carry ids, counts and status only, never script text.

## 14. Cost and API usage
Measured on Groq's free tier (₹0). All calls are cached, so re-running costs nothing. Details are in [docs/STUDIO_EVALUATION.md](docs/STUDIO_EVALUATION.md).

## 15. Evaluation
[docs/STUDIO_EVALUATION.md](docs/STUDIO_EVALUATION.md) compares the original and multi-agent rankings side by side on the same episodes. It is honest about what was and wasn't measured.

## 16. Known limitations
- The multi-agent ranking was run on **episodes 1–3 only**, to protect the free-tier quota. It has not been run on all 50 episodes.
- Agent scores and original scores use different inputs, so their **numbers are not comparable**. Compare the order and the editor verdicts instead.
- AI story facts come from **loglines** (one sentence per episode), so they are coarse. The code does not merge a disguised character with their real name.
- Calibration is rule-based and needs ≥5 reviews. It is not machine learning.
- n8n was tested with the API test client only, not a live n8n instance.
- SQLite plus background threads suit one team on one machine. Use Postgres and a job queue for scale.

## 17. Interview demo (5 minutes)
1. `pytest` gives 36 passed, including "submitted outputs unchanged".
2. Studio **Dashboard**: 30 original promos and 10 multi-agent promos (episodes 1–3).
3. **Promo Discovery**: switch Original and Multi-agent, open #1, read the script lines and the agent reviews, then Approve it.
4. **Story Intelligence**: focus on the lead character to see connections, events and verified flags.
5. **Copilot**: ask "Why did the Episode 16 promo rank first?" and show the tool and data used.
6. **Feedback Center**: show the calibration rules and save an audit snapshot.
7. Swap a model: `$env:STUDIO_CRITIC_MODEL="gemini/gemini-3.8-flash"`, then re-run the agents.
