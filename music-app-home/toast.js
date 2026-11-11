/* A brief message at the bottom of the screen that never blocks the page: "Passage saved",
   or "Passage deleted" with Undo. One at a time; a new one replaces the last.

   toast(text)                                  shows for 2.5 s
   toast(text, { action: "Undo", onAction, ms }) a button beside the text; onAction runs on its click
   toast(text, { onEnd })                       onEnd runs once when it goes, unless its button was used

   Screen readers hear it through a polite live region. Hovering or focusing it holds it open. */
function toast(text, { action, onAction, onEnd, ms = 2500 } = {}) {
  let box = document.getElementById("toast");
  if (!box) {
    box = Object.assign(document.createElement("div"), { id: "toast", className: "toast-region" });
    box.setAttribute("aria-live", "polite");
    document.body.append(box);
  }
  if (box.finish) box.finish();   // the last one ends now, its onEnd included

  const card = Object.assign(document.createElement("div"), { className: "toast" });
  card.append(Object.assign(document.createElement("span"), { className: "toast-text", textContent: text }));
  let timer, done = false;
  const finish = (used = false) => {
    if (done) return;
    done = true;
    clearTimeout(timer);
    card.remove();
    if (box.finish === finish) box.finish = null;
    if (!used && onEnd) onEnd();
  };
  if (action) {
    const b = Object.assign(document.createElement("button"), { type: "button", className: "toast-action", textContent: action });
    b.addEventListener("click", () => { finish(true); if (onAction) onAction(); });
    card.append(b);
  }
  const wait = () => { clearTimeout(timer); timer = setTimeout(() => finish(), ms); };
  card.addEventListener("pointerenter", () => clearTimeout(timer));
  card.addEventListener("pointerleave", wait);
  card.addEventListener("focusin", () => clearTimeout(timer));
  card.addEventListener("focusout", wait);
  box.replaceChildren(card);
  box.finish = finish;
  wait();
  return { close: () => finish() };
}
