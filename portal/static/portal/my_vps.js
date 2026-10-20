/* My VPS page: search, plan/status filters, grid/list view and IP copy.
   Presentation only. It never changes data and never sends requests. */
(function () {
  'use strict';

  var root = document.querySelector('[data-vps-page]');
  var grid = root && root.querySelector('[data-vps-grid]');
  if (!grid) { return; }

  var cards = Array.prototype.slice.call(grid.querySelectorAll('[data-vps-card]'));
  var toolbar = root.querySelector('[data-vps-toolbar]');
  var search = root.querySelector('[data-vps-search]');
  var planSelect = root.querySelector('[data-vps-plan]');
  var statusSelect = root.querySelector('[data-vps-status]');
  var viewButtons = Array.prototype.slice.call(root.querySelectorAll('[data-vps-view]'));
  var noMatch = root.querySelector('[data-vps-no-match]');
  var clearButton = root.querySelector('[data-vps-clear]');
  var live = root.querySelector('[data-vps-live]');
  var VIEW_KEY = 'portal.myVps.view';

  function addOptions(select, attr, labelAttr) {
    var seen = {};
    cards.forEach(function (card) {
      var value = card.getAttribute(attr);
      if (!value || seen[value]) { return; }
      seen[value] = card.getAttribute(labelAttr) || value;
    });
    Object.keys(seen).sort(function (a, b) {
      return seen[a].localeCompare(seen[b]);
    }).forEach(function (value) {
      var option = document.createElement('option');
      option.value = value;
      option.textContent = seen[value];
      select.appendChild(option);
    });
  }

  addOptions(planSelect, 'data-plan', 'data-plan');
  addOptions(statusSelect, 'data-status', 'data-status-label');

  function announce(message) {
    if (live) { live.textContent = message; }
  }

  function applyFilters() {
    var terms = search.value.toLowerCase().split(/\s+/).filter(Boolean);
    var plan = planSelect.value;
    var status = statusSelect.value;
    var shown = 0;

    cards.forEach(function (card) {
      var haystack = (card.getAttribute('data-search') || '').toLowerCase();
      var match = terms.every(function (term) { return haystack.indexOf(term) !== -1; }) &&
        (!plan || card.getAttribute('data-plan') === plan) &&
        (!status || card.getAttribute('data-status') === status);
      card.hidden = !match;
      if (match) { shown += 1; }
    });

    grid.hidden = shown === 0;
    noMatch.hidden = shown !== 0;
    announce('Showing ' + shown + ' of ' + cards.length + (cards.length === 1 ? ' server' : ' servers'));
  }

  function setView(view) {
    if (view !== 'list') { view = 'grid'; }
    grid.setAttribute('data-view', view);
    viewButtons.forEach(function (button) {
      var active = button.getAttribute('data-vps-view') === view;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    try { window.localStorage.setItem(VIEW_KEY, view); } catch (e) { /* storage unavailable */ }
  }

  search.addEventListener('input', applyFilters);
  planSelect.addEventListener('change', applyFilters);
  statusSelect.addEventListener('change', applyFilters);
  search.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && search.value) { search.value = ''; applyFilters(); }
  });
  viewButtons.forEach(function (button) {
    button.addEventListener('click', function () { setView(button.getAttribute('data-vps-view')); });
  });
  clearButton.addEventListener('click', function () {
    search.value = '';
    planSelect.value = '';
    statusSelect.value = '';
    applyFilters();
    search.focus();
  });

  var saved = null;
  try { saved = window.localStorage.getItem(VIEW_KEY); } catch (e) { saved = null; }
  setView(saved);
  toolbar.hidden = false;

  /* ---------- Copy IP address ---------- */
  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      var field = document.createElement('textarea');
      field.value = text;
      field.setAttribute('readonly', '');
      field.style.position = 'fixed';
      field.style.opacity = '0';
      document.body.appendChild(field);
      field.select();
      var ok = false;
      try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
      document.body.removeChild(field);
      if (ok) { resolve(); } else { reject(new Error('copy failed')); }
    });
  }

  var timers = new WeakMap();

  function showCopyState(button, copied) {
    var tip = button.querySelector('.vps-copy-tip');
    button.classList.remove('is-copied', 'is-failed');
    button.classList.add(copied ? 'is-copied' : 'is-failed');
    if (tip) { tip.textContent = copied ? 'Copied' : 'Copy failed'; }
    clearTimeout(timers.get(button));
    timers.set(button, setTimeout(function () {
      button.classList.remove('is-copied', 'is-failed');
    }, 1800));
  }

  grid.addEventListener('click', function (event) {
    var button = event.target.closest('[data-copy-ip]');
    if (!button) { return; }
    var address = button.getAttribute('data-copy-ip');
    copyText(address).then(function () {
      showCopyState(button, true);
      announce('IP address ' + address + ' copied to clipboard');
    }, function () {
      showCopyState(button, false);
      announce('Could not copy the IP address. Select it and copy it manually.');
    });
  });
}());
