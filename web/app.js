/* WebUI talks ONLY to /api — no business logic duplication. */
(() => {
  const $ = (sel) => document.querySelector(sel);
  const providerEl = $("#provider");
  const modelEl = $("#model");
  const folderEl = $("#folder");
  const workersEl = $("#workers");
  const limitEl = $("#limit");
  const temperatureEl = $("#temperature");
  const topPEl = $("#top-p");
  const maxTokensEl = $("#max-tokens");
  const seedEl = $("#seed");
  const maxSideEl = $("#max-side");
  const imagePrepEl = $("#image-prep");
  const imageFormatEl = $("#image-format");
  const imageQualityEl = $("#image-quality");
  const overwriteEl = $("#overwrite");
  const dryRunEl = $("#dry-run");
  const recursiveEl = $("#recursive");
  const fromIndexEl = $("#from-index");
  const promptEl = $("#prompt");
  const geminiKeyEl = $("#gemini-key");
  const openrouterKeyEl = $("#openrouter-key");
  const modelsOut = $("#models-out");
  const summaryEl = $("#summary");
  const statusDetail = $("#status-detail");
  const jobPill = $("#job-pill");
  const debugPanel = $("#debug-panel");
  const debugLogs = $("#debug-logs");
  const toastEl = $("#toast");

  let toastTimer = null;
  let pollTimer = null;
  let defaultsCache = null;

  function toast(msg, isError = false) {
    toastEl.textContent = msg;
    toastEl.hidden = false;
    toastEl.classList.toggle("error", isError);
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toastEl.hidden = true; }, 3200);
  }

  async function api(path, options = {}) {
    const res = await fetch(`/api${path}`, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    let parsed = null;
    const text = await res.text();
    try { parsed = text ? JSON.parse(text) : null; } catch { parsed = text; }
    if (!res.ok) {
      const detail = parsed && parsed.detail ? parsed.detail : res.statusText;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return parsed;
  }

  function parseOptionalFloat(el) {
    const raw = (el.value || "").trim();
    if (!raw) return null;
    const n = parseFloat(raw);
    return Number.isFinite(n) ? n : null;
  }

  function parseOptionalInt(el) {
    const raw = (el.value || "").trim();
    if (!raw) return null;
    const n = parseInt(raw, 10);
    return Number.isFinite(n) ? n : null;
  }

  function jobBody() {
    const limitRaw = limitEl.value.trim();
    const body = {
      provider: providerEl.value,
      model: modelEl.value.trim(),
      folder: folderEl.value.trim(),
      workers: parseInt(workersEl.value, 10) || 4,
      overwrite: overwriteEl.checked,
      dry_run: dryRunEl.checked,
      recursive: recursiveEl.checked,
      from_index: fromIndexEl.checked,
      temperature: parseOptionalFloat(temperatureEl),
      top_p: parseOptionalFloat(topPEl),
      max_output_tokens: parseOptionalInt(maxTokensEl),
      seed: parseOptionalInt(seedEl),
      max_image_side: parseInt(maxSideEl.value, 10) || 768,
      image_prep_enabled: !!imagePrepEl.checked,
      image_format: imageFormatEl.value || "webp",
      image_quality: parseInt(imageQualityEl.value, 10) || 95,
      prompt: promptEl.value,
    };
    if (limitRaw) body.limit = parseInt(limitRaw, 10);
    return body;
  }

  function collectSettings() {
    const body = jobBody();
    if (!limitEl.value.trim()) body.limit = null;
    return body;
  }

  function setOptionalNumber(el, value) {
    if (value === null || value === undefined || value === "") {
      el.value = "";
    } else {
      el.value = String(value);
    }
  }

  function applySettings(s, dflt) {
    if (!s) return;
    if (s.provider) providerEl.value = s.provider;
    if (s.model != null) modelEl.value = s.model;
    if (s.folder != null) folderEl.value = s.folder;
    if (s.workers != null) workersEl.value = s.workers;
    setOptionalNumber(limitEl, s.limit);
    if (s.overwrite != null) overwriteEl.checked = !!s.overwrite;
    if (s.dry_run != null) dryRunEl.checked = !!s.dry_run;
    if (s.recursive != null) recursiveEl.checked = !!s.recursive;
    if (s.from_index != null) fromIndexEl.checked = !!s.from_index;
    setOptionalNumber(temperatureEl, s.temperature);
    setOptionalNumber(topPEl, s.top_p);
    setOptionalNumber(maxTokensEl, s.max_output_tokens != null ? s.max_output_tokens : (dflt && dflt.max_output_tokens));
    setOptionalNumber(seedEl, s.seed);
    if (s.max_image_side != null) maxSideEl.value = s.max_image_side;
    if (s.image_prep_enabled != null) imagePrepEl.checked = !!s.image_prep_enabled;
    if (s.image_format) imageFormatEl.value = s.image_format;
    if (s.image_quality != null) imageQualityEl.value = s.image_quality;
    if (s.prompt != null) promptEl.value = s.prompt;
  }

  function applyHelp(help) {
    if (!help) return;
    document.querySelectorAll("[data-help-key]").forEach((el) => {
      const key = el.getAttribute("data-help-key");
      if (help[key]) el.textContent = help[key];
    });
    if (help.image_prep_enabled) {
      const block = $("#help-image-prep");
      if (block) {
        block.innerHTML = "<strong>契約:</strong> " + help.image_prep_enabled;
      }
    }
  }

  function renderStatus(st) {
    if (!st) return;
    const running = !!st.running;
    jobPill.textContent = running ? "running" : (st.error ? "error" : (st.stopped ? "stopped" : "idle"));
    jobPill.className = "status-pill " + (running ? "running" : (st.error ? "fail" : "ok"));
    summaryEl.textContent =
      `ok=${st.ok || 0} fail=${st.fail || 0} skip=${st.skip || 0} todo=${st.todo || 0} total=${st.total || 0}`;
    statusDetail.textContent = JSON.stringify(st, null, 2);
  }

  async function refreshStatus() {
    try {
      const st = await api("/job/status");
      renderStatus(st);
      if (!st.running && pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
    } catch (e) {
    }
  }

  function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(refreshStatus, 1000);
  }

  $("#btn-save-keys").addEventListener("click", async () => {
    try {
      const body = {};
      if (geminiKeyEl.value.trim()) body.gemini_api_key = geminiKeyEl.value.trim();
      if (openrouterKeyEl.value.trim()) body.openrouter_api_key = openrouterKeyEl.value.trim();
      const r = await api("/save-keys", { method: "POST", body: JSON.stringify(body) });
      toast("Saved: " + (r.updated || []).join(", "));
      geminiKeyEl.value = "";
      openrouterKeyEl.value = "";
    } catch (e) {
      toast(String(e.message || e), true);
    }
  });

  $("#btn-list-models").addEventListener("click", async () => {
    try {
      const r = await api("/list-models", {
        method: "POST",
        body: JSON.stringify({ provider: providerEl.value, vision_only: true, as_json: false }),
      });
      modelsOut.hidden = false;
      modelsOut.textContent = r.text || "(empty)";
      toast(`models: ${r.count}`);
    } catch (e) {
      toast(String(e.message || e), true);
    }
  });

  $("#btn-start").addEventListener("click", async () => {
    try {
      const r = await api("/job/start", { method: "POST", body: JSON.stringify(jobBody()) });
      toast("Job started");
      renderStatus(r.status || r);
      startPolling();
    } catch (e) {
      toast(String(e.message || e), true);
    }
  });

  $("#btn-stop").addEventListener("click", async () => {
    try {
      const r = await api("/job/stop", { method: "POST", body: "{}" });
      toast(r.message || "stop requested");
      renderStatus(r.status || (await api("/job/status")));
    } catch (e) {
      toast(String(e.message || e), true);
    }
  });

  $("#btn-diagnostics").addEventListener("click", async () => {
    try {
      const r = await api("/diagnostics/collect", { method: "POST", body: "{}" });
      toast("zip: " + (r.zip_path || "?"));
    } catch (e) {
      toast(String(e.message || e), true);
    }
  });

  $("#btn-refresh-logs").addEventListener("click", async () => {
    try {
      const r = await api("/debug/logs?limit=100");
      debugLogs.textContent = (r.logs || [])
        .map((x) => `${x.ts || ""} [${x.level || ""}] ${x.message || ""}`)
        .join("\n");
    } catch (e) {
      toast(String(e.message || e), true);
    }
  });

  $("#btn-save-settings").addEventListener("click", async () => {
    try {
      const settings = collectSettings();
      const r = await api("/ui-settings", {
        method: "POST",
        body: JSON.stringify({ settings }),
      });
      try {
        localStorage.setItem("caption-batch-ui-settings", JSON.stringify(settings));
      } catch (_) { }
      toast("設定を保存しました");
    } catch (e) {
      toast(String(e.message || e), true);
    }
  });

  $("#btn-load-settings").addEventListener("click", async () => {
    try {
      const r = await api("/ui-settings");
      applySettings(r.settings || {}, defaultsCache);
      toast(r.exists ? "設定を読み込みました" : "保存なし — 既定値を適用");
    } catch (e) {
      toast(String(e.message || e), true);
    }
  });

  $("#btn-llm-recommend").addEventListener("click", () => {
    temperatureEl.value = "0.2";
    topPEl.value = "0.95";
    if (!maxTokensEl.value.trim()) maxTokensEl.value = "1024";
    toast("旧モデル向けの参考値を入れました（Gemini 3.x は空欄推奨）");
  });

  document.addEventListener("keydown", (ev) => {
    if (ev.key === "d" && !ev.ctrlKey && !ev.metaKey && document.activeElement === document.body) {
      debugPanel.hidden = !debugPanel.hidden;
    }
  });

  (async () => {
    try {
      const d = await api("/defaults");
      defaultsCache = d;
      applyHelp(d.help);
      if (d.notes && d.notes.gemini_3x) {
        const note = $("#note-gemini3");
        if (note) note.textContent = d.notes.gemini_3x;
      }
      if (d.prompt) promptEl.value = d.prompt;
      setOptionalNumber(temperatureEl, d.temperature);
      setOptionalNumber(topPEl, d.top_p);
      setOptionalNumber(maxTokensEl, d.max_output_tokens);
      setOptionalNumber(seedEl, d.seed);
      if (d.max_image_side != null) maxSideEl.value = d.max_image_side;
      if (d.image_prep_enabled != null) imagePrepEl.checked = !!d.image_prep_enabled;
      if (d.image_format) imageFormatEl.value = d.image_format;
      if (d.image_quality != null) imageQualityEl.value = d.image_quality;
      if (d.workers != null) workersEl.value = d.workers;

      try {
        const saved = await api("/ui-settings");
        if (saved && saved.exists && saved.settings) {
          applySettings(saved.settings, d);
        }
      } catch (_) { }
    } catch (e) {
      promptEl.placeholder = "defaults load failed";
    }
    refreshStatus();
  })();
})();
