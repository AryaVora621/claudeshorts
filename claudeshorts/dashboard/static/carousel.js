// Swipeable carousel decks. Progressive enhancement over a scroll-snap track:
// the track already swipes/scrolls on its own; this wires the prev/next
// buttons, click-drag on desktop, arrow keys, and a live "n / total" counter.
(function () {
  "use strict";

  function setup(root) {
    var track = root.querySelector(".carousel-track");
    if (!track) return;
    var slides = track.querySelectorAll(".carousel-slide");
    var total = slides.length;
    var curEl = root.querySelector(".carousel-count .cur");
    var prev = root.querySelector(".carousel-nav.prev");
    var next = root.querySelector(".carousel-nav.next");

    function index() {
      // Nearest slide to the current scroll offset.
      var w = track.clientWidth || 1;
      return Math.round(track.scrollLeft / w);
    }
    function update() {
      var i = index();
      if (curEl) curEl.textContent = Math.min(i + 1, total);
      if (prev) prev.disabled = i <= 0;
      if (next) next.disabled = i >= total - 1;
    }
    function go(i) {
      i = Math.max(0, Math.min(total - 1, i));
      track.scrollTo({ left: i * track.clientWidth, behavior: "smooth" });
    }

    if (prev) prev.addEventListener("click", function () { go(index() - 1); });
    if (next) next.addEventListener("click", function () { go(index() + 1); });

    var raf = 0;
    track.addEventListener("scroll", function () {
      if (raf) return;
      raf = requestAnimationFrame(function () { raf = 0; update(); });
    });

    // Arrow keys when the deck is focused/hovered.
    root.tabIndex = 0;
    root.addEventListener("keydown", function (e) {
      if (e.key === "ArrowLeft") { go(index() - 1); e.preventDefault(); }
      else if (e.key === "ArrowRight") { go(index() + 1); e.preventDefault(); }
    });

    // Click-and-drag panning on desktop (touch already pans natively).
    var down = false, startX = 0, startLeft = 0, moved = false;
    track.addEventListener("pointerdown", function (e) {
      if (e.pointerType === "touch") return;
      down = true; moved = false; startX = e.clientX; startLeft = track.scrollLeft;
      track.classList.add("dragging");
    });
    window.addEventListener("pointermove", function (e) {
      if (!down) return;
      var dx = e.clientX - startX;
      if (Math.abs(dx) > 4) moved = true;
      track.scrollLeft = startLeft - dx;
    });
    window.addEventListener("pointerup", function () {
      if (!down) return;
      down = false; track.classList.remove("dragging");
      if (moved) go(index()); // settle to the nearest slide
    });
    // Don't let a drag fire the image's native drag-ghost.
    track.addEventListener("dragstart", function (e) { e.preventDefault(); });

    update();
  }

  function init() {
    document.querySelectorAll(".carousel").forEach(setup);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
