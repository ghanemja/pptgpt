/* ============================================================
   pptgpt — demo gate
   ------------------------------------------------------------
   Client-side gate. NOT real authentication. Source is visible,
   anyone can read the creds. Purpose: keep the demo URL from
   being crawled / shared casually. Don't put anything sensitive
   on this site.
   ============================================================ */
(function () {
  if (sessionStorage.getItem('pptgpt.gate') === 'ok') return;
  // Block render until gate passes — redirect to /login with a
  // return path so the user lands back where they tried to go.
  var here = location.pathname + location.search + location.hash;
  if (location.pathname === '/login' || location.pathname === '/login.html') return;
  location.replace('/login.html?next=' + encodeURIComponent(here));
})();
