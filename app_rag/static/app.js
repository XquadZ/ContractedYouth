const $ = (id) => document.getElementById(id);
const LABELS = { "위반": "viol", "위험": "risk", "확인 필요": "review", "문제 없음": "ok" };
const FACT_LABELS = {
  domain: "유형", hourly_wage: "시급", monthly_wage: "월급", work_days_per_week: "주 근로일",
  work_hours_per_day: "일 근로시간", break_minutes: "휴게(분)", probation_months: "수습(개월)",
  probation_cut_rate: "수습 감액", contract_period: "계약 기간", deposit: "보증금",
  down_payment: "계약금", balance: "잔금", monthly_rent: "월세", maintenance_fee: "관리비",
  lease_period: "임대차 기간", rent_increase_rate: "증액률", principal: "원금",
  interest_rate: "이자율", delay_interest_rate: "지연 이율", repay_date: "변제기",
  start_date: "시작일", end_date: "종료일", date_source: "날짜 출처", date_missing: "날짜 없음",
};
const VIEWS = ["home", "check", "guide", "faq"];
const SAMPLE_BY_DOMAIN = { LEASE: "oneroom_lease", LAB: "alba_cafe", LOAN: "" };

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function show(id, on) { $(id).hidden = !on; }

function currentView() {
  const hash = (location.hash || "#home").replace("#", "");
  return VIEWS.includes(hash) ? hash : "home";
}

function showView(name) {
  const view = VIEWS.includes(name) ? name : "home";
  VIEWS.forEach((v) => {
    const el = $("view-" + v);
    if (el) el.hidden = v !== view;
  });
  document.querySelectorAll("[data-view]").forEach((a) => {
    a.classList.toggle("on", a.getAttribute("data-view") === view);
  });
  document.body.dataset.view = view;
  if (location.hash.replace("#", "") !== view) {
    history.replaceState(null, "", "#" + view);
  }
  window.scrollTo(0, 0);
}

async function loadHealth() {
  const el = $("health");
  if (!el) return;
  try {
    const h = await (await fetch("/api/health")).json();
    el.className = "health " + (h.ax ? "up" : "down");
    el.textContent = h.ax
      ? `모델 연결 · 근거 ${h.n_records}건 · 검색 ${h.embed_ok ? "BM25+bge-m3" : "BM25"}`
      : `모델 꺼짐 · 근거 ${h.n_records}건`;
  } catch {
    el.className = "health down";
    el.textContent = "서버에 연결하지 못함";
  }
}

async function loadSample(id) {
  if (!id) return;
  const row = await (await fetch("/api/samples/" + id)).json();
  $("text").value = row.text || "";
  const box = $("sample-chips");
  if (box) {
    box.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", x.dataset.id === id ? "true" : "false"));
  }
}

function setDomain(domain) {
  document.querySelectorAll(".tab[data-domain], .domain-card[data-domain]").forEach((el) => {
    el.classList.toggle("on", el.dataset.domain === domain);
  });
}

async function loadSamples() {
  const data = await (await fetch("/api/samples")).json();
  const box = $("sample-chips");
  box.replaceChildren();
  data.samples.forEach((s) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = s.title;
    b.dataset.id = s.id;
    b.addEventListener("click", async () => {
      await loadSample(s.id);
    });
    box.appendChild(b);
  });
}

$("file").addEventListener("change", async (ev) => {
  const f = ev.target.files && ev.target.files[0];
  if (!f) return;
  $("text").value = await f.text();
});

function setPipe(step) {
  $("pipe").hidden = false;
  const order = ["split", "facts", "retrieve", "judge", "verify", "report"];
  const idx = order.indexOf(step);
  $("pipe").querySelectorAll("li").forEach((li) => {
    const s = li.getAttribute("data-step");
    const i = order.indexOf(s);
    li.classList.toggle("on", s === step);
    li.classList.toggle("done", i < idx);
  });
}

function renderFacts(facts) {
  show("facts-panel", true);
  const dl = $("facts-dl");
  dl.replaceChildren();
  Object.entries(FACT_LABELS).forEach(([k, label]) => {
    const v = facts[k];
    const div = document.createElement("div");
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = v == null ? "null" : (typeof v === "object" ? `${v.start || ""} ~ ${v.end || ""}` : String(v));
    div.append(dt, dd);
    dl.appendChild(div);
  });
}

function renderTally(summary) {
  show("tally-panel", true);
  const box = $("tally");
  box.replaceChildren();
  [
    ["t-viol", summary.n_violation, "위반"],
    ["t-risk", summary.n_risk, "위험"],
    ["t-review", summary.n_review, "확인 필요"],
    ["t-ok", summary.n_ok, "문제 없음"],
  ].forEach(([cls, n, label]) => {
    const d = document.createElement("div");
    d.className = cls;
    d.innerHTML = `<b>${n ?? 0}</b><span>${label}</span>`;
    box.appendChild(d);
  });
}

function addCard(f) {
  const cls = LABELS[f.verdict] || "review";
  const art = document.createElement("article");
  art.className = "card " + cls;
  art.id = "card-" + f.segment_id;
  const ev = (f.evidence || []).map((e) =>
    `<div class="ev"><span class="tag">${esc(e.source_tag || "")}</span><b>${esc(e.id)}</b> ${esc(e.title || "")}<p class="quote">${esc(e.quote || "")}</p></div>`
  ).join("") || "<p class='muted'>근거 없음</p>";
  const hits = (f.hits || []).map((h) => `${h.id}(${h.score})`).join(", ");
  art.innerHTML = `
    <div class="card-top">
      <span class="badge ${cls}">${esc(f.verdict)}</span>
      <span class="card-title">${esc(f.article_title || f.segment_id)}</span>
      <span class="meta">${esc(f.segment_id)} · ${esc(String(f.latency_ms ?? ""))}ms · 검색 ${esc(f.filter_mode || "")}</span>
    </div>
    <div class="card-body">
      <div class="block"><h3>계약서 원문 인용</h3><p class="quote">${esc(f.contract_quote || f.text || "")}</p></div>
      <div class="block"><h3>표준·법 기준</h3>${ev}</div>
      <div class="block"><h3>차이</h3><p>${esc(f.gap || "")}</p></div>
      <div class="block"><h3>왜 문제인지</h3><p>${esc(f.why || "")}</p></div>
      <div class="block"><h3>수정 문구</h3><p>${esc(f.suggestion || "")}</p></div>
      <p class="pipe-note">넘긴 근거 ${esc(hits)} · 고른 근거 ${(f.evidence || []).map((e) => e.id).join(", ") || "없음"} · std_item ${(f.std_items || []).join("|") || "없음"}</p>
    </div>`;
  $("cards").appendChild(art);
}

function renderReport(report) {
  setPipe("report");
  renderTally(report.summary || {});
  const crit = report.critical || [];
  show("critical", crit.length > 0);
  $("critical-list").innerHTML = crit.map((c) => `<li><b>${esc(c.label)}</b> · ${esc(c.segment_id)} — ${esc(c.quote)}</li>`).join("");
  if (!$("cards").children.length) {
    (report.findings || report.cards || []).forEach(addCard);
  }
  const missing = report.missing || [];
  show("missing-panel", true);
  $("missing-list").innerHTML = missing.length
    ? missing.map((m) => `<li><code>${esc(m.id)}</code> ${esc(m.name)} — not_present (${esc(m.basis || "")})</li>`).join("")
    : "<li>필수 항목이 조항에서 확인됨</li>";
  const mm = report.mismatches || [];
  show("mismatch-panel", true);
  $("mismatch-list").innerHTML = mm.length ? mm.map((m) => `<li>${esc(JSON.stringify(m))}</li>`).join("") : "<li>해당 없음</li>";
  const nf = report.needs_fact || [];
  show("needs-panel", true);
  $("needs-list").innerHTML = nf.length ? nf.map((n) => `<li>${esc(n.segment_id)}: ${esc(n.fact)}</li>`).join("") : "<li>없음</li>";
  show("next-panel", true);
  const reqs = (report.next_actions && report.next_actions.requests) || [];
  $("next-list").innerHTML = reqs.length ? reqs.map((r) => `<li>${esc(r)}</li>`).join("") : "<li>수정 요청 문구 없음</li>";
  $("helpline").textContent = "상담 창구: " + ((report.next_actions && report.next_actions.helpline) || "");
}

$("go").addEventListener("click", async () => {
  const text = $("text").value.trim();
  if (!text) return;
  $("go").disabled = true;
  $("status").innerHTML = '<span class="dot"></span>점검 중';
  $("cards").replaceChildren();
  ["facts-panel", "tally-panel", "critical", "missing-panel", "mismatch-panel", "needs-panel", "next-panel"].forEach((id) => show(id, false));
  setPipe("split");
  $("input-panel").classList.add("collapsed");
  $("input-body").hidden = true;
  const toggle = $("toggle-input");
  if (toggle) {
    toggle.hidden = false;
    toggle.textContent = "입력 펼치기";
  }
  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, no_llm: $("no-llm").checked }),
    });
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const parts = buf.split("\n\n");
      buf = parts.pop();
      for (const block of parts) {
        const ev = (block.match(/^event:\s*(.+)$/m) || [])[1];
        const dataLine = block.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim()).join("");
        if (!ev || !dataLine) continue;
        const data = JSON.parse(dataLine);
        if (ev === "split") setPipe("facts");
        if (ev === "facts") { setPipe("retrieve"); renderFacts(data.facts || {}); }
        if (ev === "clause") {
          setPipe("judge");
          if (data.finding) addCard(data.finding);
        }
        if (ev === "done") {
          setPipe("report");
          renderReport(data.report || {});
        }
        if (ev === "error") $("status").textContent = data.message || "오류";
      }
    }
    $("status").textContent = "점검이 끝났습니다";
  } catch (err) {
    $("status").textContent = "요청 실패: " + err;
  } finally {
    $("go").disabled = false;
  }
});

$("toggle-input").addEventListener("click", () => {
  const body = $("input-body");
  const collapsed = body.hidden;
  body.hidden = !collapsed;
  $("input-panel").classList.toggle("collapsed", body.hidden);
  $("toggle-input").textContent = body.hidden ? "입력 펼치기" : "입력 접기";
});

async function openCheck(domain, sampleId, autoRun) {
  setDomain(domain || "LEASE");
  showView("check");
  const sample = sampleId || SAMPLE_BY_DOMAIN[domain] || "";
  if (sample) await loadSample(sample);
  if (autoRun && $("text").value.trim()) $("go").click();
}

document.querySelectorAll("[data-view]").forEach((el) => {
  el.addEventListener("click", (ev) => {
    const view = el.getAttribute("data-view");
    if (!VIEWS.includes(view)) return;
    ev.preventDefault();
    showView(view);
  });
});

document.querySelectorAll(".domain-card, .tab").forEach((el) => {
  el.addEventListener("click", async () => {
    const domain = el.dataset.domain;
    const sample = el.dataset.sample;
    setDomain(domain);
    if (el.classList.contains("domain-card")) {
      await openCheck(domain, sample, false);
      return;
    }
    if (sample) await loadSample(sample);
  });
});

$("btn-home-check").addEventListener("click", async (ev) => {
  ev.preventDefault();
  const on = document.querySelector("#view-home .tab.on");
  await openCheck(on && on.dataset.domain, on && on.dataset.sample, false);
});

$("btn-sample").addEventListener("click", async () => {
  await openCheck("LEASE", "oneroom_lease", true);
});

window.addEventListener("hashchange", () => showView(currentView()));

showView(currentView());
loadHealth();
loadSamples();
setInterval(loadHealth, 15000);
