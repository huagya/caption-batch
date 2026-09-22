/* Loader: concat gzip b64 parts then eval (0.6.0). */
(async () => {
  try {
    const parts = [];
    for (let i = 0; i < 20; i++) {
      const name = "/app.js.gz.b64.part" + String(i).padStart(2, "0");
      const res = await fetch(name, { cache: "no-store" });
      if (!res.ok) break;
      parts.push((await res.text()).trim());
    }
    if (!parts.length) throw new Error("no app.js.gz.b64 parts");
    const b64 = parts.join("");
    const bin = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const ds = new DecompressionStream("gzip");
    const stream = new Blob([bin]).stream().pipeThrough(ds);
    const text = await new Response(stream).text();
    (0, eval)(text);
  } catch (e) {
    console.error("app.js load failed", e);
    const el = document.getElementById("toast");
    if (el) {
      el.hidden = false;
      el.textContent = "UIスクリプトの読み込みに失敗しました。ブラウザを更新するか、update.bat を実行してください。";
      el.classList.add("error");
    }
  }
})();
