'use strict';
document.addEventListener('click', async (event) => {
  const button = event.target.closest('button[data-copy-text]');
  if (!button) return;
  const status = document.getElementById('hosting-copy-status');
  try {
    await navigator.clipboard.writeText(button.dataset.copyText);
    status.textContent = 'Copied.';
  } catch (_) {
    status.textContent = 'Copy unavailable. Select and copy the displayed text manually.';
  }
});
