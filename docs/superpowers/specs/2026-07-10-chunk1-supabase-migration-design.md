# Chunk 1: Supabase schema + migrate off SQLite

## Context

claudeshorts is being rebuilt into a full automation platform per `goal.md`
(plugin-based providers, job queue, service layer, REST API, Telegram bot,
scheduling, multi-channel publishing). This is chunk 1 of 14 in that roadmap
(see `TASK_QUEUE.md` / session task list for the full order). It is the
foundation every later chunk depends on: nothing else can be Postgres-native
until the datastore is.

The project currently persists everything in a single SQLite file
(`data/app.db`), initialized by `claudeshorts/store/db.py`. Per explicit user
decision, **SQLite is being dropped entirely** — a new Supabase project
(`claudeshorts`, project id `nddlutmilajkqtoygmfi`, region `us-east-1`, free
tier) is the sole datastore going forward, including for existing data. The
final product must be deployable on a Raspberry Pi, so the datastore access
pattern needs to be resilient to a low-power ARM host with a home network
connection to a cloud database (not a local file).

An older, unrelated Supabase project (`adhdsat`) was paused as part of this
decision; it is unrelated to claudeshorts and not touched further here.

## Current state

`claudeshorts/store/db.py` defines 7 SQLite tables: `items`, `posts`,
`threads`, `post_threads`, `runs`, `pins`, `jobs`. Six call sites use the
store layer, none touch SQL directly:

- `claudeshorts/dashboard/app.py`
- `claudeshorts/dashboard/jobs.py`
- `claudeshorts/generate/runner.py`
- `claudeshorts/generate/select.py`
- `claudeshorts/ingest/runner.py`
- `claudeshorts/orchestrate/runner.py`
- `claudeshorts/publish/exporter.py`
- `claudeshorts/review/queue.py`

Each table already has a corresponding module (`store/items.py`,
`store/posts.py`, `store/threads.py`, `store/pins.py`, `store/runs.py`,
`store/jobs.py`) wrapping its SQL behind plain functions. No existing test
suite covers the store layer.

Current row counts in `data/app.db`: 616 items, 13 posts, 13 threads, 13
post_threads, 0 pins, 3 runs, 1 job — small enough for a straightforward
one-time migration script.

## Decision: DB access approach

**Raw SQL via psycopg3** against Supabase's **Session Pooler** connection
string (not the Transaction pooler, which is meant for high-churn serverless
callers; a long-running RPi process holding a handful of persistent
connections is exactly what the session pooler is for).

Rejected alternatives:
- **Supabase Python SDK (PostgREST)** — would require rewriting store/*.py
  query logic against a less expressive query builder; no benefit here since
  Auth/Storage/Realtime aren't needed.
- **SQLAlchemy Core + Alembic** — heavier abstraction than this project's
  scale warrants; conflicts with goal.md's "favor readability over
  cleverness" and "simple abstractions" principles.

`store/items.py`, `posts.py`, `threads.py`, `pins.py`, `runs.py`, `jobs.py`
keep their exact public function signatures. Only their internals change
(sqlite3 calls → psycopg3 calls). The 8 calling files above are not touched.
A `StorageProvider` `typing.Protocol` documents the contract these modules
satisfy — enough to honor goal.md's "always code against interfaces, never
hardcode providers" without building a plugin-loader system prematurely (a
second backend can promote this to a real plugin registry later if one ever
shows up).

## Schema mapping (SQLite → Postgres)

| SQLite | Postgres | Notes |
|---|---|---|
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `BIGSERIAL PRIMARY KEY` | |
| `TEXT` timestamp, `datetime('now')` default | `TIMESTAMPTZ`, `DEFAULT now()` | |
| JSON-as-TEXT (`item_ids`, `slides_json`, `theme_json`, `captions_json`, `log`) | `JSONB` | enables querying later (e.g. dashboard filters) instead of full-column parse |
| `TEXT` enums (`status` columns) | `TEXT` with `CHECK` constraint | keep simple text, add CHECK for the known value set per table |
| Foreign keys + `ON DELETE CASCADE` | identical | |
| Indexes (`idx_*`) | identical, `CREATE INDEX` | |

`jobs` table is migrated as-is in this chunk (structure only, not behavior) —
chunk 2 extends/replaces it with the full state machine (`PENDING`,
`RUNNING`, `WAITING_FOR_APPROVAL`, `RETRYING`, `FAILED`, `COMPLETED`,
`CANCELLED`) and worker semantics. This chunk's job is just "the same table,
on Postgres."

## Migration script

`scripts/migrate_sqlite_to_supabase.py`:

- Reads all 7 tables from `data/app.db` in dependency order: `items` →
  `posts` → `threads` → `post_threads` → `pins` → `runs` → `jobs`.
- Inserts into Supabase preserving primary key `id` values explicitly (so
  `post_threads` foreign keys stay valid), then resets each table's
  `BIGSERIAL` sequence to `MAX(id) + 1` afterward.
- Verifies row counts match source vs destination per table before exiting
  successfully.
- Guarded against accidental re-runs: refuses to proceed if any destination
  table is non-empty, unless invoked with `--force`.
- Leaves `data/app.db` untouched (read-only) as a local backup; nothing
  deletes it.

## Secrets

`.env.example` gains a `SUPABASE_DB_URL` entry (session pooler connection
string format) with a comment explaining it's required once this chunk lands.
The real value goes only in `.env` (gitignored), consistent with existing
convention.

## RPi / resilience

The datastore is now network-dependent (Supabase is cloud-hosted) instead of
a local file. This chunk's scope is limited to making that connection fail
fast and clearly:

- `connect_timeout` and TCP keepalives set on the psycopg3 connection.
- A connection failure raises a clear, catchable exception from the store
  layer rather than hanging indefinitely.

Retry-on-transient-DB-error and offline-queueing behavior is explicitly
**out of scope for this chunk** — that logic belongs in chunk 2's job queue
(jobs can sit in `PENDING`/`RETRYING` state until connectivity returns), not
in the base storage layer.

## Testing

No test suite exists for `store/*.py` today. This chunk adds minimal tests
exercising each store module's public functions against a real Postgres
target — either a disposable Supabase branch or a local Postgres via Docker,
decided at plan time (both are viable; branches cost nothing extra on this
org per the earlier `$0/month` project-cost check, but add a dependency on
network access during test runs, whereas Docker keeps tests offline-capable
for RPi-adjacent dev work).

## Out of scope for this chunk

- Job queue state machine and worker loop (chunk 2).
- Service layer extraction (chunk 3).
- Any plugin-based storage provider registry beyond the single `Protocol`
  (revisit only if a second backend is ever actually needed).
