/* Live jobs UI: progress bars, list polling, and terminal streaming.
 *
 * Shared by the Jobs page (inline terminal), the single-job page, and the
 * Overview widget. The server exposes /jobs.json (snapshot list) and
 * /jobs/<id>/stream (SSE: log lines + `progress` + `done` events). Lists poll;
 * the open terminal streams. No build step: plain ES5-ish browser JS.
 */
(function () {
  "use strict";

  function esc(s) {
    return (s == null ? "" : String(s)).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function el(tag, cls, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    return e;
  }

  function fmtElapsed(s) {
    s = Math.round(s || 0);
    if (s < 60) return s + "s";
    var m = Math.floor(s / 60);
    if (m < 60) return m + "m " + (s % 60) + "s";
    return Math.floor(m / 60) + "h " + (m % 60) + "m";
  }

  // ---- progress bars ----------------------------------------------------
  // opts: {percent, status, done, indeterminate, label}
  function barHTML(opts) {
    var done = !!opts.done;
    var indeterminate = opts.indeterminate && !done;
    var statusClass = done ? (opts.status || "ok") : "";
    var pct = done ? 100 : (opts.percent == null ? 0 : opts.percent);
    var cls = "bar " + statusClass + (indeterminate ? " indeterminate" : "");
    var right = done ? (opts.status || "done")
      : (indeterminate || opts.percent == null ? "" : opts.percent + "%");
    var label = opts.label ? esc(opts.label) : "";
    var head = (label || right)
      ? '<div class="bar-label"><span>' + label + '</span><span class="pct">' + right + "</span></div>"
      : "";
    return '<div class="bar-wrap">' + head +
      '<div class="' + cls + '"><i style="width:' + (indeterminate ? 35 : pct) + '%"></i></div></div>';
  }

  function rowLabel(job) {
    var p = job.phase, s = job.step, parts = [];
    if (p.total) parts.push((p.label || "phase") + " " + p.index + "/" + p.total);
    else if (p.label) parts.push(p.label);
    if (s.label) parts.push(s.label + (s.total ? " " + s.current + "/" + s.total : ""));
    return parts.join(" · ") || job.name;
  }

  // Compact single bar for a list row.
  function listBar(job) {
    if (job.done) return barHTML({ done: true, status: job.status, label: job.phase.label || job.name });
    if (job.step.total) return barHTML({ percent: job.step.percent, label: rowLabel(job) });
    if (job.phase.total) return barHTML({ percent: job.phase.percent, label: rowLabel(job) });
    return barHTML({ indeterminate: true, label: rowLabel(job) });
  }

  // Phase + step bars for the terminal/detail view.
  function detailBars(job) {
    var out = "";
    if (job.phase.total) {
      out += barHTML({
        percent: job.done ? null : job.phase.percent, done: job.done, status: job.status,
        label: "Phase: " + (job.phase.label || "") + " (" + job.phase.index + "/" + job.phase.total + ")"
      });
    }
    var s = job.step;
    if (s.total) {
      out += barHTML({
        percent: job.done ? null : s.percent, done: job.done, status: job.status,
        label: "Step" + (s.label ? ": " + s.label : "") + " (" + s.current + "/" + s.total + ")"
      });
    } else {
      out += barHTML({
        indeterminate: !job.done, done: job.done, status: job.status,
        label: s.label || job.phase.label || job.name
      });
    }
    return out;
  }

  function badge(status) {
    return '<span class="badge ' + esc(status) + '">' + esc(status) + "</span>";
  }

  // ---- list polling -----------------------------------------------------
  function renderList(container, jobs) {
    var mode = container.getAttribute("data-jobs-mode") || "link";
    var selected = container.getAttribute("data-selected");
    container.innerHTML = "";
    if (!jobs.length) {
      container.appendChild(el("p", "empty", "No jobs yet. Run something from the Overview."));
      return;
    }
    jobs.forEach(function (job) {
      var row = el("div", "job-row" + (String(job.id) === selected ? " sel" : ""));
      row.setAttribute("data-id", job.id);
      row.innerHTML =
        '<div class="top"><span class="jn">#' + job.id + " " + esc(job.name) + "</span>" + badge(job.status) + "</div>" +
        listBar(job) +
        '<div class="meta">' + fmtElapsed(job.elapsed_seconds) + (job.done ? "" : " · running") + "</div>";
      if (mode === "inline") {
        row.addEventListener("click", function () { selectJob(container, job.id); });
      } else {
        row.addEventListener("click", function () { window.location = "/jobs/" + job.id; });
      }
      container.appendChild(row);
    });
  }

  function pollList(container) {
    var mode = container.getAttribute("data-jobs-mode") || "link";
    var limit = container.getAttribute("data-limit") || 50;
    var autoSelected = false;
    function tick() {
      fetch("/jobs.json?limit=" + limit)
        .then(function (r) { return r.json(); })
        .then(function (d) {
          var jobs = d.jobs || [];
          renderList(container, jobs);
          if (mode === "inline" && !autoSelected && jobs.length &&
              !container.getAttribute("data-selected")) {
            autoSelected = true;
            var running = jobs.filter(function (j) { return !j.done; })[0];
            selectJob(container, (running || jobs[0]).id);
          }
        })
        .catch(function () { /* transient; next tick retries */ });
    }
    tick();
    setInterval(tick, 1500);
  }

  // ---- terminal streaming ----------------------------------------------
  var current = { es: null, id: null };

  function attachTerminal(id, opts) {
    opts = opts || {};
    var logEl = document.getElementById(opts.logId || "term-log");
    var barsEl = document.getElementById(opts.barsId || "term-bars");
    var statusEl = document.getElementById(opts.statusId || "term-status");
    var titleEl = opts.titleId ? document.getElementById(opts.titleId) : null;
    if (current.es) { current.es.close(); current.es = null; }
    if (logEl) logEl.textContent = "";
    current.id = id;
    if (titleEl) titleEl.textContent = "Job #" + id;

    var es = new EventSource("/jobs/" + id + "/stream");
    current.es = es;
    es.onmessage = function (e) {
      if (!logEl) return;
      logEl.textContent += e.data + "\n";
      logEl.scrollTop = logEl.scrollHeight;
    };
    es.addEventListener("progress", function (e) {
      try {
        var p = JSON.parse(e.data);
        var job = { phase: p.phase, step: p.step, status: p.status,
          done: p.status !== "running", name: "", elapsed_seconds: p.elapsed_seconds };
        if (barsEl) barsEl.innerHTML = detailBars(job);
        if (statusEl) { statusEl.className = "badge " + p.status; statusEl.textContent = p.status; }
      } catch (_) { /* ignore malformed frame */ }
    });
    es.addEventListener("done", function (e) {
      if (statusEl) { statusEl.className = "badge " + e.data; statusEl.textContent = e.data; }
      es.close(); current.es = null;
    });
    es.onerror = function () { es.close(); current.es = null; };
  }

  function selectJob(container, id) {
    container.setAttribute("data-selected", String(id));
    Array.prototype.forEach.call(container.querySelectorAll(".job-row"), function (r) {
      r.classList.toggle("sel", r.getAttribute("data-id") === String(id));
    });
    attachTerminal(id, { titleId: "term-title" });
  }

  window.JobsUI = {
    pollList: pollList, attachTerminal: attachTerminal,
    renderList: renderList, detailBars: detailBars, selectJob: selectJob
  };

  // Auto-wire any list container present on the page.
  document.addEventListener("DOMContentLoaded", function () {
    Array.prototype.forEach.call(document.querySelectorAll("[data-jobs-list]"), pollList);
  });
})();
