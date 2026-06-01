# Deploying the daily pipeline (home desktop)

The pipeline runs once a day, produces 2–3 themed videos into the review queue,
and waits for you to approve them in the dashboard. Generation uses your logged-in
Claude subscription (`claude login`), so there's no API key/cost.

## One-time setup

```bash
git clone https://github.com/AryaVora621/claudeshorts.git ~/claudeshorts
cd ~/claudeshorts
python3 -m venv .venv
.venv/bin/pip install -U pip setuptools wheel
.venv/bin/pip install -r requirements.txt
cd renderer && npm install && npx playwright install chromium && cd ..
claude login            # subscription auth for generation
# optional: drop assets/logo.png and royalty-free tracks in assets/music/
```

Run it manually once to confirm:

```bash
.venv/bin/python -m claudeshorts.cli run      # ingest -> generate -> render -> queue
.venv/bin/python -m claudeshorts.cli serve    # review dashboard at http://127.0.0.1:8000
```

## Schedule with systemd (user timer)

```bash
mkdir -p ~/.config/systemd/user
cp deploy/claudeshorts.service deploy/claudeshorts.timer ~/.config/systemd/user/
# edit WorkingDirectory/ExecStart paths in the .service if your checkout isn't ~/claudeshorts
systemctl --user daemon-reload
systemctl --user enable --now claudeshorts.timer
systemctl --user list-timers | grep claudeshorts     # confirm it's scheduled
loginctl enable-linger "$USER"                        # so the timer runs while logged out
```

Logs: `journalctl --user -u claudeshorts.service -e`

## Cron fallback

```cron
# crontab -e  — daily at 08:00
0 8 * * * cd ~/claudeshorts && .venv/bin/python -m claudeshorts.cli run >> ~/claudeshorts/data/cron.log 2>&1
```

## Notes
- The runner is idempotent per day (a completed run is skipped; use `--force` to repeat).
- Already-posted news items are never reused; developing stories become follow-ups.
- `--skip-render` runs ingest+generate only (e.g. on a headless box without a browser).
