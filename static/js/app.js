/* SnapFind front-end behaviour: theme, toasts, uploads, drag-drop, zoom/pan. */
(function () {
  "use strict";

  const csrf = () =>
    (document.querySelector('meta[name="csrf-token"]') || {}).content || "";

  // --- Theme -------------------------------------------------------------- //
  window.toggleTheme = function () {
    const dark = document.documentElement.classList.toggle("dark");
    try { localStorage.setItem("theme", dark ? "dark" : "light"); } catch (e) {}
  };

  // --- Toasts ------------------------------------------------------------- //
  window.toast = function (msg) {
    const wrap = document.getElementById("toast");
    if (!wrap) return;
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = msg;
    wrap.appendChild(el);
    requestAnimationFrame(() => el.classList.add("show"));
    setTimeout(() => {
      el.classList.remove("show");
      setTimeout(() => el.remove(), 250);
    }, 2200);
  };

  // --- Copy helper -------------------------------------------------------- //
  window.copyText = function (id) {
    const el = document.getElementById(id);
    if (!el) return;
    navigator.clipboard.writeText(el.innerText).then(
      () => window.toast("Copied to clipboard"),
      () => window.toast("Copy failed")
    );
  };

  window.copyValue = function (el) {
    const v = el && el.dataset ? el.dataset.copy : "";
    if (!v) return;
    navigator.clipboard.writeText(v).then(
      () => window.toast("Copied"),
      () => window.toast("Copy failed")
    );
  };

  // --- Undo toast (soft-delete) ------------------------------------------- //
  window.showUndoToast = function (ids) {
    ids = (ids || []).map(Number).filter(Boolean);
    if (!ids.length) return;
    const wrap = document.getElementById("toast");
    if (!wrap) return;
    const el = document.createElement("div");
    el.className = "toast flex items-center gap-3";
    const span = document.createElement("span");
    span.textContent =
      ids.length === 1 ? "Moved to Trash" : ids.length + " moved to Trash";
    const btn = document.createElement("button");
    btn.textContent = "Undo";
    btn.className = "font-semibold underline shrink-0";
    let used = false;
    btn.addEventListener("click", function () {
      if (used) return;
      used = true;
      Promise.all(
        ids.map((id) =>
          fetch("/screenshot/" + id + "/restore", {
            method: "POST",
            headers: { "X-CSRF-Token": csrf() },
          })
        )
      ).then(() => {
        if (window.htmx) window.htmx.trigger(document.body, "refresh-grid");
        window.toast("Restored");
      });
      el.classList.remove("show");
      setTimeout(() => el.remove(), 250);
    });
    el.appendChild(span);
    el.appendChild(btn);
    wrap.appendChild(el);
    requestAnimationFrame(() => el.classList.add("show"));
    setTimeout(() => {
      el.classList.remove("show");
      setTimeout(() => el.remove(), 250);
    }, 6000);
  };

  document.body.addEventListener("snap-undo", function (evt) {
    window.showUndoToast((evt.detail && evt.detail.ids) || []);
  });

  // Undo toast after a viewer delete redirected to /app?undo=<id>.
  (function () {
    const p = new URLSearchParams(location.search);
    const undo = p.get("undo");
    if (undo) {
      window.showUndoToast([undo]);
      p.delete("undo");
      const qs = p.toString();
      history.replaceState({}, "", location.pathname + (qs ? "?" + qs : ""));
    }
  })();

  // --- Ensure CSRF header on every htmx request --------------------------- //
  document.body.addEventListener("htmx:configRequest", function (evt) {
    evt.detail.headers["X-CSRF-Token"] = csrf();
  });

  // --- data-toast buttons ------------------------------------------------- //
  // (Upload previews / progress / paste live in upload.js.)
  document.body.addEventListener("htmx:afterRequest", function (evt) {
    const elt = evt.detail.elt;
    if (elt && elt.dataset && elt.dataset.toast && evt.detail.successful) {
      window.toast(elt.dataset.toast);
    }
  });

  // --- Custom confirm dialog (replaces native hx-confirm popup) ----------- //
  let confirmCb = null;

  function showConfirm(message, cb) {
    const modal = document.getElementById("confirm-modal");
    if (!modal) {
      if (window.confirm(message)) cb();
      return;
    }
    const msg = document.getElementById("confirm-message");
    if (msg) msg.textContent = message;
    confirmCb = cb;
    modal.classList.remove("hidden");
    modal.classList.add("flex");
  }

  function hideConfirm() {
    const modal = document.getElementById("confirm-modal");
    if (modal) {
      modal.classList.add("hidden");
      modal.classList.remove("flex");
    }
    confirmCb = null;
  }

  document.body.addEventListener("htmx:confirm", function (evt) {
    if (!evt.detail.question) return; // element has no hx-confirm
    evt.preventDefault();
    showConfirm(evt.detail.question, function () {
      evt.detail.issueRequest(true);
    });
  });

  // Expose the styled confirm dialog for non-htmx callers (e.g. bulk actions).
  window.confirmDialog = showConfirm;

  // --- Keyboard shortcuts ------------------------------------------------- //
  document.addEventListener("keydown", function (e) {
    const t = e.target;
    const typing =
      t &&
      (t.tagName === "INPUT" ||
        t.tagName === "TEXTAREA" ||
        t.tagName === "SELECT" ||
        t.isContentEditable);

    if (e.key === "Escape") {
      if (typing) { t.blur(); return; }
      const uf = document.getElementById("upload-form");
      const uploadOpen = uf && uf.offsetParent !== null;
      const cm = document.getElementById("confirm-modal");
      const confirmOpen = cm && !cm.classList.contains("hidden");
      if (uploadOpen || confirmOpen) return; // closed by their own handlers
      if (document.getElementById("zoom-wrap")) history.back();
      return;
    }

    if (typing || e.ctrlKey || e.metaKey || e.altKey) return;

    // Viewer prev/next within the active filtered set.
    const zoom = document.getElementById("zoom-wrap");
    if (zoom && (e.key === "ArrowLeft" || e.key === "ArrowRight")) {
      e.preventDefault();
      const params = new URLSearchParams(location.search);
      params.set("dir", e.key === "ArrowLeft" ? "prev" : "next");
      fetch("/screenshot/" + zoom.dataset.screenshotId + "/neighbor?" + params.toString())
        .then((r) => r.json())
        .then((d) => {
          if (d && d.id) location.href = "/screenshot/" + d.id + location.search;
        });
      return;
    }

    if (e.key === "/") {
      const search = document.querySelector('input[type="search"][name="q"]');
      if (search) { e.preventDefault(); search.focus(); }
    } else if (e.key === "u") {
      e.preventDefault();
      window.dispatchEvent(new CustomEvent("snap-open-upload"));
    } else if (e.key === "f") {
      const favBtn = document.querySelector("#viewer-fav button");
      if (favBtn) { e.preventDefault(); favBtn.click(); }
    }
  });

  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-confirm-cancel]")) {
      hideConfirm();
      return;
    }
    if (e.target.closest("#confirm-ok")) {
      const cb = confirmCb;
      hideConfirm();
      if (cb) cb();
    }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    const modal = document.getElementById("confirm-modal");
    if (modal && !modal.classList.contains("hidden")) hideConfirm();
  });

  // --- Drag screenshots onto collections ---------------------------------- //
  let draggedId = null;
  document.addEventListener("dragstart", function (e) {
    const card = e.target.closest && e.target.closest(".ss-card");
    if (!card) return;
    draggedId = card.dataset.screenshotId;
    card.classList.add("dragging");
    if (e.dataTransfer) e.dataTransfer.effectAllowed = "move";
  });
  document.addEventListener("dragend", function (e) {
    const card = e.target.closest && e.target.closest(".ss-card");
    if (card) card.classList.remove("dragging");
    draggedId = null;
  });
  document.addEventListener("dragover", function (e) {
    const target = e.target.closest && e.target.closest(".drop-collection");
    if (target && draggedId) { e.preventDefault(); target.classList.add("drag-over"); }
  });
  document.addEventListener("dragleave", function (e) {
    const target = e.target.closest && e.target.closest(".drop-collection");
    if (target) target.classList.remove("drag-over");
  });
  document.addEventListener("drop", function (e) {
    const target = e.target.closest && e.target.closest(".drop-collection");
    if (!target || !draggedId) return;
    e.preventDefault();
    target.classList.remove("drag-over");
    const id = draggedId;
    const collectionId = target.dataset.collectionId;
    const body = new FormData();
    body.append("collection_id", collectionId);
    fetch("/screenshot/" + id + "/move", {
      method: "POST",
      headers: { "X-CSRF-Token": csrf() },
      body: body,
    }).then((r) => {
      if (r.ok) {
        window.toast("Moved to " + (target.innerText || "collection").trim().split("\n")[0]);
        if (window.htmx) window.htmx.trigger(document.body, "refresh-grid");
      } else {
        window.toast("Move failed");
      }
    });
  });

  // --- Viewer: zoom & pan ------------------------------------------------- //
  function initZoom() {
    const img = document.getElementById("zoom-img");
    if (!img || img.dataset.zoomReady) return;
    img.dataset.zoomReady = "1";
    let scale = 1, x = 0, y = 0, dragging = false, sx = 0, sy = 0;

    function apply() {
      img.style.transform =
        "translate(" + x + "px," + y + "px) scale(" + scale + ")";
      img.style.cursor = scale > 1 ? "grab" : "default";
    }
    function reset() { scale = 1; x = 0; y = 0; apply(); }
    function zoom(delta) {
      scale = Math.min(6, Math.max(1, scale + delta));
      if (scale === 1) { x = 0; y = 0; }
      apply();
    }

    const wrap = document.getElementById("zoom-wrap");
    wrap.addEventListener("wheel", function (e) {
      e.preventDefault();
      zoom(e.deltaY < 0 ? 0.2 : -0.2);
    }, { passive: false });

    img.addEventListener("mousedown", function (e) {
      if (scale <= 1) return;
      dragging = true; sx = e.clientX - x; sy = e.clientY - y;
      img.style.cursor = "grabbing"; e.preventDefault();
    });
    window.addEventListener("mousemove", function (e) {
      if (!dragging) return;
      x = e.clientX - sx; y = e.clientY - sy; apply();
    });
    window.addEventListener("mouseup", function () {
      dragging = false; if (scale > 1) img.style.cursor = "grab";
    });

    const zi = document.getElementById("zoom-in");
    const zo = document.getElementById("zoom-out");
    const zr = document.getElementById("zoom-reset");
    if (zi) zi.addEventListener("click", () => zoom(0.4));
    if (zo) zo.addEventListener("click", () => zoom(-0.4));
    if (zr) zr.addEventListener("click", reset);
  }

  document.addEventListener("DOMContentLoaded", initZoom);
  // Re-init if the viewer arrives via htmx swap.
  document.body.addEventListener("htmx:afterSwap", initZoom);
})();
