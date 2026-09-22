/* Assemble app from plain text parts (0.6.0). */
(async () => {
  try {
    const texts = [];
    for (let i = 0; i < 10; i++) {
      const res = await fetch("/app.part" + i + ".js.txt", { cache: "no-store" });
      if (!res.ok) break;
      texts.push(await res.text());
    }
    if (!texts.length) throw new Error("no app parts");
    (0, eval)(texts.join(""));
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
