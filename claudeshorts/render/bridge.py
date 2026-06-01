"""Bridge from the Python core to the Node renderer.

Assembles a render *spec* (slides + theme + channel + video/audio settings) for
one post, invokes ``renderer/render.mjs`` via subprocess, and returns the paths
it produced. Keeping config in Python means the Node side stays a pure renderer.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import subprocess
from pathlib import Path
from typing import Any

from ..config import RENDERER_DIR, RENDERS_DIR, ROOT, ensure_dirs, settings


def _logo_data_uri(logo_rel: str | None) -> str | None:
    if not logo_rel:
        return None
    path = (ROOT / logo_rel)
    if not path.exists():
        return None
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def build_spec(post: dict) -> dict[str, Any]:
    """Construct the renderer spec from a post row + settings."""
    cfg = settings()
    channel = dict(cfg.get("channel", {}))
    channel["logo_data_uri"] = _logo_data_uri(channel.get("logo"))

    audio = dict(cfg.get("audio", {"mode": "silent"}))
    music_dir = ROOT / audio.get("music_dir", "assets/music")
    if "music_file" not in audio and music_dir.is_dir():
        tracks = sorted(
            p for p in music_dir.iterdir()
            if p.suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg"}
        )
        if tracks:
            audio["music_file"] = str(tracks[0])

    return {
        "title": post.get("title"),
        "theme": post.get("theme") or {},
        "slides": post.get("slides") or [],
        "channel": channel,
        "video": cfg.get("video", {}),
        "audio": audio,
    }


def render_post(post: dict, out_dir: Path | None = None) -> dict[str, Any]:
    """Render one post to an MP4. Returns the parsed renderer result JSON."""
    ensure_dirs()
    out_dir = out_dir or (RENDERS_DIR / f"post_{post['id']}")
    out_dir.mkdir(parents=True, exist_ok=True)

    spec = build_spec(post)
    spec_path = out_dir / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    proc = subprocess.run(
        ["node", "render.mjs", "--spec", str(spec_path), "--out", str(out_dir)],
        cwd=RENDERER_DIR, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "renderer failed: " + (proc.stderr.strip() or proc.stdout.strip())
        )
    last_line = proc.stdout.strip().splitlines()[-1]
    return json.loads(last_line)
