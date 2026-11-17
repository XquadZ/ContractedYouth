const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const samples = (window.CONTRACT_SAMPLES || []).filter((s) => s && s.id !== "sale");
let selected = 0,
  activeHistoryId = null,
  reviewHistory = [],
  page = 1,
  zoom = 100,
  tab = "risks",
  filter = "all",
  customFile = null,
  customUrl = null;
let activeRiskId = null,
  pendingDocumentFocus = false,
  activeDocumentId = null;
/** 세션 메모리만 — IndexedDB/디스크 저장 안 함 */
const uploadedDocuments = [];
const answers = new Set();
/** @type {null | object} */
let axSession = null;
let secPerClause = 2.64;
const OUT_OF_CORPUS_RE = /민법\s*제\s*(618|397|568|580)\s*조|민간임대주택|시행령\s*제\s*(38|40)\s*조/;

const esc = (v) =>
  String(v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
/** UTC ISO → Asia/Seoul 표시 (저장값은 그대로) */
function formatSeoul(iso) {
  if (!iso) return "-";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso).replace("T", " ").slice(0, 16);
    return new Intl.DateTimeFormat("sv-SE", {
      timeZone: "Asia/Seoul",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(d);
  } catch (_) {
    return String(iso).replace("T", " ").slice(0, 16);
  }
}
const FACT_LABEL_KO = {
  domain: "계약 유형",
  hourly_wage: "시급(원)",
  monthly_wage: "월급(원)",
  work_days_per_week: "주 근로일",
  work_hours_per_day: "일 근로시간",
  break_minutes: "휴게(분)",
  weekly_scheduled_hours: "1주 소정근로시간",
  weekly_hours_formula: "1주 시간 계산식",
  regular_workers: "상시근로자수",
  probation_months: "수습 기간(개월)",
  probation_cut_rate: "수습 감액률",
  contract_period: "계약 기간",
  contract_months: "계약기간(개월)",
  apply_year: "적용 연도",
  deposit: "보증금(원)",
  down_payment: "계약금(원)",
  balance: "잔금(원)",
  monthly_rent: "월세(원)",
  maintenance_fee: "관리비(원)",
  lease_period: "임대차 기간",
  rent_increase_rate: "증액률",
  principal: "원금(원)",
  interest_rate: "이자율",
  delay_interest_rate: "지연 이율",
  repay_date: "변제기",
  start_date: "계약 시작일",
  end_date: "계약 종료일",
  date_source: "날짜 출처 문장",
  continuous_service_months: "계속근로 개월",
  is_simple_labor: "단순노무 여부",
  is_employee: "근로자 여부",
  is_part_time: "단시간 여부",
  agreed_scheduled_hours: "약정 소정근로시간",
};
const FACT_HIDE = new Set(["date_missing", "date_invalid", "raw"]);
function factLabelKo(key) {
  return FACT_LABEL_KO[key] || key;
}
function formatFactValue(key, v) {
  if (key === "domain") return domainLabelKo(v) || String(v);
  if (v && typeof v === "object") {
    if (v.start || v.end) return `${v.start || "?"} ~ ${v.end || "?"}`;
    return JSON.stringify(v);
  }
  return String(v);
}
const data = () => samples[selected];
const risks = () => (axSession?.status === "done" ? axSession.risks : data().risks);
const isUserSession = () => !!(axSession && axSession.isUser);
const isSampleMode = () => !axSession && !customFile;

function toast(t) {
  $("#toast").textContent = t;
  $("#toast").classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => $("#toast").classList.remove("show"), 2800);
}
function source(p, label = "원문 보기", riskId = null) {
  return `<button class="source" data-page="${p}" ${riskId ? `data-risk-source="${riskId}"` : ""}>▤ ${esc(label)} · ${p}쪽 ↗</button>`;
}
function riskBadge(r) {
  return `<span class="badge ${r.level === "high" ? "high" : r.level === "info" ? "neutral" : "warn"}">${
    r.level === "high" ? "우선 확인" : r.level === "info" ? "참고" : "확인 필요"
  }</span><span class="badge ok">${axSession ? (axSession.isUser ? "내 파일 분석" : "EXAONE 분석") : "원본 참고"}</span>`;
}

function verdictLevel(v) {
  if (v === "위반" || v === "위험") return "high";
  if (v === "확인 필요") return "check";
  return "info";
}

function domainLabelKo(id) {
  return { LAB: "근로", LEASE: "임대차", LOAN: "차용" }[id] || id || "";
}

function cardsToRisks(cards) {
  return (cards || [])
    .filter((c) => (c.verdict || "") !== "문제 없음")
    .map((c, i) => {
      const quote = (c.contract_quote || c.clause_text || "").trim();
      const evidence = (c.evidence || []).map((e) => ({
        title: `${e.source_tag ? e.source_tag + " " : ""}${e.title || e.id || "근거"}`.trim(),
        url: e.url || "#",
        summary: e.quote || "",
        connection: "법령 원문에서 확인한 근거입니다.",
        source_tag: e.source_tag || "",
        id: e.id || "",
      }));
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
        evidence,
        highlights: [],
        _quote: quote,
        _text: c.clause_text || "",
      };
    });
}

function updateBadges() {
  const sampleBadge = $("#sampleBadge");
  const userBadge = $("#userBadge");
  const guide = $("#chatGuideNote");
  if (sampleBadge) sampleBadge.hidden = !isSampleMode();
  if (userBadge) userBadge.hidden = !(isUserSession() || (customFile && !axSession));
  if (guide) guide.hidden = !isUserSession();
}

function showDomainBanner(guess, chosen) {
  const el = $("#domainBanner");
  if (!el) return;
  if (!axSession?.isUser) {
    el.hidden = true;
    el.innerHTML = "";
    return;
  }
  if (guess?.out_of_scope && !chosen) {
    el.hidden = false;
    el.innerHTML = `<b>지금은 근로·임대차·차용 계약서만 분석해요.</b>
      <span>${esc(guess.reason || "")}</span>
      <div class="domain-choices">${["LAB", "LEASE", "LOAN"]
        .map((id) => `<button type="button" data-domain-pick="${id}">${domainLabelKo(id)}로 분석</button>`)
        .join("")}<button type="button" data-domain-cancel>닫기</button></div>`;
    bindDomainBanner();
    return;
  }
  const label = domainLabelKo(chosen || guess?.domain) || "미정";
  el.hidden = false;
  el.innerHTML = `<span><b>${esc(label)}계약서로 인식했어요</b> <button type="button" data-domain-change>바꾸기</button></span>
    <div class="domain-choices" id="domainChoices" hidden>${["LAB", "LEASE", "LOAN"]
      .map((id) => `<button type="button" data-domain-pick="${id}" class="${id === (chosen || guess?.domain) ? "active" : ""}">${domainLabelKo(id)}</button>`)
      .join("")}</div>`;
  bindDomainBanner();
}

function bindDomainBanner() {
  $$("[data-domain-change]").forEach(
    (b) =>
      (b.onclick = () => {
        const box = $("#domainChoices");
        if (box) box.hidden = !box.hidden;
      })
  );
  $$("[data-domain-pick]").forEach(
    (b) =>
      (b.onclick = () => {
        if (!axSession) return;
        axSession.domain = b.dataset.domainPick;
        axSession.domainLabel = domainLabelKo(axSession.domain);
        showDomainBanner(axSession.domainGuess, axSession.domain);
        if (axSession.status === "domain" || axSession.status === "error") {
          startUserAnalyze();
        } else if (axSession.status === "done") {
          toast("종류를 바꿨어요. 다시 분석합니다.");
          startUserAnalyze();
        }
      })
  );
  $$("[data-domain-cancel]").forEach(
    (b) =>
      (b.onclick = () => {
        axSession = null;
        $("#domainBanner").hidden = true;
        drawList();
        drawViewer();
        render();
      })
  );
}

function showProgress(msg) {
  const el = $("#analyzeProgress");
  if (!el) return;
  if (!msg) {
    el.hidden = true;
    el.textContent = "";
    return;
  }
  el.hidden = false;
  el.textContent = msg;
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
  showProgress("");
  $("#domainBanner").hidden = true;
  $("#jumpNotice").textContent = "";
  drawList();
  drawViewer();
  render();
  $("#reportBody").scrollTop = 0;
  document.dispatchEvent(new Event("contract-view-change"));
}

function drawList() {
  const userDocs = uploadedDocuments
    .map((d) => {
      const active = activeDocumentId === d.id || (axSession?.docId === d.id);
      const st =
        axSession?.docId === d.id
          ? axSession.status === "done"
            ? "분석 완료"
            : axSession.status === "loading"
              ? "분석 중"
              : axSession.status === "domain"
                ? "종류 확인"
                : "대기"
          : "내 파일";
      return `<button class="sample uploaded-document ${active ? "active" : ""}" data-document="${d.id}" aria-pressed="${active}"><span class="file-icon">▤</span><span><b>${esc(
        d.title || d.file?.name || "내 계약서"
      )}</b><small><span class="mine-tag">내 파일</span> · ${esc(st)}</small></span></button>`;
    })
    .join("");
  const axBtn =
    axSession && !axSession.isUser
      ? `<button class="sample active ax-sample" data-ax="1" aria-pressed="true"><span class="file-icon">✧</span><span><b>EXAONE 분석</b><small>${esc(
          axSession.status === "done" ? "분석 완료" : axSession.status === "error" ? "실패" : "분석 중"
        )}</small></span><span class="num">AI</span></button>`
      : "";
  $("#sampleList").innerHTML =
    (userDocs ? '<div class="uploaded-list-label">내 계약서</div>' + userDocs : "") +
    axBtn +
    '<div class="uploaded-list-label">예시 샘플</div>' +
    samples
      .map(
        (s, i) =>
          `<button class="sample ${i === selected && !customFile && !axSession ? "active" : ""}" data-sample="${i}" aria-pressed="${
            i === selected && !customFile && !axSession
          }"><span class="file-icon">▤</span><span><b>${esc(s.short)}</b><small>${s.count}쪽 · 예시</small></span><span class="num">0${i + 1}</span></button>`
      )
      .join("");
  $$("[data-sample]").forEach((b) => (b.onclick = () => selectSample(+b.dataset.sample)));
  $$("[data-document]").forEach((b) => (b.onclick = () => selectDocument(b.dataset.document)));
  $$("[data-ax]").forEach(
    (b) =>
      (b.onclick = () => {
        drawViewer();
        render();
      })
  );
  drawReviewHistory();
}

function gradeBadgeClass(grade) {
  if (grade === "위험") return "hist-grade risk";
  if (grade === "주의") return "hist-grade caution";
  if (grade === "안전") return "hist-grade safe";
  return "hist-grade";
}

function historyTitle(row) {
  if (row.filename) return row.filename;
  const dom = domainLabelKo(row.domain) || row.domain || "검토";
  return `${dom} · ${formatSeoul(row.created_at)}`;
}

function drawReviewHistory() {
  const box = $("#reviewHistoryList");
  if (!box) return;
  if (!reviewHistory.length) {
    box.innerHTML = `<p class="side-note">아직 검토한 계약서가 없어요</p>`;
    return;
  }
  box.innerHTML = reviewHistory
    .map((r) => {
      const active = activeHistoryId === r.id;
      return `<button type="button" class="sample history-item ${active ? "active" : ""}" data-history="${r.id}" aria-pressed="${active}"><span class="file-icon">▤</span><span><b>${esc(
        historyTitle(r)
      )}</b><small><span class="${gradeBadgeClass(r.grade)}">${esc(r.grade || "-")}</span> · ${esc(
        String(r.score ?? "-")
      )}점 · ${esc(formatSeoul(r.created_at))}</small></span></button>`;
    })
    .join("");
  $$("[data-history]").forEach((b) => (b.onclick = () => openReviewHistory(+b.dataset.history)));
}

async function refreshReviewHistory() {
  try {
    const r = await fetch("/api/reviews");
    if (!r.ok) return;
    const j = await r.json();
    reviewHistory = j.reviews || [];
    drawReviewHistory();
  } catch (_) {}
}
window.refreshReviewHistory = refreshReviewHistory;

async function openReviewHistory(id) {
  try {
    const detail = await fetch("/api/reviews/" + id).then((x) => x.json());
    if (detail.error) {
      toast(detail.error);
      return;
    }
    if (detail.original_message) toast(detail.original_message);
    activeHistoryId = id;
    window.__lastReviewId = id;
    customFile = null;
    customUrl = null;
    activeDocumentId = null;
    axSession = {
      status: "done",
      isUser: true,
      title: historyTitle(detail.review || {}) || "기록 #" + id,
      report: detail.report,
      risks: cardsToRisks((detail.report && detail.report.cards) || []),
      domain: detail.review?.domain,
      reviewId: id,
      text: detail.review?.masked_text || "",
      kind: "txt",
    };
    tab = "overview";
    drawList();
    drawViewer();
    render();
    document.dispatchEvent(new CustomEvent("contract-ax-status", { detail: axSession }));
    const boxMsg = document.getElementById("chatMessages");
    if (boxMsg && detail.chats) {
      // review-chat will sync; also seed via event
      document.dispatchEvent(
        new CustomEvent("contract-load-chats", { detail: { reviewId: id, chats: detail.chats } })
      );
    }
  } catch (err) {
    toast("기록을 열지 못했어요");
  }
}

function drawViewer() {
  document.dispatchEvent(new Event("contract-view-change"));
  updateBadges();
  const textStage = $("#textStage");
  const pageCanvas = $("#pageCanvas");
  const customPdf = $("#customPdf");

  if (axSession) {
    $("#contractTitle").textContent = axSession.title;
    $("#contractDesc").textContent =
      axSession.status === "done"
        ? axSession.isUser
          ? "EXAONE 분석 · 업로드 원본은 암호화해 보관하고 24시간 뒤 자동 삭제돼요"
          : "EXAONE 분석 · 업로드 원본은 암호화해 보관하고 24시간 뒤 자동 삭제돼요"
        : axSession.status === "error"
          ? "분석에 실패했어요"
          : axSession.status === "domain"
            ? "계약서 종류를 확인해 주세요"
            : "계약서를 분석하는 중…";
    showDomainBanner(axSession.domainGuess, axSession.domain);

    const usePdfPages = axSession.kind === "pdf" && axSession.pdfPages?.length;
    if (usePdfPages && axSession.status === "done") {
      if (textStage) textStage.hidden = true;
      customPdf.hidden = true;
      pageCanvas.hidden = false;
      $("#highlightLegend").hidden = false;
      $("#pageStrip").hidden = false;
      $("#pdfLink").hidden = true;
      const pages = axSession.pdfPages;
      const maxP = pages.length;
      if (page > maxP) page = 1;
      const cur = pages[page - 1];
      $("#pageCount").textContent = `${maxP} pages`;
      $("#pageNumber").textContent = `${page} / ${maxP}`;
      $("#prev").disabled = page === 1;
      $("#next").disabled = page === maxP;
      $("#zoomOut").disabled = zoom <= 60;
      $("#zoomIn").disabled = zoom >= 180;
      $("#zoomValue").textContent = zoom + "%";
      $("#pageImage").src = cur.data_url;
      $("#pageImage").alt = `${axSession.title} ${page}쪽`;
      pageCanvas.style.width = zoom + "%";
      drawHighlights();
      $("#pageStrip").innerHTML = pages
        .map(
          (p, i) =>
            `<button data-view-page="${i + 1}" class="${page === i + 1 ? "active" : ""}" aria-label="원본 ${i + 1}쪽">${i + 1}</button>`
        )
        .join("");
      $$("[data-view-page]").forEach((b) => (b.onclick = () => jump(+b.dataset.viewPage, false)));
      return;
    }

    $("#pageCount").textContent = axSession.kind === "pdf" ? "PDF 텍스트" : "텍스트 원문";
    $("#pageNumber").textContent = (axSession.kind || "TXT").toUpperCase();
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

  $("#domainBanner").hidden = true;
  const s = data();
  // bodyText만 있고 페이지 이미지가 없는 샘플만 텍스트 뷰 (차용도 loan-N.jpg 사용)
  const textOnlySample = !customFile && s && s.bodyText && !(s.count > 0 && !s.forceText);
  if (textOnlySample) {
    if (textStage) {
      textStage.hidden = false;
      textStage.innerHTML = `<pre class="ax-contract-text">${esc(s.bodyText || "")}</pre>`;
    }
    pageCanvas.hidden = true;
    customPdf.hidden = true;
    $("#pdfLink").hidden = true;
    $("#highlightLegend").hidden = true;
    $("#pageStrip").hidden = true;
    $("#contractTitle").textContent = s.name;
    $("#contractDesc").textContent = s.subtitle;
    $("#pageCount").textContent = "텍스트 원문";
    $("#pageNumber").textContent = "TXT";
    $("#prev").disabled = true;
    $("#next").disabled = true;
    $("#zoomOut").disabled = true;
    $("#zoomIn").disabled = true;
    return;
  }
  if (textStage) textStage.hidden = true;
  $("#pdfLink").hidden = false;
  $("#contractTitle").textContent = customFile ? customFile.name : s.name;
  $("#contractDesc").textContent = customFile ? "내 계약서 · 분석 대기" : s.subtitle;
  $("#pageCount").textContent = customFile ? "로컬 파일" : `${s.count} pages`;
  pageCanvas.hidden = !!customFile;
  $("#highlightLegend").hidden = !!customFile;
  customPdf.hidden = !customFile || !/\.pdf$/i.test(customFile.name || "");
  $("#pageStrip").hidden = !!customFile;
  $("#pageNumber").textContent = customFile ? "FILE" : `${page} / ${s.count}`;
  $("#prev").disabled = !!customFile || page === 1;
  $("#next").disabled = !!customFile || page === s.count;
  $("#zoomOut").disabled = !!customFile || zoom <= 60;
  $("#zoomIn").disabled = !!customFile || zoom >= 180;
  $("#pdfLink").href = customFile && customUrl && /\.pdf$/i.test(customFile.name) ? customUrl : customFile ? "#" : `assets/contracts/${s.id}.pdf`;
  $("#pdfLink").hidden = !!(customFile && !/\.pdf$/i.test(customFile.name || ""));
  $("#zoomValue").textContent = zoom + "%";
  if (customFile) {
    if (/\.pdf$/i.test(customFile.name) && customUrl) customPdf.src = customUrl;
    else {
      customPdf.hidden = true;
      if (textStage) {
        textStage.hidden = false;
        textStage.innerHTML = `<pre class="ax-contract-text">파일을 분석하면 텍스트가 여기에 표시됩니다.</pre>`;
      }
    }
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
  let idx = raw.indexOf(q);
  if (idx < 0) idx = raw.indexOf(q.slice(0, 30));
  if (idx < 0) idx = raw.indexOf(q.slice(0, 15));
  if (idx < 0) {
    pre.innerHTML = esc(raw);
    return;
  }
  const len = raw.indexOf(q) === idx ? q.length : Math.min(30, q.length);
  const hit = raw.slice(idx, idx + len);
  pre.innerHTML = esc(raw.slice(0, idx)) + `<mark class="ax-mark" id="axMark">${esc(hit)}</mark>` + esc(raw.slice(idx + hit.length));
  const mark = $("#axMark");
  if (mark) mark.scrollIntoView({ behavior: "smooth", block: "center" });
}

function jump(p, explain = true) {
  if (customFile && !(axSession?.pdfPages?.length)) return;
  if (axSession && !axSession.pdfPages?.length) return;
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
    .filter(([k, v]) => !FACT_HIDE.has(k) && v != null && v !== "" && !(typeof v === "boolean" && v === false))
    .slice(0, 8)
    .map(([k, v]) => `<div><small>${esc(factLabelKo(k))}</small><b>${esc(formatFactValue(k, v))}</b></div>`)
    .join("");
  const hl =
    axSession.locateRatio != null
      ? `<p class="muted">원문 하이라이트 찾은 비율: ${Math.round((axSession.locateRatio || 0) * 100)}% (${axSession.locateFound || 0}/${
          axSession.locateTotal || 0
        })</p>`
      : "";
  const score = axSession.report?.score;
  const grade = axSession.report?.grade || "";
  const scoreNote =
    axSession.report?.score_detail?.score_note ||
    axSession.report?.score_note ||
    "확인할 조항이 3개 이상이면 '주의'로 표시해요.";
  const scoreBlock =
    score != null
      ? `<div class="summary-state score-gauge"><div class="ring">${esc(String(score))}</div><div><b>${esc(grade)}</b><p>점수 ${esc(
          String(score)
        )}점 · 위반 ${s.n_violation || 0} · 위험 ${s.n_risk || 0} · 확인 ${s.n_review || 0}</p><p class="muted">${esc(
          scoreNote
        )}</p>${
          grade === "안전"
            ? `<p class="muted">법 기준을 어긴 조항을 찾지 못했다는 뜻이며, 법률 자문이 아니에요.</p>`
            : ""
        }</div></div>`
      : `<div class="summary-state"><div class="ring">분석</div><div><b>판정 조각 ${s.n_segments || 0}개</b><p>위반 ${
          s.n_violation || 0
        } · 위험 ${s.n_risk || 0} · 확인 필요 ${s.n_review || 0} · 문제 없음 ${s.n_ok || 0}</p></div></div>`;
  const demo = axSession.report?.demo_notice
    ? `<p class="muted">${esc(axSession.report.demo_notice)}</p>`
    : "";
  const modelName = axSession.report?.model || "로컬 모델";
  return `<span class="section-kicker">CONTRACT REPORT</span><h2>서명 전, 살펴본 결과예요.</h2><p class="muted">${esc(
    axSession.title
  )} · 모델 ${esc(modelName)} · ${esc(domainLabelKo(axSession.domain) || "")}</p>${demo}${hl}${scoreBlock}<div class="metrics"><div class="metric red"><b>${
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
    return `<span class="section-kicker">COMPLETENESS</span><h2>필수 조항 완결성</h2><div class="complete-success" role="status">✓ 표시한 누락 항목이 없어요.</div>`;
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
  const p = axSession.progress || {};
  const n = p.n_clauses || 0;
  const done = p.done || 0;
  const eta = n ? Math.ceil((n - done) * secPerClause) : Math.ceil(8 * secPerClause);
  const detail =
    n > 0
      ? done > 0
        ? `조항 ${done}/${n} · 약 ${eta}초 남음`
        : `분석 중(조항 ${n}개, 약 ${Math.ceil(n * secPerClause)}초 예상)`
      : `분석 중(약 ${eta}초 예상)`;
  return `<span class="section-kicker">ANALYSIS</span><h2>계약서를 분석하고 있어요</h2><div class="document-status"><span>◷</span><div><b>EXAONE 분석 중</b><p>${esc(
    axSession.title
  )}</p><p>${esc(detail)}</p></div></div><div class="custom-note">같은 검토 워크스페이스에서 결과가 채워집니다.</div><div class="pending-checks"><div>조항 분할 · 검색 <span>진행</span></div><div>판정 <span>${done || "…"}/${n || "?"}</span></div><div>근거 검증 <span>진행</span></div></div>`;
}

function axError() {
  return `<span class="section-kicker">ANALYSIS</span><h2>분석을 마치지 못했어요</h2><div class="custom-note">${esc(
    axSession.error || "알 수 없는 오류"
  )}</div>`;
}

function axDomainPick() {
  return `<span class="section-kicker">종류 확인</span><h2>계약서 종류를 확인해 주세요</h2><div class="custom-note">상단 배너에서 종류를 고르면 분석을 시작합니다. 지금은 근로·임대차·차용만 지원해요.</div>`;
}

function overview() {
  if (axSession?.status === "loading") return axLoading();
  if (axSession?.status === "error") return axError();
  if (axSession?.status === "domain") return axDomainPick();
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
  if (axSession?.status === "domain") return axDomainPick();
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
  if (!r.evidence?.length) {
    if (axSession?.status === "done")
      return `<section class="legal-evidence"><div class="legal-title">⚖ 관련 법률 · 검토 근거</div><p class="no-evidence">근거를 찾지 못해 직접 확인이 필요해요</p></section>`;
    return "";
  }
  const sampleMode = !axSession;
  return `<section class="legal-evidence"><div class="legal-title">⚖ 관련 법률 · 검토 근거</div>${r.evidence
    .map((e) => {
      const ooc = sampleMode && OUT_OF_CORPUS_RE.test(e.title || "");
      return `<div class="legal-ref"><a href="${esc(e.url)}" target="_blank" rel="noopener">${esc(e.title)} ↗</a>${
        ooc ? `<span class="ooc-badge">근거 자료 밖 조문(참고)</span>` : ""
      }<p>${esc(e.summary)}</p><div class="legal-connection"><b>이 조항과 연결되는 이유</b><p>${esc(e.connection)}</p></div></div>`;
    })
    .join("")}<small>${
    sampleMode
      ? "출처: 예시 설명<br>미리 작성한 샘플 화면입니다."
      : "출처: 국가법령정보센터 / 검증된 법령 근거<br>관련 규정의 존재가 해당 계약의 위법성을 곧바로 의미하지는 않습니다."
  }</small></section>`;
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
  if (axSession?.status === "domain") return axDomainPick();
  const rs = risks();
  return `<div class="review-summary"><div><span class="section-kicker">검토 결과</span><h2>위험 조항 필터링</h2></div><span class="result-total">총 ${
    rs.length
  }건</span></div><p class="muted compact-intro">${
    axSession ? "판정 카드입니다. 원문 인용을 누르면 왼쪽 텍스트로 이동합니다." : "원문의 색상 표시를 누르면 해당 검토 항목으로 이동해요."
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
  if (axSession?.status === "domain") return axDomainPick();
  const rs = risks();
  const keyPrefix = axSession ? "ax:" + axSession.sampleId : data().id;
  return `<span class="section-kicker">BEFORE YOU SIGN</span><h2>계약 전에, 이렇게 물어보세요.</h2><p class="muted">상대방과 확인할 질문을 모았어요.</p>${rs
    .map((r, i) => {
      const key = keyPrefix + ":" + r.title;
      return `<article class="question"><span class="badge neutral">${axSession ? "분석 관련 질문" : "원본 관련 질문"}</span><b style="margin-top:10px">${esc(
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
  )}</p></div></div><div class="custom-note">파일을 열면 추출 → 종류 확인 → 분석이 이어집니다.</div>`;
}

function render() {
  updateBadges();
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
  activeDocumentId = id;
  customFile = d.file || null;
  customUrl = d.url || (d.file && /\.pdf$/i.test(d.file.name) ? (d.url = URL.createObjectURL(d.file)) : null);
  page = 1;
  zoom = 100;
  activeRiskId = null;
  pendingDocumentFocus = false;
  $("#jumpNotice").textContent = "";
  if (d.session && d.session.status === "done") {
    axSession = d.session;
  } else if (d.text) {
    axSession = {
      status: "domain",
      isUser: true,
      docId: d.id,
      sampleId: d.id,
      title: d.title,
      text: d.text,
      kind: d.kind,
      file: d.file,
      pages: d.pages,
      domainGuess: d.domainGuess,
      domain: d.domainGuess?.confident ? d.domainGuess.domain : null,
      domainLabel: d.domainGuess?.label || "",
    };
    if (axSession.domain && axSession.domainGuess?.confident && !axSession.domainGuess?.out_of_scope) {
      startUserAnalyze();
      return;
    }
  } else {
    axSession = null;
  }
  drawList();
  drawViewer();
  render();
  $("#reportBody").scrollTop = 0;
  document.dispatchEvent(new Event("contract-view-change"));
}

async function receiveFile(file) {
  if (!(file instanceof File)) return;
  if (file.size > 10 * 1024 * 1024 || !file.size) {
    toast("비어 있지 않은 10MB 이하 파일을 선택해주세요.");
    return;
  }
  if (!/\.(pdf|hwp|hwpx|txt)$/i.test(file.name)) {
    toast("PDF, HWP, HWPX, TXT만 지원해요.");
    return;
  }
  toast("파일을 읽고 있어요…");
  const fd = new FormData();
  fd.append("file", file, file.name);
  let extracted;
  try {
    const res = await fetch("/api/extract", { method: "POST", body: fd });
    extracted = await res.json();
    if (!res.ok) throw new Error(extracted.error || "추출 실패");
  } catch (err) {
    toast(err.message || "추출 실패");
    $("#upload").value = "";
    return;
  }
  if (extracted.scanned) {
    toast("글자를 읽을 수 없는 PDF(스캔본)예요. 텍스트로 된 PDF나 HWP를 올려 주세요.");
    $("#upload").value = "";
    return;
  }
  const text = (extracted.pages || []).map((p) => p.text || "").join("\n");
  if (!text.trim()) {
    toast("추출된 텍스트가 없어요.");
    $("#upload").value = "";
    return;
  }
  const id = crypto.randomUUID();
  const d = {
    id,
    file,
    title: file.name,
    createdAt: Date.now(),
    text,
    kind: extracted.kind,
    pages: extracted.pages,
    chars: extracted.chars,
    domainGuess: extracted.domain_guess,
    fileId: extracted.file_id || null,
    url: /\.pdf$/i.test(file.name) ? URL.createObjectURL(file) : null,
  };
  uploadedDocuments.unshift(d);
  $("#upload").value = "";
  activeDocumentId = id;
  customFile = file;
  customUrl = d.url;
  axSession = {
    status: "domain",
    isUser: true,
    docId: id,
    sampleId: id,
    title: file.name,
    text,
    kind: extracted.kind,
    file,
    pages: extracted.pages,
    domainGuess: extracted.domain_guess,
    domain: extracted.domain_guess?.confident ? extracted.domain_guess.domain : null,
    domainLabel: extracted.domain_guess?.label || "",
    fileId: extracted.file_id || null,
  };
  if (extracted.ttl_notice) toast(extracted.ttl_notice);
  tab = "overview";
  drawList();
  drawViewer();
  render();
  document.dispatchEvent(new CustomEvent("contract-ax-status", { detail: axSession }));
  if (extracted.domain_guess?.out_of_scope) {
    toast("지금은 근로·임대차·차용 계약서만 분석해요.");
    return;
  }
  if (axSession.domain && extracted.domain_guess?.confident) {
    startUserAnalyze();
  } else {
    toast("계약서 종류를 확인해 주세요.");
  }
}

async function receivePasteText(raw) {
  const text = (raw || "").trim();
  if (!text) {
    toast("텍스트를 붙여넣어 주세요.");
    return;
  }
  if (new Blob([text]).size > 10 * 1024 * 1024) {
    toast("10MB 이하로 붙여넣어 주세요.");
    return;
  }
  let guess;
  try {
    guess = await (await fetch("/api/domain", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) })).json();
  } catch {
    guess = { domain: null, confident: false, scores: {} };
  }
  const id = crypto.randomUUID();
  const d = {
    id,
    file: null,
    title: "붙여넣은 텍스트",
    createdAt: Date.now(),
    text,
    kind: "txt",
    pages: [{ page: 1, text }],
    chars: text.length,
    domainGuess: guess,
  };
  uploadedDocuments.unshift(d);
  activeDocumentId = id;
  customFile = null;
  customUrl = null;
  axSession = {
    status: "domain",
    isUser: true,
    docId: id,
    sampleId: id,
    title: d.title,
    text,
    kind: "txt",
    file: null,
    pages: d.pages,
    domainGuess: guess,
    domain: guess?.confident ? guess.domain : null,
    domainLabel: guess?.label || "",
  };
  tab = "overview";
  drawList();
  drawViewer();
  render();
  document.dispatchEvent(new CustomEvent("contract-ax-status", { detail: axSession }));
  if (guess?.out_of_scope) {
    toast("지금은 근로·임대차·차용 계약서만 분석해요.");
    return;
  }
  if (axSession.domain && guess?.confident) startUserAnalyze();
  else toast("계약서 종류를 확인해 주세요.");
}

async function startUserAnalyze() {
  if (!axSession?.text) return;
  if (!axSession.domain) {
    axSession.status = "domain";
    drawList();
    drawViewer();
    render();
    toast("계약서 종류를 선택해 주세요.");
    return;
  }
  const text = axSession.text;
  const domain = axSession.domain;
  const title = axSession.title;
  const kind = axSession.kind;
  const file = axSession.file;
  const docId = axSession.docId;
  const pages = axSession.pages;
  const domainGuess = axSession.domainGuess;
  axSession = {
    status: "loading",
    isUser: true,
    docId,
    sampleId: docId,
    title,
    text,
    kind,
    file,
    pages,
    domain,
    domainLabel: domainLabelKo(domain),
    domainGuess,
    progress: { n_clauses: 0, done: 0 },
  };
  const doc = uploadedDocuments.find((d) => d.id === docId);
  if (doc) doc.session = axSession;
  tab = "overview";
  showProgress(`분석 중(약 ${Math.ceil(8 * secPerClause)}초 예상)`);
  drawList();
  drawViewer();
  render();
  document.dispatchEvent(new CustomEvent("contract-ax-status", { detail: axSession }));
  toast("분석을 시작했어요.");
  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, no_llm: false, domain, file_id: axSession.fileId || null }),
    });
    if (res.status === 401) {
      location.href = "/login";
      return;
    }
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
        if (ev === "progress" || ev === "clause") {
          axSession.progress = {
            n_clauses: js.n_clauses || axSession.progress?.n_clauses || 0,
            done: js.done || axSession.progress?.done || 0,
          };
          const n = axSession.progress.n_clauses || 0;
          const doneN = axSession.progress.done || 0;
          const eta = n ? Math.ceil((n - doneN) * secPerClause) : 0;
          showProgress(
            n
              ? doneN
                ? `분석 중 ${doneN}/${n} · 약 ${eta}초 남음`
                : `분석 중(조항 ${n}개, 약 ${Math.ceil(n * secPerClause)}초 예상)`
              : "분석 중…"
          );
          if (tab === "overview") render();
        }
        if (ev === "meta" && js.demo_notice) {
          axSession.demoNotice = js.demo_notice;
        }
        if (ev === "saved") {
          axSession.reviewId = js.review_id;
          window.__lastReviewId = js.review_id;
          if (typeof refreshReviewHistory === "function") refreshReviewHistory();
          window.__lastReviewId = js.review_id;
        }
        if (ev === "done") report = js.report || js;
      }
    }
    if (!report) throw new Error("리포트를 받지 못했습니다.");
    axSession.status = "done";
    axSession.report = report;
    axSession.risks = cardsToRisks(report.cards || report.findings || []);
    await attachHighlights(axSession);
    if (doc) doc.session = axSession;
    tab = "risks";
    showProgress("");
    drawList();
    drawViewer();
    render();
    document.dispatchEvent(new CustomEvent("contract-ax-status", { detail: axSession }));
    toast("분석이 끝났어요.");
  } catch (err) {
    axSession.status = "error";
    axSession.error = err && err.message ? err.message : String(err);
    showProgress("");
    drawList();
    drawViewer();
    render();
    document.dispatchEvent(new CustomEvent("contract-ax-status", { detail: axSession }));
    toast("분석 실패");
  }
}

function riskLocateNeedles(r) {
  const out = [];
  const q = (r._quote || "").trim();
  const t = (r._text || "").trim();
  if (q && q !== "(인용 없음)") out.push(q);
  if (t) {
    for (const n of [40, 30, 20, 15]) {
      const piece = t.slice(0, n);
      if (piece.length >= 8 && !out.includes(piece)) out.push(piece);
    }
  }
  return out;
}

async function attachHighlights(session) {
  const risks = session.risks || [];
  session.locateTotal = risks.length;
  session.locateFound = 0;
  session.locateRatio = 0;
  if (session.kind === "pdf" && session.file) {
    try {
      const needles = [];
      const owner = [];
      for (const r of risks) {
        for (const n of riskLocateNeedles(r)) {
          needles.push(n);
          owner.push(r.id);
        }
      }
      const fd = new FormData();
      fd.append("file", session.file, session.file.name);
      fd.append("quotes", JSON.stringify(needles));
      const loc = await (await fetch("/api/locate", { method: "POST", body: fd })).json();
      const byNeedle = {};
      for (const item of loc.items || []) {
        if (item.found && item.rects?.length) byNeedle[item.quote] = item.rects;
      }
      let found = 0;
      for (const r of risks) {
        let rects = null;
        for (const n of riskLocateNeedles(r)) {
          const key = n.slice(0, 80);
          rects = byNeedle[key] || byNeedle[n.slice(0, 30)] || byNeedle[n];
          if (rects?.length) break;
        }
        if (rects?.length) {
          found += 1;
          r.highlights = rects.map((x) => ({ x: x.x, y: x.y, width: x.width, height: x.height, page: x.page }));
          r.page = rects[0].page || 1;
        }
      }
      session.locateFound = found;
      session.locateTotal = risks.length;
      session.locateRatio = risks.length ? found / risks.length : 0;
      const fd2 = new FormData();
      fd2.append("file", session.file, session.file.name);
      fd2.append("max_pages", "8");
      const rendered = await (await fetch("/api/pdf_pages", { method: "POST", body: fd2 })).json();
      if (rendered.pages?.length) session.pdfPages = rendered.pages;
    } catch {
      /* 하이라이트 실패해도 분석 결과는 유지 */
      session.locateRatio = null;
    }
  } else {
    const raw = session.text || "";
    let found = 0;
    for (const r of risks) {
      const ok = riskLocateNeedles(r).some(
        (q) => raw.includes(q) || raw.includes(q.slice(0, 30)) || raw.includes(q.slice(0, 15))
      );
      if (ok) found += 1;
    }
    session.locateFound = found;
    session.locateTotal = risks.length;
    session.locateRatio = risks.length ? found / risks.length : 0;
  }
}

$("#upload").onchange = (e) => receiveFile(e.target.files[0]);

$("#pasteBtn").onclick = () => {
  const dlg = $("#pasteDialog");
  $("#pasteText").value = "";
  if (dlg.showModal) dlg.showModal();
  else toast("이 브라우저는 붙여넣기 창을 지원하지 않아요.");
};
$("#pasteCancel").onclick = () => $("#pasteDialog").close();
$("#pasteForm").onsubmit = (e) => {
  e.preventDefault();
  const t = $("#pasteText").value;
  $("#pasteDialog").close();
  receivePasteText(t);
};

async function runAxAnalyze(msg) {
  const sampleId = msg.sampleId;
  const title = msg.title || "샘플 분석";
  axSession = { status: "loading", sampleId, title, text: "", domainLabel: msg.domainLabel || "", isUser: false };
  customFile = null;
  customUrl = null;
  activeDocumentId = null;
  activeRiskId = null;
  tab = "overview";
  drawList();
  drawViewer();
  render();
  document.dispatchEvent(new CustomEvent("contract-ax-status", { detail: axSession }));
  toast("EXAONE 분석을 시작했어요.");
  try {
    const row = await (await fetch("/api/samples/" + encodeURIComponent(sampleId))).json();
    const text = row.text || "";
    if (!text) throw new Error("샘플 계약서가 비어 있습니다.");
    axSession.text = text;
    drawViewer();
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, no_llm: false, domain: msg.domain || null }),
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
    axSession.kind = "txt";
    await attachHighlights(axSession);
    tab = "risks";
    drawList();
    drawViewer();
    render();
    document.dispatchEvent(new CustomEvent("contract-ax-status", { detail: axSession }));
    toast("EXAONE 분석이 끝났어요.");
  } catch (err) {
    axSession.status = "error";
    axSession.error = err && err.message ? err.message : String(err);
    drawList();
    drawViewer();
    render();
    document.dispatchEvent(new CustomEvent("contract-ax-status", { detail: axSession }));
    toast("분석 실패");
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
      `(계)약한청년들 | ${axSession.title}\n\nEXAONE 분석 결과입니다. 법률 자문이 아닙니다.\n` +
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
    a.download = `계약검토_AX_${(axSession.sampleId || "user").toString().slice(0, 8)}.txt`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    toast("리포트를 저장했어요.");
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
  if (customFile && !(axSession?.pdfPages?.length)) return;
  const list = axSession?.status === "done" ? axSession.risks : customFile ? [] : risks();
  list
    .filter((r) => (r.page || 1) === page)
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
  if (axSession?.pdfPages?.length) {
    page = risk.page || page;
    drawViewer();
  } else if (axSession) highlightAxQuote(id);
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
  if (axSession?.pdfPages?.length) {
    activeRiskId = id;
    page = risk.page || 1;
    pendingDocumentFocus = true;
    drawViewer();
    $("#jumpNotice").textContent = risk.page + "쪽의 관련 문장을 강조했어요";
    if ($("#pageImage").complete) requestAnimationFrame(scrollToHighlight);
    return;
  }
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

fetch("/api/health")
  .then((r) => r.json())
  .then((h) => {
    if (h.sec_per_clause) secPerClause = h.sec_per_clause;
  })
  .catch(() => {});

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

window.getAxSession = () => axSession;
window.getReviewRisks = () => risks();
window.__mvpReceiveFile = receiveFile;
window.__mvpReceivePaste = receivePasteText;
