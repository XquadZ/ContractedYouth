const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const samples = (window.CONTRACT_SAMPLES || []).filter((s) => s && s.id !== "sale");
let selected = 0,
  activeHistoryId = null,
  reviewHistory = [];
  page = 1,
  zoom = 100,
  tab = "risks",
  filter = "all",
  customFile = null,
  customUrl = null;
let activeRiskId = null,
  pendingDocumentFocus = false,
  activeDocumentId = null;
/** ?몄뀡 硫붾え由щ쭔 ??IndexedDB/?붿뒪?????????*/
const uploadedDocuments = [];
const answers = new Set();
/** @type {null | object} */
let axSession = null;
let secPerClause = 2.64;
const OUT_OF_CORPUS_RE = /誘쇰쾿\s*??s*(618|397|568|580)\s*議?誘쇨컙?꾨?二쇳깮|?쒗뻾??s*??s*(38|40)\s*議?;

const esc = (v) =>
  String(v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
/** UTC ISO ??Asia/Seoul ?쒖떆 (??κ컪? 洹몃?濡? */
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
  domain: "怨꾩빟 ?좏삎",
  hourly_wage: "?쒓툒(??",
  monthly_wage: "?붽툒(??",
  work_days_per_week: "二?洹쇰줈??,
  work_hours_per_day: "??洹쇰줈?쒓컙",
  break_minutes: "?닿쾶(遺?",
  weekly_scheduled_hours: "1二??뚯젙洹쇰줈?쒓컙",
  weekly_hours_formula: "1二??쒓컙 怨꾩궛??,
  regular_workers: "?곸떆洹쇰줈?먯닔",
  probation_months: "?섏뒿 湲곌컙(媛쒖썡)",
  probation_cut_rate: "?섏뒿 媛먯븸瑜?,
  contract_period: "怨꾩빟 湲곌컙",
  contract_months: "怨꾩빟湲곌컙(媛쒖썡)",
  apply_year: "?곸슜 ?곕룄",
  deposit: "蹂댁쬆湲???",
  down_payment: "怨꾩빟湲???",
  balance: "?붽툑(??",
  monthly_rent: "?붿꽭(??",
  maintenance_fee: "愿由щ퉬(??",
  lease_period: "?꾨?李?湲곌컙",
  rent_increase_rate: "利앹븸瑜?,
  principal: "?먭툑(??",
  interest_rate: "?댁옄??,
  delay_interest_rate: "吏???댁쑉",
  repay_date: "蹂?쒓린",
  start_date: "怨꾩빟 ?쒖옉??,
  end_date: "怨꾩빟 醫낅즺??,
  date_source: "?좎쭨 異쒖쿂 臾몄옣",
  continuous_service_months: "怨꾩냽洹쇰줈 媛쒖썡",
  is_simple_labor: "?⑥닚?몃Т ?щ?",
  is_employee: "洹쇰줈???щ?",
  is_part_time: "?⑥떆媛??щ?",
  agreed_scheduled_hours: "?쎌젙 ?뚯젙洹쇰줈?쒓컙",
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
function source(p, label = "?먮Ц 蹂닿린", riskId = null) {
  return `<button class="source" data-page="${p}" ${riskId ? `data-risk-source="${riskId}"` : ""}>??${esc(label)} 쨌 ${p}履???/button>`;
}
function riskBadge(r) {
  return `<span class="badge ${r.level === "high" ? "high" : r.level === "info" ? "neutral" : "warn"}">${
    r.level === "high" ? "?곗꽑 ?뺤씤" : r.level === "info" ? "李멸퀬" : "?뺤씤 ?꾩슂"
  }</span><span class="badge ok">${axSession ? (axSession.isUser ? "???뚯씪 遺꾩꽍" : "EXAONE 遺꾩꽍") : "?먮낯 李멸퀬"}</span>`;
}

function verdictLevel(v) {
  if (v === "?꾨컲" || v === "?꾪뿕") return "high";
  if (v === "?뺤씤 ?꾩슂") return "check";
  return "info";
}

function domainLabelKo(id) {
  return { LAB: "洹쇰줈", LEASE: "?꾨?李?, LOAN: "李⑥슜" }[id] || id || "";
}

function cardsToRisks(cards) {
  return (cards || [])
    .filter((c) => (c.verdict || "") !== "臾몄젣 ?놁쓬")
    .map((c, i) => {
      const quote = (c.contract_quote || c.clause_text || "").trim();
      const evidence = (c.evidence || []).map((e) => ({
        title: `${e.source_tag ? e.source_tag + " " : ""}${e.title || e.id || "洹쇨굅"}`.trim(),
        url: e.url || "#",
        summary: e.quote || "",
        connection: "寃利앹쓣 ?듦낵??corpus 洹쇨굅?낅땲??",
        source_tag: e.source_tag || "",
        id: e.id || "",
      }));
      return {
        id: "ax-" + (c.segment_id || i),
        level: verdictLevel(c.verdict),
        title: (c.article_title || c.segment_id || `議고빆 ${i + 1}`).toString().slice(0, 80),
        clause: c.verdict || "?뺤씤 ?꾩슂",
        quote: quote.slice(0, 220) || "(?몄슜 ?놁쓬)",
        explain: c.why || c.gap || "",
        suggest: c.suggestion || "",
        question: c.suggestion
          ? `??{(c.article_title || "??議고빆").toString().slice(0, 40)}?띿뿉 ????곷?諛⑷낵 ?대젃寃??묒쓽?대낵 ???덉뼱??`
          : "??議고빆???섎?? ?곸슜 踰붿쐞瑜??곷?諛⑹뿉寃??뺤씤?대낫?몄슂.",
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
    el.innerHTML = `<b>吏湲덉? 洹쇰줈쨌?꾨?李㉱룹감??怨꾩빟?쒕쭔 遺꾩꽍?댁슂.</b>
      <span>${esc(guess.reason || "")}</span>
      <div class="domain-choices">${["LAB", "LEASE", "LOAN"]
        .map((id) => `<button type="button" data-domain-pick="${id}">${domainLabelKo(id)}濡?遺꾩꽍</button>`)
        .join("")}<button type="button" data-domain-cancel>?リ린</button></div>`;
    bindDomainBanner();
    return;
  }
  const label = domainLabelKo(chosen || guess?.domain) || "誘몄젙";
  el.hidden = false;
  el.innerHTML = `<span><b>${esc(label)}怨꾩빟?쒕줈 ?몄떇?덉뼱??/b> <button type="button" data-domain-change>諛붽씀湲?/button></span>
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
          toast("醫낅쪟瑜?諛붽엥?댁슂. ?ㅼ떆 遺꾩꽍?⑸땲??");
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
            ? "遺꾩꽍 ?꾨즺"
            : axSession.status === "loading"
              ? "遺꾩꽍 以?
              : axSession.status === "domain"
                ? "醫낅쪟 ?뺤씤"
                : "?湲?
          : "???뚯씪";
      return `<button class="sample uploaded-document ${active ? "active" : ""}" data-document="${d.id}" aria-pressed="${active}"><span class="file-icon">??/span><span><b>${esc(
        d.title || d.file?.name || "??怨꾩빟??
      )}</b><small><span class="mine-tag">???뚯씪</span> 쨌 ${esc(st)}</small></span></button>`;
    })
    .join("");
  const axBtn =
    axSession && !axSession.isUser
      ? `<button class="sample active ax-sample" data-ax="1" aria-pressed="true"><span class="file-icon">??/span><span><b>EXAONE 遺꾩꽍</b><small>${esc(
          axSession.status === "done" ? "遺꾩꽍 ?꾨즺" : axSession.status === "error" ? "?ㅽ뙣" : "遺꾩꽍 以?
        )}</small></span><span class="num">AI</span></button>`
      : "";
  $("#sampleList").innerHTML =
    (userDocs ? '<div class="uploaded-list-label">??怨꾩빟??/div>' + userDocs : "") +
    axBtn +
    '<div class="uploaded-list-label">?덉떆 ?섑뵆</div>' +
    samples
      .map(
        (s, i) =>
          `<button class="sample ${i === selected && !customFile && !axSession ? "active" : ""}" data-sample="${i}" aria-pressed="${
            i === selected && !customFile && !axSession
          }"><span class="file-icon">??/span><span><b>${esc(s.short)}</b><small>${s.count}履?쨌 ?덉떆</small></span><span class="num">0${i + 1}</span></button>`
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
  if (grade === "?꾪뿕") return "hist-grade risk";
  if (grade === "二쇱쓽") return "hist-grade caution";
  if (grade === "?덉쟾") return "hist-grade safe";
  return "hist-grade";
}

function historyTitle(row) {
  if (row.filename) return row.filename;
  const dom = domainLabelKo(row.domain) || row.domain || "寃??;
  return `${dom} 쨌 ${formatSeoul(row.created_at)}`;
}

function drawReviewHistory() {
  const box = $("#reviewHistoryList");
  if (!box) return;
  if (!reviewHistory.length) {
    box.innerHTML = `<p class="side-note">?꾩쭅 寃?좏븳 怨꾩빟?쒓? ?놁뼱??/p>`;
    return;
  }
  box.innerHTML = reviewHistory
    .map((r) => {
      const active = activeHistoryId === r.id;
      return `<button type="button" class="sample history-item ${active ? "active" : ""}" data-history="${r.id}" aria-pressed="${active}"><span class="file-icon">??/span><span><b>${esc(
        historyTitle(r)
      )}</b><small><span class="${gradeBadgeClass(r.grade)}">${esc(r.grade || "-")}</span> 쨌 ${esc(
        String(r.score ?? "-")
      )}??쨌 ${esc(formatSeoul(r.created_at))}</small></span></button>`;
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
      title: historyTitle(detail.review || {}) || "湲곕줉 #" + id,
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
    toast("湲곕줉???댁? 紐삵뻽?댁슂");
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
          ? "EXAONE 遺꾩꽍 쨌 ?낅줈???먮낯? ?뷀샇?뷀빐 蹂닿??섍퀬 24?쒓컙 ???먮룞 ??젣?쇱슂"
          : "EXAONE 遺꾩꽍 쨌 ?낅줈???먮낯? ?뷀샇?뷀빐 蹂닿??섍퀬 24?쒓컙 ???먮룞 ??젣?쇱슂"
        : axSession.status === "error"
          ? "遺꾩꽍???ㅽ뙣?덉뼱??
          : axSession.status === "domain"
            ? "怨꾩빟??醫낅쪟瑜??뺤씤??二쇱꽭??
            : "怨꾩빟?쒕? 遺꾩꽍?섎뒗 以묅?;
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
      $("#pageImage").alt = `${axSession.title} ${page}履?;
      pageCanvas.style.width = zoom + "%";
      drawHighlights();
      $("#pageStrip").innerHTML = pages
        .map(
          (p, i) =>
            `<button data-view-page="${i + 1}" class="${page === i + 1 ? "active" : ""}" aria-label="?먮낯 ${i + 1}履?>${i + 1}</button>`
        )
        .join("");
      $$("[data-view-page]").forEach((b) => (b.onclick = () => jump(+b.dataset.viewPage, false)));
      return;
    }

    $("#pageCount").textContent = axSession.kind === "pdf" ? "PDF ?띿뒪?? : "?띿뒪???먮Ц";
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
  const textOnlySample = !customFile && s && (s.id === "loan" || s.bodyText);
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
    $("#pageCount").textContent = "?띿뒪???먮Ц";
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
  $("#contractDesc").textContent = customFile ? "??怨꾩빟??쨌 遺꾩꽍 ?湲? : s.subtitle;
  $("#pageCount").textContent = customFile ? "濡쒖뺄 ?뚯씪" : `${s.count} pages`;
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
        textStage.innerHTML = `<pre class="ax-contract-text">?뚯씪??遺꾩꽍?섎㈃ ?띿뒪?멸? ?ш린???쒖떆?⑸땲??</pre>`;
      }
    }
    return;
  }
  customPdf.removeAttribute("src");
  $("#pageImage").src = `assets/contracts/${s.id}-${page}.jpg`;
  $("#pageImage").alt = `${s.name} ?먮낯 ${page}履?;
  pageCanvas.style.width = zoom + "%";
  drawHighlights();
  $("#pageStrip").innerHTML = Array.from(
    { length: s.count },
    (_, i) =>
      `<button data-view-page="${i + 1}" class="${page === i + 1 ? "active" : ""}" aria-label="?먮낯 ${i + 1}履? aria-current="${
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
  if (!risk || !risk._quote || risk._quote === "(?몄슜 ?놁쓬)") {
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
  $("#jumpNotice").textContent = explain ? `${p}履??먮Ц?쇰줈 ?대룞?덉뼱?? : "";
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
      ? `<p class="muted">?먮Ц ?섏씠?쇱씠??李얠? 鍮꾩쑉: ${Math.round((axSession.locateRatio || 0) * 100)}% (${axSession.locateFound || 0}/${
          axSession.locateTotal || 0
        })</p>`
      : "";
  const score = axSession.report?.score;
  const grade = axSession.report?.grade || "";
  const scoreNote =
    axSession.report?.score_detail?.score_note ||
    axSession.report?.score_note ||
    "?뺤씤??議고빆??3媛??댁긽?대㈃ '二쇱쓽'濡??쒖떆?댁슂.";
  const scoreBlock =
    score != null
      ? `<div class="summary-state score-gauge"><div class="ring">${esc(String(score))}</div><div><b>${esc(grade)}</b><p>?먯닔 ${esc(
          String(score)
        )}??쨌 ?꾨컲 ${s.n_violation || 0} 쨌 ?꾪뿕 ${s.n_risk || 0} 쨌 ?뺤씤 ${s.n_review || 0}</p><p class="muted">${esc(
          scoreNote
        )}</p>${
          grade === "?덉쟾"
            ? `<p class="muted">踰?湲곗????닿릿 議고빆??李얠? 紐삵뻽?ㅻ뒗 ?살씠硫? 踰뺣쪧 ?먮Ц???꾨땲?먯슂.</p>`
            : ""
        }</div></div>`
      : `<div class="summary-state"><div class="ring">遺꾩꽍</div><div><b>?먯젙 議곌컖 ${s.n_segments || 0}媛?/b><p>?꾨컲 ${
          s.n_violation || 0
        } 쨌 ?꾪뿕 ${s.n_risk || 0} 쨌 ?뺤씤 ?꾩슂 ${s.n_review || 0} 쨌 臾몄젣 ?놁쓬 ${s.n_ok || 0}</p></div></div>`;
  const demo = axSession.report?.demo_notice
    ? `<p class="muted">${esc(axSession.report.demo_notice)}</p>`
    : "";
  const modelName = axSession.report?.model || "濡쒖뺄 紐⑤뜽";
  return `<span class="section-kicker">CONTRACT REPORT</span><h2>?쒕챸 ?? ?댄렣蹂?寃곌낵?덉슂.</h2><p class="muted">${esc(
    axSession.title
  )} 쨌 紐⑤뜽 ${esc(modelName)} 쨌 ${esc(domainLabelKo(axSession.domain) || "")}</p>${demo}${hl}${scoreBlock}<div class="metrics"><div class="metric red"><b>${
    (s.n_violation || 0) + (s.n_risk || 0)
  }</b><span>?꾨컲쨌?꾪뿕</span></div><div class="metric warn"><b>${s.n_review || 0}</b><span>?뺤씤 ?꾩슂</span></div><div class="metric"><b>${
    rs.length
  }</b><span>寃??移대뱶</span></div></div>${
    factRows ? `<div class="section-label">異붿텧???ъ떎</div><div class="info-grid">${factRows}</div>` : ""
  }<div class="insight"><span>??/span><div><b>??寃곌낵???댄빐瑜??뺣뒗 ?뺣낫?덉슂</b><p>${esc(
    axSession.report?.disclaimer || "踰뺣쪧 ?먮Ц???꾨떃?덈떎."
  )}</p></div></div><div class="section-label">癒쇱? 蹂대㈃ 醫뗭? ?댁슜 <button data-open-tab="risks">?꾩껜 蹂닿린 ??/button></div>${rs
    .slice(0, 3)
    .map((r) => `<button class="quick" data-risk-jump="${r.id}"><span>??/span>${esc(r.title)}<span>蹂닿린 ??/span></button>`)
    .join("")}`;
}

function axComplete() {
  const missing = axSession.report?.missing || [];
  if (!missing.length)
    return `<span class="section-kicker">COMPLETENESS</span><h2>?꾩닔 議고빆 ?꾧껐??/h2><div class="complete-success" role="status">???쒖떆???꾨씫 ??ぉ???놁뼱??</div>`;
  return `<span class="section-kicker">COMPLETENESS</span><h2>?꾩닔 議고빆 ?꾧껐??/h2><p class="muted">?꾨씫쨌異붽? ?뺤씤 ?꾨낫 ${missing.length}媛?/p>${missing
    .map(
      (m) =>
        `<article class="check-row"><div class="check-top"><b>??&nbsp; ${esc(m.label || m.std_item || m.id || "??ぉ")}</b><span class="badge warn">?뺤씤</span></div><p>${esc(
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
        ? `議고빆 ${done}/${n} 쨌 ??${eta}珥??⑥쓬`
        : `遺꾩꽍 以?議고빆 ${n}媛? ??${Math.ceil(n * secPerClause)}珥??덉긽)`
      : `遺꾩꽍 以???${eta}珥??덉긽)`;
  return `<span class="section-kicker">ANALYSIS</span><h2>怨꾩빟?쒕? 遺꾩꽍?섍퀬 ?덉뼱??/h2><div class="document-status"><span>??/span><div><b>EXAONE 遺꾩꽍 以?/b><p>${esc(
    axSession.title
  )}</p><p>${esc(detail)}</p></div></div><div class="custom-note">媛숈? 寃???뚰겕?ㅽ럹?댁뒪?먯꽌 寃곌낵媛 梨꾩썙吏묐땲??</div><div class="pending-checks"><div>議고빆 遺꾪븷 쨌 寃??<span>吏꾪뻾</span></div><div>?먯젙 <span>${done || "??}/${n || "?"}</span></div><div>洹쇨굅 寃利?<span>吏꾪뻾</span></div></div>`;
}

function axError() {
  return `<span class="section-kicker">ANALYSIS</span><h2>遺꾩꽍??留덉튂吏 紐삵뻽?댁슂</h2><div class="custom-note">${esc(
    axSession.error || "?????녿뒗 ?ㅻ쪟"
  )}</div>`;
}

function axDomainPick() {
  return `<span class="section-kicker">醫낅쪟 ?뺤씤</span><h2>怨꾩빟??醫낅쪟瑜??뺤씤??二쇱꽭??/h2><div class="custom-note">?곷떒 諛곕꼫?먯꽌 醫낅쪟瑜?怨좊Ⅴ硫?遺꾩꽍???쒖옉?⑸땲?? 吏湲덉? 洹쇰줈쨌?꾨?李㉱룹감?⑸쭔 吏?먰빐??</div>`;
}

function overview() {
  if (axSession?.status === "loading") return axLoading();
  if (axSession?.status === "error") return axError();
  if (axSession?.status === "domain") return axDomainPick();
  if (axSession?.status === "done") return axOverview();
  const s = data(),
    done = s.checks.filter((c) => c[3]).length,
    rs = risks();
  return `<span class="section-kicker">YOUR CONTRACT, AT A GLANCE</span><h2>?쒕챸 ?? ?④퍡 ?뺤씤?대킄??</h2><p class="muted">${esc(
    s.profile
  )}</p><div class="summary-state"><div class="ring">?뺤씤</div><div><b>${6 - done}媛??묒꽦쨌議곌굔 ??ぉ???댄렣蹂댁꽭??/b><p>?꾩닔 ?뺤씤 紐⑸줉 6媛?以?臾몄옣쨌湲곗엯 ?뺤씤 ${done}媛?br>怨꾩빟???덉쟾?깆쓣 ?먯닔濡??먯젙??寃곌낵???꾨땲?먯슂.</p></div></div><div class="metrics"><div class="metric"><b>${done}/6</b><span>?뺤씤 紐⑸줉 異⑹”</span></div><div class="metric warn"><b>${
    rs.filter((r) => r.level === "check").length
  }</b><span>?먮낯 ?뺤씤 ?ъ씤??/span></div><div class="metric red"><b>${
    rs.filter((r) => r.evidence?.length).length
  }</b><span>踰뺣쪧 洹쇨굅 ?곌껐 ??ぉ</span></div></div><div class="section-label">怨꾩빟 ?듭떖 ?뺣낫 <button data-open-tab="complete">誘몄땐議???ぉ 蹂닿린 ??/button></div><div class="info-grid">${s.fields
    .map((f) => `<div><small>${esc(f[0])}</small><b class="${/?꾩슂/.test(f[1]) ? "blank" : ""}">${esc(f[1])}</b></div>`)
    .join(
      ""
    )}</div><div class="insight"><span>??/span><div><b>??怨꾩빟, ?대젃寃??쎌뼱蹂댁꽭??/b><p>${esc(
    s.insight
  )}</p></div></div><div class="section-label">癒쇱? ?뺤씤?섎㈃ 醫뗭? ?댁슜 <button data-open-tab="risks">?꾩껜 蹂닿린 ??/button></div>${s.risks
    .slice(0, 2)
    .map((r) => `<button class="quick" data-page="${r.page}"><span>??/span>${esc(r.title)}<span>${r.page}履???/span></button>`)
    .join("")}`;
}

function complete() {
  if (axSession?.status === "loading") return axLoading();
  if (axSession?.status === "error") return axError();
  if (axSession?.status === "domain") return axDomainPick();
  if (axSession?.status === "done") return axComplete();
  const missing = data().checks.filter((c) => !c[3]);
  return `<span class="section-kicker">COMPLETENESS CHECK</span><h2>?꾩닔 議고빆 ?꾧껐??寃??/h2>${
    missing.length
      ? `<p class="muted">誘몄땐議굿룹텛媛 ?뺤씤???꾩슂??<b>${missing.length}媛???ぉ留?/b> ?쒖떆?⑸땲?? 異⑹”????ぉ???댁슜? ?쒖떆?섏? ?딆븘??</p>${missing
          .map(
            (c) =>
              `<article class="check-row"><div class="check-top"><b>??&nbsp; ${esc(c[0])}</b><span class="badge warn">?묒꽦쨌議곌굔 ?뺤씤</span></div><p>${esc(
                c[2]
              )}</p>${source(c[1], c[4])}</article>`
          )
          .join("")}`
      : '<div class="complete-success" role="status">???꾩닔 ?뺤씤 紐⑸줉?먯꽌 誘몄땐議???ぉ???놁뼱??</div>'
  }`;
}

function evidenceBlock(r) {
  if (!r.evidence?.length) {
    if (axSession?.status === "done")
      return `<section class="legal-evidence"><div class="legal-title">??愿??踰뺣쪧 쨌 寃??洹쇨굅</div><p class="no-evidence">洹쇨굅瑜?李얠? 紐삵빐 吏곸젒 ?뺤씤???꾩슂?댁슂</p></section>`;
    return "";
  }
  const sampleMode = !axSession;
  return `<section class="legal-evidence"><div class="legal-title">??愿??踰뺣쪧 쨌 寃??洹쇨굅</div>${r.evidence
    .map((e) => {
      const ooc = sampleMode && OUT_OF_CORPUS_RE.test(e.title || "");
      return `<div class="legal-ref"><a href="${esc(e.url)}" target="_blank" rel="noopener">${esc(e.title)} ??/a>${
        ooc ? `<span class="ooc-badge">洹쇨굅 ?먮즺 諛?議곕Ц(李멸퀬)</span>` : ""
      }<p>${esc(e.summary)}</p><div class="legal-connection"><b>??議고빆怨??곌껐?섎뒗 ?댁쑀</b><p>${esc(e.connection)}</p></div></div>`;
    })
    .join("")}<small>${
    sampleMode
      ? "異쒖쿂: ?덉떆 ?ㅻ챸<br>誘몃━ ?묒꽦???섑뵆 ?붾㈃?낅땲??"
      : "異쒖쿂: 援??踰뺣졊?뺣낫?쇳꽣 / 寃利앸맂 corpus 洹쇨굅<br>愿??洹쒖젙??議댁옱媛 ?대떦 怨꾩빟???꾨쾿?깆쓣 怨㏓컮濡??섎??섏????딆뒿?덈떎."
  }</small></section>`;
}

function riskCard(r) {
  return `<article class="risk ${activeRiskId === r.id ? "risk-selected" : ""}" id="risk-${r.id}" tabindex="-1"><div class="risk-top">${riskBadge(
    r
  )}<span style="font-size:9px;color:#a0abc0">${esc(r.clause)}</span></div><h3>${esc(r.title)}</h3><blockquote>${esc(
    r.quote
  )}</blockquote><p>${esc(r.explain)}</p>${
    axSession
      ? `<button class="source" data-risk-source="${r.id}">???먮Ц?먯꽌 李얘린 ??/button>`
      : source(r.page, "?먮Ц 蹂닿린", r.id)
  }${evidenceBlock(r)}<details><summary>?섏젙쨌?묒쓽 諛⑺뼢怨??뺤씤 吏덈Ц</summary><div class="suggestion"><strong>???묒쓽 諛⑺뼢</strong><p>${esc(
    r.suggest || "?대떦 議고빆??踰붿쐞瑜?援ъ껜?곸쑝濡??곸뼱 ?щ씪怨??붿껌?대낫?몄슂."
  )}</p></div><p><b>臾쇱뼱蹂?吏덈Ц</b><br>${esc(r.question)}</p></details></article>`;
}

function riskView() {
  if (axSession?.status === "loading") return axLoading();
  if (axSession?.status === "error") return axError();
  if (axSession?.status === "domain") return axDomainPick();
  const rs = risks();
  return `<div class="review-summary"><div><span class="section-kicker">寃??寃곌낵</span><h2>?꾪뿕 議고빆 ?꾪꽣留?/h2></div><span class="result-total">珥?${
    rs.length
  }嫄?/span></div><p class="muted compact-intro">${
    axSession ? "?먯젙 移대뱶?낅땲?? ?먮Ц ?몄슜???꾨Ⅴ硫??쇱そ ?띿뒪?몃줈 ?대룞?⑸땲??" : "?먮Ц???됱긽 ?쒖떆瑜??꾨Ⅴ硫??대떦 寃????ぉ?쇰줈 ?대룞?댁슂."
  }</p><div class="filters" aria-label="?꾪뿕 議고빆 ?꾪꽣">${[
    ["all", "?꾩껜"],
    ["high", "?곗꽑 ?뺤씤"],
    ["check", "?뺤씤 ?꾩슂"],
    ["info", "李멸퀬"],
  ]
    .map(
      ([id, label]) =>
        `<button data-filter="${id}" class="${filter === id ? "active" : ""}" aria-pressed="${filter === id}">${label} ${
          rs.filter((r) => id === "all" || r.level === id).length
        }</button>`
    )
    .join("")}</div>${[
    ["high", "?곗꽑 ?뺤씤 ?ы빆"],
    ["check", "異붽? ?뺤씤 ?ы빆"],
    ["info", "李멸퀬 ?ы빆"],
  ]
    .filter(([level]) => filter === "all" || filter === level)
    .map(([level, label]) => {
      const items = rs.filter((r) => r.level === level);
      return items.length
        ? `<details class="risk-group ${level}" open><summary><span class="status-dot"></span>${label}<b>${items.length}</b><span class="chevron">??/span></summary><div class="risk-group-body">${items
            .map(riskCard)
            .join("")}</div></details>`
        : "";
    })
    .join("") || '<div class="empty">?대떦?섎뒗 ?뺤씤 ??ぉ???놁뼱??</div>'}`;
}

function questions() {
  if (axSession?.status === "loading") return axLoading();
  if (axSession?.status === "error") return axError();
  if (axSession?.status === "domain") return axDomainPick();
  const rs = risks();
  const keyPrefix = axSession ? "ax:" + axSession.sampleId : data().id;
  return `<span class="section-kicker">BEFORE YOU SIGN</span><h2>怨꾩빟 ?꾩뿉, ?대젃寃?臾쇱뼱蹂댁꽭??</h2><p class="muted">?곷?諛⑷낵 ?뺤씤??吏덈Ц??紐⑥븯?댁슂.</p>${rs
    .map((r, i) => {
      const key = keyPrefix + ":" + r.title;
      return `<article class="question"><span class="badge neutral">${axSession ? "遺꾩꽍 愿??吏덈Ц" : "?먮낯 愿??吏덈Ц"}</span><b style="margin-top:10px">${esc(
        r.question
      )}</b><div><label class="${answers.has(key) ? "done" : "muted"}"><input type="checkbox" data-answer="${esc(key)}" ${
        answers.has(key) ? "checked" : ""
      }> ?뺤씤?덉뼱??/label><button data-copy="${i}">吏덈Ц 蹂듭궗</button></div></article>`;
    })
    .join("")}`;
}

function customReport() {
  return `<span class="section-kicker">??怨꾩빟??/span><h2>遺꾩꽍 ?뚰겕?ㅽ럹?댁뒪</h2><div class="document-status"><span>??/span><div><b>遺꾩꽍 ?湲?/b><p>${esc(
    customFile.name
  )}</p></div></div><div class="custom-note">?뚯씪???대㈃ 異붿텧 ??醫낅쪟 ?뺤씤 ??遺꾩꽍???댁뼱吏묐땲??</div>`;
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
          toast("吏덈Ц??蹂듭궗?덉뼱??");
        } catch {
          toast("釉뚮씪?곗??먯꽌 蹂듭궗媛 吏?먮릺吏 ?딆븘??");
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
    toast("鍮꾩뼱 ?덉? ?딆? 10MB ?댄븯 ?뚯씪???좏깮?댁＜?몄슂.");
    return;
  }
  if (!/\.(pdf|hwp|hwpx|txt)$/i.test(file.name)) {
    toast("PDF, HWP, HWPX, TXT留?吏?먰빐??");
    return;
  }
  toast("?뚯씪???쎄퀬 ?덉뼱?붴?);
  const fd = new FormData();
  fd.append("file", file, file.name);
  let extracted;
  try {
    const res = await fetch("/api/extract", { method: "POST", body: fd });
    extracted = await res.json();
    if (!res.ok) throw new Error(extracted.error || "異붿텧 ?ㅽ뙣");
  } catch (err) {
    toast(err.message || "異붿텧 ?ㅽ뙣");
    $("#upload").value = "";
    return;
  }
  if (extracted.scanned) {
    toast("湲?먮? ?쎌쓣 ???녿뒗 PDF(?ㅼ틪蹂??덉슂. ?띿뒪?몃줈 ??PDF??HWP瑜??щ젮 二쇱꽭??");
    $("#upload").value = "";
    return;
  }
  const text = (extracted.pages || []).map((p) => p.text || "").join("\n");
  if (!text.trim()) {
    toast("異붿텧???띿뒪?멸? ?놁뼱??");
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
    toast("吏湲덉? 洹쇰줈쨌?꾨?李㉱룹감??怨꾩빟?쒕쭔 遺꾩꽍?댁슂.");
    return;
  }
  if (axSession.domain && extracted.domain_guess?.confident) {
    startUserAnalyze();
  } else {
    toast("怨꾩빟??醫낅쪟瑜??뺤씤??二쇱꽭??");
  }
}

async function receivePasteText(raw) {
  const text = (raw || "").trim();
  if (!text) {
    toast("?띿뒪?몃? 遺숈뿬?ｌ뼱 二쇱꽭??");
    return;
  }
  if (new Blob([text]).size > 10 * 1024 * 1024) {
    toast("10MB ?댄븯濡?遺숈뿬?ｌ뼱 二쇱꽭??");
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
    title: "遺숈뿬?ｌ? ?띿뒪??,
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
    toast("吏湲덉? 洹쇰줈쨌?꾨?李㉱룹감??怨꾩빟?쒕쭔 遺꾩꽍?댁슂.");
    return;
  }
  if (axSession.domain && guess?.confident) startUserAnalyze();
  else toast("怨꾩빟??醫낅쪟瑜??뺤씤??二쇱꽭??");
}

async function startUserAnalyze() {
  if (!axSession?.text) return;
  if (!axSession.domain) {
    axSession.status = "domain";
    drawList();
    drawViewer();
    render();
    toast("怨꾩빟??醫낅쪟瑜??좏깮??二쇱꽭??");
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
  showProgress(`遺꾩꽍 以???${Math.ceil(8 * secPerClause)}珥??덉긽)`);
  drawList();
  drawViewer();
  render();
  document.dispatchEvent(new CustomEvent("contract-ax-status", { detail: axSession }));
  toast("遺꾩꽍???쒖옉?덉뼱??");
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
    if (!res.ok) throw new Error("遺꾩꽍 ?붿껌 ?ㅽ뙣 (" + res.status + ")");
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
        if (ev === "error") throw new Error(js.message || "遺꾩꽍 ?ㅽ뙣");
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
                ? `遺꾩꽍 以?${doneN}/${n} 쨌 ??${eta}珥??⑥쓬`
                : `遺꾩꽍 以?議고빆 ${n}媛? ??${Math.ceil(n * secPerClause)}珥??덉긽)`
              : "遺꾩꽍 以묅?
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
    if (!report) throw new Error("由ы룷?몃? 諛쏆? 紐삵뻽?듬땲??");
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
    toast("遺꾩꽍???앸궗?댁슂.");
  } catch (err) {
    axSession.status = "error";
    axSession.error = err && err.message ? err.message : String(err);
    showProgress("");
    drawList();
    drawViewer();
    render();
    document.dispatchEvent(new CustomEvent("contract-ax-status", { detail: axSession }));
    toast("遺꾩꽍 ?ㅽ뙣");
  }
}

function riskLocateNeedles(r) {
  const out = [];
  const q = (r._quote || "").trim();
  const t = (r._text || "").trim();
  if (q && q !== "(?몄슜 ?놁쓬)") out.push(q);
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
      /* ?섏씠?쇱씠???ㅽ뙣?대룄 遺꾩꽍 寃곌낵???좎? */
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
  else toast("??釉뚮씪?곗???遺숈뿬?ｊ린 李쎌쓣 吏?먰븯吏 ?딆븘??");
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
  const title = msg.title || "?섑뵆 遺꾩꽍";
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
  toast("EXAONE 遺꾩꽍???쒖옉?덉뼱??");
  try {
    const row = await (await fetch("/api/samples/" + encodeURIComponent(sampleId))).json();
    const text = row.text || "";
    if (!text) throw new Error("?섑뵆 怨꾩빟?쒓? 鍮꾩뼱 ?덉뒿?덈떎.");
    axSession.text = text;
    drawViewer();
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, no_llm: false, domain: msg.domain || null }),
    });
    if (!res.ok) throw new Error("遺꾩꽍 ?붿껌 ?ㅽ뙣 (" + res.status + ")");
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
        if (ev === "error") throw new Error(js.message || "遺꾩꽍 ?ㅽ뙣");
        if (ev === "done") report = js.report || js;
      }
    }
    if (!report) throw new Error("由ы룷?몃? 諛쏆? 紐삵뻽?듬땲??");
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
    toast("EXAONE 遺꾩꽍???앸궗?댁슂.");
  } catch (err) {
    axSession.status = "error";
    axSession.error = err && err.message ? err.message : String(err);
    drawList();
    drawViewer();
    render();
    document.dispatchEvent(new CustomEvent("contract-ax-status", { detail: axSession }));
    toast("遺꾩꽍 ?ㅽ뙣");
  }
}

window.addEventListener("message", (e) => {
  if (e.source !== parent || e.origin !== location.origin) return;
  if (e.data?.type === "contract-review-file") receiveFile(e.data.file);
  if (e.data?.type === "contract-review-ax") runAxAnalyze(e.data);
  if (e.data?.type === "contract-review-open") {
    /* ?섑뵆 由ы룷??癒쇱? 蹂닿린 ??湲곕낯 ?섑뵆 ?좎? */
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
      `(怨??쏀븳泥?뀈??| ${axSession.title}\n\nEXAONE 遺꾩꽍 寃곌낵?낅땲?? 踰뺣쪧 ?먮Ц???꾨떃?덈떎.\n` +
      `?꾨컲 ${s.n_violation || 0} 쨌 ?꾪뿕 ${s.n_risk || 0} 쨌 ?뺤씤 ?꾩슂 ${s.n_review || 0} 쨌 臾몄젣 ?놁쓬 ${s.n_ok || 0}\n\n` +
      risks()
        .map(
          (r) =>
            `[${r.clause}] ${r.title}\n${r.quote}\n${r.explain}\n洹쇨굅: ${(r.evidence || []).map((e) => e.title).join(", ")}\n吏덈Ц: ${r.question}`
        )
        .join("\n\n");
    const url = URL.createObjectURL(new Blob(["\ufeff" + text], { type: "text/plain;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `怨꾩빟寃??AX_${(axSession.sampleId || "user").toString().slice(0, 8)}.txt`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    toast("由ы룷?몃? ??ν뻽?댁슂.");
    return;
  }
  if (customFile) {
    toast("吏곸젒 ??臾몄꽌?먮뒗 ?앹꽦??遺꾩꽍 由ы룷?멸? ?놁뼱??");
    return;
  }
  const s = data();
  const text =
    `(怨??쏀븳泥?뀈??| ${s.name}\n\n誘몃━ ?묒꽦???섑뵆 由ы룷?몄엯?덈떎. ?ㅼ젣 AI 遺꾩꽍?대굹 踰뺤쟻 ?먮떒???꾨떃?덈떎.\n?먮낯 PDF: ${s.filename}\n\n[誘몄땐議굿룹텛媛 ?뺤씤 ??ぉ]\n` +
    s.checks
      .filter((c) => !c[3])
      .map((c) => `[?묒꽦쨌議곌굔 ?뺤씤] ${c[0]} / ${c[1]}履?n${c[2]}`)
      .join("\n\n") +
    "\n\n[?꾪뿕 ??ぉ 諛?愿??踰뺣쪧]\n" +
    risks()
      .map(
        (r) =>
          `[?먮낯 李멸퀬] ${r.title}\n${r.quote}\n${r.explain}\n愿??踰뺣쪧: ${r.evidence.map((e) => e.title + " / " + e.url + " / " + e.connection).join("\n")}\n?뺤씤 吏덈Ц: ${r.question}\n?뺤씤 ?щ?: ${
            answers.has(s.id + ":" + r.title) ? "?뺤씤?? : "誘명솗??
          }\n李멸퀬 ?먮Ц: ${r.page}履?
      )
      .join("\n\n");
  const url = URL.createObjectURL(new Blob(["\ufeff" + text], { type: "text/plain;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `怨꾩빟寃??${s.short}_?섑뵆.txt`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
  toast("由ы룷?몃? ??ν뻽?댁슂.");
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
        const level = r.level === "high" ? "鍮④컯 쨌 ?곗꽑 ?뺤씤" : r.level === "info" ? "珥덈줉 쨌 李멸퀬" : "?몃옉 쨌 ?뺤씤 ?꾩슂";
        mark.setAttribute("aria-label", level + " 쨌 " + r.title + " 쨌 ?ㅻⅨ履?寃????ぉ 蹂닿린");
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
  $("#jumpNotice").textContent = axSession ? "?먮Ц?먯꽌 ?대떦 ?몄슜??媛뺤“?덉뼱?? : "?좏깮??議고빆??寃??洹쇨굅瑜??쒖떆?덉뼱??;
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
    $("#jumpNotice").textContent = risk.page + "履쎌쓽 愿??臾몄옣??媛뺤“?덉뼱??;
    if ($("#pageImage").complete) requestAnimationFrame(scrollToHighlight);
    return;
  }
  if (axSession) {
    activeRiskId = id;
    drawViewer();
    highlightAxQuote(id);
    $("#jumpNotice").textContent = "?먮Ц?먯꽌 愿??臾몄옣??媛뺤“?덉뼱??;
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
  $("#jumpNotice").textContent = risk.page + "履쎌쓽 愿??臾몄옣??媛뺤“?덉뼱??;
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
