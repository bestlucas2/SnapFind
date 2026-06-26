/* SnapFind grid multi-select + bulk actions. */
(function () {
  "use strict";

  const csrf = () =>
    (document.querySelector('meta[name="csrf-token"]') || {}).content || "";

  const selected = new Set();
  let lastIndex = null;

  const checkboxes = () => Array.from(document.querySelectorAll(".ss-select"));
  const cardOf = (cb) => cb.closest(".ss-card");

  function updateBar() {
    const bar = document.getElementById("bulk-bar");
    const count = document.getElementById("bulk-count");
    if (count) count.textContent = String(selected.size);
    if (bar) bar.classList.toggle("hidden", selected.size === 0);
  }

  function setChecked(cb, on) {
    cb.checked = on;
    const card = cardOf(cb);
    if (card) card.classList.toggle("ss-selected", on);
    if (on) selected.add(cb.dataset.id);
    else selected.delete(cb.dataset.id);
  }

  // Re-apply selection state after the grid is swapped by htmx.
  function syncFromDom() {
    const present = new Set(checkboxes().map((cb) => cb.dataset.id));
    for (const id of [...selected]) if (!present.has(id)) selected.delete(id);
    checkboxes().forEach((cb) => setChecked(cb, selected.has(cb.dataset.id)));
    updateBar();
  }

  function applySelect(cb, targetState) {
    setChecked(cb, targetState);
    updateBar();
  }

  document.addEventListener("click", function (e) {
    // Direct checkbox click — it already toggled itself.
    const cb = e.target.closest && e.target.closest(".ss-select");
    if (cb) {
      applySelect(cb, cb.checked);
      return;
    }
    // Shift-click anywhere on a card selects only that card (no range) instead
    // of opening the image in a new window.
    if (e.shiftKey) {
      const card = e.target.closest && e.target.closest(".ss-card");
      const box = card && card.querySelector(".ss-select");
      if (box) {
        e.preventDefault();
        applySelect(box, !box.checked);
      }
    }
  });

  document.body.addEventListener("htmx:afterSwap", function (evt) {
    if (evt.target && evt.target.id === "grid") syncFromDom();
  });

  // --- Bulk actions ------------------------------------------------------- //
  function ids() {
    return [...selected].join(",");
  }

  function postBulk(path, extra) {
    const fd = new FormData();
    fd.append("ids", ids());
    if (extra) for (const k in extra) fd.append(k, extra[k]);
    return fetch(path, {
      method: "POST",
      headers: { "X-CSRF-Token": csrf() },
      body: fd,
    });
  }

  function clearSelection() {
    selected.clear();
    lastIndex = null;
    checkboxes().forEach((cb) => {
      cb.checked = false;
      const card = cardOf(cb);
      if (card) card.classList.remove("ss-selected");
    });
    updateBar();
  }

  function afterMutation(msg) {
    clearSelection();
    if (window.htmx) window.htmx.trigger(document.body, "refresh-grid");
    if (msg && window.toast) window.toast(msg);
  }

  window.bulkClear = clearSelection;
  window.bulkSelectAll = function () {
    checkboxes().forEach((cb) => setChecked(cb, true));
    updateBar();
  };
  window.bulkTag = function (name) {
    name = (name || "").trim();
    if (!name || !selected.size) return;
    postBulk("/bulk/tag", { tag: name }).then(() => afterMutation("Tagged"));
  };
  window.bulkFavorite = function (v) {
    if (!selected.size) return;
    postBulk("/bulk/favorite", { favorite: v ? "1" : "0" }).then(() =>
      afterMutation(v ? "Favorited" : "Unfavorited")
    );
  };
  window.bulkArchive = function (v) {
    if (!selected.size) return;
    postBulk("/bulk/archive", { archived: v ? "1" : "0" }).then(() =>
      afterMutation("Archived")
    );
  };
  window.bulkRetry = function () {
    if (!selected.size) return;
    postBulk("/bulk/retry").then(() => afterMutation("Re-running OCR"));
  };
  window.bulkDelete = function () {
    if (!selected.size) return;
    const snapshot = [...selected];
    postBulk("/bulk/delete")
      .then((r) => r.json())
      .then((data) => {
        afterMutation();
        if (window.showUndoToast) window.showUndoToast((data && data.ids) || snapshot);
      });
  };
  window.bulkRestore = function () {
    if (!selected.size) return;
    postBulk("/bulk/restore").then(() => afterMutation("Restored"));
  };
  window.bulkPermanent = function () {
    if (!selected.size) return;
    const n = selected.size;
    const go = () => postBulk("/bulk/permanent").then(() => afterMutation("Deleted"));
    if (window.confirmDialog) window.confirmDialog(
      "Permanently delete " + n + " screenshot" + (n === 1 ? "" : "s") + "? This cannot be undone.", go
    );
    else if (window.confirm("Permanently delete " + n + " screenshots? This cannot be undone.")) go();
  };
  window.bulkExport = function (fmt) {
    if (!selected.size) return;
    window.location =
      "/bulk/export?format=" + encodeURIComponent(fmt) + "&ids=" + encodeURIComponent(ids());
  };
})();
