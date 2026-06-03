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
import threading
from pathlib import Path
from typing import Any

from .. import progress
from ..config import RENDERER_DIR, RENDERS_DIR, ROOT, ensure_dirs, settings


def _handle_stderr_line(line: str, errors: list[str]) -> None:
    """Translate one renderer stderr line into a progress update.

    The renderer prints ``@@PROGRESS cur total label`` per batch of frames and
    ``@@STATUS label`` for indeterminate stages. Everything else is real stderr
    output, kept so a failure can be reported. Parsing runs on the caller's
    thread so the per-thread progress sink (installed by the dashboard job) is in
    scope.
    """
    if line.startswith("@@PROGRESS "):
        parts = line.split(" ", 3)
        try:
            cur, total = int(parts[1]), int(parts[2])
        except (IndexError, ValueError):
            return
        progress.step(cur, total, parts[3] if len(parts) > 3 else "rendering")
    elif line.startswith("@@STATUS "):
        progress.step(0, 0, line[len("@@STATUS "):].strip() or "rendering")
    elif line.strip():
        errors.append(line)


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

    proc = subprocess.Popen(
        ["node", "render.mjs", "--spec", str(spec_path), "--out", str(out_dir)],
        cwd=RENDERER_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )

    # Drain stdout on a side thread (it carries only the final result JSON) while
    # this thread parses stderr live for progress. Reading both avoids a pipe
    # deadlock on a chatty render.
    stdout_chunks: list[str] = []

    def _drain_stdout() -> None:
        assert proc.stdout is not None
        stdout_chunks.append(proc.stdout.read())

    t = threading.Thread(target=_drain_stdout, daemon=True)
    t.start()

    errors: list[str] = []
    assert proc.stderr is not None
    for raw in proc.stderr:
        _handle_stderr_line(raw.rstrip("\n"), errors)

    proc.wait()
    t.join()
    stdout = "".join(stdout_chunks)

    if proc.returncode != 0:
        raise RuntimeError(
            "renderer failed: " + ("\n".join(errors).strip() or stdout.strip())
        )
    last_line = stdout.strip().splitlines()[-1]
    return json.loads(last_line)
