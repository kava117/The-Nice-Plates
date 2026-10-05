/* Keyboard press state, shared by both pages.
   Mouse and touch presses use CSS :active. This adds the same look
   (.is-pressed) while Enter or Space is held on a focused .press element.
   It never blocks the element's normal action. */
(function () {
  var PRESSED = "is-pressed";

  function release() {
    document.querySelectorAll("." + PRESSED).forEach(function (el) {
      el.classList.remove(PRESSED);
    });
  }

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    var el = document.activeElement;
    if (el && el.classList.contains("press")) el.classList.add(PRESSED);
  });

  document.addEventListener("keyup", release);
  document.addEventListener("focusout", release);
  window.addEventListener("blur", release);
})();
