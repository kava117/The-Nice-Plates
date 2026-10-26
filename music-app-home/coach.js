/* The coach on the practice page: ask about your own practice, answered from your record (coach.py).
   A panel beside the score, so the bars it talks about stay in view.

   addCoach(els) wires it. */
function addCoach(els) {
  const { panel, toggle, close } = els;
  const OPEN = "coach-open";

  // ---- opening and closing ----
  const isOpen = () => !panel.hidden;
  function setOpen(open, { focus = true } = {}) {
    panel.hidden = !open;
    toggle.setAttribute("aria-expanded", open);
    toggle.classList.toggle("is-on", open);
    document.body.classList.toggle("coach-open", open);
    try { sessionStorage.setItem(OPEN, open ? "1" : ""); } catch {}
    dispatchEvent(new Event("resize"));   // the score re-flows into the narrower column
    if (focus) (open ? close : toggle).focus();
  }
  const flip = () => setOpen(!isOpen());

  toggle.addEventListener("click", flip);
  close.addEventListener("click", () => setOpen(false));
  panel.addEventListener("keydown", e => {
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); setOpen(false); }
  });

  let wasOpen = false;
  try { wasOpen = !!sessionStorage.getItem(OPEN); } catch {}
  if (wasOpen) setOpen(true, { focus: false });

  return { toggle: flip, get open() { return isOpen(); } };
}
