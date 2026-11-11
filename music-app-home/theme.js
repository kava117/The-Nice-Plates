/* Theme handling, shared by both pages, and the sidebar's collapsed state.
   Loaded in <head> WITHOUT defer so both are set before first paint.
   Priority: saved choice, then the OS setting, then light. */
(function () {
  var KEY = "theme";
  var root = document.documentElement;

  // localStorage can throw (blocked storage, private mode), so always guard it.
  function readSaved() {
    try {
      var value = localStorage.getItem(KEY);
      return value === "light" || value === "dark" ? value : null;
    } catch (e) {
      return null;
    }
  }

  function save(theme) {
    try {
      localStorage.setItem(KEY, theme);
    } catch (e) {
      /* Storage blocked: the theme still changes for this page view. */
    }
  }

  function systemTheme() {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }

  // Keep the toggle's label describing the action it will perform.
  function updateLabel() {
    var button = document.querySelector("[data-theme-toggle]");
    if (!button) return;
    var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    button.setAttribute("aria-label", "Switch to " + next + " theme");
  }

  // Runs immediately, before the body is parsed.
  root.setAttribute("data-theme", readSaved() || systemTheme());

  document.addEventListener("DOMContentLoaded", updateLabel);

  // Event delegation, because the toggle doesn't exist yet when this runs.
  document.addEventListener("click", function (event) {
    if (!event.target.closest("[data-theme-toggle]")) return;
    var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    save(next);
    updateLabel();
  });
})();

/* The sidebar: the toggle in the top bar hides it so the page gets the full width, and the
   choice is remembered between visits (data-sidebar="collapsed" on <html>, set before paint). */
(function () {
  var KEY = "sidebar", root = document.documentElement;
  try { if (localStorage.getItem(KEY) === "collapsed") root.setAttribute("data-sidebar", "collapsed"); } catch (e) {}

  function sync() {
    var button = document.querySelector("[data-sidebar-toggle]");
    if (!button) return;
    var collapsed = root.getAttribute("data-sidebar") === "collapsed";
    var label = collapsed ? "Show the menu" : "Hide the menu";
    button.setAttribute("aria-expanded", String(!collapsed));
    button.setAttribute("aria-label", label);
    button.title = label;
  }
  document.addEventListener("DOMContentLoaded", sync);
  document.addEventListener("click", function (event) {
    if (!event.target.closest("[data-sidebar-toggle]")) return;
    var collapsed = root.getAttribute("data-sidebar") !== "collapsed";
    if (collapsed) root.setAttribute("data-sidebar", "collapsed"); else root.removeAttribute("data-sidebar");
    try { localStorage.setItem(KEY, collapsed ? "collapsed" : "open"); } catch (e) {}
    sync();
    window.dispatchEvent(new Event("resize"));   // the sheet music re-flows into the new width
  });
})();
