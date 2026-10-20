/* My orders (/orders/) only. Progressive enhancement: the filter form is a plain GET form that works
   without JavaScript (Enter in the search box, or the Apply button shown by <noscript>). This script
   only submits it automatically when a dropdown changes or the search box is cleared. Filters always
   reload the page so tabs, search, dropdowns and pagination are computed on the server across the
   customer's full order set. */
(function () {
  'use strict';
  var form = document.querySelector('form[data-orders-filter]');
  if (!form) { return; }

  form.querySelectorAll('select').forEach(function (select) {
    select.addEventListener('change', function () { form.submit(); });
  });

  var search = form.querySelector('input[type="search"]');
  if (search) {
    // Fired by the browser's built-in clear (x) button and by Escape in type="search" fields.
    search.addEventListener('search', function () {
      if (search.value === '' && search.defaultValue !== '') { form.submit(); }
    });
  }
})();
