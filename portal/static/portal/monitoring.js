/* Monitoring page behaviour: tabs, saved-snapshot refresh and VM filters.
   Nothing here contacts Proxmox. "Refresh" re-reads the saved snapshot from this portal. */
(() => {
  "use strict";
  const root = document.getElementById("monitoring");
  if (!root) return;

  /* ---------- small helpers ---------- */
  const store = {
    get(key) { try { return window.localStorage.getItem("mon." + key); } catch (error) { return null; } },
    set(key, value) { try { window.localStorage.setItem("mon." + key, value); } catch (error) { /* private mode */ } },
  };
  const live = document.getElementById("mon-live");
  const announce = text => { if (live) { live.textContent = ""; window.setTimeout(() => { live.textContent = text; }, 30); } };
  const intervalMs = (Number(root.dataset.refreshSeconds) || 60) * 1000;

  /* ---------- tabs ---------- */
  const tabs = [...root.querySelectorAll('[role="tab"]')];
  const panels = {};
  tabs.forEach(tab => { panels[tab.dataset.tab] = document.getElementById(tab.getAttribute("aria-controls")); });
  const graphControls = document.getElementById("mon-graph-controls");
  const listeners = [];
  let active = "overview";

  function activate(name, options = {}) {
    if (!panels[name]) name = "overview";
    const changed = name !== active;
    active = name;
    tabs.forEach(tab => {
      const on = tab.dataset.tab === name;
      tab.setAttribute("aria-selected", on ? "true" : "false");
      tab.tabIndex = on ? 0 : -1;
      if (on && options.focus) tab.focus();
    });
    Object.entries(panels).forEach(([key, panel]) => { panel.hidden = key !== name; });
    if (graphControls) graphControls.hidden = name !== "graphs";
    if (options.remember !== false) {
      store.set("tab", name);
      // replaceState changes the address without navigating, reloading or adding history entries.
      try { window.history.replaceState(null, "", name === "overview" ? window.location.pathname + window.location.search
        : "#" + name); } catch (error) { /* ignore */ }
    }
    listeners.forEach(fn => fn(name, changed));
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => activate(tab.dataset.tab));
    tab.addEventListener("keydown", event => {
      const keys = { ArrowRight: 1, ArrowLeft: -1, Home: "first", End: "last" };
      if (!(event.key in keys)) return;
      event.preventDefault();
      let next = index;
      if (keys[event.key] === "first") next = 0;
      else if (keys[event.key] === "last") next = tabs.length - 1;
      else next = (index + keys[event.key] + tabs.length) % tabs.length;
      activate(tabs[next].dataset.tab, { focus: true });
    });
  });

  window.MonitoringUI = {
    prefs: store,
    announce,
    activeTab: () => active,
    onTab: fn => { listeners.push(fn); },
    onRefresh: fn => { refreshListeners.push(fn); },
  };
  const refreshListeners = [];

  /* ---------- VM filters (client-side, over the rows already on the page) ---------- */
  const search = document.getElementById("mon-search");
  const hostFilter = document.getElementById("mon-filter-host");
  const stateFilter = document.getElementById("mon-filter-state");
  const countLabel = document.getElementById("mon-count");

  function applyFilters() {
    const rows = [...root.querySelectorAll("#mon-vms tbody tr[data-vm]")];
    const query = (search ? search.value : "").trim().toLowerCase();
    const host = hostFilter ? hostFilter.value : "";
    const state = stateFilter ? stateFilter.value : "";
    let shown = 0;
    rows.forEach(row => {
      const match = (!query || row.dataset.search.includes(query)) && (!host || row.dataset.host === host)
        && (!state || row.dataset.state === state);
      row.hidden = !match;
      if (match) shown++;
    });
    const none = document.getElementById("mon-filter-empty");
    if (none) none.hidden = !(rows.length && shown === 0);
    if (countLabel) countLabel.textContent = rows.length && (query || host || state) ? `Showing ${shown} of ${rows.length}` : "";
    if (rows.length) announce(shown === rows.length ? "" : `${shown} of ${rows.length} virtual machines shown`);
  }
  if (search) {
    search.value = store.get("vm.q") || "";
    search.addEventListener("input", () => { store.set("vm.q", search.value); applyFilters(); });
  }
  [["vm.host", hostFilter], ["vm.state", stateFilter]].forEach(([key, select]) => {
    if (!select) return;
    const saved = store.get(key) || "";
    if ([...select.options].some(option => option.value === saved)) select.value = saved;
    select.addEventListener("change", () => { store.set(key, select.value); applyFilters(); });
  });

  /* ---------- freshness / age text ---------- */
  let serverOffset = 0; // serverNow - clientNow, so a wrong laptop clock cannot fake "stale"
  function syncClock() {
    const status = root.querySelector('[data-region="status"]');
    const now = status ? Number(status.dataset.serverNow) : NaN;
    if (Number.isFinite(now)) serverOffset = now - Date.now() / 1000;
  }
  function humanAge(seconds) {
    if (seconds < 90) return "just now";
    if (seconds < 3600) return Math.round(seconds / 60) + " min ago";
    if (seconds < 86400) return Math.round(seconds / 3600) + " h ago";
    return Math.round(seconds / 86400) + " d ago";
  }
  function tickAge() {
    const status = root.querySelector('[data-region="status"]');
    if (!status) return;
    const stamp = status.querySelector("time[data-epoch]");
    const age = status.querySelector("[data-age]");
    const pill = status.querySelector("[data-fresh-pill]");
    if (!stamp) return;
    const seconds = Date.now() / 1000 + serverOffset - Number(stamp.dataset.epoch);
    if (age && Number.isFinite(seconds)) age.textContent = "(" + humanAge(Math.max(0, seconds)) + ")";
    const limit = Number(status.dataset.staleSeconds);
    if (pill && status.dataset.freshness === "fresh" && Number.isFinite(limit) && seconds > limit) {
      pill.className = "mon-fresh stale";
      pill.lastChild.textContent = "Stale data";
    }
  }

  /* ---------- refresh of the saved snapshot ---------- */
  const refreshButton = document.getElementById("mon-refresh");
  const auto = document.getElementById("mon-auto");
  let inflight = null;
  let lastRefresh = Date.now();

  function setBusy(busy) {
    if (!refreshButton) return;
    refreshButton.setAttribute("aria-busy", busy ? "true" : "false");
    refreshButton.disabled = busy;
    refreshButton.querySelector(".mon-refresh-text").textContent = busy ? "Refreshing…" : "Refresh view";
  }

  function swapRegions(html) {
    const doc = new DOMParser().parseFromString(html, "text/html");
    const fresh = [...doc.querySelectorAll("[data-region]")];
    if (!fresh.some(node => node.dataset.region === "status")) return false; // e.g. a sign-in page
    fresh.forEach(node => {
      const current = root.querySelector(`[data-region="${node.dataset.region}"]`);
      if (current) current.replaceWith(document.importNode(node, true));
    });
    return true;
  }

  async function refresh(reason) {
    if (inflight) return inflight;           // never overlap requests
    setBusy(true);
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 15000);
    inflight = (async () => {
      try {
        const response = await fetch(root.dataset.overviewUrl, {
          credentials: "same-origin", cache: "no-store", signal: controller.signal,
          headers: { Accept: "text/html", "X-Requested-With": "fetch" },
        });
        if (!response.ok || response.redirected) throw new Error("session");
        if (!swapRegions(await response.text())) throw new Error("session");
        const emptyHint = root.querySelector('[data-region="hosts"] .mon-empty');
        const card = document.getElementById("mon-vm-card");
        if (card) card.hidden = !!emptyHint;
        syncClock(); applyFilters(); tickAge();
        lastRefresh = Date.now();
        refreshListeners.forEach(fn => fn(reason));
        if (reason === "manual") announce("Latest saved snapshot loaded.");
      } catch (error) {
        const message = error && error.message === "session"
          ? "Your session may have expired. Reload the page to sign in again."
          : "Could not reload the saved snapshot. Showing the previous readings.";
        const note = root.querySelector('[data-region="status"] .mon-collected');
        if (note && !note.querySelector(".mon-refresh-error")) {
          const span = document.createElement("span");
          span.className = "mon-refresh-error";
          span.textContent = " · " + message;
          note.appendChild(span);
        }
        announce(message);
      } finally {
        window.clearTimeout(timer);
        inflight = null;
        setBusy(false);
      }
    })();
    return inflight;
  }

  if (refreshButton) refreshButton.addEventListener("click", () => refresh("manual"));
  if (auto) {
    auto.checked = store.get("auto") !== "off";
    auto.addEventListener("change", () => store.set("auto", auto.checked ? "on" : "off"));
  }
  window.setInterval(() => {                  // checks only; a hidden tab makes no requests
    tickAge();
    if (auto && auto.checked && !document.hidden && Date.now() - lastRefresh >= intervalMs - 1000) refresh("auto");
  }, 15000);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && auto && auto.checked && Date.now() - lastRefresh >= intervalMs) refresh("auto");
  });

  /* ---------- start ---------- */
  syncClock(); applyFilters(); tickAge();
  const fromHash = window.location.hash.replace("#", "");
  const saved = store.get("tab");
  activate(panels[fromHash] ? fromHash : (panels[saved] ? saved : "overview"), { remember: false });
})();
