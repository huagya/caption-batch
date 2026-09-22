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
  const thinkingLevelEl = $("#thinking-level");
  const mediaResolutionEl = $("#media-resolution");
  const mediaResolutionWrap = $("#media-resolution-wrap");
  const thinkingTokenTip = $("#thinking-token-tip");
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
  const rateLimitRpmEl = $("#rate-limit-rpm");
  const previewCountEl = $("#preview-count");
  const progressBarEl = $("#progress-bar");
  const statusMetaEl = $("#status-meta");
  const statusCurrentEl = $("#status-current");
  const errorListEl = $("#error-list");
  const previewResultsEl = $("#preview-results");
  const previewSummaryEl = $("#preview-summary");
  const btnPreviewEl = $("#btn-preview");
  const btnLoadSnapshotEl = $("#btn-load-snapshot");

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
      thinking_level: (thinkingLevelEl.value || "").trim() || null,
      media_resolution: (mediaResolutionEl.value || "").trim() || null,
      max_image_side: parseInt(maxSideEl.value, 10) || 768,
      image_prep_enabled: !!imagePrepEl.checked,
      image_format: imageFormatEl.value || "webp",
      image_quality: parseInt(imageQualityEl.value, 10) || 95,
      prompt: promptEl.value,
      rate_limit_rpm: parseOptionalInt(rateLimitRpmEl) || 0,
      few_shot: collectFewShot(),
    };
    if (limitRaw) body.limit = parseInt(limitRaw, 10);
    return body;
  }

  function collectFewShot() {
    const rows = document.querySelectorAll("#few-shot-list .few-shot-row");
    const out = [];
    rows.forEach((row) => {
      const image = (row.querySelector(".fs-image")?.value || "").trim();
      const caption = (row.querySelector(".fs-caption")?.value || "").trim();
      if (image && caption) out.push({ image, caption });
    });
    return out.slice(0, 3);
  }

  function applyFewShot(list) {
    const rows = document.querySelectorAll("#few-shot-list .few-shot-row");
    const items = Array.isArray(list) ? list : [];
    rows.forEach((row, i) => {
      const img = row.querySelector(".fs-image");
      const cap = row.querySelector(".fs-caption");
      if (!img || !cap) return;
      if (items[i]) {
        img.value = items[i].image || "";
        cap.value = items[i].caption || "";
      } else {
        img.value = "";
        cap.value = "";
      }
    });
  }

  function collectSettings() {
    const body = jobBody();
    if (!limitEl.value.trim()) body.limit = null;
    if (previewCountEl) {
      let n = parseInt(previewCountEl.value, 10);
      if (!Number.isFinite(n)) n = 3;
      body.preview_count = Math.max(1, Math.min(5, n));
    }
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
    if (s.thinking_level != null && s.thinking_level !== "") thinkingLevelEl.value = s.thinking_level;
    else if (s.thinking_level === null || s.thinking_level === "") thinkingLevelEl.value = "";
    if (s.media_resolution != null && s.media_resolution !== "") mediaResolutionEl.value = s.media_resolution;
    else if (s.media_resolution === null || s.media_resolution === "") mediaResolutionEl.value = "";
    if (s.max_image_side != null) maxSideEl.value = s.max_image_side;
    if (s.image_prep_enabled != null) imagePrepEl.checked = !!s.image_prep_enabled;
    if (s.image_format) imageFormatEl.value = s.image_format;
    if (s.image_quality != null) imageQualityEl.value = s.image_quality;
    if (s.prompt != null) promptEl.value = s.prompt;
    if (s.rate_limit_rpm != null) setOptionalNumber(rateLimitRpmEl, s.rate_limit_rpm || "");
    if (s.preview_count != null && previewCountEl) previewCountEl.value = s.preview_count;
    if (s.few_shot != null) applyFewShot(s.few_shot);
  }

  function applyHelp(help) {
    if (!help) return;
    document.querySelectorAll("[data-help-key]").forEach((el) => {
      const key = el.getAttribute("data-help-key");
      if (help[key]) el.textContent = help[key];
    });
    if (help.image_prep_enabled) {
      const block = $("#help-image-prep");
      if (block) block.innerHTML = "<strong>契約:</strong> " + help.image_prep_enabled;
    }
  }

  function formatEta(sec) {
    if (sec == null || !Number.isFinite(sec)) return "—";
    const s = Math.max(0, Math.round(sec));
    if (s < 60) return s + "秒";
    const m = Math.floor(s / 60);
    const r = s % 60;
    if (m < 60) return m + "分" + r + "秒";
    const h = Math.floor(m / 60);
    return h + "時間" + (m % 60) + "分";
  }

  function renderPreviewResults(results) {
    if (!previewResultsEl) return;
    if (!results || !results.length) {
      previewResultsEl.innerHTML = "<span class=\"muted\">結果なし</span>";
      return;
    }
    previewResultsEl.innerHTML = results.map((r) => {
      const cls = r.error ? "preview-item error" : (r.skipped ? "preview-item skipped" : "preview-item");
      const flag = r.skipped ? "（スキップ・既存）" : (r.error ? "（エラー）" : "");
      const body = r.error
        ? ("<p class=\"pv-caption\">" + escapeHtml(r.error) + "</p>")
        : ("<p class=\"pv-caption\">" + escapeHtml(r.caption || "(空)") + "</p>");
      return "<div class=\"" + cls + "\"><div class=\"pv-path\">" + escapeHtml(r.image || "") + " " + flag + "</div>" + body + "</div>";
    }).join("");
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, String.fromCharCode(38) + "amp;")
      .replace(/</g, String.fromCharCode(38) + "lt;")
      .replace(/>/g, String.fromCharCode(38) + "gt;")
      .replace(/"/g, String.fromCharCode(38) + "quot;");
  }

  function renderStatus(st) {
    if (!st) return;
    const running = !!st.running;
    const kind = st.kind || "batch";
    jobPill.textContent = running ? (kind === "preview" ? "preview" : "running") : (st.error ? "error" : (st.stopped ? "stopped" : "idle"));
    jobPill.className = "status-pill " + (running ? "running" : (st.error ? "fail" : "ok"));
    const ok = st.ok || 0, fail = st.fail || 0, skip = st.skip || 0, todo = st.todo || 0, total = st.total || 0;
    const done = ok + fail;
    const denom = todo > 0 ? todo : (total > 0 ? total : 0);
    const pct = denom > 0 ? Math.min(100, Math.round((done / denom) * 100)) : (running ? 0 : 100);
    if (progressBarEl) progressBarEl.style.width = pct + "%";
    summaryEl.textContent = `ok=${ok} fail=${fail} skip=${skip} todo=${todo} total=${total}`;
    const rate = st.rate_per_sec;
    const rateTxt = (rate != null && Number.isFinite(rate)) ? (rate.toFixed(2) + " 枚/秒") : "—";
    const etaTxt = formatEta(st.eta_sec);
    if (statusMetaEl) statusMetaEl.textContent = `進捗 ${done}/${denom || "—"} (${pct}%) · ETA ${etaTxt} · 速度 ${rateTxt}` + (st.error ? (" · エラー: " + st.error) : "");
    if (statusCurrentEl) statusCurrentEl.textContent = st.current_image ? ("処理中: " + st.current_image) : (running ? "処理中…" : "");
    if (errorListEl) {
      const errs = st.recent_errors || [];
      errorListEl.innerHTML = !errs.length ? "<li class=\"muted\">なし</li>" : errs.slice(-20).reverse().map((e) => {
        const msg = (e.error || "").slice(0, 120);
        return "<li><span class=\"err-path\">" + escapeHtml(e.image || "") + "</span> — " + escapeHtml(msg) + "</li>";
      }).join("");
    }
    if (statusDetail) statusDetail.textContent = JSON.stringify(st, null, 2);
    if (kind === "preview" && Array.isArray(st.results)) {
      renderPreviewResults(st.results);
      if (previewSummaryEl) previewSummaryEl.textContent = running ? "プレビュー実行中…" : `完了 ok=${ok} fail=${fail} skip=${skip}`;
    }
  }

  let wasRunning = false;
  let lastKind = null;

  async function refreshStatus() {
    try {
      const st = await api("/job/status");
      const nowRunning = !!st.running;
      if (wasRunning && !nowRunning && (st.kind === "preview" || lastKind === "preview")) {
        if (st.error) toast("プレビュー失敗: " + st.error, true);
        else toast("プレビュー完了");
      }
      wasRunning = nowRunning;
      lastKind = st.kind || lastKind;
      renderStatus(st);
      if (!st.running && pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    } catch (e) { /* ignore */ }
  }

  function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(refreshStatus, 1000);
  }

  function updateMediaResolutionVisibility() {
    const isGemini = providerEl.value === "gemini";
    if (mediaResolutionWrap) mediaResolutionWrap.style.opacity = isGemini ? "1" : "0.45";
    if (mediaResolutionEl) mediaResolutionEl.disabled = !isGemini;
  }

  function updateThinkingTokenTip() {
    if (!thinkingTokenTip) return;
    const level = (thinkingLevelEl.value || "").trim();
    const tokens = parseOptionalInt(maxTokensEl);
    const highThink = level === "medium" || level === "high";
    const lowTokens = tokens !== null && tokens < 2048;
    thinkingTokenTip.hidden = !(highThink && lowTokens);
  }

  providerEl.addEventListener("change", () => { updateMediaResolutionVisibility(); });
  thinkingLevelEl.addEventListener("change", updateThinkingTokenTip);
  maxTokensEl.addEventListener("input", updateThinkingTokenTip);
  maxTokensEl.addEventListener("change", updateThinkingTokenTip);

  $("#btn-save-keys").addEventListener("click", async () => {
    try {
      const body = {};
      if (geminiKeyEl.value.trim()) body.gemini_api_key = geminiKeyEl.value.trim();
      if (openrouterKeyEl.value.trim()) body.openrouter_api_key = openrouterKeyEl.value.trim();
      const r = await api("/save-keys", { method: "POST", body: JSON.stringify(body) });
      toast("Saved: " + (r.updated || []).join(", "));
      geminiKeyEl.value = "";
      openrouterKeyEl.value = "";
    } catch (e) { toast(String(e.message || e), true); }
  });

  $("#btn-list-models").addEventListener("click", async () => {
    try {
      const r = await api("/list-models", { method: "POST", body: JSON.stringify({ provider: providerEl.value, vision_only: true, as_json: false }) });
      modelsOut.hidden = false;
      modelsOut.textContent = r.text || "(empty)";
      toast(`models: ${r.count}`);
    } catch (e) { toast(String(e.message || e), true); }
  });

  $("#btn-start").addEventListener("click", async () => {
    try {
      const r = await api("/job/start", { method: "POST", body: JSON.stringify(jobBody()) });
      toast("ジョブを開始しました");
      lastKind = "batch"; wasRunning = true;
      renderStatus(r.status || r); startPolling();
    } catch (e) { toast(String(e.message || e), true); }
  });

  if (btnPreviewEl) btnPreviewEl.addEventListener("click", async () => {
    try {
      const body = jobBody();
      let n = parseInt(previewCountEl && previewCountEl.value, 10);
      if (!Number.isFinite(n)) n = 3;
      n = Math.max(1, Math.min(5, n));
      body.preview_count = n; body.preview_write = true;
      if (btnPreviewEl) btnPreviewEl.textContent = "プレビュー (" + n + "枚)";
      const r = await api("/job/preview", { method: "POST", body: JSON.stringify(body) });
      toast("プレビュー開始 (" + n + "枚)");
      lastKind = "preview"; wasRunning = true;
      renderStatus(r.status || r); startPolling();
    } catch (e) { toast(String(e.message || e), true); }
  });

  if (previewCountEl) {
    const syncPreviewLabel = () => {
      let n = parseInt(previewCountEl.value, 10);
      if (!Number.isFinite(n)) n = 3;
      n = Math.max(1, Math.min(5, n));
      if (btnPreviewEl) btnPreviewEl.textContent = "プレビュー (" + n + "枚)";
    };
    previewCountEl.addEventListener("change", syncPreviewLabel);
    previewCountEl.addEventListener("input", syncPreviewLabel);
    syncPreviewLabel();
  }

  if (btnLoadSnapshotEl) btnLoadSnapshotEl.addEventListener("click", async () => {
    try {
      const folder = folderEl.value.trim();
      if (!folder) { toast("先に画像フォルダのパスを入力してください", true); return; }
      const r = await api("/job/snapshot?folder=" + encodeURIComponent(folder));
      if (!r.exists || !r.snapshot) { toast("このフォルダに前回のジョブ設定がありません", true); return; }
      applySettings((r.snapshot.params) || {}, defaultsCache);
      overwriteEl.checked = false;
      toast("前回の設定を読み込みました（上書きOFF・既存.txtはスキップ）");
    } catch (e) { toast(String(e.message || e), true); }
  });

  $("#btn-stop").addEventListener("click", async () => {
    try {
      const r = await api("/job/stop", { method: "POST", body: "{}" });
      toast(r.message || "stop requested");
      renderStatus(r.status || (await api("/job/status")));
    } catch (e) { toast(String(e.message || e), true); }
  });

  $("#btn-diagnostics").addEventListener("click", async () => {
    try {
      const r = await api("/diagnostics/collect", { method: "POST", body: "{}" });
      toast("zip: " + (r.zip_path || "?"));
    } catch (e) { toast(String(e.message || e), true); }
  });

  $("#btn-refresh-logs").addEventListener("click", async () => {
    try {
      const r = await api("/debug/logs?limit=100");
      debugLogs.textContent = (r.logs || []).map((x) => `${x.ts || ""} [${x.level || ""}] ${x.message || ""}`).join("\n");
    } catch (e) { toast(String(e.message || e), true); }
  });

  $("#btn-save-settings").addEventListener("click", async () => {
    try {
      const settings = collectSettings();
      await api("/ui-settings", { method: "POST", body: JSON.stringify({ settings }) });
      try { localStorage.setItem("caption-batch-ui-settings", JSON.stringify(settings)); } catch (_) {}
      toast("設定を保存しました");
    } catch (e) { toast(String(e.message || e), true); }
  });

  $("#btn-load-settings").addEventListener("click", async () => {
    try {
      const r = await api("/ui-settings");
      applySettings(r.settings || {}, defaultsCache);
      toast(r.exists ? "設定を読み込みました" : "保存なし — 既定値を適用");
    } catch (e) { toast(String(e.message || e), true); }
  });

  $("#btn-llm-recommend").addEventListener("click", () => {
    temperatureEl.value = "0.2"; topPEl.value = "0.95";
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
      if (d.thinking_level) thinkingLevelEl.value = d.thinking_level; else thinkingLevelEl.value = "";
      if (d.media_resolution) mediaResolutionEl.value = d.media_resolution; else mediaResolutionEl.value = "";
      if (d.max_image_side != null) maxSideEl.value = d.max_image_side;
      if (d.image_prep_enabled != null) imagePrepEl.checked = !!d.image_prep_enabled;
      if (d.image_format) imageFormatEl.value = d.image_format;
      if (d.image_quality != null) imageQualityEl.value = d.image_quality;
      if (d.workers != null) workersEl.value = d.workers;
      if (d.rate_limit_rpm != null && rateLimitRpmEl) setOptionalNumber(rateLimitRpmEl, d.rate_limit_rpm || "");
      if (d.preview_count != null && previewCountEl) previewCountEl.value = d.preview_count;
      if (d.few_shot) applyFewShot(d.few_shot);
      try {
        const saved = await api("/ui-settings");
        if (saved && saved.exists && saved.settings) applySettings(saved.settings, d);
      } catch (_) {}
      updateMediaResolutionVisibility();
      updateThinkingTokenTip();
    } catch (e) { promptEl.placeholder = "defaults load failed"; }
    updateMediaResolutionVisibility();
    updateThinkingTokenTip();
    refreshStatus();
  })();
})();
