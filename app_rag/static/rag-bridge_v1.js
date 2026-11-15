/* RAG bridge v=figma5 — 상태 표시만 (샘플 A.X 버튼 제거) */
(() => {
  if (!document.getElementById("analyze")) return;

  async function loadHealth() {
    try {
      const h = await (await fetch("/api/health")).json();
      let tip = document.getElementById("rag-health");
      if (!tip) {
        tip = document.createElement("div");
        tip.id = "rag-health";
        tip.style.cssText =
          "position:fixed;right:16px;bottom:16px;z-index:50;background:#172743;color:#fff;padding:10px 14px;border-radius:8px;font-size:11px;opacity:.92";
        document.body.appendChild(tip);
      }
      tip.textContent = h.ax
        ? `A.X 연결 · 근거 ${h.n_records}건`
        : `A.X 꺼짐 · 근거 ${h.n_records}건`;
    } catch (_) {}
  }

  loadHealth();
})();
