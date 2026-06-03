// Renderer entrypoint: a post spec (slides + theme + channel + audio) -> MP4.
//
//   node render.mjs --spec <spec.json> --out <dir>
//
// Pipeline: optional TTS synth -> deterministic Playwright frame capture ->
// ffmpeg encode -> optional audio (music / narration[+ducked music]) -> mux.
// The spec is produced by the Python bridge (claudeshorts/render/bridge.py).

import { execFile, spawn } from "node:child_process";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { promisify } from "node:util";
import { chromium } from "playwright";

import { buildTimeline, perSlideDurations } from "./lib/timeline.mjs";
import {
  durationProbeArgs, encodeArgs, muxArgs, musicTrackArgs,
  narrationTrackArgs, thumbnailArgs,
} from "./lib/ffmpeg.mjs";

const execFileP = promisify(execFile);
const HERE = dirname(fileURLToPath(import.meta.url));
const TEMPLATE = join(HERE, "templates", "slideshow.html");

function arg(name, fallback = null) {
  const i = process.argv.indexOf(name);
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}

const ff = (args) => execFileP("ffmpeg", args, { maxBuffer: 1 << 26 });

async function probeDuration(path) {
  const { stdout } = await execFileP("ffprobe", durationProbeArgs(path));
  return parseFloat(stdout.trim()) || 0;
}

// Run a TTS command template (text on stdin, must write {out}).
function synth(commandTpl, text, outPath) {
  return new Promise((res, rej) => {
    const cmd = commandTpl.replaceAll("{out}", outPath);
    const p = spawn("sh", ["-c", cmd], { stdio: ["pipe", "ignore", "inherit"] });
    p.on("error", rej);
    p.on("close", (code) =>
      code === 0 && existsSync(outPath) ? res(outPath)
        : rej(new Error(`tts command failed (exit ${code}): ${cmd}`)));
    p.stdin.write(text); p.stdin.end();
  });
}

async function main() {
  const specPath = arg("--spec");
  const outDir = resolve(arg("--out", "."));
  if (!specPath) throw new Error("usage: render.mjs --spec <spec.json> --out <dir>");

  const spec = JSON.parse(await readFile(specPath, "utf-8"));
  const v = spec.video || {};
  const fps = v.fps || 30;
  const width = v.width || 1080;
  const height = v.height || 1920;
  const slides = spec.slides || [];
  const audio = spec.audio || { mode: "silent" };

  await mkdir(outDir, { recursive: true });
  const framesDir = join(outDir, "_frames");
  await rm(framesDir, { recursive: true, force: true });
  await mkdir(framesDir, { recursive: true });

  // --- 1. optional TTS narration (per slide) -----------------------------
  let narration = null; // {clips:[{path,startMs}], perSlideSec:[]}
  if (audio.mode === "tts" && audio.tts && audio.tts.command) {
    const pad = audio.tts.pad_seconds ?? 0.6;
    const clips = [];
    const perSlideSec = [];
    for (let i = 0; i < slides.length; i++) {
      const text = slides[i].voiceover || slides[i].headline || "";
      const wav = join(framesDir, `tts_${i}.wav`);
      await synth(audio.tts.command, text, wav);
      perSlideSec.push(await probeDuration(wav));
      clips.push({ path: wav, startMs: 0 }); // startMs filled after timeline
    }
    narration = { clips, perSlideSec, pad };
  }

  // --- 2. timeline -------------------------------------------------------
  // Reading-time aware: hold each slide long enough to read its text, bounded
  // by [seconds_per_slide, max_seconds_per_slide]; TTS narration is never cut.
  const perSlide = perSlideDurations(slides, {
    minSeconds: v.seconds_per_slide || 4.0,
    maxSeconds: v.max_seconds_per_slide || 8.0,
    wpm: v.reading_speed_wpm || 200,
    leadSeconds: v.read_lead_seconds ?? 0.8,
    audioSeconds: narration ? narration.perSlideSec : null,
    padSeconds: narration ? narration.pad : 0.6,
  });
  const tl = buildTimeline(perSlide, fps);
  if (narration) {
    narration.clips.forEach((c, i) => { c.startMs = tl.slideStartsMs[i]; });
  }

  // --- 3. capture frames (Playwright, deterministic) ---------------------
  const browser = await chromium.launch({ args: ["--no-sandbox"] });
  const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
  await page.goto(pathToFileURL(TEMPLATE).href);
  await page.evaluate((s) => window.__init(s), spec);
  for (let f = 0; f < tl.frames.length; f++) {
    const fr = tl.frames[f];
    const globalMs = tl.slideStartsMs[fr.slide] + fr.localMs;
    await page.evaluate(([i, localMs, gMs]) => window.__render(i, localMs, gMs),
      [fr.slide, fr.localMs, globalMs]);
    await page.screenshot({
      path: join(framesDir, `frame_${String(f + 1).padStart(5, "0")}.png`),
    });
    // Progress for any watching parent (the Python bridge parses these from
    // stderr to drive the dashboard bar). Throttled so it stays cheap; stdout
    // is reserved for the final result JSON.
    if ((f + 1) % 5 === 0 || f + 1 === tl.frames.length) {
      process.stderr.write(`@@PROGRESS ${f + 1} ${tl.frames.length} capturing frames\n`);
    }
  }

  // --- 3b. per-slide settled stills (swipeable carousel) -----------------
  // One 1080x1920 PNG per slide at its fully-settled state (headline + every
  // bullet revealed), so the same post can be published as an Instagram/TikTok
  // swipe carousel, not just an auto-advancing video. Captured one frame before
  // each slide's end, which is guaranteed past all entrance animations.
  const slidesDir = join(outDir, "slides");
  await rm(slidesDir, { recursive: true, force: true });
  await mkdir(slidesDir, { recursive: true });
  const slideStills = [];
  process.stderr.write(`@@STATUS capturing carousel stills\n`);
  for (let i = 0; i < slides.length; i++) {
    const settledMs = Math.max(0, perSlide[i] * 1000 - 1000 / fps);
    const globalMs = tl.slideStartsMs[i] + settledMs;
    await page.evaluate(([idx, localMs, gMs]) => window.__render(idx, localMs, gMs),
      [i, settledMs, globalMs]);
    const stillPath = join(slidesDir, `slide_${String(i + 1).padStart(2, "0")}.png`);
    await page.screenshot({ path: stillPath });
    slideStills.push(stillPath);
  }

  await browser.close();

  // --- 4. encode silent video + thumbnail --------------------------------
  process.stderr.write(`@@STATUS encoding video\n`);
  const silent = join(outDir, "video_silent.mp4");
  await ff(encodeArgs(join(framesDir, "frame_%05d.png"), fps, silent));
  const thumb = join(outDir, "thumb.png");
  await ff(thumbnailArgs(join(framesDir, "frame_00001.png"), thumb));

  // --- 5. audio track ----------------------------------------------------
  const music = audio.music_file && existsSync(audio.music_file) ? audio.music_file : null;
  let audioTrack = null;
  if (narration) {
    audioTrack = join(outDir, "audio.m4a");
    const bed = music ? { path: music, volume: audio.tts.music_volume ?? 0.12 } : null;
    await ff(narrationTrackArgs(narration.clips, tl.totalMs, audioTrack, bed));
  } else if (audio.mode === "music" && music) {
    audioTrack = join(outDir, "audio.m4a");
    await ff(musicTrackArgs(music, tl.totalMs, audio.music_volume ?? 0.18, audioTrack));
  }

  // --- 6. mux (or keep silent) -------------------------------------------
  const finalPath = join(outDir, "video.mp4");
  if (audioTrack) {
    await ff(muxArgs(silent, audioTrack, finalPath));
    await rm(silent, { force: true });
  } else {
    await rm(finalPath, { force: true });
    await execFileP("mv", [silent, finalPath]);
  }
  await rm(framesDir, { recursive: true, force: true });

  process.stdout.write(JSON.stringify({
    video: finalPath, thumb, slides: slideStills,
    duration_ms: Math.round(tl.totalMs),
    frames: tl.totalFrames, audio_mode: narration ? "tts" : audio.mode,
  }) + "\n");
}

main().catch((e) => { console.error(e.message || e); process.exit(1); });
