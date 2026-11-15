# 점검 결과

계산 코드: `exp_v2/score_v2.py`의 `metric_ci`, `paired_cluster_diff`, `t3_pack`. 합성 조합 조립은 `app_compare/pipelines/replay.py`. 재생 일치는 `app_compare/check_match.py`.

## 1. 재생 일치

`/api/analyze`에 T3 402문장을 조항 하나씩 넣었다. 이 검사의 판정 호출만 비교했고, 조문 선택 호출은 예시 점검에서 했다. 부트스트랩이 아니라 저장된 판정과의 일치 비율이다.

| 모드 | 왼쪽 = Q8B T3 A4-BM25 | 오른쪽 문구형 = AX7 T3 A1 |
|---|---:|---:|
| oracle_slot=1 (gold check 조문, A1과 같은 자료) | 1.000 (n=402) | 0.991 (n=228, 불일치 2건: `L-T03-P1-S-A`, `H-T05-P1-R`) |
| slot 예측 (분류기 slot의 check 조문 전부) | 1.000 (n=402) | 0.886 (n=228) |

oracle 문구형은 95%를 넘었다. 프롬프트는 고치지 않았다. slot 예측 모드는 정답 조문만 넣는 A1과 자료가 달라 일치율이 낮다. 화면의 실험 근거에 이 차이를 적었다.

## 2. 오른쪽 합성 조합 (새 추론 없음)

왼쪽은 저장된 Q8B T3 A4-BM25. 오른쪽은 numeric이면 규칙, 규칙을 못 하면 AX7 T3 A1, text면 AX7 T3 A1. 부트스트랩 1,000회, seed 42, T3는 pair 단위.

| | 균형 정확도 | 쌍 정답률 | 숫자형 정확도 | 문구형 정확도 |
|---|---|---|---|---|
| 왼쪽 | 0.724 [0.669, 0.776] (n=402) | 0.473 [0.400, 0.550] (n=402) | 0.690 [0.603, 0.776] (n=174) | 0.750 [0.684, 0.816] (n=228) |
| 오른쪽 합성 | 0.933 [0.893, 0.968] (n=402) | 0.866 [0.814, 0.923] (n=402) | 1.000 [1.000, 1.000] (n=174) | 0.882 [0.820, 0.939] (n=228) |
| 오른쪽−왼쪽 | +0.209 [0.147, 0.269] (n=402) | +0.393 [0.304, 0.480] (n=402) |  |  |

## 3. 예시 3개

맞힘/놓침/오탐. 시간은 그 조합의 모델 지연 합이다.

| 예시 | 조항 수 | 왼쪽 맞힘/놓침/오탐 | 오른쪽 맞힘/놓침/오탐 | 왼쪽 합(조항당) | 오른쪽 합(조항당) |
|---|---:|---|---|---|---|
| alba_cafe | 12 | 3 / 1 / 2 | 3 / 1 / 0 | 108.3초 (9.0초) | 77.8초 (6.5초) |
| oneroom_lease | 11 | 4 / 0 / 1 | 4 / 0 / 0 | 158.0초 (14.4초) | 126.4초 (11.5초) |
| clean_alba | 11 | 0 / 0 / 4 | 0 / 0 / 0 | 64.9초 (5.9초) | 35.7초 (3.2초) |

alba_cafe에서 왼쪽은 시급 9,860원을 놓쳤고, 오른쪽은 지각 벌금을 놓쳤다.

## 4. 화면

- `app_compare/logs/shots/check_wide.png` 넓은 점검 탭 (alba_cafe 결과, 두 열)
- `app_compare/logs/shots/check_narrow.png` 너비 400px (위아래, 조항마다 왼쪽 다음 오른쪽)
- `app_compare/logs/shots/replay.png` 평가 재생 탭

## 5. 서버와 분류기

두 모델이 4090 24GB에 같이 올라갔다. `nvidia-smi` 메모리: 시작 10,571MiB 사용, Qwen 후 19,938MiB, 둘 다 후 23,474MiB 사용, 여유 669MiB. 기록은 `app_compare/logs/vram.json`.

RoBERTa T2 seed 42를 다시 학습해 `app_compare/models/roberta_t2_seed42`에 저장했다. T2 test top1 0.860606 (n=330). 보고서의 0.861과 0.001 이내다. 설정은 lr 2e-5, epoch 3, batch 16, max_len 256, seed 42.

Qwen 서버는 요청마다 thinking을 바꾸려고 `--reasoning auto`로 띄웠다. 판정 요청 본문(temperature 0, max_tokens 256, repeat_penalty 1.05, thinking 끔)과 thinking 요청 본문(temperature 0.6, top_p 0.95, top_k 20, seed 42, max_tokens 4096)은 RUN과 같다.
