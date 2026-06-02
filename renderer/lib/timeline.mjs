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
 * Reading time for one slide's on-screen text (silent mode). Viewers read the
 * headline plus every bullet, so the hold must cover all of it. `leadSeconds`
 * accounts for the entrance animation settling before reading really starts.
 * @param {{headline?:string,bullets?:string[]}} slide
 * @param {{wpm?:number,leadSeconds?:number}} [opts]
 * @returns {number} recommended hold in seconds (unclamped)
 */
export function readingHoldSeconds(slide, { wpm = 200, leadSeconds = 0.8 } = {}) {
  const text = [slide.headline || "", ...(slide.bullets || [])].join(" ");
  const words = (text.match(/\S+/g) || []).length;
  const wordsPerSecond = Math.max(1, wpm) / 60;
  return leadSeconds + words / wordsPerSecond;
}

/**
 * Per-slide durations. Each slide is held long enough to read its text
 * (reading-time aware), clamped to [minSeconds, maxSeconds]. With TTS we never
 * cut a slide shorter than its narration (plus padding), even past maxSeconds.
 * @param {{headline?:string,bullets?:string[]}[]} slides
 * @param {{minSeconds?:number,maxSeconds?:number,wpm?:number,
 *          leadSeconds?:number,audioSeconds?:number[]|null,padSeconds?:number}} [opts]
 */
export function perSlideDurations(
  slides,
  {
    minSeconds = 4.0,
    maxSeconds = 8.0,
    wpm = 200,
    leadSeconds = 0.8,
    audioSeconds = null,
    padSeconds = 0.6,
  } = {},
) {
  return slides.map((slide, s) => {
    const read = readingHoldSeconds(slide, { wpm, leadSeconds });
    const readHold = Math.min(maxSeconds, Math.max(minSeconds, read));
    const narration = audioSeconds && audioSeconds[s] ? audioSeconds[s] + padSeconds : 0;
    return Math.max(readHold, narration);
  });
}
