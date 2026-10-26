/* Monitoring "Graphs" tab.
   History is requested from this portal's own endpoint (which reads Proxmox RRD on the server, GET only,
   with a short cache). The browser never talks to Proxmox and never sees Proxmox URLs or tokens.
   Missing samples arrive as null and are drawn as gaps; nothing here turns a missing sample into zero. */
(() => {
  "use strict";
  const root = document.getElementById("monitoring");
  const ui = window.MonitoringUI;
  const grid = document.getElementById("mon-chart-grid");
  const hostSelect = document.getElementById("mon-graph-host");
  if (!root || !ui || !grid || !hostSelect) return; // no hosts configured: the template shows an empty state

  const panel = document.getElementById("mon-panel-graphs");
  const banner = document.getElementById("mon-graph-banner");
  const foot = document.getElementById("mon-graph-foot");
  const intervalNote = document.getElementById("mon-graph-interval");
  const rangeButtons = [...root.querySelectorAll(".mon-range-btn")];
  const TZ = root.dataset.timezone || "UTC";
  const TZ_LABEL = root.dataset.timezoneLabel || TZ;
  const hasPlot = typeof window.uPlot === "function";

  // Client freshness limits mirror the server cache so tab switches never re-request needlessly.
  const FRESH_SECONDS = { "1h": 60, "24h": 300, "7d": 900 };
  const REQUEST_TIMEOUT_MS = 25000;
  const COLORS = { cpu: "#2563eb", memory: "#6d3fd6", receive: "#2563eb", transmit: "#0b7f70",
    storage: ["#2563eb", "#6d3fd6", "#0b7f70", "#b4298f", "#a16207", "#0e7490", "#475569", "#be123c"],
    warning: "#d97706", critical: "#dc2626", axis: "#475569", grid: "#e6ecf4" };
  const REASONS = {
    CREDENTIALS_MISSING: "monitoring credentials are not configured on the server",
    TLS_CONFIGURATION_INVALID: "the TLS settings for this host are invalid",
    TLS_VERIFICATION_FAILED: "the host's TLS certificate could not be verified",
    ACCESS_DENIED: "the read-only monitoring account is not allowed to read this history",
    CONNECTION_FAILED: "the host could not be reached",
    API_UNAVAILABLE: "Proxmox returned an error",
    RESPONSE_TOO_LARGE: "Proxmox returned more data than expected",
    INVALID_RESPONSE: "Proxmox returned an unexpected response",
    TIMEOUT: "loading took too long",
    BUSY: "another history request is still loading; try again shortly",
    CONFIGURATION_INVALID: "the monitoring host configuration is invalid",
  };
  const reason = code => REASONS[code] || "history could not be read";

  /* ---------- formatting ---------- */
  const dateTime = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, day: "numeric", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit", hour12: false });
  const clock = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hour12: false });
  const stamp = seconds => dateTime.format(new Date(seconds * 1000)) + " " + TZ_LABEL;
  const stampShort = seconds => clock.format(new Date(seconds * 1000)) + " " + TZ_LABEL;
  const pct = value => value.toFixed(1) + "%";
  const gib = bytes => (bytes / 1073741824).toFixed(bytes >= 10737418240 ? 1 : 2) + " GiB";
  function rate(bitsPerSecond, short) {
    const units = [[1e9, "Gbps"], [1e6, "Mbps"], [1e3, "kbps"]];
    for (const [size, name] of units) {
      if (bitsPerSecond >= size) {
        const scaled = bitsPerSecond / size;
        return (short && scaled >= 10 ? scaled.toFixed(0) : scaled.toFixed(short ? 1 : 2)).replace(/\.0$/, "") + " " + name;
      }
    }
    return (short ? Math.round(bitsPerSecond) : bitsPerSecond.toFixed(0)) + " bit/s";
  }
  const isNumber = value => typeof value === "number" && Number.isFinite(value);
  const duration = seconds => seconds >= 3600 ? Math.round(seconds / 360) / 10 + " h" : Math.max(1, Math.round(seconds / 60)) + " min";

  function lastSample(values) {
    for (let i = values.length - 1; i >= 0; i--) if (isNumber(values[i])) return { index: i, value: values[i] };
    return null;
  }
  function peak(values) {
    return values.reduce((best, value) => (isNumber(value) && (best === null || value > best) ? value : best), null);
  }
  function isolatedIndexes(values) {   // a lone sample between gaps has no line; draw a dot so it stays visible
    const found = [];
    values.forEach((value, i) => {
      if (isNumber(value) && !isNumber(values[i - 1]) && !isNumber(values[i + 1])) found.push(i);
    });
    return found;
  }
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  /* ---------- state ---------- */
  const saved = { host: ui.prefs.get("graph.host"), range: ui.prefs.get("graph.range") };
  const state = {
    host: [...hostSelect.options].some(o => o.value === saved.host) ? saved.host : hostSelect.value,
    range: FRESH_SECONDS[saved.range] ? saved.range : "24h",
    payload: null, loadedKey: null, fetchedAt: 0, dirty: false, sequence: 0, inflight: null, controller: null,
  };
  hostSelect.value = state.host;
  const keyOf = (host, range) => host + "|" + range;
  const charts = {};   // name -> { section, plot, msg, legend, instance, signature, tip, observer }
  grid.querySelectorAll("[data-chart]").forEach(section => {
    const field = name => section.querySelector(`[data-field="${name}"]`);
    charts[section.dataset.chart] = { name: section.dataset.chart, section, plot: field("plot"), msg: field("msg"),
      legend: field("legend"), sub: field("sub"), current: field("current"), last: field("last"), scope: field("scope"),
      stage: section.querySelector(".mon-chart-stage"), instance: null, signature: "", tip: null, observer: null };
  });

  /* ---------- banner and per-chart messages ---------- */
  function showBanner(kind, text) {
    if (!banner) return;
    banner.className = "mon-graph-banner" + (kind ? " " + kind : "");
    banner.textContent = text || "";
    banner.hidden = !text;
  }
  function setMessage(chart, kind, text) {
    chart.msg.className = "mon-chart-msg" + (kind === "error" ? " error" : "");
    chart.msg.textContent = text || "";
    chart.msg.hidden = !text;
  }
  function destroy(chart) {
    if (chart.instance) { chart.instance.destroy(); chart.instance = null; chart.signature = ""; }
    if (chart.observer) { chart.observer.disconnect(); chart.observer = null; }
    if (chart.tip) { chart.tip.remove(); chart.tip = null; }
  }

  /* ---------- plotting ---------- */
  function thresholdHook(chart, lines) {
    return u => {
      if (!lines.length) return;
      const ratio = window.devicePixelRatio || 1;
      const { left, top, width, height } = u.bbox;
      const ctx = u.ctx;
      ctx.save();
      ctx.beginPath(); ctx.rect(left, top, width, height); ctx.clip();
      ctx.lineWidth = 1.5 * ratio;
      ctx.font = `600 ${11 * ratio}px system-ui, sans-serif`;
      ctx.textAlign = "right"; ctx.textBaseline = "bottom";
      lines.forEach(line => {
        const y = Math.round(u.valToPos(line.value, "y", true));
        if (y < top || y > top + height) return;
        ctx.strokeStyle = line.color; ctx.fillStyle = line.color;
        ctx.setLineDash([6 * ratio, 4 * ratio]);
        ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(left + width, y); ctx.stroke();
        ctx.setLineDash([]);
        ctx.textBaseline = "top";   // always under its line, so labels of close thresholds never overlap or clip
        ctx.fillText(line.label, left + width - 4 * ratio, y + 3 * ratio);
      });
      ctx.restore();
    };
  }

  function tooltipHook(chart, describe) {
    return u => {
      const idx = u.cursor.idx;
      if (!chart.tip) {
        chart.tip = el("div", "mon-tip"); chart.tip.hidden = true; chart.tip.setAttribute("aria-hidden", "true");
        chart.stage.appendChild(chart.tip);
      }
      const tip = chart.tip;
      if (idx === null || idx === undefined || u.cursor.left < 0) { tip.hidden = true; return; }
      const rows = describe(idx, u);
      tip.replaceChildren(el("time", "", stamp(u.data[0][idx])));
      rows.forEach(row => {
        const line = el("div");
        const swatch = el("span", "sw"); swatch.style.background = row.color;
        line.append(swatch, el("em", "", row.label), el("b", "", row.value));
        tip.appendChild(line);
      });
      tip.hidden = false;
      const room = chart.stage.clientWidth;
      let x = u.over.offsetLeft + u.cursor.left + 14;
      if (x + tip.offsetWidth > room) x = Math.max(0, u.over.offsetLeft + u.cursor.left - tip.offsetWidth - 14);
      tip.style.left = x + "px";
      tip.style.top = Math.max(0, u.over.offsetTop + 6) + "px";
    };
  }

  function buildOptions(chart, payload, spec) {
    const width = Math.max(240, chart.plot.clientWidth);
    const height = Math.max(160, chart.plot.clientHeight);
    const axisBase = { stroke: COLORS.axis, grid: { stroke: COLORS.grid, width: 1 }, ticks: { stroke: COLORS.grid, width: 1 },
      font: "12px system-ui, sans-serif" };
    const yScale = spec.percent
      ? { range: () => [0, 100] }
      : { range: (u, min, max) => [0, Math.max(isNumber(max) ? max * 1.15 : 0, 1000)] };
    const isolated = spec.series.map(item => isolatedIndexes(item.values));
    return {
      width, height, tzDate: ts => window.uPlot.tzDate(new Date(ts * 1000), TZ),
      legend: { show: false },
      cursor: { drag: { x: false, y: false }, points: { size: 7 } },
      select: { show: false },
      scales: { x: { time: true, range: () => [payload.window_start, payload.window_end] }, y: yScale },
      axes: [
        { ...axisBase, space: 80, grid: { stroke: COLORS.grid, width: 1 } },
        { ...axisBase, size: spec.percent ? 52 : 74,
          values: (u, ticks) => ticks.map(tick => spec.percent ? tick + "%" : (tick === 0 ? "0" : rate(tick, true))) },
      ],
      series: [{}, ...spec.series.map((item, i) => ({
        label: item.name, stroke: item.color, width: 2, spanGaps: false,
        dash: item.dash, fill: item.fill ? item.color + "1f" : undefined,
        points: { show: true, size: 5, fill: item.color, stroke: item.color, filter: () => isolated[i] },
      }))],
      hooks: { draw: [thresholdHook(chart, spec.thresholds || [])], setCursor: [tooltipHook(chart, spec.describe)] },
    };
  }

  function drawPlot(chart, payload, spec) {
    const data = [payload.times, ...spec.series.map(item => item.values)];
    const signature = [payload.host, payload.range, spec.series.map(item => item.key).join(",")].join("|");
    if (chart.instance && chart.signature === signature) {
      chart.instance.setData(data, true);
      chart.instance.redraw();
      return;
    }
    destroy(chart);
    chart.instance = new window.uPlot(buildOptions(chart, payload, spec), data, chart.plot);
    chart.signature = signature;
    chart.observer = new ResizeObserver(() => {
      if (!chart.instance || panel.hidden) return;
      const width = chart.plot.clientWidth;
      if (width > 0 && Math.abs(width - chart.instance.width) > 1) chart.instance.setSize({ width, height: chart.plot.clientHeight });
    });
    chart.observer.observe(chart.plot);
  }

  function legendItem(label, color, value, dashed) {
    const item = el("span", "mon-legend-item");
    const swatch = el("span", "mon-legend-swatch" + (dashed ? " dashed" : ""));
    swatch.style.color = color;
    item.append(swatch, el("span", "", label));
    if (value) item.append(el("span", "mon-legend-value", value));
    return item;
  }

  /* ---------- per-chart specs built from the payload ---------- */
  function limitLines(payload, kind) {
    const limit = (payload.thresholds || {})[kind];
    if (!limit) return [];
    return [{ value: limit.warning, color: COLORS.warning, label: "Warning " + limit.warning + "%" },
            { value: limit.critical, color: COLORS.critical, label: "Critical " + limit.critical + "%" }];
  }

  function percentSpec(payload, name, title, color, kind) {
    const info = payload.charts[name];
    const values = info.values;
    const used = info.used, total = info.total;
    return {
      percent: true, thresholds: limitLines(payload, kind),
      series: [{ key: name, name: title, color, values, fill: true }],
      describe: idx => {
        const rows = [{ color, label: title, value: isNumber(values[idx]) ? pct(values[idx]) : "No sample" }];
        if (used && isNumber(used[idx]) && isNumber(total[idx])) rows.push({ color: "transparent", label: "Used", value: gib(used[idx]) + " of " + gib(total[idx]) });
        return rows;
      },
    };
  }

  function storageSpec(payload) {
    const info = payload.charts.storage;
    const series = info.series.map((item, i) => ({ key: item.key, name: item.name, color: COLORS.storage[i % COLORS.storage.length],
      values: item.values, error: item.error }));
    return { percent: true, thresholds: limitLines(payload, "storage"), series,
      describe: idx => series.map(item => ({ color: item.color, label: item.name,
        value: isNumber(item.values[idx]) ? pct(item.values[idx]) : (item.error ? "Unavailable" : "No sample") })) };
  }

  function networkSpec(payload) {
    const info = payload.charts.network;
    const series = [{ key: "receive", name: "Receive", color: COLORS.receive, values: info.receive },
                    { key: "transmit", name: "Transmit", color: COLORS.transmit, values: info.transmit, dash: [7, 4] }];
    return { percent: false, thresholds: [], series,
      describe: idx => series.map(item => ({ color: item.color, label: item.name,
        value: isNumber(item.values[idx]) ? rate(item.values[idx]) : "No sample" })) };
  }

  function renderChart(chart, payload) {
    const info = (payload.charts || {})[chart.name];
    const where = payload.host + " · last " + (payload.range_label || state.range);
    chart.sub.textContent = where;
    chart.section.classList.remove("is-loading");
    if (!info) {                                   // whole request failed: say why, keep the layout
      destroy(chart); chart.legend.replaceChildren();
      setMessage(chart, "error", "History unavailable: " + reason((payload.errors || [])[0]) + ".");
      return;
    }
    if (info.state !== "ok") {
      destroy(chart); chart.legend.replaceChildren();
      setMessage(chart, info.state === "error" ? "error" : "", info.state === "error"
        ? "History unavailable: " + reason(info.error) + "." : "No samples were returned for this range.");
      return;
    }
    setMessage(chart, "", "");
    const spec = chart.name === "cpu" ? percentSpec(payload, "cpu", "CPU usage", COLORS.cpu, "cpu")
      : chart.name === "memory" ? percentSpec(payload, "memory", "Memory usage", COLORS.memory, "memory")
      : chart.name === "storage" ? storageSpec(payload) : networkSpec(payload);
    if (hasPlot) drawPlot(chart, payload, spec);

    const legend = [];
    spec.series.forEach(item => {
      const latest = lastSample(item.values);
      const text = latest ? (spec.percent ? pct(latest.value) : rate(latest.value)) : (item.error ? "unavailable" : "no data");
      legend.push(legendItem(item.name, item.color, chart.name === "storage" || chart.name === "network" ? text : "", item.dash));
    });
    spec.thresholds.forEach(line => legend.push(legendItem(line.label, line.color, "", true)));
    chart.legend.replaceChildren(...legend);

    const all = spec.series.flatMap(item => item.values);
    const latestTime = Math.max(...spec.series.map(item => { const s = lastSample(item.values); return s ? payload.times[s.index] : 0; }));
    if (chart.last) chart.last.textContent = latestTime ? "Last history sample " + stampShort(latestTime) : "";
    chart.plot.setAttribute("aria-label", (spec.series[0].name === "Receive" ? "Network traffic" : chart.name === "storage" ? "Storage usage"
      : spec.series[0].name) + " chart for " + where + ". " + summaryText(chart.name, spec, all));
    if (chart.current && (chart.name === "cpu" || chart.name === "memory")) {
      const now = payload.current ? payload.current[chart.name] : null;
      chart.current.textContent = isNumber(now) ? pct(now) : "—";
      const note = payload.current && payload.current.stale ? "Last known value" : "";
      chart.current.title = isNumber(now) ? "Latest saved collection" + (note ? " (" + note.toLowerCase() + ")" : "") : "No saved snapshot for this host";
      const latest = lastSample(spec.series[0].values);
      chart.last.textContent = (note ? note + " · " : "") + (latest ? "Last history sample " + pct(latest.value) + " at " + stampShort(payload.times[latest.index]) : "No history samples");
    }
    if (chart.scope && payload.charts.network) chart.scope.textContent = payload.charts.network.scope_label || "";
  }

  function summaryText(name, spec, all) {
    const top = peak(all);
    const latest = spec.series.map(item => { const s = lastSample(item.values); return s ? item.name + " " + (spec.percent ? pct(s.value) : rate(s.value)) : null; }).filter(Boolean);
    return (latest.length ? "Latest: " + latest.join(", ") + ". " : "") + (top === null ? "" : "Highest: " + (spec.percent ? pct(top) : rate(top)) + ". ") + "Gaps mean no sample was available.";
  }

  /* ---------- whole-payload rendering ---------- */
  function render() {
    const payload = state.payload;
    if (!payload) return;
    if (panel.hidden) { state.dirty = true; return; }   // charts cannot be sized while hidden
    state.dirty = false;
    Object.values(charts).forEach(chart => renderChart(chart, payload));

    const problems = [];
    const messages = [];
    if (payload.stale) {
      messages.push(["warning", "Proxmox could not be reached just now, so the last good history is shown"
        + (payload.last_sample_at ? " (newest sample " + stampShort(payload.last_sample_at) + ")" : "") + "."]);
    }
    if (payload.status === "unavailable") {
      messages.push(["error", "History could not be loaded for " + payload.host + ": " + reason((payload.errors || [])[0]) + "."]);
    } else if (payload.status === "empty") {
      messages.push(["info", "Proxmox returned no history samples for " + payload.host + " in this range."]);
    } else if (payload.status === "partial") {
      Object.entries(payload.charts).forEach(([key, info]) => { if (info.state === "error") problems.push(key); });
      messages.push(["info", "Some charts are unavailable (" + problems.join(", ") + "). The others are shown."]);
    }
    if (payload.current && payload.current.stale) messages.push(["info", "The latest saved collection is out of date; current snapshot values are the last known readings."]);
    else if (!payload.current) messages.push(["info", "No saved collection exists for this host yet, so there is no current snapshot value."]);
    const first = messages.find(m => m[0] === "error") || messages.find(m => m[0] === "warning") || messages[0];
    showBanner(first ? first[0] : "", messages.map(m => m[1]).join(" "));

    if (intervalNote) intervalNote.textContent = payload.step_seconds ? "· samples about every " + duration(payload.step_seconds) : "";
    if (foot) {
      const cached = payload.cache === "hit" || payload.cache === "last-good" ? " (from a short cache)" : "";
      foot.textContent = "Source: Proxmox built-in history (RRD, averaged) for " + payload.host + ", loaded " + stampShort(payload.fetched_at) + cached
        + ". “Current snapshot” is the latest saved collection" + (payload.snapshot_at ? " from " + stampShort(payload.snapshot_at) : "")
        + "; “Last history sample” is the newest point on the chart and may be a few minutes older.";
    }
  }

  function markLoading(on) {
    Object.values(charts).forEach(chart => {
      chart.section.classList.toggle("is-loading", on);
      if (on && !chart.instance) { setMessage(chart, "", "Loading…"); chart.sub.textContent = state.host + " · loading"; }
    });
    grid.setAttribute("aria-busy", on ? "true" : "false");
  }

  /* ---------- loading ---------- */
  async function load(force) {
    const key = keyOf(state.host, state.range);
    if (!state.host) return;
    const fresh = state.payload && state.loadedKey === key && Date.now() - state.fetchedAt < FRESH_SECONDS[state.range] * 1000;
    if (!force && fresh) { if (state.dirty) render(); return; }
    if (state.inflight && state.inflightKey === key) return state.inflight;   // never overlap identical requests
    if (state.controller) state.controller.abort();                          // a newer selection replaces the old request
    const controller = new AbortController();
    const sequence = ++state.sequence;
    state.controller = controller; state.inflightKey = key;
    const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    markLoading(true);
    const url = new URL(root.dataset.historyUrl, window.location.origin);
    url.searchParams.set("host", state.host); url.searchParams.set("range", state.range);
    const run = (async () => {
      try {
        const response = await fetch(url, { credentials: "same-origin", cache: "no-store", signal: controller.signal,
          headers: { Accept: "application/json", "X-Requested-With": "fetch" } });
        const type = response.headers.get("content-type") || "";
        if (response.redirected || response.status === 401 || !type.includes("json")) throw new Error("session");
        if (response.status === 403) throw new Error("forbidden");
        if (!response.ok) throw new Error("server");
        const payload = await response.json();
        if (sequence !== state.sequence) return;              // superseded while loading
        state.payload = payload; state.loadedKey = key; state.fetchedAt = Date.now();
        render();
        ui.announce("Graph history loaded for " + payload.host + ", " + (payload.range_label || state.range) + ".");
      } catch (error) {
        if (sequence !== state.sequence) return;
        const aborted = error && error.name === "AbortError";
        // Keep earlier charts only when they belong to the same host and range that just failed to refresh.
        const keep = !!state.payload && state.loadedKey === key;
        if (!keep) { state.payload = null; state.loadedKey = null; Object.values(charts).forEach(chart => { destroy(chart); chart.legend.replaceChildren(); }); }
        const tail = keep ? "Showing the previous charts." : "Try again shortly.";
        const text = error && error.message === "session" ? "Your session may have expired. Reload the page to sign in again."
          : error && error.message === "forbidden" ? "You are not allowed to view infrastructure history."
          : aborted ? "Loading history took too long. " + tail
          : "History could not be loaded from the portal. " + tail;
        showBanner("error", text);
        Object.values(charts).forEach(chart => {
          chart.section.classList.remove("is-loading");
          if (keep) setMessage(chart, "", "");
          else { chart.sub.textContent = state.host + " · " + state.range; setMessage(chart, "error", "History unavailable."); }
        });
        ui.announce(text);
      } finally {
        window.clearTimeout(timer);
        if (sequence === state.sequence) { state.controller = null; state.inflight = null; state.inflightKey = null; markLoading(false); }
      }
    })();
    state.inflight = run;
    return run;
  }

  /* ---------- controls and integration ---------- */
  function syncRangeButtons() {
    rangeButtons.forEach(button => button.setAttribute("aria-pressed", button.dataset.range === state.range ? "true" : "false"));
  }
  rangeButtons.forEach(button => button.addEventListener("click", () => {
    if (button.dataset.range === state.range) return;
    state.range = button.dataset.range; ui.prefs.set("graph.range", state.range);
    syncRangeButtons(); load(false);
  }));
  hostSelect.addEventListener("change", () => {
    state.host = hostSelect.value; ui.prefs.set("graph.host", state.host); load(false);
  });
  syncRangeButtons();

  // Opening the tab loads history once; going back and forth within the freshness window makes no request.
  ui.onTab(name => {
    if (name !== "graphs") return;
    if (!hasPlot) showBanner("error", "The chart library could not be loaded, so graphs are unavailable.");
    load(false);
    window.requestAnimationFrame(() => Object.values(charts).forEach(chart => {
      if (chart.instance && chart.plot.clientWidth > 0) chart.instance.setSize({ width: chart.plot.clientWidth, height: chart.plot.clientHeight });
    }));
  });
  // Piggyback on the page's own refresh (manual button, or the opt-in one-minute update while visible).
  // The portal answers from a short cache, so this does not start a Proxmox collection.
  ui.onRefresh(() => { if (ui.activeTab() === "graphs") load(true); });
  if (ui.activeTab() === "graphs") load(false);
})();
