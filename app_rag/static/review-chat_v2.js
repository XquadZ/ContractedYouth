/* 채팅: 샘플 로컬 답변 + A.X 분석 세션 */
(() => {
  const histories = new Map();
  const log = document.getElementById("chatMessages");
  const input = document.getElementById("chatInput");
  let context = "";

  function axSession() {
    return typeof window.getAxSession === "function" ? window.getAxSession() : null;
  }
  function riskList() {
    return typeof window.getReviewRisks === "function" ? window.getReviewRisks() : data().risks;
  }

  const key = () => {
    const ax = axSession();
    if (ax) return "ax:" + ax.sampleId + ":" + ax.status;
    if (customFile) return "local:" + activeDocumentId;
    return data().id;
  };

  function welcome() {
    const ax = axSession();
    if (ax?.status === "loading") {
      return {
        role: "assistant",
        text: `「${ax.title}」를 A.X로 분석하고 있어요.\n\n같은 검토 화면 오른쪽 패널에 결과가 채워집니다. 잠시만 기다려 주세요.`,
      };
    }
    if (ax?.status === "error") {
      return { role: "assistant", text: `분석을 마치지 못했어요.\n\n${ax.error || ""}` };
    }
    if (ax?.status === "domain") {
      return {
        role: "assistant",
        text: `「${ax.title}」 종류를 확인해 주세요.\n\n상단에서 근로·임대차·차용 중 고르면 분석을 시작해요.`,
      };
    }
    if (ax?.status === "done") {
      const s = ax.report?.summary || {};
      const rs = ax.risks || [];
      return {
        role: "assistant",
        text: `「${ax.title}」 분석이 끝났어요.\n\n• 위반 ${s.n_violation || 0} · 위험 ${s.n_risk || 0}\n• 확인 필요 ${s.n_review || 0} · 문제 없음 ${s.n_ok || 0}\n• 검토 카드 ${rs.length}개\n\nAI 답변 · 법률 자문이 아니에요`,
        action: rs[0]?.id,
        label: "첫 위험 조항 보기 ↗",
      };
    }
    if (customFile) {
      return {
        role: "assistant",
        text: "새 계약서 워크스페이스가 만들어졌어요. 원본 PDF는 확인할 수 있으며 분석은 대기 중입니다.",
      };
    }
    const s = data(),
      missing = s.checks.filter((c) => !c[3]);
    return {
      role: "assistant",
      text: `「${s.name}」의 검토 내용을 확인하세요.\n\n• 미충족·추가 확인 항목 ${missing.length}개\n• 위험·참고 조항 ${s.risks.length}개\n\n궁금한 조항을 질문해보세요.`,
      action: "complete",
      label: "필수 조항 확인하기",
    };
  }

  function escHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  /** 챗봇 마크다운 일부: **굵게** → <strong> (XSS 방지 후 치환) */
  function formatChatText(text) {
    return escHtml(text).replace(/\*\*(.+?)\*\*/gs, "<strong>$1</strong>");
  }

  function draw() {
    log.replaceChildren();
    for (const m of histories.get(context) || []) {
      const row = document.createElement("div");
      row.className = "chat-message " + m.role;
      const name = document.createElement("span");
      name.className = "chat-author";
      name.textContent = m.role === "user" ? "나" : "AI 답변 · 법률 자문이 아니에요";
      const bubble = document.createElement("div");
      bubble.className = "chat-bubble";
      bubble.innerHTML = formatChatText(m.text);
      row.append(name, bubble);
      if (m.action) {
        const b = document.createElement("button");
        b.className = "chat-source";
        b.textContent = m.label || "관련 조항 보기 ↗";
        b.onclick = () => (m.action === "complete" ? openTab("complete") : focusDocumentRisk(m.action));
        bubble.append(document.createElement("br"), b);
      }
      log.append(row);
    }
    log.scrollTop = log.scrollHeight;
  }

  function sync() {
    const ax = axSession();
    const guide = document.getElementById("chatGuideNote");
    const busy = document.getElementById("chatBusyNote");
    if (guide) guide.hidden = !(ax && ax.status === "done" && ax.isUser);
    if (busy) busy.hidden = !(ax && (ax.status === "loading" || ax.status === "domain"));
    document.getElementById("chatContract").textContent = ax
      ? ax.title
      : customFile
        ? customFile.name
        : data().short;
    const next = key();
    if (next === context) return;
    context = next;
    input.value = "";
    if (!histories.has(context)) histories.set(context, [welcome()]);
    draw();
  }

  document.addEventListener("contract-load-chats", (e) => {
    const chats = e.detail?.chats || [];
    const rid = e.detail?.reviewId;
    const k = "ax:" + (rid || "hist") + ":done";
    histories.set(
      k,
      chats.length
        ? chats.map((c) => ({ role: c.role === "user" ? "user" : "assistant", text: c.content || "" }))
        : [welcome()]
    );
    context = "";
    sync();
  });

  function reply(question) {
    const ax = axSession();
    if (ax?.status === "loading") return welcome();
    if (ax?.status === "error") return welcome();
    if (ax?.status === "done") {
      const rs = riskList();
      const s = ax.report?.summary || {};
      if (/필수|빠진|누락|완결|빈칸|요약/.test(question)) {
        const missing = ax.report?.missing || [];
        return {
          role: "assistant",
          text: missing.length
            ? `누락·확인 후보 ${missing.length}개예요.\n\n${missing
                .slice(0, 8)
                .map((m) => `• ${m.label || m.std_item || m.id || "항목"}`)
                .join("\n")}`
            : `요약: 위반 ${s.n_violation || 0}, 위험 ${s.n_risk || 0}, 확인 필요 ${s.n_review || 0}. 표시된 누락 항목은 없어요.`,
          action: "complete",
          label: "필수 조항 탭 보기 ↗",
        };
      }
      if (/위험|주의|정리|검토/.test(question)) {
        return {
          role: "assistant",
          text: rs.length
            ? `A.X가 골라 둔 확인 포인트예요.\n\n${rs
                .slice(0, 8)
                .map((r) => `• [${r.clause}] ${r.title}`)
                .join("\n")}`
            : "위반·위험·확인 필요 카드가 없어요.",
          action: rs[0]?.id,
          label: "위험 조항 보기 ↗",
        };
      }
      const words = question.replace(/[?？.,]/g, " ").split(/\s+/).filter((w) => w.length > 1);
      const ranked = rs
        .map((r) => ({
          r,
          score: words.reduce(
            (n, w) => n + ([r.title, r.clause, r.quote, r.explain, r.question].join(" ").includes(w) ? 1 : 0),
            0
          ),
        }))
        .sort((a, b) => b.score - a.score);
      const match = ranked[0];
      if (match?.score) {
        const r = match.r;
        return {
          role: "assistant",
          text: `${r.title}\n\n원문: “${r.quote}”\n\n${r.explain}\n\n근거: ${(r.evidence || []).map((e) => e.title).join(", ") || "없음"}`,
          action: r.id,
        };
      }
      return {
        role: "assistant",
        text: ax.isUser
          ? "결과 카드에서 바로 찾지 못했어요.\n\n‘필수 조항 확인’ 또는 ‘위험 조항 검토’ 버튼으로 결과만 보여 드릴게요."
          : "이 질문은 A.X 결과 카드와 바로 연결되지 않았어요.\n\n‘위험 조항을 정리해줘’를 누르거나, 오른쪽 카드 제목의 단어로 물어보세요.",
      };
    }
    if (customFile) return welcome();
    const s = data();
    if (/필수|빠진|누락|완결|빈칸/.test(question)) {
      const missing = s.checks.filter((c) => !c[3]);
      return {
        role: "assistant",
        text: missing.length
          ? `추가 확인이 필요한 항목은 ${missing.length}개예요.\n\n${missing.map((c) => `• ${c[0]} (${c[1]}쪽)\n${c[2]}`).join("\n\n")}`
          : "필수 확인 목록에서 미충족 항목이 없어요.",
        action: "complete",
        label: "미충족 항목 보기 ↗",
      };
    }
    if (/위험|주의|요약|정리|검토/.test(question))
      return {
        role: "assistant",
        text: `이 계약서의 확인 포인트예요.\n\n${s.risks.map((r) => `• ${r.title} (${r.page}쪽)`).join("\n")}`,
        action: s.risks[0]?.id,
      };
    const words = question.replace(/[?？.,]/g, " ").split(/\s+/).filter((w) => w.length > 1);
    const ranked = s.risks
      .map((r) => ({
        r,
        score: words.reduce(
          (n, w) => n + ([r.title, r.clause, r.quote, r.explain, r.question].join(" ").includes(w) ? 1 : 0),
          0
        ),
      }))
      .sort((a, b) => b.score - a.score);
    const match = ranked[0];
    if (match?.score) {
      const r = match.r;
      return {
        role: "assistant",
        text: `${r.title}\n\n원문: “${r.quote}”\n\n${r.explain}\n\n관련 법률: ${r.evidence.map((e) => e.title).join(", ")}\n\n확인할 질문: ${r.question}`,
        action: r.id,
      };
    }
    return {
      role: "assistant",
      text: "이 질문에 대한 답변은 준비되어 있지 않아요.\n\n‘필수 조항에서 빠진 내용을 알려줘’ 또는 ‘위험 조항을 정리해줘’를 선택해보세요.",
    };
  }

  async function send(text) {
    const q = text.trim();
    if (!q) return;
    sync();
    const messages = histories.get(context);
    messages.push({ role: "user", text: q });
    draw();
    const ax = axSession();
    const rid = ax?.reviewId || window.__lastReviewId;
    if (rid) {
      try {
        const r = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ review_id: rid, message: q }),
        });
        const j = await r.json();
        if (r.ok && j.answer) {
          messages.push({ role: "assistant", text: j.answer });
        } else {
          messages.push(reply(q));
        }
      } catch (_) {
        messages.push(reply(q));
      }
    } else {
      messages.push(reply(q));
    }
    input.value = "";
    draw();
    input.focus({ preventScroll: true });
  }

  document.getElementById("chatForm").onsubmit = (e) => {
    e.preventDefault();
    send(input.value);
  };
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      send(input.value);
    }
  });
  document.querySelectorAll("[data-chat-prompt]").forEach((b) => (b.onclick = () => send(b.dataset.chatPrompt)));
  document.getElementById("chatReset").onclick = () => {
    histories.set(context, [welcome()]);
    draw();
  };
  document.addEventListener("contract-view-change", sync);
  document.addEventListener("contract-ax-status", () => {
    // 상태 키가 바뀌므로 새 welcome
    const next = key();
    histories.set(next, [welcome()]);
    context = "";
    sync();
  });
  document.addEventListener("contract-tour-chat", () => {
    histories.set(key(), [welcome()]);
    context = key();
    send("위험 조항을 정리해줘");
  });
  sync();
})();
