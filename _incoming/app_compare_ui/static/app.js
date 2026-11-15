// 계약서 점검 비교 — 화면 스크립트. 서버 API(/api/samples, /api/analyze SSE, /api/evidence, /api/replay)는 기존과 같습니다.
const $ = (id) => document.getElementById(id);
const VERDICT = { risk: "위험", safe: "안전", review: "확인 필요" };
let answers = {};
let replayData = null;
let clauses = [];           // [{left, right, differ}]
let rowFilter = "all";
let replayShown = 50;

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function verdictKey(v) { return v === "risk" || v === "safe" ? v : "review"; }

/* ---------- 정답 비교 ---------- */
function riskyList() {
  const id = $("sample").value;
  return (answers[id] && answers[id].risky_clauses) || [];
}
function answerMark(data) {
  if (!$("show-answer").checked) return null;
  const list = riskyList();
  if (!list.length) return null;
  const isRisky = list.some((s) => (data.clause || "").includes(s));
  if (isRisky && data.verdict === "risk") return "hit";
  if (isRisky) return "miss";
  if (data.verdict === "risk") return "fp";
  return null;
}
const MARK_TEXT = { hit: "맞힘", miss: "놓침", fp: "오탐" };

/* ---------- 점수판 ---------- */
function tally(list, side) {
  const n = { risk: 0, safe: 0, review: 0 };
  let ms = 0, calls = 0;
  const m = { hit: 0, miss: 0, fp: 0 };
  list.forEach((d) => {
    n[verdictKey(d.verdict)]++;
    ms += d.latency_ms || 0;
    calls += d.calls || 0;
    const mk = answerMark(d);
    if (mk) m[mk]++;
  });
  const box = $("tally-" + side);
  box.replaceChildren();
  [["risk", "위험"], ["safe", "안전"], ["review", "확인 필요"]].forEach(([k, label]) => {
    const d = el("div", "t-" + k);
    d.appendChild(el("b", null, String(n[k])));
    d.appendChild(el("span", null, label));
    box.appendChild(d);
  });
  const foot = $("foot-" + side);
  foot.replaceChildren();
  foot.appendChild(el("span", null, `${(ms / 1000).toFixed(1)}초`));
  foot.appendChild(el("span", null, `모델 호출 ${calls}회`));
  if ($("show-answer").checked && riskyList().length) {
    const total = riskyList().length;
    foot.appendChild(el("span", "score", `위험 문장 ${m.hit}/${total} 맞힘`));
    foot.appendChild(el("span", null, `놓침 ${m.miss} · 오탐 ${m.fp}`));
  }
  // 기존 칩 텍스트(다른 스크립트·테스트 호환)
  $("chips-" + side).textContent = `위험 ${n.risk} / 안전 ${n.safe} / 확인 필요 ${n.review} · ${(ms / 1000).toFixed(1)}초 · 호출 ${calls}`;
}
function updateBoard() {
  tally(clauses.map((c) => c.left), "left");
  tally(clauses.map((c) => c.right), "right");
  const diff = clauses.filter((c) => c.differ).length;
  $("mid-diff").textContent = String(diff);
  $("mid-total").textContent = `전체 ${clauses.length}개 조항 중`;
  $("row-filter").querySelector('[data-f="wrong"]').hidden = !($("show-answer").checked && riskyList().length);
}

/* ---------- 조항 행 ---------- */
function verdictPanel(side, data) {
  const v = el("div", "verdict " + side);
  const line = el("div", "v-line");
  const vk = verdictKey(data.verdict);
  line.appendChild(el("span", "badge " + vk, VERDICT[vk]));
  if (data.actor) line.appendChild(el("span", "actor" + (/규칙/.test(data.actor) ? " rule" : ""), data.actor));
  const mk = answerMark(data);
  if (mk) line.appendChild(el("span", "mark " + mk, MARK_TEXT[mk]));
  v.appendChild(line);

  if (side === "right" && (data.catalog_title || data.severity)) {
    v.appendChild(el("div", "v-cat", [data.catalog_title, data.severity].filter(Boolean).join(" · ")));
  }
  if (data.slot) v.appendChild(el("div", "v-slot", "주제: " + data.slot));
  if (data.reason) v.appendChild(el("p", "v-reason", data.reason));
  if (side === "right" && data.wage_note) v.appendChild(el("div", "v-slot", data.wage_note));

  const arts = data.articles || [];
  if (arts.length) {
    const wrap = el("div", "arts");
    const body = el("pre", "art-body");
    body.hidden = true;
    arts.forEach((a) => {
      const b = el("button", "art", a.line || a.id);
      b.type = "button";
      b.setAttribute("aria-expanded", "false");
      b.addEventListener("click", () => {
        const open = b.getAttribute("aria-expanded") === "true";
        wrap.querySelectorAll(".art").forEach((x) => x.setAttribute("aria-expanded", "false"));
        if (open) { body.hidden = true; return; }
        b.setAttribute("aria-expanded", "true");
        body.textContent = a.body || "조문 본문이 없습니다.";
        body.hidden = false;
      });
      wrap.appendChild(b);
    });
    v.appendChild(wrap);
    v.appendChild(body);
  }
  return v;
}
function clauseRow(c, i) {
  const row = el("article", "clause-row" + (c.differ ? " differ" : ""));
  const top = el("div", "clause-top");
  const meta = el("div", "clause-meta");
  meta.appendChild(el("span", "clause-no", `조항 ${String(i + 1).padStart(2, "0")}`));
  const slot = c.right.slot || c.left.slot;
  if (slot) meta.appendChild(el("span", null, slot));
  if (c.differ) meta.appendChild(el("span", "tag-diff", "판정 다름"));
  top.appendChild(meta);
  const text = c.left.clause || c.right.clause || "";
  const t = el("div", "clause-text", text);
  top.appendChild(t);
  if (text.length > 160) {
    t.classList.add("clamp");
    const more = el("button", "more-btn", "전문 보기");
    more.type = "button";
    more.addEventListener("click", () => {
      const clamped = t.classList.toggle("clamp");
      more.textContent = clamped ? "전문 보기" : "접기";
    });
    top.appendChild(more);
  }
  row.appendChild(top);
  const vs = el("div", "verdicts");
  vs.appendChild(verdictPanel("left", c.left));
  vs.appendChild(verdictPanel("right", c.right));
  row.appendChild(vs);
  return row;
}
function passFilter(c) {
  if (rowFilter === "differ") return c.differ;
  if (rowFilter === "risk") return c.left.verdict === "risk" || c.right.verdict === "risk";
  if (rowFilter === "wrong") {
    const a = answerMark(c.left), b = answerMark(c.right);
    return a === "miss" || a === "fp" || b === "miss" || b === "fp";
  }
  return true;
}
function renderRows() {
  const box = $("rows");
  box.replaceChildren();
  let shown = 0;
  clauses.forEach((c, i) => {
    if (!passFilter(c)) return;
    box.appendChild(clauseRow(c, i));
    shown++;
  });
  if (!shown && clauses.length) box.appendChild(el("p", "empty", "조건에 맞는 조항이 없습니다."));
  $("row-count").textContent = `${shown} / ${clauses.length}개 조항`;
}
function showResultArea(on) {
  $("heads").hidden = !on;
  $("row-tools").hidden = !on;
  $("col-heads").hidden = !on;
}
function addClause(payload) {
  clauses.push({ left: payload.left || {}, right: payload.right || {}, differ: !!payload.differ });
  updateBoard();
  const c = clauses[clauses.length - 1];
  if (passFilter(c)) {
    const empty = $("rows").querySelector(".empty");
    if (empty) empty.remove();
    $("rows").appendChild(clauseRow(c, clauses.length - 1));
  }
  $("row-count").textContent = `${$("rows").querySelectorAll(".clause-row").length} / ${clauses.length}개 조항`;
}

$("row-filter").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  rowFilter = b.dataset.f;
  $("row-filter").querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  renderRows();
});
$("show-answer").addEventListener("change", () => {
  if (!clauses.length) return;
  updateBoard();
  if (rowFilter === "wrong" && !$("show-answer").checked) {
    rowFilter = "all";
    $("row-filter").querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.f === "all")));
  }
  renderRows();
});

/* ---------- 입력 ---------- */
async function loadSamples() {
  try {
    const data = await fetch("/api/samples").then((r) => r.json());
    answers = data.answers || {};
    const sel = $("sample");
    sel.replaceChildren(new Option("직접 입력", ""));
    const chips = $("sample-chips");
    chips.replaceChildren();
    const mk = (id, label) => {
      const b = el("button", null, label);
      b.type = "button";
      b.dataset.id = id;
      b.setAttribute("aria-pressed", "false");
      b.addEventListener("click", () => pickSample(id));
      chips.appendChild(b);
    };
    mk("", "직접 입력");
    (data.samples || []).forEach((s) => {
      sel.appendChild(new Option(s.title || s.id, s.id));
      mk(s.id, s.title || s.id);
    });
    chips.firstChild && chips.firstChild.setAttribute("aria-pressed", "true");
  } catch (e) {
    $("status").textContent = "예시 목록을 불러오지 못했습니다. 서버가 켜져 있는지 확인하세요.";
  }
}
async function pickSample(id) {
  $("sample").value = id;
  $("sample-chips").querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.id === id)));
  if (!id) { $("text").value = ""; return; }
  const data = await fetch("/api/samples/" + encodeURIComponent(id)).then((r) => r.json());
  $("text").value = data.text || "";
  $("show-answer").checked = !!(answers[id] && (answers[id].risky_clauses || []).length);
}
$("sample").addEventListener("change", () => pickSample($("sample").value));
$("file").addEventListener("change", () => {
  const file = $("file").files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => { $("text").value = String(reader.result || ""); pickSampleUi(""); };
  reader.readAsText(file, "utf-8");
});
function pickSampleUi(id) {
  $("sample").value = id;
  $("sample-chips").querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.id === id)));
}
$("toggle-input").addEventListener("click", () => {
  const body = $("input-body");
  body.hidden = !body.hidden;
  $("toggle-input").textContent = body.hidden ? "입력 펼치기" : "입력 접기";
});
function collapseInput() {
  $("input-body").hidden = true;
  $("toggle-input").hidden = false;
  $("toggle-input").textContent = "입력 펼치기";
}
function setStatus(text, busy) {
  const s = $("status");
  s.replaceChildren();
  if (busy) s.appendChild(el("span", "dot"));
  s.appendChild(document.createTextNode(text));
}

$("go").addEventListener("click", async () => {
  const text = $("text").value.trim();
  if (!text) { setStatus("계약서 본문을 입력하거나 예시를 고르세요."); return; }
  clauses = [];
  rowFilter = "all";
  $("row-filter").querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.f === "all")));
  $("rows").replaceChildren();
  showResultArea(true);
  updateBoard();
  $("go").disabled = true;
  setStatus("조항을 나누는 중", true);
  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, domain: $("domain").value || null, include_articles: true }),
    });
    if (!res.ok || !res.body) throw new Error("HTTP " + res.status);
    collapseInput();
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "", total = 0;
    for (;;) {
      const step = await reader.read();
      if (step.done) break;
      buf += dec.decode(step.value, { stream: true });
      const blocks = buf.split("\n\n");
      buf = blocks.pop();
      for (const block of blocks) {
        const lines = block.split("\n");
        const dataLine = lines.find((l) => l.startsWith("data:"));
        const evLine = lines.find((l) => l.startsWith("event:")) || "";
        if (!dataLine) continue;
        const payload = JSON.parse(dataLine.slice(5).trim());
        if (evLine.includes("meta")) {
          total = payload.n || 0;
          setStatus(`${payload.domain_ko || "계약"} · ${total}개 조항 점검 중`, true);
        } else if (evLine.includes("clause")) {
          addClause(payload);
          setStatus(`${clauses.length} / ${total || "?"}개 조항 점검 중`, true);
        } else if (evLine.includes("done")) {
          setStatus(`완료 · ${clauses.length}개 조항`);
        }
      }
    }
    if (!/완료/.test($("status").textContent)) setStatus(`완료 · ${clauses.length}개 조항`);
  } catch (e) {
    setStatus("점검하지 못했습니다. 두 모델 서버(8081, 8082)와 앱 서버가 켜져 있는지 확인한 뒤 다시 누르세요.");
  } finally {
    $("go").disabled = false;
  }
});

/* ---------- 실험 근거 ---------- */
async function loadEvidence() {
  try {
    const data = await fetch("/api/evidence").then((r) => r.json());
    $("evidence-note").textContent = data.note || "";
    const rows = [
      ["조항 주제 분류", "Qwen3-8B, 노드 목록만 (T2 A0)", "KLUE-RoBERTa seed 42", `${data.t2_q8b_a0} → ${data.t2_roberta42}`],
      ["숫자 기준 검사", "없음 (LLM이 판단)", "규칙 (휴게 4시간 이상 30분, 8시간 이상 1시간 등)", `규칙 ${data.t3_rule}`],
      ["문구 위험 판정", "Qwen3-8B + BM25 상위 5 (T3 A4-BM25)", "A.X 4.0 Light + 카탈로그 조문 (T3 A1)", `${data.t3_q8b_a4bm25} → ${data.t3_ax7_a1} (문구형 ${data.t3_ax7_a1_text})`],
      ["근거 조문", "Qwen3-8B가 BM25 자료에서 선택 (T4 A4-BM25)", "카탈로그 연결, 후보가 여럿이면 thinking (T4 A3)", `${data.t4_q8b_a4bm25} → ${data.t4_q8bt_a3}`],
    ];
    const t = $("evidence-table");
    t.replaceChildren();
    const head = t.insertRow();
    ["단계", "나빴던 조합", "최고 조합", "실험 수치 (왼쪽 → 오른쪽)"].forEach((h) => head.appendChild(el("th", null, h)));
    rows.forEach((r) => {
      const tr = t.insertRow();
      r.forEach((c, i) => tr.appendChild(el("td", i === 3 ? "num" : null, c)));
    });
  } catch (e) {
    $("evidence-note").textContent = "실험 근거를 불러오지 못했습니다.";
  }
}

/* ---------- 탭 ---------- */
function showTab(name) {
  $("view-check").hidden = name !== "check";
  $("view-replay").hidden = name !== "replay";
  $("tab-check").setAttribute("aria-selected", String(name === "check"));
  $("tab-replay").setAttribute("aria-selected", String(name === "replay"));
  if (name === "replay" && !replayData) loadReplay();
}
$("tab-check").onclick = () => showTab("check");
$("tab-replay").onclick = () => showTab("replay");

/* ---------- 평가 재생 ---------- */
function vText(v) { return v === true ? "위험" : v === false ? "안전" : "확인 필요"; }
function vClass(v) { return v === true ? "risk" : v === false ? "safe" : "review"; }
function firstNum(s) { const m = String(s ?? "").match(/-?\d+(\.\d+)?/); return m ? Number(m[0]) : NaN; }

function metricBlock(name, left, right, diff) {
  const box = el("div", "metric");
  box.appendChild(el("div", "metric-name", name));
  const bars = el("div", "metric-bars");
  [["left", "나빴던", left], ["right", "최고", right]].forEach(([side, label, val]) => {
    const row = el("div", "mbar " + side);
    const track = el("div", "mbar-track");
    const fill = el("div", "mbar-fill");
    let v = firstNum(val);
    if (v > 1.0001) v = v / 100;
    fill.style.width = isNaN(v) ? "0%" : Math.max(0, Math.min(1, v)) * 100 + "%";
    track.appendChild(fill);
    row.appendChild(track);
    row.appendChild(el("span", null, `${label} ${val ?? "—"}`));
    bars.appendChild(row);
  });
  box.appendChild(bars);
  if (diff) box.appendChild(el("div", "metric-diff", "차이(오른쪽−왼쪽) " + diff));
  return box;
}
async function loadReplay() {
  $("replay-summary").replaceChildren(el("p", "muted", "집계 중"));
  try {
    replayData = await fetch("/api/replay").then((r) => r.json());
  } catch (e) {
    $("replay-summary").replaceChildren(el("p", "muted", "저장된 결과를 불러오지 못했습니다."));
    return;
  }
  const f = replayData.summary.fmt;
  const box = $("replay-summary");
  box.replaceChildren(
    metricBlock("균형 정확도", f.left_bacc, f.right_bacc, f.diff_bacc),
    metricBlock("쌍 정답률", f.left_pair, f.right_pair, f.diff_pair),
    metricBlock("숫자형 정확도", f.left_num, f.right_num),
    metricBlock("문구형 정확도", f.left_text, f.right_text),
  );
  $("replay-code").textContent = "계산 코드: " + (replayData.code || "");
  const checks = [...new Set(replayData.rows.map((r) => r.check_id))].sort();
  const sel = $("f-check");
  sel.replaceChildren(new Option("전체", ""));
  checks.forEach((c) => sel.appendChild(new Option(c, c)));
  renderReplay();
}
function replayFiltered() {
  const err = $("f-err").value;
  return replayData.rows.filter((r) => {
    if ($("f-surface").value && r.surface !== $("f-surface").value) return false;
    if ($("f-kind").value && r.kind !== $("f-kind").value) return false;
    if ($("f-check").value && r.check_id !== $("f-check").value) return false;
    if ($("f-diff").checked && r.left_risky === r.right_risky) return false;
    if (err === "left" && !(r.left_ok === false && r.right_ok === true)) return false;
    if (err === "right" && !(r.right_ok === false && r.left_ok === true)) return false;
    if (err === "both" && !(r.left_ok === false && r.right_ok === false)) return false;
    return true;
  });
}
function verdictCell(risky, ok) {
  const td = el("td");
  const wrap = el("span", ok === false ? "ng" : ok === true ? "ok" : "");
  wrap.appendChild(el("span", "badge " + vClass(risky), vText(risky)));
  td.appendChild(wrap);
  return td;
}
function renderReplay() {
  const rows = replayFiltered();
  $("replay-count").textContent = `${rows.length}건`;
  const tb = $("replay-rows");
  tb.replaceChildren();
  rows.slice(0, replayShown).forEach((r) => {
    const tr = el("tr", "main");
    tr.appendChild(el("td", "num", r.id));
    tr.appendChild(el("td", null, `${r.check_id} · ${r.kind === "numeric" ? "숫자형" : "문구형"}`));
    const g = el("td");
    g.appendChild(el("span", "badge " + (r.gold ? "risk" : "safe"), r.gold ? "위험" : "안전"));
    tr.appendChild(g);
    tr.appendChild(verdictCell(r.left_risky, r.left_ok));
    tr.appendChild(verdictCell(r.right_risky, r.right_ok));
    const a = el("td");
    if (r.actor) a.appendChild(el("span", "actor" + (/규칙/.test(r.actor) ? " rule" : ""), r.actor));
    tr.appendChild(a);
    const det = el("tr", "detail");
    det.hidden = true;
    const td = el("td");
    td.colSpan = 6;
    const grid = el("div", "detail-grid");
    const full = el("div", "full");
    full.appendChild(el("h4", null, "조항"));
    full.appendChild(el("p", null, r.clause || ""));
    const l = el("div", "l"); l.appendChild(el("h4", null, "나빴던 조합 이유")); l.appendChild(el("p", null, r.left_reason || "—"));
    const rr = el("div", "r"); rr.appendChild(el("h4", null, "최고 조합 이유")); rr.appendChild(el("p", null, r.right_reason || "—"));
    grid.append(full, l, rr);
    td.appendChild(grid);
    det.appendChild(td);
    tr.addEventListener("click", () => { det.hidden = !det.hidden; });
    tb.append(tr, det);
  });
  $("more").hidden = rows.length <= replayShown;
  $("more").textContent = `더 보기 (${Math.min(replayShown, rows.length)} / ${rows.length})`;
}
$("more").addEventListener("click", () => { replayShown += 50; renderReplay(); });
$("seg-err").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  $("f-err").value = b.dataset.v;
  $("seg-err").querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  replayShown = 50;
  replayData && renderReplay();
});
["f-diff", "f-check", "f-kind", "f-surface"].forEach((id) => {
  $(id).addEventListener("change", () => { replayShown = 50; replayData && renderReplay(); });
});

/* ---------- 시작 ---------- */
function syncTopHeight() {
  const h = document.querySelector(".top").offsetHeight;
  document.documentElement.style.setProperty("--top-h", h + "px");
}
window.addEventListener("resize", syncTopHeight);
syncTopHeight();
loadSamples();
loadEvidence();
if (location.search.indexOf("tab=replay") >= 0) showTab("replay");
if (location.search.indexOf("demo=1") >= 0) {
  fetch("/static/demo_alba.json").then((r) => r.json()).then((list) => {
    showResultArea(true);
    clauses = [];
    list.forEach((p) => clauses.push({ left: p.left || {}, right: p.right || {}, differ: !!p.differ }));
    updateBoard();
    renderRows();
  });
}
