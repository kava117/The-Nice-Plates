/* Leaving a page, shared by every page.
   On the free server a page can take a few seconds. A click on a link shows at once that it
   registered: its sidebar item turns current and a thin bar runs under the top bar. Any other
   link still works while it loads; the browser drops the first. Back restores the old state. */
(function () {
  var root = document.documentElement;
  var current = document.querySelector(".nav-link[aria-current]");
  var timer;

  function settle() {
    clearTimeout(timer);
    root.classList.remove("is-leaving");
    document.querySelectorAll(".nav-link[aria-current]").forEach(function (link) { link.removeAttribute("aria-current"); });
    if (current) current.setAttribute("aria-current", "page");
  }

  document.addEventListener("click", function (event) {
    var link = event.target.closest("a[href]");
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if ((link.target && link.target !== "_self") || link.hasAttribute("download") || link.origin !== location.origin) return;
    if (link.pathname === location.pathname && link.search === location.search) return;   // same page, or a #link on it
    if (link.classList.contains("nav-link")) {
      document.querySelectorAll(".nav-link[aria-current]").forEach(function (l) { l.removeAttribute("aria-current"); });
      link.setAttribute("aria-current", "page");
    }
    clearTimeout(timer);
    timer = setTimeout(function () { root.classList.add("is-leaving"); }, 150);   // a fast page never shows the bar
  });

  window.addEventListener("pageshow", settle);   // back or forward from the browser's cache
})();
