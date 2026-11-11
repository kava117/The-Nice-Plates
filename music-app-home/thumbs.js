/* Piece thumbnails on Home and Library: a sharp render of each piece's own first bars.

   Each .card-art[data-thumb=<piece id>] gets an <img> once it nears the screen. The page is drawn
   by OpenSheetMusicDisplay (the practice page's renderer, loaded only when a thumbnail is missing)
   in an off-screen box, one piece at a time. The top of the page (title + first staff) is cut out
   on a canvas and saved as a JPEG in localStorage. If anything fails the card keeps its staff art. */
(function () {
  var arts = Array.prototype.slice.call(document.querySelectorAll("[data-thumb]"));
  if (!arts.length || !window.HTMLCanvasElement) return;
  // Wider, flatter crop: a page of music, not a few notes blown up to fill the card.
  var VERSION = "v7", WIDTH = 1100, OUT_W = 960, OUT_H = 420, BARS = 12, ZOOM = 1;
  var queue = [], running = false, osmdReady = null;

  function cached(id) { try { return localStorage.getItem("thumb:" + VERSION + ":" + id); } catch (e) { return null; } }
  function keep(id, url) { try { localStorage.setItem("thumb:" + VERSION + ":" + id, url); } catch (e) { /* full: draw again next time */ } }

  function show(art, url) {
    var img = document.createElement("img");
    img.alt = "";
    img.className = "card-thumb";
    img.src = url;
    art.prepend(img);
    // next frame so the opacity transition from the staff placeholder actually runs
    requestAnimationFrame(function () { art.classList.add("has-thumb"); });
  }

  function loadOsmd() {
    if (window.opensheetmusicdisplay) return Promise.resolve();
    osmdReady = osmdReady || new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = "/opensheetmusicdisplay.min.js";
      s.onload = resolve;
      s.onerror = reject;
      document.head.appendChild(s);
    });
    return osmdReady;
  }

  // The rendered page as an image: serialise OSMD's SVG and load it through a blob URL.
  function svgImage(svg) {
    svg.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    var url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(svg)], { type: "image/svg+xml" }));
    return new Promise(function (resolve, reject) {
      var img = new Image();
      img.onload = function () { URL.revokeObjectURL(url); resolve(img); };
      img.onerror = function () { URL.revokeObjectURL(url); reject(new Error("svg didn't load")); };
      img.src = url;
    });
  }

  async function draw(id) {
    await loadOsmd();
    var stage = document.createElement("div");
    stage.setAttribute("aria-hidden", "true");
    stage.style.cssText = "position:absolute;left:-10000px;top:0;width:" + WIDTH + "px;background:#fffdf5";
    document.body.appendChild(stage);
    try {
      var r = await fetch("/api/pieces/" + id + "/musicxml");
      if (!r.ok) throw new Error("musicxml " + r.status);
      // Title and composer already sit in the card caption; the art is the notes themselves.
      var osmd = new opensheetmusicdisplay.OpenSheetMusicDisplay(stage, {
        autoResize: false, drawTitle: false, drawComposer: false, drawPartNames: false,
        drawMeasureNumbers: false, drawingParameters: "compacttight",
      });
      await osmd.load(await r.text());
      osmd.setOptions({ drawUpToMeasureNumber: BARS });
      osmd.zoom = 0.85;
      osmd.render();
      var svg = stage.querySelector("svg");
      var high = svg.height.baseVal.value || svg.getBoundingClientRect().height, wide = svg.width.baseVal.value || WIDTH;
      var img = await svgImage(svg);
      var canvas = document.createElement("canvas");
      canvas.width = OUT_W; canvas.height = OUT_H;
      var ctx = canvas.getContext("2d");
      ctx.fillStyle = "#fffdf5";
      ctx.fillRect(0, 0, OUT_W, OUT_H);
      // Fit the whole rendered strip inside the card (letterbox), so short pieces aren't magnified.
      var scale = Math.min(OUT_W / wide, OUT_H / high) * ZOOM;
      var dw = wide * scale, dh = high * scale;
      ctx.drawImage(img, 0, 0, wide, high, (OUT_W - dw) / 2, (OUT_H - dh) / 2, dw, dh);
      return canvas.toDataURL("image/jpeg", 0.92);
    } finally {
      stage.remove();
    }
  }

  async function run() {
    if (running) return;
    running = true;
    while (queue.length) {
      var art = queue.shift(), id = art.dataset.thumb;
      try {
        var url = cached(id) || await draw(id);
        keep(id, url);
        show(art, url);
      } catch (err) {
        console.warn("No thumbnail for piece " + id + ":", err);
      }
      await new Promise(function (r) { setTimeout(r, 30); });   // let the page breathe between pieces
    }
    running = false;
  }

  function want(art) {
    var url = cached(art.dataset.thumb);
    if (url) return show(art, url);   // instant: no renderer needed
    queue.push(art);
    run();
  }

  if (!("IntersectionObserver" in window)) return arts.forEach(want);
  var seen = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (!e.isIntersecting) return;
      seen.unobserve(e.target);
      want(e.target);
    });
  }, { rootMargin: "200px" });
  arts.forEach(function (a) { seen.observe(a); });
})();
