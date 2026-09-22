function escapeHtml(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "\u0026amp;").replace(/</g, "\u0026lt;").replace(/>/g, "\u0026gt;")
    .replace(/"/g, "\u0026quot;");
}
