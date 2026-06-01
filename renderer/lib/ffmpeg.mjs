// ffmpeg/ffprobe argument builders.
//
// Pure functions returning argv arrays (without the leading binary name) so
// they can be unit-tested and the actual exec lives in render.mjs.

const sec = (ms) => (ms / 1000).toFixed(3);

/** Encode a directory of zero-padded PNG frames into an H.264 MP4. */
export function encodeArgs(framePattern, fps, outPath) {
  return [
    "-y", "-framerate", String(fps), "-i", framePattern,
    "-c:v", "libx264", "-preset", "medium", "-crf", "20",
    "-pix_fmt", "yuv420p", "-r", String(fps), outPath,
  ];
}

/** Grab a single still (thumbnail) from a frame file. */
export function thumbnailArgs(framePath, outPath) {
  return ["-y", "-i", framePath, "-frames:v", "1", outPath];
}

/** Loop/trim a music file to exactly totalMs at the given volume. */
export function musicTrackArgs(musicPath, totalMs, volume, outPath) {
  return [
    "-y", "-stream_loop", "-1", "-i", musicPath,
    "-t", sec(totalMs), "-filter:a", `volume=${volume}`,
    "-c:a", "aac", outPath,
  ];
}

/**
 * Place each narration clip at its slide start time and mix to one track of
 * length totalMs. Optionally duck a music bed underneath.
 * @param {{path:string,startMs:number}[]} clips
 * @param {number} totalMs
 * @param {{path:string,volume:number}|null} music
 */
export function narrationTrackArgs(clips, totalMs, outPath, music = null) {
  const inputs = [];
  const filters = [];
  const mixLabels = [];

  clips.forEach((clip, i) => {
    inputs.push("-i", clip.path);
    const delay = Math.round(clip.startMs);
    filters.push(`[${i}:a]adelay=${delay}|${delay}[v${i}]`);
    mixLabels.push(`[v${i}]`);
  });

  if (music) {
    const mi = clips.length;
    inputs.push("-stream_loop", "-1", "-i", music.path);
    // Trim/volume the looped bed, then include it in the mix.
    filters.push(`[${mi}:a]atrim=0:${sec(totalMs)},volume=${music.volume}[bed]`);
    mixLabels.push("[bed]");
  }

  filters.push(
    `${mixLabels.join("")}amix=inputs=${mixLabels.length}:duration=longest:normalize=0[mixraw]`,
    `[mixraw]apad,atrim=0:${sec(totalMs)}[mix]`,
  );

  return [
    "-y", ...inputs,
    "-filter_complex", filters.join(";"),
    "-map", "[mix]", "-c:a", "aac", outPath,
  ];
}

/** Mux a finished video with an audio track (video stream copied). */
export function muxArgs(videoPath, audioPath, outPath) {
  return [
    "-y", "-i", videoPath, "-i", audioPath,
    "-c:v", "copy", "-c:a", "aac", "-shortest", outPath,
  ];
}

/** ffprobe args to read a media file's duration in seconds. */
export function durationProbeArgs(path) {
  return [
    "-v", "error", "-show_entries", "format=duration",
    "-of", "default=noprint_wrappers=1:nokey=1", path,
  ];
}
