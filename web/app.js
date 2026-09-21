/* WebUI talks ONLY to /api — no business logic duplication. */
(() => {
  const $ = (sel) => document.querySelector(sel);
  const providerEl = $("#provider");
  const modelEl = $("#model");
  const folderEl = $("#folder");
  const workersEl = $("#workers");
  const limitEl = $("#limit");
  const temperatureEl = $("#temperature");
  const maxTokensEl = $("#max-tokens");
  const maxSideEl = $("#max-side");
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
      temperature: parseFloat(temperatureEl.value),
      max_output_tokens: parseInt(maxTokensEl.value, 10) || 1024,
      max_image_side: parseInt(maxSideEl.value, 10) || 1536,
      prompt: promptEl.value,
    };
    if (limitRaw) body.limit = parseInt(limitRaw, 10);
    return body;
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
      /* ignore poll errors */
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

  document.addEventListener("keydown", (ev) => {
    if (ev.key === "d" && !ev.ctrlKey && !ev.metaKey && document.activeElement === document.body) {
      debugPanel.hidden = !debugPanel.hidden;
    }
  });

  (async () => {
    try {
      const d = await api("/defaults");
      if (d.prompt) promptEl.value = d.prompt;
      if (d.temperature != null) temperatureEl.value = d.temperature;
      if (d.max_output_tokens != null) maxTokensEl.value = d.max_output_tokens;
      if (d.max_image_side != null) maxSideEl.value = d.max_image_side;
      if (d.workers != null) workersEl.value = d.workers;
    } catch (e) {
      promptEl.placeholder = "defaults load failed";
    }
    refreshStatus();
  })();
})();
