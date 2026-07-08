# custos-examinis

A multi-agent code and security auditor. You send it a small codebase (a zip
upload or a handful of inline files), and a graph of specialized agents reads
it in parallel: one looks for vulnerabilities, one reviews code quality, one
hunts for hardcoded secrets. Each agent is backed by a different LLM
provider, Claude for deep reasoning, Gemini for broad review, a local Ollama
model for cheap triage, with automatic fallback across providers if one is
down or rate-limited. The result is a single validated report.

I built this to go deeper on LangGraph than a toy example: real provider
routing with fallbacks, a sandboxed ingestion path, and a guardrail that
treats "the LLM might be lying or might have been prompt-injected" as a
design constraint rather than an afterthought.

## What's inside

- **Multi-provider routing.** `ModelRouter` maps a logical role (`deep_reasoning`,
  `broad_review`, `triage`, `summarize`) to an ordered provider chain, and each
  role has a *different* primary provider, so a normal run genuinely exercises
  Claude, Gemini, and Ollama instead of two of them sitting idle as unused
  fallbacks.
- **A graph, not a chain.** Three agents run in parallel over the same
  ingested file set, get deduplicated and summarized, then pass through a
  deterministic guardrail before anything is returned.
- **Sandboxed ingestion.** Zip uploads and inline files are parsed entirely
  in memory, guarded against zip-slip and path traversal, symlink entries,
  and size/count/extension limits. Nothing submitted is ever executed.
- **A guardrail that doesn't trust the model.** The last node before a report
  is returned is plain deterministic Python: every finding's file must exist
  in the sandboxed file set (so a prompt-injected "vulnerability in
  /etc/passwd" gets silently dropped), and secret snippets get forcibly
  redacted regardless of what the model echoed back.
- **A hybrid secrets scanner.** Most detection is a zero-LLM regex/entropy
  pre-filter; only ambiguous matches (not full files) get sent to the
  cheapest model for a real-secret-vs-placeholder classification.
- **Cost accounting.** Every LLM call's token usage is captured and rolled
  into an estimated dollar cost per audit, per provider.

## Project structure

```
src/custos_examinis/
  main.py             FastAPI app, middleware wiring, lifespan
  config.py           Settings (pydantic-settings, env-driven)
  logging.py          structlog JSON logging + secret redaction processor
  api/                routers, request/response schemas, dependency wiring
  middleware/          correlation id, timing, sliding-window rate limiting
  auth/                JWT bearer auth
  ingest/               sandboxed zip/inline ingestion (zip-slip guard, limits)
  domain/               Finding, AuditState, AuditReport, AgentError
  agents/                one module per agent, plus shared prompt helpers
  graph/                 build_audit_graph(): wires the agents into a StateGraph
  llm/                    ModelRouter, per-provider client factories, a sandboxed
                           file-read tool (built, not yet bound to any agent)
  jobs/                   Redis-backed job store and the background audit runner
  costs/                  token usage tracking and a static per-model price table
tests/
  unit/                  one test module per component, no network calls
  integration/            full-graph and full-API tests against fakes
  security/               zip-slip, prompt-injection delimiting, secret redaction
scripts/
  audit_local.py          audit a local directory directly, bypassing the API
```

## Running locally

### Docker

```
cp .env.example .env   # fill in whichever provider keys you have
docker compose up
```

This starts the API and Redis. Ollama is deliberately **not** part of the
default `up`, since it would pull multi-gigabyte model weights just to run
`docker compose up`. Start it explicitly when you want it:

```
docker compose --profile local-llm up
```

### Bare metal

```
python -m venv .venv && source .venv/bin/activate
pip install -e .
pip install ruff mypy pytest pytest-asyncio pytest-cov fakeredis types-pyjwt
uvicorn custos_examinis.main:app --reload
```

Redis is required at runtime (job state and rate limiting both live there),
even for local development.

### Auditing without the API

`scripts/audit_local.py` runs the same graph directly against a local
directory, without going through HTTP:

```
python scripts/audit_local.py ./some-project
```

This exists on purpose as a separate entrypoint. The API only accepts a zip
upload or inline files, both of which are request bodies from a caller who
is (at most) authenticated, not requests to read arbitrary paths off the
server's own filesystem. Exposing a "repo path" parameter over the API would
be a confused-deputy vulnerability: any authenticated caller could ask the
server to read its own local files. The local script has no such boundary
to cross, since it runs as the operator, on the operator's machine.

## Testing

```
pytest --cov --cov-report=term-missing
```

The entire suite runs with **zero real LLM API calls and zero real Redis**:
`ScriptedChatModel` (in `tests/fakes/`) stands in for every provider, including
simulating failures to exercise fallback ordering, and `fakeredis` stands in
for Redis. CI cannot and does not attempt to pull a local Ollama model or
call a live provider; that's a one-time manual step, see below.

## Configuration

All configuration is environment variables, see `.env.example` for the full
list with defaults. The ones worth calling out:

| Variable | Purpose |
|---|---|
| `JWT_SECRET` | signs/verifies API bearer tokens |
| `REDIS_URL` | job state and rate limiting |
| `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` | cloud provider credentials |
| `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | local provider endpoint |
| `AUDIT_RATE_LIMIT_PER_HOUR` | per-user cap on `POST /audits`, separate from the generic per-IP limit, since the expensive resource here is LLM spend |
| `MAX_ARCHIVE_SIZE_BYTES`, `MAX_FILE_COUNT`, `MAX_FILE_SIZE_BYTES` | ingestion sandbox limits |

## A note on scope

Every file's content is inlined directly into a single prompt call per
agent, capped by the ingestion size limits above. There is no multi-turn
tool-calling loop. `llm/tools.py` builds a sandboxed `read_file` tool bound
to the ingested file set (no real filesystem or network access) specifically
as the seam for a future large-repo mode, but no agent currently uses it.
Wiring it in properly needs a bounded tool-call loop and real testing before
it's worth turning on, see "what's next" below.

## What's next

- A real distributed job queue (arq or Celery) in place of `BackgroundTasks`,
  with LangGraph checkpointer-backed persistence so a long audit survives a
  process restart.
- Large-repo mode: bind the `read_file` tool for real, with a hard cap on
  tool-call iterations, possibly a `Send`-based per-file fan-out for the
  vulnerability agent instead of one inlined prompt.
- Multi-tenant auth and RBAC.
- Vector-store-grounded rules via retrieval instead of relying purely on
  model knowledge for vulnerability patterns.
- Server-sent events streaming of per-agent progress.
- A small cost dashboard over the token usage already being tracked.
- An LLM-based secondary "critic" pass on top of the deterministic guardrail,
  only once it has real evals behind it, not as a hand-wave.
- A documented manual Ollama smoke test (CI intentionally never pulls model
  weights).

## License

MIT
