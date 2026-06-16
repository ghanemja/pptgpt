(function () {
  if (sessionStorage.getItem('pptgpt.gate') === 'ok') return;
  var here = location.pathname + location.search + location.hash;
  if (location.pathname === '/login' || location.pathname === '/login.html') return;
  location.replace('/login.html?next=' + encodeURIComponent(here));
})();
