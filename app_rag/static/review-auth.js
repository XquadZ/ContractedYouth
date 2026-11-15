/* 로그인·기록 보조 (모델 선택 없음 — EXAONE 고정) */
(async function () {
  function safeNext(raw) {
    if (!raw || typeof raw !== "string") return "/";
    let path = raw;
    try {
      path = decodeURIComponent(raw);
    } catch (_) {}
    if (!path.startsWith("/") || path.startsWith("//") || /^https?:/i.test(path)) return "/";
    return path;
  }

  const q = new URLSearchParams(location.search);
  const isSampleMode = q.has("sample") || q.get("tour") === "1" || q.get("mode") === "sample";

  const me = await fetch("/api/auth/me")
    .then((r) => r.json())
    .catch(() => ({ user: null }));

  if (!me.user) {
    if (isSampleMode) return;
    const next = safeNext(location.pathname + location.search + location.hash);
    location.href = "/login?next=" + encodeURIComponent(next);
    return;
  }

  window.__cyUser = me.user;

  const header = document.querySelector("header.top");
  if (!header) return;
  const box = document.createElement("div");
  box.style.cssText = "display:flex;gap:8px;align-items:center;margin-left:auto;flex-wrap:wrap;";
  const isAdmin = me.user.role === "admin";
  box.innerHTML = `
    <span style="font-size:.85rem">${me.user.login_id}</span>
    <button type="button" id="btnReviews" style="padding:6px 10px;border-radius:6px;border:0;background:#e8eef8;cursor:pointer;">내 검토 기록</button>
    ${isAdmin ? '<a href="/admin" style="color:inherit;font-size:.85rem;">관리자</a>' : ""}
    <button type="button" id="btnLogout" style="padding:6px 10px;border-radius:6px;border:0;background:#1f4b99;color:#fff;cursor:pointer;">로그아웃</button>
  `;
  header.appendChild(box);
  document.getElementById("btnLogout").onclick = async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    location.href = "/";
  };
  document.getElementById("btnReviews").onclick = () => {
    const el = document.getElementById("reviewHistorySection");
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "nearest" });
      el.classList.add("history-flash");
      setTimeout(() => el.classList.remove("history-flash"), 1200);
    }
    if (typeof window.refreshReviewHistory === "function") window.refreshReviewHistory();
  };
  if (typeof window.refreshReviewHistory === "function") window.refreshReviewHistory();
})();
