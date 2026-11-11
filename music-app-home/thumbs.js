/* Piece thumbnails on Home and Library: a blurred render of each piece's own first page, centred
   on its title, in place of stock photos of other music.

   Each .card-art[data-thumb=<piece id>] gets an <img> once it nears the screen. The page is drawn
   by OpenSheetMusicDisplay (the practice page's renderer, loaded only when a thumbnail is missing)
   in an off-screen box, one piece at a time, only its first bars. The strip around the title is
   cut out on a canvas, saved as a small JPEG in localStorage (pieces never change), and blurred by
   the .card-art img rule in styles.css. If anything fails the card keeps its plain tinted art. */
(function () {
  var arts = Array.prototype.slice.call(document.querySelectorAll("[data-thumb]"));
  if (!arts.length || !window.HTMLCanvasElement) return;
  var VERSION = "v4", WIDTH = 800, OUT_W = 480, OUT_H = 264, BARS = 8, ZOOM = 0.9;   // ZOOM: share of the page width shown
  var queue = [], running = false, osmdReady = null;

  function cached(id) { try { return localStorage.getItem("thumb:" + VERSION + ":" + id); } catch (e) { return null; } }
  function keep(id, url) { try { localStorage.setItem("thumb:" + VERSION + ":" + id, url); } catch (e) { /* full: draw again next time */ } }

  function show(art, url) {
    var img = document.createElement("img");
    img.alt = "";
    img.className = "card-thumb";
    img.src = url;
    art.prepend(img);
    art.classList.add("has-thumb");
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

  // Where the title sits: the biggest text on the page (OSMD draws the title largest).
  function titleCentre(svg) {
    var best = null, size = 0;
    svg.querySelectorAll("text").forEach(function (t) {
      var s = parseFloat(t.getAttribute("font-size") || getComputedStyle(t).fontSize) || 0;
      if (s > size && t.textContent.trim()) { size = s; best = t; }
    });
    if (!best) return null;
    var box = best.getBBox();
    return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
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
      var osmd = new opensheetmusicdisplay.OpenSheetMusicDisplay(stage, {
        autoResize: false, drawTitle: true, drawComposer: true, drawPartNames: false, drawingParameters: "default",
      });
      await osmd.load(await r.text());
      osmd.setOptions({ drawUpToMeasureNumber: BARS });   // the first bars are all a thumbnail shows
      osmd.render();
      var svg = stage.querySelector("svg");
      var high = svg.height.baseVal.value || svg.getBoundingClientRect().height, wide = svg.width.baseVal.value || WIDTH;
      var centre = titleCentre(svg);
      var img = await svgImage(svg);
      // a box the shape of the card's art around the title (paper fills any part above the page)
      var stripW = wide * ZOOM, stripH = stripW * OUT_H / OUT_W;
      var c = centre || { x: wide / 2, y: stripH / 2 };
      var left = Math.max(0, Math.min(c.x - stripW / 2, wide - stripW)), top = Math.min(c.y - stripH * 0.25, high - stripH);   // the title a quarter of the way down, the first staves under it
      var canvas = document.createElement("canvas");
      canvas.width = OUT_W; canvas.height = OUT_H;
      var ctx = canvas.getContext("2d");
      ctx.fillStyle = "#fffdf5";
      ctx.fillRect(0, 0, OUT_W, OUT_H);
      var scale = OUT_W / stripW, skip = Math.max(0, -top);   // source rects must stay on the image
      ctx.drawImage(img, left, top + skip, stripW, stripH - skip, 0, skip * scale, OUT_W, OUT_H - skip * scale);
      return canvas.toDataURL("image/jpeg", 0.7);
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
