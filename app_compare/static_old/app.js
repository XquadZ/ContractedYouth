const $ = (id) => document.getElementById(id);
let answers = {};
let replayData = null;

function badge(verdict) {
  if (verdict === "risk") return '<span class="badge risk">위험</span>';
  if (verdict === "safe") return '<span class="badge safe">안전</span>';
  return '<span class="badge review">확인 필요</span>';
}

function card(side, data, riskyList) {
  const text = data.clause || "";
  const short = text.length > 200 ? text.slice(0, 200) + "…" : text;
  const articles = (data.articles || []).map((a) => {
    return `<details class="body"><summary>${escapeHtml(a.line || a.id)}</summary><p>${escapeHtml(a.body || "")}</p></details>`;
  }).join("");
  const extra = side === "right"
    ? `<div class="meta">${escapeHtml(data.catalog_title || "")} ${data.severity ? "· " + escapeHtml(data.severity) : ""} ${data.wage_note ? "· " + escapeHtml(data.wage_note) : ""}</div>`
    : "";
  let mark = "";
  if ($("show-answer").checked && riskyList) {
    const hitClause = riskyList.some((s) => text.includes(s));
    if (hitClause && data.verdict === "risk") mark = '<span class="mark hit">맞힘</span>';
    else if (hitClause) mark = '<span class="mark miss">놓침</span>';
    else if (data.verdict === "risk") mark = '<span class="mark fp">오탐</span>';
  }
  return `<article class="card">
    <h3>조항 ${mark}</h3>
    <div class="clause">${escapeHtml(short)}</div>
    ${text.length > 200 ? `<details><summary>펼치기</summary><div class="clause">${escapeHtml(text)}</div></details>` : ""}
    <div class="meta">${badge(data.verdict)} <span class="chip">${escapeHtml(data.actor || "")}</span></div>
    <div class="meta">주제: ${escapeHtml(data.slot || "-")}</div>
    ${articles}
    <p class="reason">${escapeHtml(data.reason || "")}</p>
    ${extra}
  </article>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function chips(list) {
  const n = { risk: 0, safe: 0, review: 0 };
  let ms = 0;
  let calls = 0;
  list.forEach((d) => {
    n[d.verdict] = (n[d.verdict] || 0) + 1;
    ms += d.latency_ms || 0;
    calls += d.calls || 0;
  });
  return `위험 ${n.risk || 0} / 안전 ${n.safe || 0} / 확인 필요 ${n.review || 0} · ${(ms / 1000).toFixed(1)}초 · 호출 ${calls}`;
}

async function loadSamples() {
  const res = await fetch("/api/samples");
  const data = await res.json();
  answers = data.answers || {};
  const sel = $("sample");
  sel.innerHTML = '<option value="">직접 입력</option>' + (data.samples || []).map((s) => `<option value="${s.id}">${s.id}</option>`).join("");
}

async function loadEvidence() {
  const data = await fetch("/api/evidence").then((r) => r.json());
  $("evidence-note").textContent = data.note || "";
  const rows = [
    ["조항 주제 분류", "Qwen3-8B, 노드 목록만 (T2 A0)", "KLUE-RoBERTa seed 42", `${data.t2_q8b_a0} vs ${data.t2_roberta42}`],
    ["숫자 기준 검사", "없음 (LLM)", "규칙, 휴게 4시간 이상 30분·8시간 이상 1시간", `규칙 ${data.t3_rule}`],
    ["문구 위험 판정", "Qwen3-8B + BM25 상위 5 (T3 A4-BM25)", "A.X 4.0 Light + 카탈로그 조문 (실험의 T3 A1)", `${data.t3_q8b_a4bm25} vs ${data.t3_ax7_a1}, 문구형 AX7 A1 ${data.t3_ax7_a1_text}`],
    ["근거 조문", "Qwen3-8B가 BM25 자료에서 선택 (T4 A4-BM25)", "카탈로그 연결. 후보가 여러 개면 Qwen3-8B thinking (T4 A3)", `${data.t4_q8b_a4bm25} vs ${data.t4_q8bt_a3}`],
  ];
  $("evidence-table").innerHTML = "<tr><th>단계</th><th>나빴던 조합</th><th>최고 조합</th><th>RUN 수치</th></tr>"
    + rows.map((r) => "<tr>" + r.map((c) => `<td>${escapeHtml(c)}</td>`).join("") + "</tr>").join("");
}

$("sample").addEventListener("change", async () => {
  const id = $("sample").value;
  if (!id) return;
  const data = await fetch("/api/samples/" + id).then((r) => r.json());
  $("text").value = data.text || "";
});

$("file").addEventListener("change", () => {
  const file = $("file").files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => { $("text").value = String(reader.result || ""); };
  reader.readAsText(file, "utf-8");
});

$("go").addEventListener("click", async () => {
  $("status").textContent = "점검 중";
  $("rows").innerHTML = "";
  $("heads").hidden = false;
  const lefts = [];
  const rights = [];
  const sampleId = $("sample").value;
  const riskyList = (answers[sampleId] && answers[sampleId].risky_clauses) || [];
  const res = await fetch("/api/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text: $("text").value,
      domain: $("domain").value || null,
      include_articles: true,
    }),
  });
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const step = await reader.read();
    if (step.done) break;
    buf += dec.decode(step.value, { stream: true });
    const chunks = buf.split("\n\n");
    buf = chunks.pop();
    chunks.forEach((block) => {
      const line = block.split("\n").find((l) => l.startsWith("data:"));
      const ev = block.split("\n").find((l) => l.startsWith("event:"));
      if (!line) return;
      const payload = JSON.parse(line.slice(5).trim());
      if (ev && ev.includes("clause")) {
        lefts.push(payload.left);
        rights.push(payload.right);
        const row = document.createElement("div");
        row.className = "pair" + (payload.differ ? " differ" : "");
        row.innerHTML = (payload.differ ? '<div class="flag">판정 다름</div>' : "")
          + card("left", payload.left, riskyList)
          + card("right", payload.right, riskyList);
        $("rows").appendChild(row);
        $("chips-left").textContent = chips(lefts);
        $("chips-right").textContent = chips(rights);
      }
      if (ev && ev.includes("done")) $("status").textContent = "완료";
      if (ev && ev.includes("meta")) $("status").textContent = (payload.domain_ko || "") + " · " + payload.n + "개 조항";
    });
  }
});

function showTab(name) {
  $("view-check").hidden = name !== "check";
  $("view-replay").hidden = name !== "replay";
  $("tab-check").classList.toggle("on", name === "check");
  $("tab-replay").classList.toggle("on", name === "replay");
  if (name === "replay" && !replayData) loadReplay();
}
$("tab-check").onclick = () => showTab("check");
$("tab-replay").onclick = () => showTab("replay");

function yn(v) {
  if (v === true) return "위험";
  if (v === false) return "안전";
  return "확인 필요";
}

function renderReplay() {
  const rows = replayData.rows.filter((r) => {
    if ($("f-surface").value && r.surface !== $("f-surface").value) return false;
    if ($("f-kind").value && r.kind !== $("f-kind").value) return false;
    if ($("f-check").value && r.check_id !== $("f-check").value) return false;
    if ($("f-diff").checked && r.left_risky === r.right_risky) return false;
    const err = $("f-err").value;
    if (err === "left" && !(r.left_ok === false && r.right_ok === true)) return false;
    if (err === "right" && !(r.right_ok === false && r.left_ok === true)) return false;
    if (err === "both" && !(r.left_ok === false && r.right_ok === false)) return false;
    return true;
  });
  $("replay-count").textContent = rows.length + "건";
  $("replay-rows").innerHTML = rows.slice(0, 80).map((r) => `
    <article class="replay-row">
      <strong>${escapeHtml(r.id)}</strong>
      정답 ${r.gold ? "위험" : "안전"}
      · 왼쪽 ${yn(r.left_risky)} · 오른쪽 ${yn(r.right_risky)}
      · <span class="chip">${escapeHtml(r.actor)}</span>
      · ${escapeHtml(r.check_id)} ${escapeHtml(r.kind)}
      <div>${escapeHtml((r.clause || "").slice(0, 180))}</div>
      <div>왼쪽 이유: ${escapeHtml(r.left_reason || "")}</div>
      <div>오른쪽 이유: ${escapeHtml(r.right_reason || "")}</div>
    </article>`).join("");
}

async function loadReplay() {
  $("replay-summary").textContent = "집계 중";
  replayData = await fetch("/api/replay").then((r) => r.json());
  const f = replayData.summary.fmt;
  $("replay-summary").innerHTML = `
    <p>계산: ${escapeHtml(replayData.code)}</p>
    <table>
      <tr><th></th><th>균형 정확도</th><th>쌍 정답률</th><th>숫자형 정확도</th><th>문구형 정확도</th></tr>
      <tr><td>왼쪽 Q8B A4-BM25</td><td>${escapeHtml(f.left_bacc)}</td><td>${escapeHtml(f.left_pair)}</td><td>${escapeHtml(f.left_num)}</td><td>${escapeHtml(f.left_text)}</td></tr>
      <tr><td>오른쪽 합성</td><td>${escapeHtml(f.right_bacc)}</td><td>${escapeHtml(f.right_pair)}</td><td>${escapeHtml(f.right_num)}</td><td>${escapeHtml(f.right_text)}</td></tr>
      <tr><td>오른쪽−왼쪽</td><td>${escapeHtml(f.diff_bacc)}</td><td>${escapeHtml(f.diff_pair)}</td><td></td><td></td></tr>
    </table>`;
  const checks = [...new Set(replayData.rows.map((r) => r.check_id))].sort();
  $("f-check").innerHTML = '<option value="">전체</option>' + checks.map((c) => `<option>${c}</option>`).join("");
  renderReplay();
}

["f-diff", "f-err", "f-check", "f-kind", "f-surface"].forEach((id) => {
  $(id).addEventListener("change", () => replayData && renderReplay());
});

function paint(clauses) {
  $("heads").hidden = false;
  $("rows").innerHTML = "";
  const lefts = [];
  const rights = [];
  clauses.forEach((payload) => {
    lefts.push(payload.left);
    rights.push(payload.right);
    const row = document.createElement("div");
    row.className = "pair" + (payload.differ ? " differ" : "");
    row.innerHTML = (payload.differ ? '<div class="flag">판정 다름</div>' : "")
      + card("left", payload.left, [])
      + card("right", payload.right, []);
    $("rows").appendChild(row);
  });
  $("chips-left").textContent = chips(lefts);
  $("chips-right").textContent = chips(rights);
}

loadSamples();
loadEvidence();
if (location.search.indexOf("tab=replay") >= 0) showTab("replay");
if (location.search.indexOf("demo=1") >= 0) {
  fetch("/static/demo_alba.json").then((r) => r.json()).then(paint);
}
