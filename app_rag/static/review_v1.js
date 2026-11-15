const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const samples = window.CONTRACT_SAMPLES;
let selected = 0,
  page = 1,
  zoom = 100,
  tab = "risks",
  filter = "all",
  customFile = null,
  customUrl = null;
let activeRiskId = null,
  pendingDocumentFocus = false,
  activeDocumentId = null;
const uploadedDocuments = [];
const answers = new Set();
/** @type {null | {status:'loading'|'done'|'error', sampleId:string, title:string, text:string, report?:any, error?:string}} */
let axSession = null;

const esc = (v) =>
  String(v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const data = () => samples[selected];
const risks = () => (axSession?.status === "done" ? axSession.risks : data().risks);

function toast(t) {
  $("#toast").textContent = t;
  $("#toast").classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => $("#toast").classList.remove("show"), 2500);
}
function source(p, label = "원문 보기", riskId = null) {
  return `<button class="source" data-page="${p}" ${riskId ? `data-risk-source="${riskId}"` : ""}>▤ ${esc(label)} · ${p}쪽 ↗</button>`;
}
function riskBadge(r) {
  return `<span class="badge ${r.level === "high" ? "high" : r.level === "info" ? "neutral" : "warn"}">${
    r.level === "high" ? "우선 확인" : r.level === "info" ? "참고" : "확인 필요"
  }</span><span class="badge ok">${axSession ? "A.X 분석" : "원본 참고"}</span>`;
}

function verdictLevel(v) {
  if (v === "위반" || v === "위험") return "high";
  if (v === "확인 필요") return "check";
  return "info";
}

function cardsToRisks(cards) {
  return (cards || [])
    .filter((c) => (c.verdict || "") !== "문제 없음")
    .map((c, i) => {
      const quote = (c.contract_quote || c.clause_text || "").trim();
      return {
        id: "ax-" + (c.segment_id || i),
        level: verdictLevel(c.verdict),
        title: (c.article_title || c.segment_id || `조항 ${i + 1}`).toString().slice(0, 80),
        clause: c.verdict || "확인 필요",
        quote: quote.slice(0, 220) || "(인용 없음)",
        explain: c.why || c.gap || "",
        suggest: c.suggestion || "",
        question: c.suggestion
          ? `「${(c.article_title || "이 조항").toString().slice(0, 40)}」에 대해 상대방과 이렇게 협의해볼 수 있어요.`
          : "이 조항의 의미와 적용 범위를 상대방에게 확인해보세요.",
        page: 1,
        evidence: (c.evidence || []).map((e) => ({
          title: e.title || e.id || "근거",
          url: e.url || "#",
          summary: e.quote || "",
          connection: "A.X가 검색된 근거 중에서 고른 조문입니다.",
        })),
        highlights: [],
        _quote: quote,
        _text: c.clause_text || "",
      };
    });
}

function selectSample(i) {
  selected = i;
  page = 1;
  zoom = 100;
  filter = "all";
  activeRiskId = null;
  pendingDocumentFocus = false;
  customFile = null;
  customUrl = null;
  activeDocumentId = null;
  axSession = null;
  $("#jumpNotice").textContent = "";
  drawList();
  drawViewer();
  render();
  $("#reportBody").scrollTop = 0;
  document.dispatchEvent(new Event("contract-view-change"));
}

function drawList() {
  const axBtn =
    axSession
      ? `<button class="sample active ax-sample" data-ax="1" aria-pressed="true"><span class="file-icon">✧</span><span><b>A.X 분석</b><small>${esc(
          axSession.status === "done" ? "분석 완료" : axSession.status === "error" ? "실패" : "분석 중"
        )}</small></span><span class="num">AX</span></button>`
      : "";
  $("#sampleList").innerHTML =
    axBtn +
    samples
      .map(
        (s, i) =>
          `<button class="sample ${i === selected && !customFile && !axSession ? "active" : ""}" data-sample="${i}" aria-pressed="${
            i === selected && !customFile && !axSession
          }"><span class="file-icon">▤</span><span><b>${esc(s.short)}</b><small>${s.count}쪽 · ${
            i === 2 ? "기입된 계약" : "표준 양식"
          }</small></span><span class="num">0${i + 1}</span></button>`
      )
      .join("");
  $("#sampleList").insertAdjacentHTML(
    "beforeend",
    uploadedDocuments.length
      ? '<div class="uploaded-list-label">업로드한 계약서</div>' +
          uploadedDocuments
            .map(
              (d) =>
                `<button class="sample uploaded-document ${activeDocumentId === d.id ? "active" : ""}" data-document="${d.id}" aria-pressed="${
                  activeDocumentId === d.id
                }"><span class="file-icon">▤</span><span><b>${esc(d.file.name)}</b><small>${(d.file.size / 1024 / 1024).toFixed(
                  2
                )} MB · 분석 대기</small></span></button>`
            )
            .join("")
      : ""
  );
  $$("[data-sample]").forEach((b) => (b.onclick = () => selectSample(+b.dataset.sample)));
  $$("[data-document]").forEach((b) => (b.onclick = () => selectDocument(b.dataset.document)));
  $$("[data-ax]").forEach(
    (b) =>
      (b.onclick = () => {
        drawViewer();
        render();
      })
  );
}

function drawViewer() {
  document.dispatchEvent(new Event("contract-view-change"));
  const textStage = $("#textStage");
  const pageCanvas = $("#pageCanvas");
  const customPdf = $("#customPdf");

  if (axSession) {
    $("#contractTitle").textContent = axSession.title;
    $("#contractDesc").textContent =
      axSession.status === "done"
        ? "로컬 A.X 분석 결과 · 계약서 원문은 서버에 저장하지 않아요"
        : axSession.status === "error"
          ? "분석에 실패했어요"
          : "샘플 계약서를 A.X로 분석하는 중…";
    $("#pageCount").textContent = "텍스트 원문";
    $("#pageNumber").textContent = "TXT";
    $("#prev").disabled = true;
    $("#next").disabled = true;
    $("#zoomOut").disabled = true;
    $("#zoomIn").disabled = true;
    $("#pdfLink").hidden = true;
    $("#highlightLegend").hidden = true;
    $("#pageStrip").hidden = true;
    pageCanvas.hidden = true;
    customPdf.hidden = true;
    if (textStage) {
      textStage.hidden = false;
      textStage.innerHTML = `<pre class="ax-contract-text" id="axContractText">${esc(axSession.text || "")}</pre>`;
      if (activeRiskId) highlightAxQuote(activeRiskId);
    }
    return;
  }

  if (textStage) textStage.hidden = true;
  $("#pdfLink").hidden = false;
  const s = data();
  $("#contractTitle").textContent = customFile ? customFile.name : s.name;
  $("#contractDesc").textContent = customFile ? "내 계약서 · 새 분석 워크스페이스" : s.subtitle;
  $("#pageCount").textContent = customFile ? "로컬 PDF" : `${s.count} pages`;
  pageCanvas.hidden = !!customFile;
  $("#highlightLegend").hidden = !!customFile;
  customPdf.hidden = !customFile;
  $("#pageStrip").hidden = !!customFile;
  $("#pageNumber").textContent = customFile ? "PDF" : `${page} / ${s.count}`;
  $("#prev").disabled = !!customFile || page === 1;
  $("#next").disabled = !!customFile || page === s.count;
  $("#zoomOut").disabled = !!customFile || zoom <= 60;
  $("#zoomIn").disabled = !!customFile || zoom >= 180;
  $("#pdfLink").href = customFile ? customUrl : `assets/contracts/${s.id}.pdf`;
  $("#zoomValue").textContent = zoom + "%";
  if (customFile) {
    customPdf.src = customUrl;
    return;
  }
  customPdf.removeAttribute("src");
  $("#pageImage").src = `assets/contracts/${s.id}-${page}.jpg`;
  $("#pageImage").alt = `${s.name} 원본 ${page}쪽`;
  pageCanvas.style.width = zoom + "%";
  drawHighlights();
  $("#pageStrip").innerHTML = Array.from(
    { length: s.count },
    (_, i) =>
      `<button data-view-page="${i + 1}" class="${page === i + 1 ? "active" : ""}" aria-label="원본 ${i + 1}쪽" aria-current="${
        page === i + 1 ? "page" : "false"
      }">${i + 1}</button>`
  ).join("");
  $$("[data-view-page]").forEach((b) => (b.onclick = () => jump(+b.dataset.viewPage, false)));
}

function highlightAxQuote(riskId) {
  const pre = $("#axContractText");
  if (!pre || !axSession?.risks) return;
  const risk = axSession.risks.find((r) => r.id === riskId);
  const raw = axSession.text || "";
  if (!risk || !risk._quote || risk._quote === "(인용 없음)") {
    pre.innerHTML = esc(raw);
    return;
  }
  const q = risk._quote;
  const idx = raw.indexOf(q);
  if (idx < 0) {
    pre.innerHTML = esc(raw);
    return;
  }
  pre.innerHTML = esc(raw.slice(0, idx)) + `<mark class="ax-mark" id="axMark">${esc(q)}</mark>` + esc(raw.slice(idx + q.length));
  const mark = $("#axMark");
  if (mark) mark.scrollIntoView({ behavior: "smooth", block: "center" });
}

function jump(p, explain = true) {
  if (customFile || axSession) return;
  page = p;
  drawViewer();
  $("#pageStage").scrollTo({ top: 0, left: 0 });
  $("#jumpNotice").textContent = explain ? `${p}쪽 원문으로 이동했어요` : "";
  if (matchMedia("(max-width:850px)").matches && explain)
    document.querySelector(".document-pane").scrollIntoView({ behavior: "smooth", block: "start" });
}

function axOverview() {
  const s = axSession.report?.summary || {};
  const rs = risks();
  const facts = axSession.report?.facts || {};
  const factRows = Object.entries(facts)
    .filter(([, v]) => v != null && v !== "")
    .slice(0, 8)
    .map(([k, v]) => `<div><small>${esc(k)}</small><b>${esc(typeof v === "object" ? JSON.stringify(v) : v)}</b></div>`)
    .join("");
  return `<span class="section-kicker">A.X CONTRACT REPORT</span><h2>서명 전, A.X가 살펴본 결과예요.</h2><p class="muted">${esc(
    axSession.title
  )} · 모델 A.X 4.0 Light</p><div class="summary-state"><div class="ring">분석</div><div><b>판정 조각 ${s.n_segments || 0}개</b><p>위반 ${s.n_violation || 0} · 위험 ${
    s.n_risk || 0
  } · 확인 필요 ${s.n_review || 0} · 문제 없음 ${s.n_ok || 0}</p></div></div><div class="metrics"><div class="metric red"><b>${
    (s.n_violation || 0) + (s.n_risk || 0)
  }</b><span>위반·위험</span></div><div class="metric warn"><b>${s.n_review || 0}</b><span>확인 필요</span></div><div class="metric"><b>${
    rs.length
  }</b><span>검토 카드</span></div></div>${
    factRows ? `<div class="section-label">추출한 사실</div><div class="info-grid">${factRows}</div>` : ""
  }<div class="insight"><span>✧</span><div><b>이 결과는 이해를 돕는 정보예요</b><p>${esc(
    axSession.report?.disclaimer || "법률 자문이 아닙니다."
  )}</p></div></div><div class="section-label">먼저 보면 좋은 내용 <button data-open-tab="risks">전체 보기 →</button></div>${rs
    .slice(0, 3)
    .map((r) => `<button class="quick" data-risk-jump="${r.id}"><span>●</span>${esc(r.title)}<span>보기 ↗</span></button>`)
    .join("")}`;
}

function axComplete() {
  const missing = axSession.report?.missing || [];
  if (!missing.length)
    return `<span class="section-kicker">COMPLETENESS</span><h2>필수 조항 완결성</h2><div class="complete-success" role="status">✓ A.X가 표시한 누락 항목이 없어요.</div>`;
  return `<span class="section-kicker">COMPLETENESS</span><h2>필수 조항 완결성</h2><p class="muted">누락·추가 확인 후보 ${missing.length}개</p>${missing
    .map(
      (m) =>
        `<article class="check-row"><div class="check-top"><b>○ &nbsp; ${esc(m.label || m.std_item || m.id || "항목")}</b><span class="badge warn">확인</span></div><p>${esc(
          m.reason || m.note || ""
        )}</p></article>`
    )
    .join("")}`;
}

function axLoading() {
  return `<span class="section-kicker">A.X</span><h2>계약서를 분석하고 있어요</h2><div class="document-status"><span>◷</span><div><b>A.X 4.0 Light 분석 중</b><p>${esc(
    axSession.title
  )}</p></div></div><div class="custom-note">같은 검토 워크스페이스에서 결과가 채워집니다. 잠시만 기다려 주세요.</div><div class="pending-checks"><div>조항 분할 · 검색 <span>진행</span></div><div>A.X 판정 <span>진행</span></div><div>근거 검증 <span>진행</span></div></div>`;
}

function axError() {
  return `<span class="section-kicker">A.X</span><h2>분석을 마치지 못했어요</h2><div class="custom-note">${esc(
    axSession.error || "알 수 없는 오류"
  )}</div>`;
}

function overview() {
  if (axSession?.status === "loading") return axLoading();
  if (axSession?.status === "error") return axError();
  if (axSession?.status === "done") return axOverview();
  const s = data(),
    done = s.checks.filter((c) => c[3]).length,
    rs = risks();
  return `<span class="section-kicker">YOUR CONTRACT, AT A GLANCE</span><h2>서명 전, 함께 확인해봐요.</h2><p class="muted">${esc(
    s.profile
  )}</p><div class="summary-state"><div class="ring">확인</div><div><b>${6 - done}개 작성·조건 항목을 살펴보세요</b><p>필수 확인 목록 6개 중 문장·기입 확인 ${done}개<br>계약의 안전성을 점수로 판정한 결과는 아니에요.</p></div></div><div class="metrics"><div class="metric"><b>${done}/6</b><span>확인 목록 충족</span></div><div class="metric warn"><b>${
    rs.filter((r) => r.level === "check").length
  }</b><span>원본 확인 포인트</span></div><div class="metric red"><b>${
    rs.filter((r) => r.evidence?.length).length
  }</b><span>법률 근거 연결 항목</span></div></div><div class="section-label">계약 핵심 정보 <button data-open-tab="complete">미충족 항목 보기 →</button></div><div class="info-grid">${s.fields
    .map((f) => `<div><small>${esc(f[0])}</small><b class="${/필요/.test(f[1]) ? "blank" : ""}">${esc(f[1])}</b></div>`)
    .join(
      ""
    )}</div><div class="insight"><span>✧</span><div><b>내 계약, 이렇게 읽어보세요</b><p>${esc(
    s.insight
  )}</p></div></div><div class="section-label">먼저 확인하면 좋은 내용 <button data-open-tab="risks">전체 보기 →</button></div>${s.risks
    .slice(0, 2)
    .map((r) => `<button class="quick" data-page="${r.page}"><span>●</span>${esc(r.title)}<span>${r.page}쪽 ↗</span></button>`)
    .join("")}`;
}

function complete() {
  if (axSession?.status === "loading") return axLoading();
  if (axSession?.status === "error") return axError();
  if (axSession?.status === "done") return axComplete();
  const missing = data().checks.filter((c) => !c[3]);
  return `<span class="section-kicker">COMPLETENESS CHECK</span><h2>필수 조항 완결성 검사</h2>${
    missing.length
      ? `<p class="muted">미충족·추가 확인이 필요한 <b>${missing.length}개 항목만</b> 표시합니다. 충족한 항목의 내용은 표시하지 않아요.</p>${missing
          .map(
            (c) =>
              `<article class="check-row"><div class="check-top"><b>○ &nbsp; ${esc(c[0])}</b><span class="badge warn">작성·조건 확인</span></div><p>${esc(
                c[2]
              )}</p>${source(c[1], c[4])}</article>`
          )
          .join("")}`
      : '<div class="complete-success" role="status">✓ 필수 확인 목록에서 미충족 항목이 없어요.</div>'
  }`;
}

function evidenceBlock(r) {
  if (!r.evidence?.length) return "";
  return `<section class="legal-evidence"><div class="legal-title">⚖ 관련 법률 · 검토 근거</div>${r.evidence
    .map(
      (e) =>
        `<div class="legal-ref"><a href="${esc(e.url)}" target="_blank" rel="noopener">${esc(e.title)} ↗</a><p>${esc(
          e.summary
        )}</p><div class="legal-connection"><b>이 조항과 연결되는 이유</b><p>${esc(e.connection)}</p></div></div>`
    )
    .join(
      ""
    )}<small>출처: 국가법령정보센터 / A.X 검색 근거<br>관련 규정의 존재가 해당 계약의 위법성을 곧바로 의미하지는 않습니다.</small></section>`;
}

function riskCard(r) {
  return `<article class="risk ${activeRiskId === r.id ? "risk-selected" : ""}" id="risk-${r.id}" tabindex="-1"><div class="risk-top">${riskBadge(
    r
  )}<span style="font-size:9px;color:#a0abc0">${esc(r.clause)}</span></div><h3>${esc(r.title)}</h3><blockquote>${esc(
    r.quote
  )}</blockquote><p>${esc(r.explain)}</p>${
    axSession
      ? `<button class="source" data-risk-source="${r.id}">▤ 원문에서 찾기 ↗</button>`
      : source(r.page, "원문 보기", r.id)
  }${evidenceBlock(r)}<details><summary>수정·협의 방향과 확인 질문</summary><div class="suggestion"><strong>✧ 협의 방향</strong><p>${esc(
    r.suggest || "해당 조항의 범위를 구체적으로 적어 달라고 요청해보세요."
  )}</p></div><p><b>물어볼 질문</b><br>${esc(r.question)}</p></details></article>`;
}

function riskView() {
  if (axSession?.status === "loading") return axLoading();
  if (axSession?.status === "error") return axError();
  const rs = risks();
  return `<div class="review-summary"><div><span class="section-kicker">검토 결과</span><h2>위험 조항 필터링</h2></div><span class="result-total">총 ${
    rs.length
  }건</span></div><p class="muted compact-intro">${
    axSession ? "A.X 판정 카드입니다. 원문 인용을 누르면 왼쪽 텍스트로 이동합니다." : "원문의 색상 표시를 누르면 해당 검토 항목으로 이동해요."
  }</p><div class="filters" aria-label="위험 조항 필터">${[
    ["all", "전체"],
    ["high", "우선 확인"],
    ["check", "확인 필요"],
    ["info", "참고"],
  ]
    .map(
      ([id, label]) =>
        `<button data-filter="${id}" class="${filter === id ? "active" : ""}" aria-pressed="${filter === id}">${label} ${
          rs.filter((r) => id === "all" || r.level === id).length
        }</button>`
    )
    .join("")}</div>${[
    ["high", "우선 확인 사항"],
    ["check", "추가 확인 사항"],
    ["info", "참고 사항"],
  ]
    .filter(([level]) => filter === "all" || filter === level)
    .map(([level, label]) => {
      const items = rs.filter((r) => r.level === level);
      return items.length
        ? `<details class="risk-group ${level}" open><summary><span class="status-dot"></span>${label}<b>${items.length}</b><span class="chevron">⌃</span></summary><div class="risk-group-body">${items
            .map(riskCard)
            .join("")}</div></details>`
        : "";
    })
    .join("") || '<div class="empty">해당하는 확인 항목이 없어요.</div>'}`;
}

function questions() {
  if (axSession?.status === "loading") return axLoading();
  if (axSession?.status === "error") return axError();
  const rs = risks();
  const keyPrefix = axSession ? "ax:" + axSession.sampleId : data().id;
  return `<span class="section-kicker">BEFORE YOU SIGN</span><h2>계약 전에, 이렇게 물어보세요.</h2><p class="muted">상대방과 확인할 질문을 모았어요.</p>${rs
    .map((r, i) => {
      const key = keyPrefix + ":" + r.title;
      return `<article class="question"><span class="badge neutral">${axSession ? "A.X 관련 질문" : "원본 관련 질문"}</span><b style="margin-top:10px">${esc(
        r.question
      )}</b><div><label class="${answers.has(key) ? "done" : "muted"}"><input type="checkbox" data-answer="${esc(key)}" ${
        answers.has(key) ? "checked" : ""
      }> 확인했어요</label><button data-copy="${i}">질문 복사</button></div></article>`;
    })
    .join("")}`;
}

function customReport() {
  return `<span class="section-kicker">내 계약서</span><h2>분석 워크스페이스</h2><div class="document-status"><span>◷</span><div><b>분석 대기</b><p>${esc(
    customFile.name
  )}</p></div></div><div class="custom-note">원본 PDF를 확인할 수 있어요. 실제 AI 분석 서버가 연결되면 이 문서의 필수 조항 검사와 위험 조항 검토 결과가 여기에 표시됩니다.</div><div class="pending-checks"><div>필수 조항 완결성 검사 <span>대기</span></div><div>위험 조항 필터링 <span>대기</span></div><div>관련 법률·검토 근거 <span>대기</span></div></div>`;
}

function render() {
  let content;
  if (axSession) content = ({ overview, complete, risks: riskView, questions }[tab])();
  else if (customFile) content = customReport();
  else content = ({ overview, complete, risks: riskView, questions }[tab])();
  $("#reportBody").innerHTML = content;
  $$("[data-tab]").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === tab);
    b.setAttribute("aria-current", b.dataset.tab === tab ? "page" : "false");
  });
  $$("[data-page]").forEach(
    (b) => (b.onclick = () => (b.dataset.riskSource ? focusDocumentRisk(b.dataset.riskSource) : jump(+b.dataset.page)))
  );
  $$("[data-risk-source]").forEach((b) => (b.onclick = () => focusDocumentRisk(b.dataset.riskSource)));
  $$("[data-risk-jump]").forEach((b) => (b.onclick = () => focusReportRisk(b.dataset.riskJump)));
  $$("[data-open-tab]").forEach((b) => (b.onclick = () => openTab(b.dataset.openTab)));
  $$("[data-filter]").forEach(
    (b) =>
      (b.onclick = () => {
        filter = b.dataset.filter;
        const pos = $("#reportBody").scrollTop;
        render();
        $("#reportBody").scrollTop = pos;
      })
  );
  $$("[data-answer]").forEach(
    (b) =>
      (b.onchange = () => {
        b.checked ? answers.add(b.dataset.answer) : answers.delete(b.dataset.answer);
        b.parentElement.className = b.checked ? "done" : "muted";
      })
  );
  $$("[data-copy]").forEach(
    (b) =>
      (b.onclick = async () => {
        try {
          await navigator.clipboard.writeText(risks()[+b.dataset.copy].question);
          toast("질문을 복사했어요.");
        } catch {
          toast("브라우저에서 복사가 지원되지 않아요.");
        }
      })
  );
}

function openTab(t) {
  tab = t;
  filter = "all";
  render();
  $("#reportBody").scrollTop = 0;
}
$$("[data-tab]").forEach((b) => (b.onclick = () => openTab(b.dataset.tab)));
$("#prev").onclick = () => jump(page - 1, false);
$("#next").onclick = () => jump(page + 1, false);
$("#zoomOut").onclick = () => {
  zoom -= 20;
  drawViewer();
};
$("#zoomIn").onclick = () => {
  zoom += 20;
  drawViewer();
};

function selectDocument(id) {
  const d = uploadedDocuments.find((x) => x.id === id);
  if (!d) return;
  axSession = null;
  activeDocumentId = id;
  customFile = d.file;
  customUrl = d.url || (d.url = URL.createObjectURL(d.file));
  page = 1;
  zoom = 100;
  activeRiskId = null;
  pendingDocumentFocus = false;
  $("#jumpNotice").textContent = "";
  drawList();
  drawViewer();
  render();
  $("#reportBody").scrollTop = 0;
}

const documentStore = new Promise((resolve) => {
  if (!window.indexedDB) {
    resolve(null);
    return;
  }
  const request = indexedDB.open("youth-contract-workspaces", 1);
  request.onupgradeneeded = () => request.result.createObjectStore("documents", { keyPath: "id" });
  request.onsuccess = () => resolve(request.result);
  request.onerror = () => resolve(null);
});
const restoredDocuments = documentStore.then(
  (db) =>
    new Promise((resolve) => {
      if (new URLSearchParams(location.search).get("tour") === "1") {
        resolve();
        return;
      }
      if (!db) {
        resolve();
        return;
      }
      const request = db.transaction("documents").objectStore("documents").getAll();
      request.onsuccess = () => {
        for (const d of request.result) uploadedDocuments.push(d);
        drawList();
        resolve();
      };
      request.onerror = () => resolve();
    })
);

async function receiveFile(file) {
  if (!(file instanceof File)) return;
  if (!/\.pdf$/i.test(file.name) || file.size > 20 * 1024 * 1024 || !file.size) {
    toast("비어 있지 않은 20MB 이하의 PDF를 선택해주세요.");
    return;
  }
  const header = new TextDecoder().decode(await file.slice(0, 1024).arrayBuffer());
  if (!header.includes("%PDF-")) {
    toast("올바른 PDF 파일을 선택해주세요.");
    return;
  }
  await restoredDocuments;
  const d = { id: crypto.randomUUID(), file, createdAt: Date.now() };
  uploadedDocuments.push(d);
  selectDocument(d.id);
  $("#upload").value = "";
  const db = await documentStore;
  if (db) {
    try {
      const tx = db.transaction("documents", "readwrite");
      tx.objectStore("documents").put({ id: d.id, file: d.file, createdAt: d.createdAt });
      tx.onerror = () => toast("저장 공간이 부족해 현재 화면에서만 유지됩니다.");
    } catch {
      toast("현재 화면에서만 문서를 유지합니다.");
    }
  }
  toast("새 분석 워크스페이스에 계약서를 추가했어요.");
}
$("#upload").onchange = (e) => receiveFile(e.target.files[0]);

async function runAxAnalyze(msg) {
  const sampleId = msg.sampleId;
  const title = msg.title || "A.X 샘플 분석";
  axSession = { status: "loading", sampleId, title, text: "", domainLabel: msg.domainLabel || "" };
  customFile = null;
  customUrl = null;
  activeDocumentId = null;
  activeRiskId = null;
  tab = "overview";
  drawList();
  drawViewer();
  render();
  document.dispatchEvent(new CustomEvent("contract-ax-status", { detail: axSession }));
  toast("A.X 분석을 시작했어요.");
  try {
    const row = await (await fetch("/api/samples/" + encodeURIComponent(sampleId))).json();
    const text = row.text || "";
    if (!text) throw new Error("샘플 계약서가 비어 있습니다.");
    axSession.text = text;
    drawViewer();
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, no_llm: false }),
    });
    if (!res.ok) throw new Error("분석 요청 실패 (" + res.status + ")");
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    let report = null;
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const parts = buf.split("\n\n");
      buf = parts.pop() || "";
      for (const chunk of parts) {
        const lines = chunk.split("\n");
        let ev = "message";
        let dataLine = "";
        for (const line of lines) {
          if (line.startsWith("event:")) ev = line.slice(6).trim();
          if (line.startsWith("data:")) dataLine += line.slice(5).trim();
        }
        if (!dataLine) continue;
        const js = JSON.parse(dataLine);
        if (ev === "error") throw new Error(js.message || "분석 실패");
        if (ev === "done") report = js.report || js;
      }
    }
    if (!report) throw new Error("리포트를 받지 못했습니다.");
    axSession.status = "done";
    axSession.report = report;
    axSession.risks = cardsToRisks(report.cards || report.findings || []);
    tab = "risks";
    drawList();
    drawViewer();
    render();
    document.dispatchEvent(new CustomEvent("contract-ax-status", { detail: axSession }));
    toast("A.X 분석이 끝났어요.");
  } catch (err) {
    axSession.status = "error";
    axSession.error = err && err.message ? err.message : String(err);
    drawList();
    drawViewer();
    render();
    document.dispatchEvent(new CustomEvent("contract-ax-status", { detail: axSession }));
    toast("A.X 분석 실패");
  }
}

window.addEventListener("message", (e) => {
  if (e.source !== parent || e.origin !== location.origin) return;
  if (e.data?.type === "contract-review-file") receiveFile(e.data.file);
  if (e.data?.type === "contract-review-ax") runAxAnalyze(e.data);
  if (e.data?.type === "contract-review-open") {
    /* 샘플 리포트 먼저 보기 — 기본 샘플 유지 */
  }
});

$("#close").onclick = () => {
  if (parent !== window) parent.postMessage({ type: "contract-review-close" }, location.origin);
  else location.href = "/#start";
};

$("#export").onclick = () => {
  if (axSession?.status === "done") {
    const s = axSession.report?.summary || {};
    const text =
      `(계)약한청년들 | ${axSession.title}\n\n로컬 A.X 분석 결과입니다. 법률 자문이 아닙니다.\n` +
      `위반 ${s.n_violation || 0} · 위험 ${s.n_risk || 0} · 확인 필요 ${s.n_review || 0} · 문제 없음 ${s.n_ok || 0}\n\n` +
      risks()
        .map(
          (r) =>
            `[${r.clause}] ${r.title}\n${r.quote}\n${r.explain}\n근거: ${(r.evidence || []).map((e) => e.title).join(", ")}\n질문: ${r.question}`
        )
        .join("\n\n");
    const url = URL.createObjectURL(new Blob(["\ufeff" + text], { type: "text/plain;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `계약검토_AX_${axSession.sampleId}.txt`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    toast("A.X 리포트를 저장했어요.");
    return;
  }
  if (customFile) {
    toast("직접 연 문서에는 생성된 분석 리포트가 없어요.");
    return;
  }
  const s = data();
  const text =
    `(계)약한청년들 | ${s.name}\n\n미리 작성한 샘플 리포트입니다. 실제 AI 분석이나 법적 판단이 아닙니다.\n원본 PDF: ${s.filename}\n\n[미충족·추가 확인 항목]\n` +
    s.checks
      .filter((c) => !c[3])
      .map((c) => `[작성·조건 확인] ${c[0]} / ${c[1]}쪽\n${c[2]}`)
      .join("\n\n") +
    "\n\n[위험 항목 및 관련 법률]\n" +
    risks()
      .map(
        (r) =>
          `[원본 참고] ${r.title}\n${r.quote}\n${r.explain}\n관련 법률: ${r.evidence.map((e) => e.title + " / " + e.url + " / " + e.connection).join("\n")}\n확인 질문: ${r.question}\n확인 여부: ${
            answers.has(s.id + ":" + r.title) ? "확인함" : "미확인"
          }\n참고 원문: ${r.page}쪽`
      )
      .join("\n\n");
  const url = URL.createObjectURL(new Blob(["\ufeff" + text], { type: "text/plain;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `계약검토_${s.short}_샘플.txt`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
  toast("리포트를 저장했어요.");
};

function drawHighlights() {
  const layer = $("#highlightLayer");
  layer.replaceChildren();
  if (customFile || axSession) return;
  risks()
    .filter((r) => r.page === page)
    .forEach((r) =>
      (r.highlights || []).forEach((rect) => {
        const mark = document.createElement("button");
        mark.type = "button";
        mark.className = "pdf-highlight " + r.level + (activeRiskId === r.id ? " selected" : "");
        mark.dataset.highlightRisk = r.id;
        mark.style.cssText = `left:${rect.x}%;top:${rect.y}%;width:${rect.width}%;height:${rect.height}%`;
        const level = r.level === "high" ? "빨강 · 우선 확인" : r.level === "info" ? "초록 · 참고" : "노랑 · 확인 필요";
        mark.setAttribute("aria-label", level + " · " + r.title + " · 오른쪽 검토 항목 보기");
        mark.setAttribute("aria-pressed", activeRiskId === r.id);
        mark.title = level + " | " + r.title;
        mark.onclick = () => focusReportRisk(r.id);
        layer.append(mark);
      })
    );
}

function focusReportRisk(id) {
  const risk = risks().find((r) => r.id === id);
  if (!risk) return;
  activeRiskId = id;
  tab = "risks";
  filter = "all";
  render();
  if (axSession) highlightAxQuote(id);
  else drawHighlights();
  const card = document.getElementById("risk-" + id),
    body = $("#reportBody");
  if (card) {
    card.focus({ preventScroll: true });
    if (matchMedia("(max-width:850px)").matches) card.scrollIntoView({ behavior: "smooth", block: "start" });
    else body.scrollTo({ top: body.scrollTop + card.getBoundingClientRect().top - body.getBoundingClientRect().top - 12, behavior: "instant" });
  }
  $("#jumpNotice").textContent = axSession ? "원문에서 해당 인용을 강조했어요" : "선택한 조항의 검토 근거를 표시했어요";
}

function scrollToHighlight() {
  if (!pendingDocumentFocus) return;
  const mark = [...$("#highlightLayer").children].find((n) => n.dataset.highlightRisk === activeRiskId);
  if (!mark) return;
  const stage = $("#pageStage"),
    mr = mark.getBoundingClientRect(),
    sr = stage.getBoundingClientRect();
  stage.scrollTo({
    top: stage.scrollTop + mr.top - sr.top - stage.clientHeight * 0.35,
    left: Math.max(0, stage.scrollLeft + mr.left - sr.left - stage.clientWidth * 0.2),
    behavior: "smooth",
  });
  pendingDocumentFocus = false;
}

function focusDocumentRisk(id) {
  const risk = risks().find((r) => r.id === id);
  if (!risk) return;
  if (axSession) {
    activeRiskId = id;
    drawViewer();
    highlightAxQuote(id);
    $("#jumpNotice").textContent = "원문에서 관련 문장을 강조했어요";
    if (matchMedia("(max-width:850px)").matches)
      document.querySelector(".document-pane").scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  const reportPosition = $("#reportBody").scrollTop;
  activeRiskId = id;
  page = risk.page;
  pendingDocumentFocus = true;
  drawViewer();
  render();
  $("#reportBody").scrollTop = reportPosition;
  $("#jumpNotice").textContent = risk.page + "쪽의 관련 문장을 강조했어요";
  if ($("#pageImage").complete) requestAnimationFrame(scrollToHighlight);
  if (matchMedia("(max-width:850px)").matches)
    document.querySelector(".document-pane").scrollIntoView({ behavior: "smooth", block: "start" });
}
$("#pageImage").addEventListener("load", () => {
  drawHighlights();
  scrollToHighlight();
});

const initial = new URLSearchParams(location.search).get("sample");
const n = samples.findIndex((s) => s.id === initial);
selectSample(n < 0 ? 0 : n);

const initialTab = new URLSearchParams(location.search).get("tab");
if (["overview", "complete", "risks", "questions"].includes(initialTab)) openTab(initialTab);

if (new URLSearchParams(location.search).get("tour") === "1") {
  window.addEventListener("message", (e) => {
    if (e.source !== parent || e.origin !== location.origin || e.data?.type !== "contract-tour-step") return;
    const step = e.data.step;
    if (![0, 1, 2].includes(step)) return;
    selectSample(step);
    openTab(["overview", "complete", "risks"][step]);
    if (step === 2) {
      focusReportRisk(data().risks[0].id);
      focusDocumentRisk(data().risks[0].id);
    }
  });
}

// chat / 외부에서 상태 조회
window.getAxSession = () => axSession;
window.getReviewRisks = () => risks();
