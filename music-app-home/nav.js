/* Leaving a page, shared by every page.
   On the free server a page can take a few seconds. A click on a link shows at once that it
   registered: its sidebar item turns current and a thin bar runs under the top bar. Any other
   link still works while it loads; the browser drops the first. Back restores the old state.
   After 15 idle minutes the server sleeps and takes up to a minute to wake, so a long wait says so. */
(function () {
  var root = document.documentElement;
  var current = document.querySelector(".nav-link[aria-current]");
  var timer, slow, note;

  function sayWaking() {
    note = document.createElement("p");
    note.className = "leaving-note";
    note.setAttribute("role", "status");
    note.textContent = "Still loading. The server sleeps when nobody’s using it and can take up to a minute to wake.";
    document.body.appendChild(note);
  }

  function settle() {
    clearTimeout(timer);
    clearTimeout(slow);
    if (note) note.remove();
    note = null;
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
    clearTimeout(slow);
    timer = setTimeout(function () { root.classList.add("is-leaving"); }, 150);   // a fast page never shows the bar
    if (!note) slow = setTimeout(sayWaking, 5000);
  });

  window.addEventListener("pageshow", settle);   // back or forward from the browser's cache
})();
