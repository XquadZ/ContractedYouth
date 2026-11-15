# 계약서 점검 비교

로컬에서만 연다. 주소는 `http://127.0.0.1:8090`. 외부 API와 CDN은 쓰지 않는다.

## 모델 서버

작업 폴더의 llama.cpp b11755 로 두 프로세스를 띄운다. 설정은 RUN과 같다. ctx 8192, `-np 1`, `--cache-prompt`. thinking 켜고 끄기는 요청마다 바꾸므로 서버는 `--reasoning auto`다.

```text
python app_compare\llm_servers.py
```

- Qwen3-8B Q8_0: `127.0.0.1:8081`
  - 파일: `data_local\models\Qwen3-8B-Q8_0.gguf`
  - 판정: temperature 0, max_tokens 256, repeat_penalty 1.05, thinking 끔
  - 조문 선택(후보가 여러 개): temperature 0.6, top_p 0.95, top_k 20, seed 42, max_tokens 4096, thinking 켬
- A.X 4.0 Light Q8_0: `127.0.0.1:8082`
  - 파일: `data_local\models\A.X-4.0-Light-Q8_0.gguf`
  - temperature 0, max_tokens 256

메모리 기록은 `app_compare\logs\vram.json`이다. 두 모델이 같이 올라가지 않으면 `logs\vram_fail.json`을 남기고 프로세스를 끈다.

끄는 법: 서버 창에서 Ctrl+C. 남아 있으면 작업 관리자에서 `llama-server.exe` 두 개를 끝낸다.

## 분류기

`app_compare\models\roberta_t2_seed42`

없을 때 다시 학습한다. lr 2e-5, epoch 3, batch 16, max_len 256, seed 42.

```text
python app_compare\train_t2.py
```

## 앱

모델 서버를 켠 다음:

```text
python app_compare\server.py
```

브라우저에서 `http://127.0.0.1:8090`.

끄는 법: 앱 창에서 Ctrl+C.

## 재생 일치

```text
python app_compare\check_match.py oracle
python app_compare\check_match.py slot
```

`oracle`은 gold check 조문(A1)을 넣는다. `slot`은 분류기가 고른 slot의 조문을 넣는다.
