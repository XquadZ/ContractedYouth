# 화면 확인용 가짜 서버 (실제 모델 없음). python mock_server.py 8765
import json, sys, time, random
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).parent
SAMPLE = """제1조(근로계약기간) 2026년 3월 1일부터 2026년 8월 31일까지로 한다.
제2조(근무장소) 카페 본점 매장
제3조(소정근로시간) 10:00부터 16:00까지(휴게시간 없음)
제4조(근무일) 주 5일, 1일 5시간 근무하며 주휴수당은 지급하지 않는다.
제5조(임금) 시급은 9,860원으로 하며 매월 10일에 지급한다.
제6조(복무) 지각 1회당 10,000원을 벌금으로 급여에서 차감한다.
제7조(연차휴가) 근로기준법에서 정하는 바에 따라 부여한다.
제8조(사회보험) 고용보험, 산재보험, 국민연금, 건강보험에 가입한다."""
RISKY = ["10:00부터 16:00까지(휴게시간 없음)", "주휴수당은 지급하지 않는다", "시급은 9,860원", "지각 1회당 10,000원"]

ART = {"근기법:제54조": ("근로기준법 제54조(휴게)", "① 사용자는 근로시간이 4시간인 경우에는 30분 이상, 8시간인 경우에는 1시간 이상의 휴게시간을 근로시간 도중에 주어야 한다."),
       "최임법:제6조": ("최저임금법 제6조(최저임금의 효력)", "① 사용자는 최저임금의 적용을 받는 근로자에게 최저임금액 이상의 임금을 지급하여야 한다."),
       "근기법:제20조": ("근로기준법 제20조(위약 예정의 금지)", "사용자는 근로계약 불이행에 대한 위약금 또는 손해배상액을 예정하는 계약을 체결하지 못한다."),
       "근기법:제55조": ("근로기준법 제55조(휴일)", "① 사용자는 근로자에게 1주에 평균 1회 이상의 유급휴일을 보장하여야 한다.")}
def arts(*ids): return [{"id": i, "line": ART[i][0], "body": ART[i][1]} for i in ids]

def judge(i, line):
    L = {"clause": line, "verdict": "safe", "actor": "모델", "slot": "기타", "reason": "약한 쪽에게 불리한 내용이 확인되지 않는다.", "articles": [], "latency_ms": random.randint(1500, 2500), "calls": 2}
    R = {"clause": line, "verdict": "safe", "actor": "모델", "slot": "기타", "reason": "표준계약서와 같은 내용이다.", "articles": [], "latency_ms": random.randint(600, 1600), "calls": 1}
    if "휴게시간 없음" in line:
        L.update(verdict="safe", reason="근로시간을 명시하고 있어 문제가 없다.", slot="근로 시간", articles=arts("근기법:제55조"))
        R.update(verdict="risk", actor="규칙", slot="근로시간·휴게", reason="1일 6시간 근무인데 휴게시간이 없다. 4시간 이상이면 30분 이상 휴게를 주어야 한다.", catalog_title="휴게시간 미달·미부여", severity="법 위반", articles=arts("근기법:제54조"), calls=0)
    elif "주휴수당" in line:
        L.update(verdict="risk", reason="주휴수당을 지급하지 않는 것은 불리하다.", slot="휴일", articles=arts("근기법:제55조"))
        R.update(verdict="risk", actor="규칙", slot="근무일·휴일", reason="주 25시간 근무로 15시간 이상이므로 주휴일이 보장되어야 한다.", catalog_title="주 15시간 이상인데 주휴 배제", severity="법 위반", articles=arts("근기법:제55조"), calls=0)
    elif "9,860" in line:
        L.update(verdict="safe", reason="시급과 지급일이 명시되어 있다.", slot="임금액", articles=arts("근기법:제20조"))
        R.update(verdict="risk", actor="규칙", slot="임금", reason="2026년 최저임금 10,320원보다 낮다.", catalog_title="최저임금 미달 시급", severity="무효", wage_note="기준: 2026년 고시 10,320원", articles=arts("최임법:제6조"), calls=0)
    elif "지각" in line:
        L.update(verdict="risk", reason="벌금 부과는 근로자에게 불리하다.", slot="손해배상의 예정", articles=arts("근기법:제20조"))
        R.update(verdict="risk", slot="위약·손해배상", reason="지각에 대해 정액 벌금을 미리 정하는 것은 위약 예정에 해당한다.", catalog_title="위약금·손해배상 예정(지각·중도퇴사 벌금)", severity="무효", articles=arts("근기법:제20조"))
    elif "근무장소" in line:
        L.update(verdict="risk", reason="근무장소 변경 가능성에 대한 언급이 없어 불리할 수 있다.")
    return L, R

class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=str(ROOT), **k)
    def log_message(self, *a): pass
    def _json(self, obj):
        b = json.dumps(obj, ensure_ascii=False).encode(); self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"): self.path = "/static/index.html"; return super().do_GET()
        if self.path == "/api/samples": return self._json({"samples": [{"id": "alba_cafe", "title": "카페 알바 계약서"}, {"id": "oneroom_lease", "title": "원룸 월세 계약서"}, {"id": "clean_alba", "title": "표준 알바 계약서"}], "answers": {"alba_cafe": {"risky_clauses": RISKY}}})
        if self.path.startswith("/api/samples/"): return self._json({"text": SAMPLE})
        if self.path == "/api/evidence": return self._json({"note": "RUN_REPORT.md 수치. 실서비스 오른쪽은 분류기가 고른 주제로 조문을 연결하므로 실험 A1보다 조건이 나쁠 수 있습니다.", "t2_q8b_a0": "0.609", "t2_roberta42": "0.861", "t3_rule": "1.000", "t3_q8b_a4bm25": "0.724", "t3_ax7_a1": "0.838", "t3_ax7_a1_text": "0.882", "t4_q8b_a4bm25": "0.448", "t4_q8bt_a3": "0.806"})
        if self.path == "/api/replay":
            random.seed(1); rows = []
            for i in range(402):
                gold = i % 2 == 0; kind = "numeric" if i % 5 < 2 else "text"
                lr = gold if random.random() < .72 else (not gold); rr = gold if random.random() < .9 else (not gold)
                rows.append({"id": f"L-T0{i%9+1}-P{i%5+1}-{'R' if gold else 'S'}", "gold": gold, "left_risky": lr, "right_risky": rr, "left_ok": lr == gold, "right_ok": rr == gold,
                             "actor": "규칙" if kind == "numeric" else "모델", "check_id": f"L-T0{i%9+1}", "kind": kind, "surface": "0AB"[i % 3],
                             "clause": "주 5일, 1일 5시간 근무하며 주휴수당은 지급하지 않는다.", "left_reason": "주휴수당 미지급은 불리하다.", "right_reason": "주 25시간 근무이므로 주휴일 보장 대상이다."})
            return self._json({"code": "app_compare/replay.py → exp_v2/score_v2.py::balanced_acc, pair_acc", "summary": {"fmt": {"left_bacc": "0.724 [0.669, 0.776]", "right_bacc": "0.912 [0.876, 0.944]", "diff_bacc": "+0.188 [0.131, 0.246]", "left_pair": "0.473 [0.400, 0.550]", "right_pair": "0.836 [0.776, 0.888]", "diff_pair": "+0.363 [0.276, 0.448]", "left_num": "0.701", "right_num": "1.000", "left_text": "0.744", "right_text": "0.882"}}, "rows": rows})
        return super().do_GET()
    def do_POST(self):
        if self.path != "/api/analyze": self.send_error(404); return
        n = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(n) or b"{}")
        lines = [l for l in body.get("text", "").splitlines() if l.strip()]
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        def send(ev, obj): self.wfile.write(f"event: {ev}\ndata: {json.dumps(obj, ensure_ascii=False)}\n\n".encode()); self.wfile.flush()
        send("meta", {"domain_ko": "근로·알바", "n": len(lines)})
        for i, l in enumerate(lines):
            L, R = judge(i, l); time.sleep(0.05)
            send("clause", {"left": L, "right": R, "differ": L["verdict"] != R["verdict"]})
        send("done", {})

if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8765), H).serve_forever()
