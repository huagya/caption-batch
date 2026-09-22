/* caption-batch 0.6.0 WebUI loader — concatenates app.body.*.js.txt then runs */
(async () => {
  try {
    const parts = [];
    for (let i = 0; i < 8; i++) {
      const res = await fetch("/app.body." + i + ".js.txt", { cache: "no-store" });
      if (!res.ok) break;
      parts.push(await res.text());
    }
    if (!parts.length) throw new Error("missing app.body.*.js.txt");
    const code = "(() => {" + parts.join("") + "})();";
    (0, eval)(code);
  } catch (e) {
    console.error(e);
    const el = document.getElementById("toast");
    if (el) {
      el.hidden = false;
      el.textContent = "UIの読み込みに失敗しました。";
      el.classList.add("error");
    }
  }
})();
