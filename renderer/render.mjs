// Renderer entrypoint: slides JSON -> vertical MP4.
//
// Phase 0 stub. Phase 3 implements:
//   - launch Playwright chromium at the configured 1080x1920 viewport
//   - load templates/ with injected slide data
//   - capture frames deterministically at the configured fps per slide
//   - pipe frames to ffmpeg -> H.264 MP4 (+ thumbnail from slide 1)
//
// Usage (Phase 3): node render.mjs --slides <path.json> --out <dir>

console.error("renderer not implemented yet (Phase 3).");
process.exit(1);
