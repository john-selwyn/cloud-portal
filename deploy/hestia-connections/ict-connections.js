'use strict';
document.addEventListener('click', async (event) => {
  const button = event.target.closest('button[data-ict-copy]');
  if (!button) return;
  const status = document.getElementById('ict-copy-status');
  try {
    await navigator.clipboard.writeText(button.dataset.ictCopy);
    status.textContent = 'Copied.';
  } catch (_) {
    status.textContent = 'Copy unavailable. Select and copy the text manually.';
  }
});
