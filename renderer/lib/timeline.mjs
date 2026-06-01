// Deterministic frame plan for a slideshow.
//
// Pure functions (no I/O) so they can be unit-tested without a browser/ffmpeg.
// Capture is deterministic: each frame is (slideIndex, localMs) computed from
// the fps, never wall-clock — so renders are reproducible.

/**
 * @param {number[]} perSlideSeconds  display duration of each slide
 * @param {number} fps
 * @returns {{frames:{slide:number,localMs:number,durMs:number}[],
 *            slideStartsMs:number[], totalMs:number, totalFrames:number}}
 */
export function buildTimeline(perSlideSeconds, fps) {
  const frames = [];
  const slideStartsMs = [];
  let t = 0;
  for (let s = 0; s < perSlideSeconds.length; s++) {
    const durMs = perSlideSeconds[s] * 1000;
    slideStartsMs.push(t);
    const n = Math.max(1, Math.round(perSlideSeconds[s] * fps));
    for (let f = 0; f < n; f++) {
      frames.push({ slide: s, localMs: (f / fps) * 1000, durMs });
    }
    t += durMs;
  }
  return { frames, slideStartsMs, totalMs: t, totalFrames: frames.length };
}

/**
 * Per-slide durations. With TTS we stretch a slide to fit its narration
 * (plus padding); otherwise every slide uses the configured default.
 * @param {number} slideCount
 * @param {number} defaultSeconds
 * @param {number[]|null} audioSeconds  per-slide narration length, or null
 * @param {number} padSeconds
 */
export function perSlideDurations(slideCount, defaultSeconds, audioSeconds, padSeconds = 0.6) {
  const out = [];
  for (let s = 0; s < slideCount; s++) {
    const a = audioSeconds && audioSeconds[s] ? audioSeconds[s] + padSeconds : 0;
    out.push(Math.max(defaultSeconds, a));
  }
  return out;
}
