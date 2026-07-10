# Chunk 10: Publishing platform plugins + multi-channel posting

## Context

Tenth of 14 chunks rebuilding claudeshorts per `goal.md`. This is the first
of the deferred, human-required chunks (per the user's "leave human
required tasks for last" instruction) — but per the established pattern
for this rebuild, the **plugin architecture and multi-channel data model
can be fully designed and implemented now**; only the final step (wiring
real YouTube/TikTok/Instagram API credentials and OAuth) is genuinely
blocked on the user and stays a last, explicitly-flagged task.

## Current state

`claudeshorts/publish/exporter.py::export_post` does one thing: copy the
rendered MP4 + carousel stills + a formatted caption into
`publish/<platform>/<date>/post_<id>/` for manual upload, then mark the
post `exported`. There is exactly one hardcoded channel identity
(`config/settings.yaml`'s `channel:` block — name/handle/logo) applied to
every post's outro/watermark. `platforms:` is a flat global list. No API
publishing exists or is stubbed; no per-channel branding, credentials, or
platform selection exists.

## Decision (confirmed with user)

Build the full multi-channel data model now, not just the plugin
interface — `config.channels` becomes a list, `posts` gains a
`channel_id`, and the pipeline runs per-channel — even though only one
channel exists today. This gives real infrastructure a second channel can
attach to later without another migration.

Two independent mechanisms, mirroring this rebuild's established patterns:

1. **`PublishProvider` plugin interface** (same shape as chunk 7's
   `LLMProvider`): a `publish(post, platform, channel) -> dict` method.
   Two kinds of providers: **`folder_export`** — today's assisted-export
   behavior, refactored to implement the interface, always available, no
   credentials needed, remains the default for every platform on every
   channel. Per-platform **API providers** (`youtube_api`, `tiktok_api`,
   `instagram_api`) get real interface classes now, each reading
   channel-scoped credentials from config/env and raising a clear,
   actionable error if unset — the code path exists and works the moment
   credentials do, exactly like chunk 7's `local`/`openai_compat`
   providers, without blocking this chunk on obtaining those credentials.
2. **Multi-channel routing**: a deterministic, config-driven
   `select_channel(item, channel_rules, default_channel) -> str` function
   (same keyword-matching shape as chunk 8's `select_layout`) picks which
   enabled channel a given item's post belongs to. With only one channel
   configured, every post trivially routes to it — the mechanism is
   inert until a second channel is added, but it's real and tested now.

Ingestion (`items`) stays channel-agnostic in this chunk — which raw news
items exist is unaffected by channels; only which channel a *generated
post* belongs to, and where/how it publishes, is new. Per-channel topic
sourcing (e.g. channel A only covers robotics news) is an explicit
non-goal here (see Out of scope).

## Architecture

### `claudeshorts/publish/providers/` (new package)

- `base.py` — `PublishProvider` Protocol:
  ```python
  class PublishProvider(Protocol):
      def publish(self, post: dict, platform: str, channel: dict) -> dict: ...
  ```
  Return shape: `{"status": "exported" | "published", "location": str,
  "published_at": str}` — `"exported"` for folder-drop (human still
  uploads), `"published"` reserved for a future API provider that
  actually completes the upload server-side.
- `folder_export.py` — `FolderExportProvider`, wrapping today's
  `export_post`'s per-platform copy logic (video + slides + caption.txt
  into `publish/<platform>/<date>/post_<id>/`), parameterized by
  `channel["slug"]` in the destination path
  (`publish/<channel_slug>/<platform>/<date>/post_<id>/`) so multiple
  channels' exports never collide.
- `youtube_api.py`, `tiktok_api.py`, `instagram_api.py` — one class each
  (`YouTubeAPIProvider`, `TikTokAPIProvider`, `InstagramAPIProvider`),
  constructed with `credentials_env` names from channel config; each
  raises `RuntimeError(f"channel '{channel['slug']}' has no {platform}
  credentials configured — set {credentials_env} or use provider:
  folder_export")` when the referenced env var is unset. No actual
  network calls implemented yet — that's chunk 10's last task, explicitly
  gated on the user supplying real API credentials/OAuth apps per
  platform (YouTube Data API, TikTok Content Posting API, Instagram
  Graph API each have their own app-registration process).
- `registry.py` — `PROVIDERS: dict[str, Callable[..., PublishProvider]]`
  and `get_provider(name: str, *, credentials_env: str | None = None) ->
  PublishProvider`.

### `claudeshorts/publish/channel_rules.py` (new)

```python
def select_channel(item: dict, channel_rules: dict, default_channel: str) -> str:
    """Same deterministic keyword-match shape as generate/style_rules.py's
    select_layout — first channel slug whose keyword list matches
    item['title']/['summary'] wins; no match -> default_channel."""
```

### `config/settings.yaml` changes

`channel:` (singular) is replaced by `channels:` (a list), each entry:

```yaml
channels:
  - slug: midnight-curiosity
    name: "Midnight Curiosity"
    handle: "@midnight.curiosity"
    logo: "assets/logo.png"
    enabled: true
    platforms:
      youtube:   {provider: folder_export}
      tiktok:    {provider: folder_export}
      instagram: {provider: folder_export}

channel_rules: {}     # e.g. {robotics-daily: ["robot", "boston dynamics"]}
default_channel: midnight-curiosity
```

Each platform entry's `provider` key selects `folder_export` (default,
always safe) or `<platform>_api` once real credentials exist; an optional
`credentials_env` key names the env var an API provider reads (e.g.
`YOUTUBE_API_CREDENTIALS_JSON`).

### Storage: new `channels` table + `posts.channel_id`

```sql
CREATE TABLE IF NOT EXISTS channels (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    slug       TEXT UNIQUE NOT NULL,
    name       TEXT NOT NULL,
    handle     TEXT,
    logo       TEXT,
    enabled    INTEGER NOT NULL DEFAULT 1
);
```
(Postgres per chunk 1's dialect: `id SERIAL PRIMARY KEY`, `enabled BOOLEAN
NOT NULL DEFAULT true`.)

`posts` gains `channel_id INTEGER REFERENCES channels(id)`, added via the
same migration-tuple pattern as chunks 2/8's column additions. A one-time
data migration (mirroring chunk 1's real-data migration script) seeds the
`channels` table from today's single `config.channels[0]` entry and
backfills every existing `posts` row's `channel_id` to that seeded row —
so no existing post is ever left with a null channel.

### Call sites

- `claudeshorts/store/channels.py` (new, thin wrapper module matching the
  existing `store/*.py` style) — `create_channel`, `get_channel`,
  `list_enabled_channels`.
- `claudeshorts/generate/runner.py` — after `style_rules.select_layout`
  (chunk 8), add:
  ```python
  channel_slug = channel_rules.select_channel(
      item, cfg.get("channel_rules", {}), cfg.get("default_channel"),
  )
  channel = channels.get_by_slug(channel_slug)
  ```
  and pass `channel_id=channel["id"]` into `posts.create_post`. The
  render bridge (`render/bridge.py`) already builds a `"channel"` spec key
  from a single global config value; it now instead loads the post's
  linked channel row (name/handle/logo) so rendering reflects the correct
  channel's branding.
- `claudeshorts/publish/exporter.py::export_post` is rewritten to iterate
  the post's channel's configured platforms, resolve each platform's
  provider via `registry.get_provider(platform_cfg["provider"],
  credentials_env=platform_cfg.get("credentials_env"))`, and call
  `.publish(post, platform, channel)` — replacing the current
  hand-copied per-platform loop with the same logic now living inside
  `FolderExportProvider`.

## Out of scope for this chunk

- Per-channel topic/source routing at ingestion time (e.g. a
  robotics-only channel only pulling robotics RSS feeds) — `items` stays
  global; `select_channel` only decides which channel a *generated post*
  belongs to among already-selected items. Revisit if/when a second
  channel with genuinely different subject matter exists.
- Actually calling any platform's real API (OAuth flows, upload
  endpoints, rate limits) — the three `*_api.py` provider classes exist
  as real, interface-conformant code with a clear "credentials missing"
  error path, but no network code is implemented. Wiring real credentials
  and testing an end-to-end API publish is this chunk's explicit last
  task, blocked on the user obtaining developer-app access for each
  platform.
- A dashboard UI for managing channels — `config/settings.yaml` edits,
  consistent with `brand_colors`/`layout_rules` from chunk 8.
- Deleting/renaming channels once created — only create + list is needed
  for a single-active-channel-today, more-later system.

## Testing

`tests/publish/providers/test_folder_export.py` — same assertions as
today's existing `export_post` tests, adapted to the new provider class
and channel-scoped destination path.
`tests/publish/providers/test_api_stubs.py` — each `*_api.py` provider
raises the expected `RuntimeError` with credentials unset; does not raise
when a (test-only, fake-valid) credentials env var is set (network calls
themselves are out of scope, so "doesn't raise" is as far as this chunk's
tests go).
`tests/publish/providers/test_registry.py` — provider name -> class
resolution.
`tests/publish/test_channel_rules.py` — `select_channel` keyword matching,
default fallback, mirrors chunk 8's `test_style_rules.py` test shapes.
`tests/store/test_channels.py` — create/get/list round-trip.
Migration test — seeding one channel from config and backfilling existing
posts' `channel_id`, mirroring chunk 1's migration test approach.
