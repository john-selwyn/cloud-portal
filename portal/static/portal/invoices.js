/* My invoices (/invoices/) only. Progressive enhancement: the filter form is a plain GET form that
   works without JavaScript (Enter in the search box, or the Apply button shown by <noscript>). This
   script only submits it automatically when the due-date dropdown changes or the search box is
   cleared. Filtering always reloads the page, so tabs, search, due date and pagination are computed
   on the server across the customer's full invoice set. */
(function () {
  'use strict';
  var form = document.querySelector('form[data-invoices-filter]');
  if (!form) { return; }

  form.querySelectorAll('select').forEach(function (select) {
    select.addEventListener('change', function () { form.submit(); });
  });

  var search = form.querySelector('input[type="search"]');
  if (search) {
    search.addEventListener('search', function () {
      if (search.value === '' && search.defaultValue !== '') { form.submit(); }
    });
  }
})();
