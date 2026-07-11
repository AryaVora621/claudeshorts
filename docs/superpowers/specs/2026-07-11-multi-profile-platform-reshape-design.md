# Multi-profile platform reshape — design

> Status: **Sub-project A (multi-profile data model) is fully specced below
> and ready to plan.** Sub-projects B (analytics collection) and C (dashboard
> reshape) are scoped at a high level here so the whole reshape is documented
> in one place, but each needs its own brainstorming pass before planning —
> don't jump straight to implementing B/C from this doc alone.

## Why

The project currently assumes a single implicit channel (`channel.name`/
`channel.handle` in `config/settings.yaml`, still stuck on the pre-rebrand
"Midnight Curiosity" value even though the live brand is fork.ai). The
operator actually runs — or wants to run — **multiple independent content
profiles** from one instance:

- **fork.ai** — tech/AI news, the existing pipeline's content.
- **Midnight Curiosity** — a genuinely separate niche (study/SAT material),
  not a re-skin: different topic sources, different generation voice/tone.
- More profiles may be added later; the architecture should not hardcode two.

On top of that, the operator wants the system to run **mostly headless**
(automation runs unattended, human review becomes optional rather than
mandatory) with a **monitoring dashboard** giving cross-channel analytics
visibility, while still supporting human review of posts where wanted.

## Decisions made during brainstorming

1. **One running instance manages all profiles** — single dashboard, single
   job queue/scheduler/worker process, not separate deployments per profile.
   (Confirmed over the alternative of running separate instances per
   profile with analytics as the only aggregation layer.)
2. **Human approval is a per-profile toggle** (`auto_publish`), not a global
   switch — e.g. fork.ai can go fully headless once proven while Midnight
   Curiosity stays review-gated as a newer, less-trusted content operation.
3. **Analytics collection will use browser scraping** of platform dashboards
   (YouTube Studio / Instagram Professional Dashboard / TikTok Analytics)
   via the existing `browser/profiles.py`-style logged-in session pattern,
   **plus the official vidIQ MCP server** (`vidiq.com/mcp`) as a bonus
   YouTube-only, read-only, quota-free data source (requires a vidIQ Max
   plan). Not platform APIs (YouTube Analytics API etc.) — consistent with
   the operator's earlier decision to skip API-credential-gated publishing
   in favor of the browser-automation path.
4. **TikTok stays in scope.** A deep-research note flagged TikTok as
   officially restricted in India (IT Act Section 69A); the operator is
   building from India but will operate the system from the US, so this is
   not a blocker.
5. **A prior "deep research" report's audit of this repo (recommending
   scrap-and-rebuild) was based on stale information** — likely a GitHub
   snapshot from before this session pushed 130+ commits of the goal.md
   platform rebuild to `origin/main`. It does not reflect the current
   codebase (no Remotion, already has a job queue/scheduler/REST API/
   structured logging). Its general industry-research sections (config-
   driven multi-tenant architecture, retention-based analytics metrics,
   `rebrowser-playwright` for scrape-detection resistance) remain useful
   input and are folded into this design and the future B/C specs; its
   specific verdict on this codebase is not being acted on.

## Sub-project A: multi-profile data model

### Approach

Hybrid storage, chosen over all-YAML and all-DB alternatives:

- **`profiles` table (Postgres)** holds the *operational* fields other
  tables need to join against and that change at runtime: `slug`,
  `display_name`, `active`, `auto_publish`, `posts_per_day`, `platforms`
  (JSONB list, e.g. `["youtube","tiktok","instagram"]`), `created_at`.
- **`config/profiles/<slug>/` (versionable files)** holds the *content
  identity* that's naturally prose/list-shaped and belongs in git history:
  - `profile.yaml` — display name, brand theme/colors, default
    `posts_per_day`/`platforms` (seeds the DB row on first boot), and the
    browser-automation session metadata that `claudeshorts/browser/
    profiles.py` currently stores in a flat `config/profiles/<slug>.yaml`
    (`login_health`, `browser`, `notes`) — **merged in, not duplicated**,
    since a content profile inherently owns its own browser session for
    scraping/publishing.
  - `sources.yaml` — this profile's RSS/HN/Reddit feed list (was the global
    `config/sources.yaml`; that file's shape is unchanged, just now loaded
    per-profile from this path instead of one global location).
  - `prompt.md` — the generation system prompt / tone-and-style rules
    specific to this profile (fork.ai: concise tech/AI voice; Midnight
    Curiosity: calm study/SAT voice).

The DB row is the join key everything else references (`profile_id`); the
YAML files are loaded by `slug` when a service needs this profile's content
identity. This mirrors the project's existing `settings.yaml`/`sources.yaml`
config-over-code convention rather than introducing a new pattern.

### Schema changes (additive, same style as existing `store/db.py`)

```sql
CREATE TABLE IF NOT EXISTS profiles (
    id            BIGSERIAL PRIMARY KEY,
    slug          TEXT        NOT NULL UNIQUE,
    display_name  TEXT        NOT NULL,
    active        BOOLEAN     NOT NULL DEFAULT true,
    auto_publish  BOOLEAN     NOT NULL DEFAULT false,
    posts_per_day INTEGER     NOT NULL DEFAULT 3,
    platforms     JSONB       NOT NULL DEFAULT '["youtube","tiktok","instagram"]'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE items     ADD COLUMN IF NOT EXISTS profile_id BIGINT REFERENCES profiles(id);
ALTER TABLE posts     ADD COLUMN IF NOT EXISTS profile_id BIGINT REFERENCES profiles(id);
ALTER TABLE threads   ADD COLUMN IF NOT EXISTS profile_id BIGINT REFERENCES profiles(id);
ALTER TABLE runs      ADD COLUMN IF NOT EXISTS profile_id BIGINT REFERENCES profiles(id);
ALTER TABLE schedules ADD COLUMN IF NOT EXISTS profile_id BIGINT REFERENCES profiles(id);
-- jobs.payload (JSONB) carries profile_id per-job; no column needed there.
```

`items`'s dedupe key changes from a global-unique `content_hash` to a
**composite unique index on `(profile_id, content_hash)`** — two profiles
covering the same story independently (e.g. both fork.ai and a future tech
profile picking up the same launch) is fine and expected; dedupe should
only apply within a profile, not across profiles. Add matching
`(profile_id, ...)` indexes mirroring the existing status/date indexes on
`posts`/`runs`/`schedules`.

### Migration path

One-time additive script (same spirit as `scripts/migrate_sqlite_to_supabase.py`):

1. Insert `fork-ai` (active, seeded from `config/profiles/fork-ai/profile.yaml`)
   and `midnight-curiosity` (active, empty so far) profile rows.
2. Backfill every existing `profile_id IS NULL` row in `items`/`posts`/
   `threads`/`runs` to `fork-ai`'s id — all historical content was
   generated under the tech/AI identity fork.ai now represents.
3. Verify counts (existing rows with `profile_id IS NULL` == 0 after
   backfill), same verification pattern as the SQLite migration script.

### Services impact

- `ingest/select/generate` all gain a `profile_id` parameter and load that
  profile's `sources.yaml`/`prompt.md` instead of the current single global
  config. `generate/style_rules.py`'s brand-color/layout rules likely also
  move under `profile.yaml` (each profile's own brand palette), while the
  *content-subject* color pinning (Nvidia→green, etc., within a post) stays
  as-is — these are orthogonal (profile brand vs. story subject).
- `pipeline_service.run_full_pipeline_service` takes `profile_id`; the
  scheduler seeds one `full_run`/`drain_scheduled_posts`/`weekly_report`
  schedule set **per active profile** instead of one global set.
- The `runs` idempotency guard becomes `(profile_id, run_date)`-scoped so
  two profiles can each complete their own "today's run" independently.
- **`auto_publish` is the actual headless mechanism**: `posts_service`'s
  render→review path checks the post's profile's `auto_publish` flag; if
  true, a successfully rendered post exports immediately instead of
  sitting in `rendered` status waiting for a dashboard Approve click. If
  false (default), today's review-gate behavior is unchanged.
- Dashboard/API routes need a profile filter — deferred to sub-project C,
  but every query this sub-project touches must expose `profile_id` so C
  has something to filter by.

### Explicitly out of scope for sub-project A

- Real analytics collection (browser scraping, vidIQ MCP) — sub-project B.
- The dashboard reshape / analytics-first monitoring UI — sub-project C.
- Actual TikTok/Instagram publish automation — unchanged; still gated on
  credentials/calibration independent of this reshape (see
  `docs/ARCHITECTURE.md`'s "what's deferred" section).
- `rebrowser-playwright` adoption — bundled into sub-project B, since that's
  where scraping-detection risk actually lives (analytics scraping, not the
  data model).

## Sub-project B (high-level scope, not yet planned)

Real cross-platform analytics: browser-scrape YouTube Studio / Instagram
Professional Dashboard / TikTok Analytics using per-profile logged-in
sessions (building on sub-project A's merged `browser/profiles.py` +
`config/profiles/<slug>/profile.yaml`), prioritizing retention/conversion
metrics (7-second retention, average view duration) over vanity metrics
(likes/views) per the deep-research note's finding that vanity metrics are
too noisy at low sample sizes to act on. Adopt `rebrowser-playwright` over
plain Playwright for scrape-detection resistance. Wire the vidIQ MCP server
in as a bonus YouTube data source. Replaces `reporting_service.weekly_report`'s
hardcoded `platform_engagement: {"status": "pending"}` placeholder with real
data. Needs its own brainstorming session before a plan is written — open
questions include scrape frequency/scheduling, where scraped data is stored
(new table vs. extending `runs`), and how login-session expiry is surfaced
to the operator.

## Sub-project C (high-level scope, not yet planned)

Dashboard reshape: a new analytics-forward "monitoring" home view (per-profile
and cross-profile stat tiles/trends, headless automation status, job health)
replacing today's operator-console-first Overview page as the default
landing view. The existing Review/Posts/Articles/Schedule/Threads/Runs/Jobs/
Settings pages stay, gain a profile filter/selector, and the review queue
specifically becomes conditional on the viewed profile's `auto_publish`
flag (profiles with it off show their pending reviews prominently; profiles
with it on show recent-auto-published activity instead). Needs its own
brainstorming session — open questions include exact stat tile selection,
whether profile switching is a page-level selector or all-profiles-at-once
layout, and how alerting/notification (Telegram bot ties in here) surfaces
analytics-driven signals vs. just job failures as it does today.
