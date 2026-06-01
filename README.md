# claudeshorts

Automated content pipeline that uses Claude to generate short-form videos and
slideshows, then publishes 2-3 posts per day to YouTube, TikTok, and Instagram,
plus a daily niche-news newsletter.

> Status: planning. Architecture and phased build plan are being designed before
> any feature code lands.

## Planned subsystems

1. **News ingestion** — monitor a niche daily, dedupe, store fresh items.
2. **Claude generation** — turn items into short scripts, slideshow content, and
   newsletter copy.
3. **Media rendering** — Claude-generated interactive HTML slideshows / animated
   videos, captured to publishable video.
4. **Publishing** — upload to YouTube, TikTok, and Instagram on a daily cadence.
5. **Newsletter + orchestration** — daily digest email and the scheduled loop
   that ties everything together with retries and logging.

See `docs/` for specs and plans as they are written.
