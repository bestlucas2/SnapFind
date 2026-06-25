/* SnapFind upload modal: previews, tag editor, category, AI suggestions. */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const csrf = () =>
    (document.querySelector('meta[name="csrf-token"]') || {}).content || "";

  const state = { files: [], tags: [], urls: [], analyzeTimer: null };

  // Alpine component for the custom, rounded category dropdown.
  document.addEventListener("alpine:init", () => {
    window.Alpine.data("categoryPicker", (cats) => ({
      open: false,
      value: "",
      categories: Array.isArray(cats) ? cats : [],
      filtered() {
        const q = (this.value || "").trim().toLowerCase();
        return q
          ? this.categories.filter((c) => c.toLowerCase().includes(q))
          : this.categories;
      },
      canCreate() {
        const q = (this.value || "").trim();
        return !!q && !this.categories.some((c) => c.toLowerCase() === q.toLowerCase());
      },
      select(c) {
        this.value = c;
        this.open = false;
      },
    }));
  });

  function els() {
    return {
      input: $("file-input"),
      dropzone: $("dropzone"),
      previews: $("upload-previews"),
      count: $("file-count"),
      tagInput: $("upload-tag-input"),
      tagAdd: $("upload-tag-add"),
      chips: $("upload-tag-chips"),
      tagsHidden: $("upload-tags-hidden"),
      category: $("upload-category"),
      suggestions: $("upload-suggestions"),
      suggestStatus: $("upload-suggest-status"),
      bar: $("upload-bar"),
      form: $("upload-form"),
    };
  }

  // --- File selection ----------------------------------------------------- //
  function syncInput() {
    const e = els();
    if (!e.input) return;
    const dt = new DataTransfer();
    state.files.forEach((f) => dt.items.add(f));
    e.input.files = dt.files;
  }

  function addFiles(fileList) {
    const incoming = Array.from(fileList || []).filter((f) =>
      f.type.startsWith("image/")
    );
    for (const f of incoming) {
      const dup = state.files.some(
        (g) => g.name === f.name && g.size === f.size
      );
      if (!dup) state.files.push(f);
    }
    syncInput();
    renderPreviews();
    scheduleAnalyze();
  }

  function removeFile(idx) {
    state.files.splice(idx, 1);
    syncInput();
    renderPreviews();
    scheduleAnalyze();
  }

  function renderPreviews() {
    const e = els();
    if (!e.previews) return;
    state.urls.forEach((u) => URL.revokeObjectURL(u));
    state.urls = [];
    e.previews.innerHTML = "";

    state.files.forEach((file, idx) => {
      const url = URL.createObjectURL(file);
      state.urls.push(url);

      const card = document.createElement("div");
      card.className =
        "relative group rounded-lg overflow-hidden border border-neutral-200 dark:border-neutral-700 aspect-square bg-neutral-100 dark:bg-neutral-800";

      const img = document.createElement("img");
      img.src = url;
      img.className = "w-full h-full object-cover";
      card.appendChild(img);

      const btn = document.createElement("button");
      btn.type = "button";
      btn.title = "Remove";
      btn.className =
        "absolute top-1 right-1 w-6 h-6 rounded-full bg-white/90 dark:bg-neutral-900/80 backdrop-blur text-neutral-500 hover:text-red-500 hover:ring-1 hover:ring-red-400 shadow-sm flex items-center justify-center opacity-0 group-hover:opacity-100 transition";
      btn.innerHTML =
        '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" d="M6 6l12 12M18 6L6 18"/></svg>';
      btn.addEventListener("click", () => removeFile(idx));
      card.appendChild(btn);

      e.previews.appendChild(card);
    });

    if (e.count) {
      const n = state.files.length;
      e.count.textContent = n
        ? n + " image" + (n === 1 ? "" : "s") + " ready"
        : "";
    }
  }

  // --- Tags --------------------------------------------------------------- //
  function maxTags() {
    const el = $("upload-tag-chips");
    const n = el ? parseInt(el.dataset.maxTags, 10) : 3;
    return Number.isFinite(n) && n > 0 ? n : 3;
  }

  function syncTagsHidden() {
    const e = els();
    if (e.tagsHidden) e.tagsHidden.value = state.tags.join(",");
  }

  function addTag(name) {
    name = (name || "").trim().toLowerCase().replace(/\s+/g, " ").slice(0, 80);
    if (!name || state.tags.includes(name)) return;
    if (state.tags.length >= maxTags()) return; // cap reached
    state.tags.push(name);
    syncTagsHidden();
    renderChips();
    refreshTagMenu();
  }

  function removeTag(name) {
    state.tags = state.tags.filter((t) => t !== name);
    syncTagsHidden();
    renderChips();
    refreshTagMenu();
  }

  function renderChips() {
    const e = els();
    if (!e.chips) return;
    e.chips.innerHTML = "";
    state.tags.forEach((name) => {
      const chip = document.createElement("span");
      chip.className =
        "inline-flex items-center gap-1 pl-2.5 pr-1 py-1 rounded-full text-xs font-medium bg-brand-50 dark:bg-brand-950/40 text-brand-700 dark:text-brand-300 ring-1 ring-brand-100 dark:ring-brand-900/50";
      const label = document.createElement("span");
      label.textContent = "#" + name;
      chip.appendChild(label);
      const x = document.createElement("button");
      x.type = "button";
      x.title = "Remove tag";
      x.className =
        "w-4 h-4 rounded-full inline-flex items-center justify-center text-brand-400 hover:text-white hover:bg-red-500 transition";
      x.innerHTML =
        '<svg class="w-3 h-3" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" d="M6 6l12 12M18 6L6 18"/></svg>';
      x.addEventListener("click", () => removeTag(name));
      chip.appendChild(x);
      e.chips.appendChild(chip);
    });
    // mark suggestion chips already added
    document.querySelectorAll("#upload-suggestions [data-suggest]").forEach((b) => {
      b.classList.toggle("opacity-40", state.tags.includes(b.dataset.suggest));
    });

    // Disable the tag input once the cap is reached.
    const atMax = state.tags.length >= maxTags();
    const inp = $("upload-tag-input");
    const addBtn = $("upload-tag-add");
    if (inp) {
      inp.disabled = atMax;
      inp.placeholder = atMax ? "Max " + maxTags() + " tags" : "Type or pick a tag…";
    }
    if (addBtn) addBtn.disabled = atMax;
    if (atMax) hideTagMenu();
  }

  // --- Tag chooser dropdown (existing tags + create new) ------------------ //
  function tagNames() {
    const el = $("upload-tag-names");
    if (!el) return [];
    try {
      return JSON.parse(el.textContent) || [];
    } catch (e) {
      return [];
    }
  }

  function renderTagMenu() {
    const menu = $("upload-tag-menu");
    const inp = $("upload-tag-input");
    if (!menu || !inp) return;
    if (state.tags.length >= maxTags()) {
      menu.classList.add("hidden");
      return;
    }
    const q = inp.value.trim().toLowerCase();
    const available = tagNames().filter(
      (n) => !state.tags.includes(n) && (!q || n.toLowerCase().includes(q))
    );
    menu.innerHTML = "";

    available.slice(0, 40).forEach((n) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className =
        "w-full text-left px-3 py-1.5 rounded-lg text-sm text-neutral-700 dark:text-neutral-300 transition hover:bg-brand-50 dark:hover:bg-brand-950/40 hover:ring-1 hover:ring-brand-400";
      b.textContent = "#" + n;
      b.addEventListener("mousedown", (ev) => {
        ev.preventDefault();
        addTag(n);
        inp.value = "";
      });
      menu.appendChild(b);
    });

    const typed = inp.value.trim();
    const lc = typed.toLowerCase();
    const exists = tagNames().some((n) => n.toLowerCase() === lc) || state.tags.includes(lc);
    if (typed && !exists) {
      const c = document.createElement("button");
      c.type = "button";
      c.className =
        "w-full text-left px-3 py-1.5 rounded-lg text-sm text-brand-600 dark:text-brand-400 transition hover:bg-brand-50 dark:hover:bg-brand-950/40 hover:ring-1 hover:ring-brand-400";
      c.textContent = 'Create "' + typed + '"';
      c.addEventListener("mousedown", (ev) => {
        ev.preventDefault();
        addTag(typed);
        inp.value = "";
      });
      menu.appendChild(c);
    }

    menu.classList.toggle("hidden", menu.children.length === 0);
  }

  function hideTagMenu() {
    const menu = $("upload-tag-menu");
    if (menu) menu.classList.add("hidden");
  }

  function refreshTagMenu() {
    const menu = $("upload-tag-menu");
    if (menu && !menu.classList.contains("hidden")) renderTagMenu();
  }

  // --- AI suggestions ----------------------------------------------------- //
  function scheduleAnalyze() {
    clearTimeout(state.analyzeTimer);
    if (!state.files.length) {
      const e = els();
      if (e.suggestions) e.suggestions.innerHTML = "";
      if (e.suggestStatus) e.suggestStatus.textContent = "";
      return;
    }
    state.analyzeTimer = setTimeout(analyze, 600);
  }

  function analyze() {
    const e = els();
    if (!e.suggestions || !state.files.length) return;
    e.suggestStatus.textContent = "analyzing…";

    const fd = new FormData();
    state.files.slice(0, 8).forEach((f) => fd.append("files", f));

    fetch("/upload/analyze", {
      method: "POST",
      headers: { "X-CSRF-Token": csrf() },
      body: fd,
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((data) => {
        if (!data.available) {
          e.suggestStatus.textContent = "install Tesseract for AI suggestions";
          return;
        }
        renderSuggestions(data.suggested_tags || [], data.suggested_category);
      })
      .catch(() => {
        e.suggestStatus.textContent = "";
      });
  }

  function renderSuggestions(tags, category) {
    const e = els();
    e.suggestions.innerHTML = "";
    const fresh = tags.filter((t) => !state.tags.includes(t));
    e.suggestStatus.textContent = fresh.length ? "tap to add" : "no new suggestions";

    if (category && e.category && !e.category.value.trim()) {
      const c = document.createElement("button");
      c.type = "button";
      c.className =
        "inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 ring-1 ring-amber-200/70 dark:ring-amber-900/50 hover:ring-amber-400 transition";
      c.textContent = "Category: " + category;
      c.addEventListener("click", () => {
        window.dispatchEvent(new CustomEvent("snap-set-category", { detail: category }));
        c.remove();
      });
      e.suggestions.appendChild(c);
    }

    tags.forEach((name) => {
      const b = document.createElement("button");
      b.type = "button";
      b.dataset.suggest = name;
      b.className =
        "inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-300 ring-1 ring-transparent hover:bg-brand-50 hover:text-brand-700 hover:ring-brand-300 dark:hover:bg-brand-950/40 transition";
      b.textContent = "+ " + name;
      if (state.tags.includes(name)) b.classList.add("opacity-40");
      b.addEventListener("click", () => addTag(name));
      e.suggestions.appendChild(b);
    });
  }

  // --- Reset on successful upload ----------------------------------------- //
  function reset() {
    state.files = [];
    state.tags = [];
    state.urls.forEach((u) => URL.revokeObjectURL(u));
    state.urls = [];
    syncInput();
    syncTagsHidden();
    renderPreviews();
    renderChips();
    const e = els();
    if (e.suggestions) e.suggestions.innerHTML = "";
    if (e.suggestStatus) e.suggestStatus.textContent = "";
    window.dispatchEvent(new CustomEvent("snap-reset-upload"));
    if (e.bar) e.bar.style.width = "0%";
  }

  // --- Wiring (event delegation so it survives htmx swaps) ---------------- //
  document.addEventListener("change", (ev) => {
    if (ev.target && ev.target.id === "file-input") addFiles(ev.target.files);
  });

  document.addEventListener("keydown", (ev) => {
    if (ev.target && ev.target.id === "upload-tag-input") {
      if (ev.key === "Enter" || ev.key === ",") {
        ev.preventDefault();
        addTag(ev.target.value);
        ev.target.value = "";
      }
    }
  });

  document.addEventListener("click", (ev) => {
    const add = ev.target.closest && ev.target.closest("#upload-tag-add");
    if (add) {
      const inp = $("upload-tag-input");
      if (inp) { addTag(inp.value); inp.value = ""; }
    }
  });

  // Tag chooser open / filter / close.
  document.addEventListener("focusin", (ev) => {
    if (ev.target && ev.target.id === "upload-tag-input") renderTagMenu();
  });
  document.addEventListener("input", (ev) => {
    if (ev.target && ev.target.id === "upload-tag-input") renderTagMenu();
  });
  document.addEventListener("focusout", (ev) => {
    if (ev.target && ev.target.id === "upload-tag-input") setTimeout(hideTagMenu, 120);
  });
  document.addEventListener("click", (ev) => {
    if (ev.target.closest("#upload-tag-menu") || ev.target.id === "upload-tag-input") return;
    hideTagMenu();
  });

  // Dropzone drag styling + drop.
  document.addEventListener("dragover", (ev) => {
    const dz = ev.target.closest && ev.target.closest("#dropzone");
    if (dz) { ev.preventDefault(); dz.classList.add("border-brand-400"); }
  });
  document.addEventListener("dragleave", (ev) => {
    const dz = ev.target.closest && ev.target.closest("#dropzone");
    if (dz) dz.classList.remove("border-brand-400");
  });
  document.addEventListener("drop", (ev) => {
    const dz = ev.target.closest && ev.target.closest("#dropzone");
    if (!dz) return;
    ev.preventDefault();
    dz.classList.remove("border-brand-400");
    if (ev.dataTransfer && ev.dataTransfer.files.length) addFiles(ev.dataTransfer.files);
  });

  // Clipboard paste of images.
  window.addEventListener("paste", (ev) => {
    const items = (ev.clipboardData && ev.clipboardData.files) || [];
    const images = Array.from(items).filter((f) => f.type.startsWith("image/"));
    if (!images.length) return;
    addFiles(images);
    window.dispatchEvent(new CustomEvent("paste-image"));
    if (window.toast) window.toast(images.length + " image pasted");
  });

  // Upload progress + reset.
  document.body.addEventListener("htmx:xhr:progress", (ev) => {
    if (ev.target && ev.target.id !== "upload-form") return;
    const bar = $("upload-bar");
    if (bar && ev.detail.lengthComputable) {
      bar.style.width = Math.round((ev.detail.loaded / ev.detail.total) * 100) + "%";
    }
  });
  document.body.addEventListener("htmx:afterRequest", (ev) => {
    if (ev.target && ev.target.id === "upload-form" && ev.detail.successful) reset();
  });
})();
