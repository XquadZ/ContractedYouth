/* 로그인·기록·모델 선택 보조 */
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

  const header = document.querySelector("header.top");
  if (!header) return;
  const box = document.createElement("div");
  box.style.cssText = "display:flex;gap:8px;align-items:center;margin-left:auto;flex-wrap:wrap;";
  box.innerHTML = `
    <span style="font-size:.85rem">${me.user.login_id}</span>
    <select id="modelSelect" title="분석 모델" style="padding:4px 8px;border-radius:6px;border:1px solid #cfd6e4;">
      <option value="exaone">exaone 정밀</option>
      <option value="ax">ax 빠른</option>
      <option value="gpt">gpt 시연</option>
    </select>
    <button type="button" id="btnReviews" style="padding:6px 10px;border-radius:6px;border:0;background:#e8eef8;cursor:pointer;">내 검토 기록</button>
    ${me.user.role === "admin" ? '<a href="/admin" style="color:inherit;font-size:.85rem;">관리자</a>' : ""}
    <button type="button" id="btnLogout" style="padding:6px 10px;border-radius:6px;border:0;background:#1f4b99;color:#fff;cursor:pointer;">로그아웃</button>
  `;
  header.appendChild(box);
  const health = await fetch("/api/health").then((r) => r.json()).catch(() => ({}));
  const sel = document.getElementById("modelSelect");
  if (health.analyze_model) sel.value = health.analyze_model;
  sel.onchange = async () => {
    await fetch("/api/settings/model", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ analyze_model: sel.value }),
    });
    if (window.toast) toast("분석 모델: " + sel.value + (sel.value !== "gpt" ? " (전환 중일 수 있어요)" : ""));
  };
  document.getElementById("btnLogout").onclick = async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    location.href = "/";
  };
  document.getElementById("btnReviews").onclick = async () => {
    const r = await fetch("/api/reviews");
    const j = await r.json();
    const list = (j.reviews || [])
      .map(
        (x) =>
          `#${x.id} ${x.domain || "-"} ${x.grade || ""} ${x.score ?? ""}점 ${x.created_at} [${x.model}]`
      )
      .join("\n");
    const pick = prompt("열 검토 id를 입력하세요.\n\n" + (list || "(기록 없음)"));
    if (!pick) return;
    const id = parseInt(pick, 10);
    if (!id) return;
    const detail = await fetch("/api/reviews/" + id).then((x) => x.json());
    if (detail.error) {
      alert(detail.error);
      return;
    }
    if (detail.original_message) alert(detail.original_message);
    window.__lastReviewId = id;
    if (detail.report && typeof axSession !== "undefined") {
      axSession = {
        status: "done",
        isUser: true,
        title: "기록 #" + id,
        report: detail.report,
        risks: typeof cardsToRisks === "function" ? cardsToRisks(detail.report.cards || []) : [],
        domain: detail.review.domain,
        reviewId: id,
        text: detail.review.masked_text || "",
      };
      if (typeof render === "function") {
        tab = "overview";
        render();
      }
      if (detail.ttl_notice && window.toast)
        toast(detail.ttl_notice + (detail.ttl_seconds_left != null ? ` (남은 ${detail.ttl_seconds_left}초)` : ""));
      const boxMsg = document.getElementById("chatMessages");
      if (boxMsg && detail.chats) {
        boxMsg.innerHTML = "";
        detail.chats.forEach((c) => {
          const div = document.createElement("div");
          div.className = "chat-bubble " + (c.role === "user" ? "user" : "bot");
          div.textContent = c.content;
          boxMsg.appendChild(div);
        });
      }
    }
  };
})();
