/* Uploading sheet music (Library and Home): every form marked data-upload.

   Without script the form posts and the server redirects. With it, the file goes up by
   XMLHttpRequest so the page can say what's happening:
     1. "Uploading your sheet music…" with a real percentage (the browser reports upload bytes)
     2. "Converting to notation — this can take up to a minute": the server doesn't report its
        progress, so this stage is named, not measured
     3. "Done", then the practice page for the new piece.
   The server answers with a redirect either way: /practice?piece=N when it worked, /library?error=…
   when it didn't. A failure says why and offers Try again, which sends the same file again. */
(function () {
  var MAX = 20 * 1024 * 1024;   // the server's limit
  var box = document.getElementById("upload-status");
  if (!box || !window.FormData) return;
  var message = document.getElementById("upload-message"), bar = document.getElementById("upload-bar");
  var fill = bar.querySelector(".upload-bar-fill"), actions = document.getElementById("upload-actions");
  var retry = document.getElementById("upload-retry");
  var last = null, busy = false;   // the last form and its data, for Try again
  var ORDER = ["upload", "convert", "done"];

  function stage(name) {
    var at = ORDER.indexOf(name);
    box.querySelectorAll("[data-stage]").forEach(function (li) {
      var mine = ORDER.indexOf(li.dataset.stage);
      li.classList.toggle("is-done", mine < at || name === "done");
      li.classList.toggle("is-current", mine === at && name !== "done");
      if (mine === at) li.setAttribute("aria-current", "step"); else li.removeAttribute("aria-current");
    });
  }
  function percent(n) {
    bar.hidden = n === null;
    if (n === null) return;
    fill.style.width = n + "%";
    bar.setAttribute("aria-valuenow", String(n));
  }
  function show(text, kind) {   // kind: "busy", "error" or "done"
    box.hidden = false;
    box.classList.toggle("is-error", kind === "error");
    box.classList.toggle("is-busy", kind === "busy");
    message.textContent = text;
    actions.hidden = kind !== "error";
    if (kind === "error") { percent(null); retry.focus(); }
  }
  function setBusy(form, on) {
    busy = on;
    form.querySelectorAll("button, input, label.btn").forEach(function (el) {
      if (el.tagName === "LABEL") el.classList.toggle("is-disabled", on); else el.disabled = on;
    });
  }

  function send(form, data) {
    last = { form: form, data: data };
    var file = data.get("file");
    if (file && file.size > MAX) { show("That file is over 20 MB. Try a smaller PDF or photo.", "error"); return; }
    setBusy(form, true);
    stage("upload");
    show("Uploading your sheet music…", "busy");
    percent(0);
    var xhr = new XMLHttpRequest();
    xhr.open("POST", form.action);
    xhr.upload.onprogress = function (e) { if (e.lengthComputable) percent(Math.round(e.loaded / e.total * 100)); };
    xhr.upload.onload = function () {
      percent(null);
      stage("convert");
      show("Converting to notation — this can take up to a minute", "busy");
    };
    xhr.onload = function () {
      setBusy(form, false);
      var to = new URL(xhr.responseURL || location.href, location.href);
      var error = to.searchParams.get("error");
      if (to.pathname === "/practice" && to.searchParams.get("piece")) {
        stage("done");
        show("Done — opening your piece…", "done");
        location.assign(to.pathname + to.search);
      } else if (error) {
        stage("upload");
        show(error, "error");
      } else if (xhr.status >= 400) {
        show("Something went wrong on our side (" + xhr.status + "). Try again in a moment.", "error");
      } else {
        show("The upload finished, but the piece didn't open. Check Library, or try again.", "error");
      }
    };
    xhr.onerror = xhr.ontimeout = function () {
      setBusy(form, false);
      show("The upload didn't get through. Check your connection and try again.", "error");
    };
    xhr.send(data);
  }

  document.querySelectorAll("form[data-upload]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (!busy) send(form, new FormData(form));
    });
    var details = form.querySelector("[data-upload-details]");
    if (details) {   // Library: title, composer and Upload once there's a file to name
      form.querySelector("input[type=file]").addEventListener("change", function (e) {
        var file = e.target.files[0];
        details.hidden = !file;
        if (!file) return;
        var title = form.querySelector("input[name=title]");
        title.placeholder = file.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim() + " (or type a title)";
        title.focus();
      });
    }
    if (form.hasAttribute("data-upload-on-pick")) {   // Home: picking the file is the whole form
      form.querySelector("input[type=file]").addEventListener("change", function (e) {
        if (e.target.files[0] && !busy) send(form, new FormData(form));
      });
    }
  });
  retry.addEventListener("click", function () {   // after a reload with ?error= there's no file kept: pick one again
    if (busy) return;
    if (last) return send(last.form, last.data);
    var input = document.querySelector("form[data-upload] input[type=file]");
    if (input) input.click();
  });
})();
