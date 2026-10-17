/* Refreshes the saved view only. No notifications or infrastructure actions. */
(() => {
  const search = document.getElementById("mon-search");
  const rows = [...document.querySelectorAll("#mon-vms tbody tr")];
  if (search) search.addEventListener("input", () => {
    const query = search.value.trim().toLowerCase();
    let visible = 0;
    rows.forEach(row => {
      row.hidden = !row.textContent.toLowerCase().includes(query);
      if (!row.hidden) visible++;
    });
    document.getElementById("mon-filter-empty").hidden = visible !== 0;
  });
  window.setInterval(() => {
    if (document.getElementById("mon-auto")?.checked && !document.hidden && !search?.value)
      window.location.reload();
  }, 60000);
})();
