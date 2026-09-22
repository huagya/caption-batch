/* Loader: fetches gzipped app bundle and evals it (0.6.0). */
(async () => {
  try {
    const b64 = (await (await fetch("/app.js.gz.b64", { cache: "no-store" })).text()).trim();
    const bin = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const ds = new DecompressionStream("gzip");
    const stream = new Blob([bin]).stream().pipeThrough(ds);
    const text = await new Response(stream).text();
    // eslint-disable-next-line no-eval
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
