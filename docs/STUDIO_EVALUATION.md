# Studio evaluation: original pipeline vs multi-agent ranking

**Show:** the company's 50-episode input pack (confidential; title and script content withheld).
**Date:** 2026-11-17. **Everything below comes from real runs.** No mock data appears in this report.

## 1. What was run

| Run | Scope | Model calls | Tokens | Time | Cost |
|---|---|---|---|---|---|
| Original pipeline (submitted, unchanged) | all 50 episodes | 59 | (saved run log is the final fully-cached reproduction: 59/59 cached, 12 s) | — | ₹0 (Groq free) |
| Multi-agent ranking | **episodes 1–3 only** | 14 (hook 1, cliffhanger 1, stranger 10, critic 2) | 23,375 | 62 s | ₹0 (Groq free) |
| Story events from loglines | all 50 loglines | 5 | 10,939 | 36 s | ₹0 |
| Copilot (3 real questions) | — | 1 plan + 1 answer per question (live calls logged in `model_usage_logs`; repeats cached) | ~4k | ~10 s | ₹0 |

Models: hook, cliffhanger and critic agents used `groq/openai/gpt-oss-120b`. The stranger agent used `groq/openai/gpt-oss-20b`. Every stored agent output records its model.

**Why only episodes 1–3:** the brief and the free tier (200k tokens per day per model) favour a small, representative test. At about 7.8k tokens per episode, a full 50-episode agent run would need roughly 390k tokens, which is about two days of free quota or a paid key. That run **has not been done**, and no full-show agent numbers are claimed.

## 2. The original ranking is preserved
- The original 30 promos are imported read-only as `ranking_kind = original`. Agent results are stored separately as `agents`.
- The test `test_original_kuku_outputs_unchanged` checks the SHA-256 of the 10 submitted output files against hashes recorded before the studio was built. It passes.
- The API and UI refuse to re-run the pipeline over the submitted show.

## 3. Both rankings on episodes 1–3

The original ranking has 4 promos in episodes 1–3, at overall ranks #2, #8, #11 and #25. The agents produced 10.

| Agents # | Cut | Agent scores (hook/cliff/standalone) | Critic | Same or near clip in the original |
|---|---|---|---|---|
| 1 | Ep3 1:00–1:26 | 4 / 4 / 5 | approve | ≈ original #11 (Ep3 0:58–1:26) |
| 2 | Ep3 0:21–1:00 | 3 / 5 / 4 | review | — |
| 3 | Ep1 0:26–1:00 | 2 / 5 / 5 | review | overlaps original #25 (Ep1 0:39–1:00) |
| 4 | Ep1 1:00–1:59 | 2 / 4 / 4 | approve | — |
| 5 | Ep3 0:09–0:40 | 3 / 3 / 4 | review | — |
| 6 | Ep3 0:38–1:12 | 3 / 4 / 4 | reject | — |
| 7 | Ep2 1:04–1:33 | 2 / 4 / 3 | review | — |
| 8 | Ep2 0:00–0:30 | 2 / 3 / 4 | review | **= original #8** |
| 9 | Ep3 1:24–2:16 | 5 / 5 / 1 | **reject** | **= original #2** |
| 10 | Ep1 0:18–0:43 | 2 / 2 / 2 | reject | — |

Every agent clip passed the deterministic `validate_candidate` check: the ids exist, the times equal the parser's, the clip stays in one episode, and it lasts 20–60 s.

## 4. What this shows (honestly)

**Where the agents add something**
- **Context dependency becomes visible.** The original stranger test gave nearly every Kuku promo a low standalone score (average 0.63/5), so that score barely separated promos. The agent stranger spreads its scores (1–5) and labels context dependency low, medium or high, which editors can filter on.
- **Editorial reasons are readable.** For example: "Needs a sharper visual hook; consider leading with [a colder line already in the clip]." Or: "Hook weak, cliffhanger artificial, repeats earlier moments." The critic also catches near-duplicates (agents #5 and #6 overlap and #6 was rejected as redundant).
- **More choice per episode.** Episodes 1–3 went from 4 shortlisted promos to 10, each with a verdict.

**Where the agents were wrong, by the one human check available**
- Original #2 (Ep3 1:24–2:16, an action scene that ends on a surprise twist) was rated **good** in the user's own blind review (blind code P12). The critic **rejected** it: that the ending was resolved, not a hook. A human saw the same ending as a strong cliffhanger, but the critic read it as resolved. This is one data point and it goes **against** the agents.
- Original #8 (Ep2 0:00–0:30) was rated **average** in the blind review. The agents put it at #8 with verdict "review", which is consistent.
- The blind-review mapping above is by matching clip descriptions. The other agent clips have **no human rating yet**.

**Not comparable**
- Agent scores (7.5–69.4) and original scores (5.7–24.1) are computed from different inputs, mainly because the agent stranger gives much higher standalone scores. **Only orders and verdicts should be compared, not the numbers.**

**Verdict:** there is not enough evidence to say the multi-agent ranking is better. It is more informative (verdicts, context labels, reasons), and in the one human-checked disagreement it was wrong. The next step is to review the 10 agent promos in the Feedback Center (blind, like the original review) before trusting the agent order.

## 5. Story Intelligence (real run)
- **From code (certain):** 64 speaking characters, 4 alias groups, and 172 co-appearance pairs.
- **From AI (5 calls on the 50 loglines):** 68 events, of which **66 verified** (every named character matched a real speaker). 2 are marked unverified. There are 14 stated relationships (family, romantic, rivals, conflict), each with evidence text and its source episode.
- **Known gap:** the AI keeps a disguised alias of the lead and the lead as two people. The code only merges names by titles, not by plot reveals.

## 6. Copilot (real run, 3 questions)
| Question | Tool chosen by AI | Result |
|---|---|---|
| Why did the Episode 16 promo rank first? | `explain_promo(rank=1)` | Correct and grounded: hook 5, cliff 5, the actual cliffhanger line, early-episode bonus. All were in the data |
| Show me the agent-ranked promos with [lead character] | `search_promos([lead], agents)` | Listed 10 promos as `#rank (EpN m:ss-m:ss)`, matching the database |
| Which promos depend heavily on previous episodes? | `promos_by_context_dependency` | **Weak:** "All listed promos are marked as depending on earlier episodes", with no citations. **Fixed in code:** an AI answer with promo data but no `#` citation now gets the data list attached automatically |

## 7. Tests
`pytest tests -q`: **36 passed**, all offline. A mock LLM (labelled `mock/deterministic-test-llm`) is used only in tests.
