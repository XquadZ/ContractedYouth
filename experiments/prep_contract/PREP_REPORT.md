# PREP_REPORT — 계약서 분석 실험 준비 측정

## 실패/미확인 항목 요약

- T1 student ctx=16384: OutOfMemoryError: CUDA out of memory. Tried to allocate 24.90 GiB. GPU 0 has a total capacity of 24.00 GiB of which 14.3
- T2 표 누락 standard_forms\_excluded\상가건물임대차권리금계약서(국토교통부작성)_2015-05-27.hwp chars=1369 status=표 누락(가능) — hwp5txt 평문, 테이블 구조 없음
- T2 표 누락 standard_forms\lease\H3_민간임대주택표준임대차계약서(별지24호)_2025-10-31.hwp chars=36 status=표 누락(가능) — hwp5txt 평문, 테이블 구조 없음
- T2 표 누락 standard_forms\lease\H3a_민간임대주택표준임대차계약서(별지24호)_2020-12-10시행.hwp chars=36 status=표 누락(가능) — hwp5txt 평문, 테이블 구조 없음
- T2 표 누락 standard_forms\lease\H3b_민간임대주택표준임대차계약서(별지24호)_2022-01-15시행.hwp chars=36 status=표 누락(가능) — hwp5txt 평문, 테이블 구조 없음
- T2 표 누락 standard_forms\lease\H3c_민간임대주택표준임대차계약서(별지24호)_2023-01-01시행.hwp chars=36 status=표 누락(가능) — hwp5txt 평문, 테이블 구조 없음
- T2 표 누락 standard_forms\lease\H3d_민간임대주택표준임대차계약서(별지24호)_2023-08-03시행.hwp chars=36 status=표 누락(가능) — hwp5txt 평문, 테이블 구조 없음
- T2 표 누락 standard_forms\lease\H3e_민간임대주택표준임대차계약서(별지24호)_2025-06-04시행.hwp chars=36 status=표 누락(가능) — hwp5txt 평문, 테이블 구조 없음
- T2 표 누락 standard_forms\loan\D1_금전소비대차계약서-지연손해금특약(KLAC서식1770)_현행.hwp chars=627 status=표 누락(가능) — hwp5txt 평문, 테이블 구조 없음
- T2 표 누락 standard_forms\loan\D1_금전차용계약서(KLAC서식1769)_현행.hwp chars=621 status=표 누락(가능) — hwp5txt 평문, 테이블 구조 없음
- T2 표 누락 standard_forms\loan\D2_보증계약서-일반(KLAC서식1807)_현행.hwp chars=457 status=표 누락(가능) — hwp5txt 평문, 테이블 구조 없음
- T3: OC 미설정 (LAW_OC 비어 있음) — 전체 건너뜀

---

## T1. 긴 문맥 처리량·VRAM

### 모델 경로

- 교사 GGUF: `C:\Users\DMLAB\pilot_root\models\Qwen3-32B-GGUF\Qwen3-32B-Q6_K.gguf`
- 학생 베이스 (run3/adapter_B/train_meta.json): `C:\Users\DMLAB\pilot_root\models\Qwen2.5-14B-Instruct`
- 측정 조건: 입력≈ctx×0.8 토큰 한국어, 출력 max 512, thinking 끔

### 교사 (llama-server Qwen3-32B-Q6_K)

| ctx | load_ok | infer_ok | input_tokens | prompt tok/s | gen tok/s | elapsed_sec | VRAM(after load) | error |
|---:|:---:|:---:|---:|---:|---:|---:|---|---|
| 4096 | True | True | 3325 | 361.14705417994156 | 16.085683654597766 | 16.314 | `index, name, memory.used [MiB], memory.total [MiB], utilization.gpu [%] ; 0, NVIDIA TITAN RTX, 14328 MiB, 24576 MiB, 8 % ; 1, NVIDIA TITAN RTX, 13365 MiB, 24576` |  |
| 8192 | True | True | 6520 | 766.7141055252433 | 15.970127969574841 | 19.266 | `index, name, memory.used [MiB], memory.total [MiB], utilization.gpu [%] ; 0, NVIDIA TITAN RTX, 14867 MiB, 24576 MiB, 11 % ; 1, NVIDIA TITAN RTX, 13877 MiB, 2457` |  |
| 16384 | True | True | 13067 | 818.2157301911822 | 14.569924042129328 | 22.463 | `index, name, memory.used [MiB], memory.total [MiB], utilization.gpu [%] ; 0, NVIDIA TITAN RTX, 15956 MiB, 24576 MiB, 39 % ; 1, NVIDIA TITAN RTX, 14901 MiB, 2457` |  |

<details><summary>nvidia-smi teacher ctx=4096 after load</summary>

```
index, name, memory.used [MiB], memory.total [MiB], utilization.gpu [%]
0, NVIDIA TITAN RTX, 14328 MiB, 24576 MiB, 8 %
1, NVIDIA TITAN RTX, 13365 MiB, 24576 MiB, 0 %
```
</details>

<details><summary>nvidia-smi teacher ctx=4096 after infer</summary>

```
index, name, memory.used [MiB], memory.total [MiB], utilization.gpu [%]
0, NVIDIA TITAN RTX, 14322 MiB, 24576 MiB, 55 %
1, NVIDIA TITAN RTX, 13383 MiB, 24576 MiB, 42 %
```
</details>

<details><summary>nvidia-smi teacher ctx=8192 after load</summary>

```
index, name, memory.used [MiB], memory.total [MiB], utilization.gpu [%]
0, NVIDIA TITAN RTX, 14867 MiB, 24576 MiB, 11 %
1, NVIDIA TITAN RTX, 13877 MiB, 24576 MiB, 26 %
```
</details>

<details><summary>nvidia-smi teacher ctx=8192 after infer</summary>

```
index, name, memory.used [MiB], memory.total [MiB], utilization.gpu [%]
0, NVIDIA TITAN RTX, 14865 MiB, 24576 MiB, 57 %
1, NVIDIA TITAN RTX, 13895 MiB, 24576 MiB, 42 %
```
</details>

<details><summary>nvidia-smi teacher ctx=16384 after load</summary>

```
index, name, memory.used [MiB], memory.total [MiB], utilization.gpu [%]
0, NVIDIA TITAN RTX, 15956 MiB, 24576 MiB, 39 %
1, NVIDIA TITAN RTX, 14901 MiB, 24576 MiB, 22 %
```
</details>

<details><summary>nvidia-smi teacher ctx=16384 after infer</summary>

```
index, name, memory.used [MiB], memory.total [MiB], utilization.gpu [%]
0, NVIDIA TITAN RTX, 16025 MiB, 24576 MiB, 59 %
1, NVIDIA TITAN RTX, 14919 MiB, 24576 MiB, 41 %
```
</details>


원본 JSON: `prep_contract/t1_teacher_results.json` / 로그 `t1_teacher_console.log`

### 학생 (HF 4bit nf4 float16)

| ctx | load_ok | infer_ok | input_tokens | prompt tok/s (approx) | gen tok/s (approx) | elapsed_sec | overall tok/s | error |
|---:|:---:|:---:|---:|---:|---:|---:|---:|---|
| 4096 | True | True | 3240 | 669.922 | 7.454 | 26.301 | 129.275 |  |
| 8192 | True | True | 6467 | 401.117 | 5.035 | 39.361 | 167.271 |  |
| 16384 | True | False | 12926 | None | None | None | None | OutOfMemoryError: CUDA out of memory. Tried to allocate 24.90 GiB. GPU 0 has a t |

참고: HF `generate` 단일 호출이라 prompt/gen tok/s는 분리 미측정. `prompt_tok_s_approx_via_max1` / `gen_tok_s_approx`는 스크립트 근사값.

<details><summary>nvidia-smi student after load (공통)</summary>

```
index, name, memory.used [MiB], memory.total [MiB], utilization.gpu [%]
0, NVIDIA TITAN RTX, 5248 MiB, 24576 MiB, 42 %
1, NVIDIA TITAN RTX, 5383 MiB, 24576 MiB, 11 %
```
</details>

<details><summary>nvidia-smi student ctx=4096 after infer</summary>

```
index, name, memory.used [MiB], memory.total [MiB], utilization.gpu [%]
0, NVIDIA TITAN RTX, 9830 MiB, 24576 MiB, 9 %
1, NVIDIA TITAN RTX, 9951 MiB, 24576 MiB, 97 %
```
</details>

<details><summary>nvidia-smi student ctx=8192 after infer</summary>

```
index, name, memory.used [MiB], memory.total [MiB], utilization.gpu [%]
0, NVIDIA TITAN RTX, 22596 MiB, 24576 MiB, 31 %
1, NVIDIA TITAN RTX, 22715 MiB, 24576 MiB, 99 %
```
</details>

<details><summary>nvidia-smi student ctx=16384 after error</summary>

```
index, name, memory.used [MiB], memory.total [MiB], utilization.gpu [%]
0, NVIDIA TITAN RTX, 9451 MiB, 24576 MiB, 48 %
1, NVIDIA TITAN RTX, 22715 MiB, 24576 MiB, 0 %
```
</details>

<details><summary>error ctx=16384</summary>

```
OutOfMemoryError: CUDA out of memory. Tried to allocate 24.90 GiB. GPU 0 has a total capacity of 24.00 GiB of which 14.36 GiB is free. Of the allocated memory 6.63 GiB is allocated by PyTorch, and 1.75 GiB is reserved by PyTorch but unallocated. If reserved but unallocated memory is large try setting PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True to avoid fragmentation.  See documentation for Memory Management  (https://pytorch.org/docs/stable/notes/cuda.html#environment-variables)
Traceback (most recent call last):
  File "C:\Users\DMLAB\pilot_root\prep_contract\t1_measure_student.py", line 180, in main
    gen = model.generate(
  File "C:\Users\DMLAB\anaconda3\envs\pytorch\lib\site-packages\torch\utils\_contextlib.py", line 120, in decorate_context
    return func(*args, **kwargs)
  File "C:\Users\DMLAB\anaconda3\envs\pytorch\lib\site-packages\transformers\generation\utils.py", line 2982, in generate
    result = decoding_method(
  File "C:\Users\DMLAB\anaconda3\envs\pytorch\lib\site-packages\transformers\generation\utils.py", line 3182, in _sample
    outputs = self._prefill(
  File "C:\Users\DMLAB\anaconda3\envs\pytorch\lib\site-packages\transformers\generation\utils.py", line 4293, in _prefill
    return self(**model_inputs, return_dict=True)
  File "C:\Users\DMLAB\anaconda3\envs\pytorch\lib\site-packages\torch\nn\modules\module.py", line 1775, in _wrapped_call_impl
    return self._call_impl(*args, **kwargs)
  File "C:\Users\DMLAB\anaconda3\envs\pytorch\lib\site-packages\torch\nn\modules\module.py", line 1786, in _call_impl
    return forward_call(*args, **kwargs)
  File "C:\Users\DMLAB\anaconda3\envs\pytorch\lib\site-packages\accelerate\hooks.py", line 192, in new_forward
    output = module._old_forward(*args, **kwargs)
  File "C:\Users\DMLAB\anaconda3\envs\pytorch\lib\site-packages\transformers\utils\generic.py", line 943, in wrapper
    output = func(self, *args, **kwargs)
  File "C:\Users\DMLAB\anaconda3\envs\pytorch\lib\site-packages\transformers\models\qwen2\modeling_qwen2.py", line 444, in forward
    outputs: BaseModelOutputWithPast = self.model(
  File "C:\Users\DMLAB\anaconda3\envs\pytorch\lib\site-packages\torch\nn\modules\module.py", line 1775, in _wrapped_call_impl
    return self._call_impl(*args, **kwargs)
  File "C:\Users\DMLAB\anaconda3\envs\pytorch\lib\site-packages\torch\nn\modules\module.py", line 1786, in _call_impl
    return forward_call(*args, **kwargs)
  File "C:\Users\DMLAB\anaconda3\envs\pytorch\lib\site-packages\transformers\utils\generic.py", line 1081, in wrapper
    output = func(self, *args, **kwargs)
  File "C:\Users\DMLAB\anaconda3\envs\pytorch\lib\site-packages\transformers\utils\output_capturing.py", line 287, in wrapper
    outputs = func(self, *args, **kwargs)
  File "C:\Users\DMLAB\anaconda3\envs\pytorch\lib\site-packages\transformers\models\qwen2\modeling_qwen2.py", line 380, in forward
    hidden_states = decoder_layer(
  File "C:\Users\DMLAB\anaconda3\envs\pytorch\lib\site-packages\transformers\modeling_layers.py", line 110, in __call__
    return super().__call__(*args, **kwargs)
  File "C:\Users\DMLAB\anaconda3\envs\pytorch\lib\site-packages\torch\nn\modules\module.py", line 1775, in _wrapped_call_impl
    return self._call_impl(*args, **kwargs)
  File "C:\Users\DMLAB\anaconda3\envs\pytorch\lib\site-packages\torch\nn\modules\module.py", line 1786, in _call_impl
    return forward_call(*args, **kwargs)
  File "C:\Users\DMLAB\anaconda3\envs\pytorch\lib\site-packages\accelerate\hooks.py", line 192, in new_forward
    output = module._old_forward(*args, **kwargs)
  File "C:\Users\DMLAB\anaconda3\envs\pytorch\lib\site-packages\transformers\models\qwen2\modeling_qwen2.py", line 274, in forward
    hidden_states, _ = self.self_attn(
  File "C:\Users\DMLAB\anaconda3\envs\pytorch\lib\site-packages\torch\nn\modules\module.py", line 1775, in _wrapped_call_impl
    return self._call_impl(*args, **kwargs)
  File "C:\Users\DMLAB\anaconda3\envs\pytorch\lib\site-packages\torch\nn\modules\mo
```
</details>


원본 JSON: `prep_contract/t1_student_results.json`

---

## T2. 문서 → 텍스트 추출

### 도구 상태
```json
{
  "hwp5txt": "C:\\Users\\DMLAB\\anaconda3\\Scripts\\hwp5txt.EXE",
  "pdftotext": null,
  "pdfplumber": true,
  "olefile": true
}
```

- 대상 파일 수: 26

| 파일 | 형식 | 성공 | 글자 수 | 표 추출 여부 | method |
|---|---|:---:|---:|---|---|
| `standard_forms\_excluded\상가건물임대차권리금계약서(국토교통부작성)_2015-05-27.hwp` | .hwp | True | 1369 | 표 누락(가능) — hwp5txt 평문, 테이블 구조 없음 | hwp5txt |
| `standard_forms\_excluded\상가건물임대차표준계약서_2026-05-12(사용용).hwp` | .hwp | True | 2466 | 표 가능(공백/탭) — 구조 미확인 | hwp5txt |
| `standard_forms\_excluded\상가건물임대차표준계약서_2026-05-12(원본게시용).pdf` | .pdf | True | 6625 | 표 추출됨(셀/테이블 텍스트 감지) | pdfplumber |
| `standard_forms\labor\L1-L3_표준근로계약서묶음(5종)_2025-03.hwp` | .hwp | True | 7351 | 표 가능(공백/탭) — 구조 미확인 | hwp5txt |
| `standard_forms\labor\L4-L6_표준근로계약서묶음(7종)_2019-06.hwp` | .hwp | True | 6319 | 표 가능(공백/탭) — 구조 미확인 | hwp5txt |
| `standard_forms\lease\H1_주택임대차표준계약서_2023-10-06(사용용).hwp` | .hwp | True | 2438 | 표 가능(공백/탭) — 구조 미확인 | hwp5txt |
| `standard_forms\lease\H1_주택임대차표준계약서_2023-10-06(원본게시용).pdf` | .pdf | True | 9782 | 표 추출됨(셀/테이블 텍스트 감지) | pdfplumber |
| `standard_forms\lease\H2_주택임대차표준계약서_2022(사용용).hwp` | .hwp | True | 2437 | 표 가능(공백/탭) — 구조 미확인 | hwp5txt |
| `standard_forms\lease\H2_주택임대차표준계약서_2022(원본게시용).pdf` | .pdf | True | 9370 | 표 추출됨(셀/테이블 텍스트 감지) | pdfplumber |
| `standard_forms\lease\H2a_주택임대차표준계약서_2023-04(사용용).hwp` | .hwp | True | 2437 | 표 가능(공백/탭) — 구조 미확인 | hwp5txt |
| `standard_forms\lease\H2a_주택임대차표준계약서_2023-04(원본게시용).pdf` | .pdf | True | 9771 | 표 추출됨(셀/테이블 텍스트 감지) | pdfplumber |
| `standard_forms\lease\H3_민간임대주택표준임대차계약서(별지24호)_2025-10-31.hwp` | .hwp | True | 36 | 표 누락(가능) — hwp5txt 평문, 테이블 구조 없음 | hwp5txt |
| `standard_forms\lease\H3_민간임대주택표준임대차계약서(별지24호)_2025-10-31.pdf` | .pdf | True | 11006 | 표 추출됨(셀/테이블 텍스트 감지) | pdfplumber |
| `standard_forms\lease\H3a_민간임대주택표준임대차계약서(별지24호)_2020-12-10시행.hwp` | .hwp | True | 36 | 표 누락(가능) — hwp5txt 평문, 테이블 구조 없음 | hwp5txt |
| `standard_forms\lease\H3a_민간임대주택표준임대차계약서(별지24호)_2020-12-10시행.pdf` | .pdf | True | 9034 | 표 추출됨(셀/테이블 텍스트 감지) | pdfplumber |
| `standard_forms\lease\H3b_민간임대주택표준임대차계약서(별지24호)_2022-01-15시행.hwp` | .hwp | True | 36 | 표 누락(가능) — hwp5txt 평문, 테이블 구조 없음 | hwp5txt |
| `standard_forms\lease\H3b_민간임대주택표준임대차계약서(별지24호)_2022-01-15시행.pdf` | .pdf | True | 9931 | 표 추출됨(셀/테이블 텍스트 감지) | pdfplumber |
| `standard_forms\lease\H3c_민간임대주택표준임대차계약서(별지24호)_2023-01-01시행.hwp` | .hwp | True | 36 | 표 누락(가능) — hwp5txt 평문, 테이블 구조 없음 | hwp5txt |
| `standard_forms\lease\H3c_민간임대주택표준임대차계약서(별지24호)_2023-01-01시행.pdf` | .pdf | True | 10236 | 표 추출됨(셀/테이블 텍스트 감지) | pdfplumber |
| `standard_forms\lease\H3d_민간임대주택표준임대차계약서(별지24호)_2023-08-03시행.hwp` | .hwp | True | 36 | 표 누락(가능) — hwp5txt 평문, 테이블 구조 없음 | hwp5txt |
| `standard_forms\lease\H3d_민간임대주택표준임대차계약서(별지24호)_2023-08-03시행.pdf` | .pdf | True | 10381 | 표 추출됨(셀/테이블 텍스트 감지) | pdfplumber |
| `standard_forms\lease\H3e_민간임대주택표준임대차계약서(별지24호)_2025-06-04시행.hwp` | .hwp | True | 36 | 표 누락(가능) — hwp5txt 평문, 테이블 구조 없음 | hwp5txt |
| `standard_forms\lease\H3e_민간임대주택표준임대차계약서(별지24호)_2025-06-04시행.pdf` | .pdf | True | 10999 | 표 추출됨(셀/테이블 텍스트 감지) | pdfplumber |
| `standard_forms\loan\D1_금전소비대차계약서-지연손해금특약(KLAC서식1770)_현행.hwp` | .hwp | True | 627 | 표 누락(가능) — hwp5txt 평문, 테이블 구조 없음 | hwp5txt |
| `standard_forms\loan\D1_금전차용계약서(KLAC서식1769)_현행.hwp` | .hwp | True | 621 | 표 누락(가능) — hwp5txt 평문, 테이블 구조 없음 | hwp5txt |
| `standard_forms\loan\D2_보증계약서-일반(KLAC서식1807)_현행.hwp` | .hwp | True | 457 | 표 누락(가능) — hwp5txt 평문, 테이블 구조 없음 | hwp5txt |

### 파일별 앞 300자

#### `standard_forms\_excluded\상가건물임대차권리금계약서(국토교통부작성)_2015-05-27.hwp`
```

<그림>

<그림>




<표>
상가건물 임대차 권리금계약서
-  / 3 -



  [계약내용]
 제1조(권리금의 지급) 신규임차인은 임차인에게 다음과 같이 권리금을 지급한다.

<표>

 제2조(임차인의 의무) ① 임차인은 신규임차인을 임대인에게 주선하여야 하며, 임대인과 신규임차인 간에 임대차계약이 체결될 수 있도록 협력하여야 한다. 
   ② 임차인은 신규임차인이 정상적인 영업을 개시할 수 있도록 전화가입권의 이전, 사업등록의 폐지 등에 협력하여야 한다.
   ③ 임차인은 신규임차인이 잔금을 지급할 때까지 권리금의 대가로
```

#### `standard_forms\_excluded\상가건물임대차표준계약서_2026-05-12(사용용).hwp`
```

<그림>

<그림>



<그림>


<표>
상가건물 임대차 표준계약서
-  / 4 -


 제2조(임대차기간) 임대인은 임차 상가건물을 임대차 목적대로 사용‧수익할 수 있는 상태로         년      월        일까지 임차인에게 인도하고, 임대차기간은 인도일로부터          년           월          일까지로 한다. 
 제3조(임차목적) 임차인은 임차 상가건물을           (업종)을 위한 용도로 사용한다.
 제4조(사용·관리·수선) ① 임차인은 임대인의 동의 없이 임차 상가건물의 구조․용도
```

#### `standard_forms\_excluded\상가건물임대차표준계약서_2026-05-12(원본게시용).pdf`
```
이 계약서는 법무부에서 국토교통부‧서울시․중소벤처기업부･소상공인진흥공단 등 유관 기관 및 학계 전문가와 함께 민법,
상가건물 임대차보호법, 공인중개사법 등 관계법령에 근거하여 만들었습니다. 법의 보호를 받기 위해 【중요확인사항】(별지)을
꼭 확인하시기 바랍니다.
q보증금 있는 월세
상가건물 임대차 표준계약서 q전세 q월세
임대인(이름 또는 법인명 기재)과 임차인(이름 또는 법인명 기재)은 아래와 같이 임대차 계약을 체결한다
[임차 상가건물의 표시]
소 재 지
토 지 지목 면적 ㎡
건 물 구조‧용도 면적 ㎡
임차할부분 면적 ㎡
유의사
```

#### `standard_forms\labor\L1-L3_표준근로계약서묶음(5종)_2025-03.hwp`
```

<표>

                (이하 “사업주”라 함)과(와)            (이하 “근로자”라 함)은 다음과 같이 근로계약을 체결한다.
1. 근로개시일 :      년   월   일부터
2. 근 무 장 소 : 
3. 업무의 내용 : 
4. 소정근로시간 :   시  분 ~   시  분 (휴게 :  시  분 ~  시  분) (1일  시간, 1주  시간)
5. 근무일/휴일 : 매주   일 근무(필요시, 근무요일       ), 주휴일 매주   요일
 - 공휴일(대체공휴일 포함)은 근로기준법이 정하는 바에 따르며, 근로자의
```

#### `standard_forms\labor\L4-L6_표준근로계약서묶음(7종)_2019-06.hwp`
```

<표>

                (이하 “사업주”라 함)과(와)            (이하 “근로자”라 함)은 다음과 같이 근로계약을 체결한다.
1. 근로개시일 :      년   월   일부터
2. 근 무 장 소 : 
3. 업무의 내용 : 
4. 소정근로시간 :    시   분부터    시   분까지 (휴게시간 :  시  분~  시   분)
5. 근무일/휴일 : 매주   일(또는 매일단위)근무, 주휴일 매주   요일
6. 임  금
  - 월(일, 시간)급 :                    원
  - 상여금 : 있음 ( 
```

#### `standard_forms\lease\H1_주택임대차표준계약서_2023-10-06(사용용).hwp`
```

<그림>

<그림>



<그림>


<그림>
주택임대차표준계약서
<표>


-  / 4 -

 제2조(임대차기간) 임대인은 임차주택을 임대차 목적대로 사용‧수익할 수 있는 상태로         년      월      일까지 임차인에게 인도하고, 임대차기간은 인도일로부터          년           월          일까지로 한다. 
 제3조(입주 전 수리) 임대인과 임차인은 임차주택의 수리가 필요한 시설물 및 비용부담에 관하여 다음과 같이 합의한다.

<표>



 제4조(임차주택의 사용·관리·수선) ① 임차인은 임
```

#### `standard_forms\lease\H1_주택임대차표준계약서_2023-10-06(원본게시용).pdf`
```
이 계약서는 법무부가 국토교통부·서울시 및 관련 전문가들과 함께 민법, 주택임대차보호법, 공인중개사법 등 관계법령에 근거하여
만들었습니다. 법의 보호를 받기 위해 【중요확인사항】(별지1)을 꼭 확인하시기 바랍니다.
주택임대차표준계약서
q보증금 있는 월세
q전세 q월세
임대인(이름 또는 법인명 기재)과 임차인(이름 또는 법인명 기재)은 아래와 같이 임대차 계약을 체결한다
[임차주택의 표시]
소 재 지 (도로명주소)
토 지 지목 면적 ㎡
건 물 구조‧용도 면적 ㎡
임차할부분 상세주소가 있는 경우 동‧층‧호 정확히 기재 면적 ㎡
q 신규
```

#### `standard_forms\lease\H2_주택임대차표준계약서_2022(사용용).hwp`
```

<그림>

<그림>



<그림>


<그림>
주택임대차표준계약서
<표>


-  / 4 -

 제2조(임대차기간) 임대인은 임차주택을 임대차 목적대로 사용‧수익할 수 있는 상태로         년      월      일까지 임차인에게 인도하고, 임대차기간은 인도일로부터          년           월          일까지로 한다. 

<표>
 제3조(입주 전 수리) 임대인과 임차인은 임차주택의 수리가 필요한 시설물 및 비용부담에 관하여 다음과 같이 합의한다.





 제4조(임차주택의 사용·관리·수선) ① 임차인은
```

#### `standard_forms\lease\H2_주택임대차표준계약서_2022(원본게시용).pdf`
```
이 계약서는 법무부가 국토교통부·서울시 및 관련 전문가들과 함께 민법, 주택임대차보호법, 공인중개사법 등 관계법령에 근거하여
만들었습니다. 법의 보호를 받기 위해 【중요확인사항】(별지1)을 꼭 확인하시기 바랍니다.
주택임대차표준계약서
q보증금 있는 월세
q전세 q월세
임대인(이름 또는 법인명 기재)과 임차인(이름 또는 법인명 기재)은 아래와 같이 임대차 계약을 체결한다
[임차주택의 표시]
소 재 지 (도로명주소)
토 지 지목 면적 ㎡
건 물 구조‧용도 면적 ㎡
임차할부분 상세주소가 있는 경우 동‧층‧호 정확히 기재 면적 ㎡
q 신규
```

#### `standard_forms\lease\H2a_주택임대차표준계약서_2023-04(사용용).hwp`
```

<그림>

<그림>



<그림>


<그림>
주택임대차표준계약서
<표>


-  / 5 -

 제2조(임대차기간) 임대인은 임차주택을 임대차 목적대로 사용‧수익할 수 있는 상태로         년      월      일까지 임차인에게 인도하고, 임대차기간은 인도일로부터          년           월          일까지로 한다. 

<표>
 제3조(입주 전 수리) 임대인과 임차인은 임차주택의 수리가 필요한 시설물 및 비용부담에 관하여 다음과 같이 합의한다.





 제4조(임차주택의 사용·관리·수선) ① 임차인은
```

#### `standard_forms\lease\H2a_주택임대차표준계약서_2023-04(원본게시용).pdf`
```
이 계약서는 법무부가 국토교통부·서울시 및 관련 전문가들과 함께 민법, 주택임대차보호법, 공인중개사법 등 관계법령에 근거하여
만들었습니다. 법의 보호를 받기 위해 【중요확인사항】(별지1)을 꼭 확인하시기 바랍니다.
주택임대차표준계약서
q보증금 있는 월세
q전세 q월세
임대인(이름 또는 법인명 기재)과 임차인(이름 또는 법인명 기재)은 아래와 같이 임대차 계약을 체결한다
[임차주택의 표시]
소 재 지 (도로명주소)
토 지 지목 면적 ㎡
건 물 구조‧용도 면적 ㎡
임차할부분 상세주소가 있는 경우 동‧층‧호 정확히 기재 면적 ㎡
q 신규
```

#### `standard_forms\lease\H3_민간임대주택표준임대차계약서(별지24호)_2025-10-31.hwp`
```

<표>


<표>


<표>


<표>


<표>


<표>


```

#### `standard_forms\lease\H3_민간임대주택표준임대차계약서(별지24호)_2025-10-31.pdf`
```
■ 민간임대주택에 관한 특별법 시행규칙 [별지 제24호서식] <개정 2025. 10. 31.>
표준임대차계약서
(6쪽 중 1쪽)
임대사업자와 임차인은 아래의 같이 임대차계약을 체결하고 이를 증명하기 위해 계약서 2통을 작성하
여 임대사업자와 임차인이 각각 서명 또는 날인한 후 각각 1통씩 보관한다.
※ 개업공인중개사가 임대차계약서를 작성하는 경우에는 계약서 3통을 작성하여 임대사업자, 임차인, 개업공인중
개사가 각각 서명 또는 날인한 후 각각 1통씩 보관한다.
계약일: 년 월 일
1. 계약 당사자
성명(법인명)
(서명 또는 인)
주
```

#### `standard_forms\lease\H3a_민간임대주택표준임대차계약서(별지24호)_2020-12-10시행.hwp`
```

<표>


<표>


<표>


<표>


<표>


<표>


```

#### `standard_forms\lease\H3a_민간임대주택표준임대차계약서(별지24호)_2020-12-10시행.pdf`
```
■ 민간임대주택에 관한 특별법 시행규칙 [별지 제24호서식] <개정 2020. 12. 10.>
표준임대차계약서
(6쪽 중 1쪽)
임대사업자와 임차인은 아래의 같이 임대차계약을 체결하고 이를 증명하기 위해 계약서 2통을 작성하여 임대
사업자와 임차인이 각각 서명 또는 날인한 후 각각 1통씩 보관한다.
※ 개업공인중개사가 임대차계약서를 작성하는 경우에는 계약서 3통을 작성하여 임대사업자, 임차인, 개업공인중개사가
각각 서명 또는 날인한 후 각각 1통씩 보관한다.
계약일: 년 월 일
1. 계약 당사자
성명(법인명)
(서명 또는 인)
주소
```

#### `standard_forms\lease\H3b_민간임대주택표준임대차계약서(별지24호)_2022-01-15시행.hwp`
```

<표>


<표>


<표>


<표>


<표>


<표>


```

#### `standard_forms\lease\H3b_민간임대주택표준임대차계약서(별지24호)_2022-01-15시행.pdf`
```
■ 민간임대주택에 관한 특별법 시행규칙 [별지 제24호서식] <개정 2022. 1. 14.>
표준임대차계약서
(6쪽 중 1쪽)
임대사업자와 임차인은 아래의 같이 임대차계약을 체결하고 이를 증명하기 위해 계약서 2통을 작성하여 임대
사업자와 임차인이 각각 서명 또는 날인한 후 각각 1통씩 보관한다.
※ 개업공인중개사가 임대차계약서를 작성하는 경우에는 계약서 3통을 작성하여 임대사업자, 임차인, 개업공인중개사가
각각 서명 또는 날인한 후 각각 1통씩 보관한다.
계약일: 년 월 일
1. 계약 당사자
성명(법인명)
(서명 또는 인)
주소

```

#### `standard_forms\lease\H3c_민간임대주택표준임대차계약서(별지24호)_2023-01-01시행.hwp`
```

<표>


<표>


<표>


<표>


<표>


<표>


```

#### `standard_forms\lease\H3c_민간임대주택표준임대차계약서(별지24호)_2023-01-01시행.pdf`
```
■ 민간임대주택에 관한 특별법 시행규칙 [별지 제24호서식] <개정 2022. 12. 30.>
표준임대차계약서
(6쪽 중 1쪽)
임대사업자와 임차인은 아래의 같이 임대차계약을 체결하고 이를 증명하기 위해 계약서 2통을 작성하여 임대
사업자와 임차인이 각각 서명 또는 날인한 후 각각 1통씩 보관한다.
※ 개업공인중개사가 임대차계약서를 작성하는 경우에는 계약서 3통을 작성하여 임대사업자, 임차인, 개업공인중개사가
각각 서명 또는 날인한 후 각각 1통씩 보관한다.
계약일: 년 월 일
1. 계약 당사자
성명(법인명)
(서명 또는 인)
주소
```

#### `standard_forms\lease\H3d_민간임대주택표준임대차계약서(별지24호)_2023-08-03시행.hwp`
```

<표>


<표>


<표>


<표>


<표>


<표>


```

#### `standard_forms\lease\H3d_민간임대주택표준임대차계약서(별지24호)_2023-08-03시행.pdf`
```
■ 민간임대주택에 관한 특별법 시행규칙 [별지 제24호서식] <개정 2023. 8. 3.>
표준임대차계약서
(6쪽 중 1쪽)
임대사업자와 임차인은 아래의 같이 임대차계약을 체결하고 이를 증명하기 위해 계약서 2통을 작성하여 임대
사업자와 임차인이 각각 서명 또는 날인한 후 각각 1통씩 보관한다.
※ 개업공인중개사가 임대차계약서를 작성하는 경우에는 계약서 3통을 작성하여 임대사업자, 임차인, 개업공인중개사가
각각 서명 또는 날인한 후 각각 1통씩 보관한다.
계약일: 년 월 일
1. 계약 당사자
성명(법인명)
(서명 또는 인)
주소
(
```

#### `standard_forms\lease\H3e_민간임대주택표준임대차계약서(별지24호)_2025-06-04시행.hwp`
```

<표>


<표>


<표>


<표>


<표>


<표>


```

#### `standard_forms\lease\H3e_민간임대주택표준임대차계약서(별지24호)_2025-06-04시행.pdf`
```
■ 민간임대주택에 관한 특별법 시행규칙 [별지 제24호서식] <개정 2025. 6. 4.>
표준임대차계약서
(6쪽 중 1쪽)
임대사업자와 임차인은 아래의 같이 임대차계약을 체결하고 이를 증명하기 위해 계약서 2통을 작성하
여 임대사업자와 임차인이 각각 서명 또는 날인한 후 각각 1통씩 보관한다.
※ 개업공인중개사가 임대차계약서를 작성하는 경우에는 계약서 3통을 작성하여 임대사업자, 임차인, 개업공인중
개사가 각각 서명 또는 날인한 후 각각 1통씩 보관한다.
계약일: 년 월 일
1. 계약 당사자
성명(법인명)
(서명 또는 인)
주소

```

#### `standard_forms\loan\D1_금전소비대차계약서-지연손해금특약(KLAC서식1770)_현행.hwp`
```
[서식 예] 금전소비대차 계약서(지연손해금 특약)
<그림>



금전소비대차 계약서


차용금원  금 ○○○원

채무자는 채권자로부터 위 금원을 아래와 같은 조건으로 차용한다.

제1조(대여일시) 채무자는 채권자로부터 20○○년 ○월 ○일 금 ○○○원을 차용하며 채권자는 이 금액을 즉시 채무자에게 지급한다.
제2조(변제기일 및 변제장소) 채무자는 위 금원의 차용금 원금을 20○○년 ○월 ○일까지 채권자의 주소지에서 채권자에게 변제한다.
제3조(이자의지급등) 위 차용금의 이자는 연 ○○%로 하고 지급은 매월 ○일에 채권자의 주소지에서
```

#### `standard_forms\loan\D1_금전차용계약서(KLAC서식1769)_현행.hwp`
```
[서식 예] 금전차용계약서
<그림>



금  전  차  용  계  약  서

제1조(당사자) 채권자 ○○○(이하 "갑"이라고 함.)는 20○○년 ○월 ○일 금○○○원을 채무자◎◎◎(이하 "을"이라고 함.)에게 대여하고 을은 이를 차용한다. 
제2조(변제기) 차용금의 변제기한은 20○○년 ○월 ○일로 한다. 
제3조(이자 및 지연손해금)  ① 이자는 연 ○%의 비율로 한다.
  ② 원리금의 변제를 지체했을 때에는 을은 연  ○○%의 비율에 의한 지연손해금을 가산해서 지불해야 한다.
제4조(변제방법) 채무의 변제는 갑의 주소 또는 갑
```

#### `standard_forms\loan\D2_보증계약서-일반(KLAC서식1807)_현행.hwp`
```
[서식 예] 보증계약서(일반)
<그림>



보 증 계 약 서 



채권자 ○○○을 갑으로 하고 보증인 ○○○을 을로 하여, 양당사자 간에 보증  채무에 관하여 다음의 계약을 체결한다. 

제1조(계약의 목적) 보증인 을은 20○○년 ○월 ○일 채권자 갑과 채무자 △△△(주소: ○○시 ○○구 ○○로 ○○번지) 간의 ○○계약서에 기재된 채무에 대해서 채무자가 이행을 하지 않을 때는 그 이행을 할 책임을 진다. 
제2조(검색의 항변권의 포기) 보증인은 검색의 이익을 포기한다. 
제3조(채무의 변제의무) 보증인은 채권자로부터 채무자가 
```


---

## T3. 국가법령정보센터 Open API

- status: **OC 미설정**
- oc_configured: False
- note: 환경변수 LAW_OC 비어 있음. T3 전체 건너뜀.

### 연혁/시행일 조회 (문서 근거, OC 미설정으로 실호출 없음)
```json
{
  "source_url": "https://open.law.go.kr/LSO/openApi/guideResult.do?targe=1&target=law&type=1",
  "endpoint": "http://www.law.go.kr/DRF/lawSearch.do?target=law",
  "params_found": {
    "efYd": "시행일자 범위 검색(20090101~20090130)",
    "date": "법령의 공포일자 검색",
    "ancYd": "공포일자 범위 검색",
    "response_field_현행연혁코드": "검색 결과 필드에 현행연혁코드 존재"
  },
  "as_of_single_date_body_fetch": "미확인(OC 없어 실제 호출 불가). 목록 검색의 efYd는 범위 필터이며, 특정일 시점 본문(연혁판) 전용 target 여부는 OC 승인 후 재확인 필요.",
  "conclusion_without_OC": "문서상 시행일(efYd) 필터는 존재. 2022-01-01 시점 본문 단건 조회 성공 여부는 OC 미설정으로 미확인."
}
```

결론: LAW_OC 미설정 → a/b/c API 호출 전부 건너뜀. 문서상 `efYd`(시행일자 범위) 파라미터는 존재하나, 2022-01-01 시점 본문 단건 조회 성공 여부는 **미확인**.

---

## T4. run3 정리 점검

### adapter_B
- eval load path (gen_eval.py): `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\run3\adapter_B`
- eval_loads_checkpoint_subdir: False
- note: gen_eval.py uses RUN3/adapter_{B|C} directory directly via PeftModel.from_pretrained; does not pass checkpoints/checkpoint-*. Root adapter_* is what trainer.save_pretrained wrote after train (final), typically equivalent to last checkpoint (106) if save at end.
- size_compare: `{"root": 275341720, "checkpoint-106": 275341720, "checkpoint-53": 275341720}`
- checkpoints:
  - `checkpoint-106` step=106 epoch=2.0 size=275341720
  - `checkpoint-53` step=53 epoch=1.0 size=275341720

<details><summary>gen_eval.py 관련 줄</summary>

```
26: BASE_MODEL = resolve_student_model()
46: def generate_worker(model_tag: str, adapter: Path | None, gpu: str, items: list[dict], out: Path) -> int:
53:         from peft import PeftModel
68:         tok = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
71:         model = AutoModelForCausalLM.from_pretrained(
72:             BASE_MODEL,
78:         if adapter is not None and adapter.exists() and (adapter / "adapter_config.json").exists():
79:             model = PeftModel.from_pretrained(model, str(adapter))
80:             log(f"[{model_tag}] loaded adapter {adapter}")
83:                 log(f"[{model_tag}] adapter missing, skip model")
168:         adapter = None if args.worker == "A" else RUN3 / f"adapter_{args.worker}"
171:         return generate_worker(args.worker, adapter, args.gpu or "0", items, args.out)
195:     if (RUN3 / "adapter_C" / "adapter_config.json").exists():
198:         log("[C] adapter missing — skip")
209:     if (RUN3 / "adapter_B" / "adapter_config.json").exists():
218:         log("[B] adapter missing — skip")
```
</details>

### adapter_C
- eval load path (gen_eval.py): `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\run3\adapter_C`
- eval_loads_checkpoint_subdir: False
- note: gen_eval.py uses RUN3/adapter_{B|C} directory directly via PeftModel.from_pretrained; does not pass checkpoints/checkpoint-*. Root adapter_* is what trainer.save_pretrained wrote after train (final), typically equivalent to last checkpoint (106) if save at end.
- size_compare: `{"root": 275341720, "checkpoint-106": 275341720, "checkpoint-53": 275341720}`
- checkpoints:
  - `checkpoint-106` step=106 epoch=2.0 size=275341720
  - `checkpoint-53` step=53 epoch=1.0 size=275341720

<details><summary>gen_eval.py 관련 줄</summary>

```
26: BASE_MODEL = resolve_student_model()
46: def generate_worker(model_tag: str, adapter: Path | None, gpu: str, items: list[dict], out: Path) -> int:
53:         from peft import PeftModel
68:         tok = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
71:         model = AutoModelForCausalLM.from_pretrained(
72:             BASE_MODEL,
78:         if adapter is not None and adapter.exists() and (adapter / "adapter_config.json").exists():
79:             model = PeftModel.from_pretrained(model, str(adapter))
80:             log(f"[{model_tag}] loaded adapter {adapter}")
83:                 log(f"[{model_tag}] adapter missing, skip model")
168:         adapter = None if args.worker == "A" else RUN3 / f"adapter_{args.worker}"
171:         return generate_worker(args.worker, adapter, args.gpu or "0", items, args.out)
195:     if (RUN3 / "adapter_C" / "adapter_config.json").exists():
198:         log("[C] adapter missing — skip")
209:     if (RUN3 / "adapter_B" / "adapter_config.json").exists():
218:         log("[B] adapter missing — skip")
```
</details>

### 평가에 쓰인 checkpoint?

근거: `gen_eval.py`는 `RUN3/adapter_{A|B|C}` 경로를 `PeftModel.from_pretrained`에 전달하며 `checkpoints/checkpoint-*` 하위 경로를 지정하지 않음. 루트 `adapter_B`/`adapter_C`는 학습 종료 시 `save_pretrained`된 최종 어댑터. trainer_state 기준 마지막 step은 checkpoint-106 (global_step=106, epoch=2.0). 따라서 평가 로드 대상은 checkpoint-53이 아니라 **루트 adapter(=학습 종료 저장본, 통상 106과 동일 계열)**.

### ROOT 내 1GB 이상 파일 (삭제 안 함)

| GB | bytes | path |
|---:|---:|---|
| 68.614 | 73673967483 | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\계약 법률 문서 서식 데이터\AI 모델.zip` |
| 62.867 | 67503398912 | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\계약 법률 문서 서식 데이터\3.도커이미지\legal_project.tar` |
| 25.037 | 26883306112 | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\models\Qwen3-32B-GGUF\Qwen3-32B-Q6_K.gguf` |
| 24.456 | 26259021600 | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\models\EXAONE-4.0-32B-GGUF\EXAONE-4.0-32B-Q6_K.gguf` |
| 4.656 | 4999802720 | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\계약 법률 문서 서식 데이터\2.AI학습모델파일\계약 법률 문서 서식 자동 생성 모델\model\model-00002-of-00004.safetensors` |
| 4.656 | 4999802720 | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\계약 법률 문서 서식 데이터\2.AI학습모델파일\계약 법률 문서 주요 내용 추출 모델\model\model-00002-of-00004.safetensors` |
| 4.635 | 4976698672 | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\계약 법률 문서 서식 데이터\2.AI학습모델파일\계약 법률 문서 서식 자동 생성 모델\model\model-00001-of-00004.safetensors` |
| 4.635 | 4976698672 | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\계약 법률 문서 서식 데이터\2.AI학습모델파일\계약 법률 문서 주요 내용 추출 모델\model\model-00001-of-00004.safetensors` |
| 4.578 | 4915916176 | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\계약 법률 문서 서식 데이터\2.AI학습모델파일\계약 법률 문서 서식 자동 생성 모델\model\model-00003-of-00004.safetensors` |
| 4.578 | 4915916176 | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\계약 법률 문서 서식 데이터\2.AI학습모델파일\계약 법률 문서 주요 내용 추출 모델\model\model-00003-of-00004.safetensors` |
| 3.721 | 3995338432 | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\models\Qwen2.5-14B-Instruct\model-00004-of-00008.safetensors` |
| 3.721 | 3995328080 | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\models\Qwen2.5-14B-Instruct\model-00003-of-00008.safetensors` |
| 3.721 | 3995328080 | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\models\Qwen2.5-14B-Instruct\model-00006-of-00008.safetensors` |
| 3.721 | 3995328080 | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\models\Qwen2.5-14B-Instruct\model-00007-of-00008.safetensors` |
| 3.721 | 3995327992 | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\models\Qwen2.5-14B-Instruct\model-00002-of-00008.safetensors` |
| 3.706 | 3979624824 | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\models\Qwen2.5-14B-Instruct\model-00005-of-00008.safetensors` |
| 3.618 | 3885154816 | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\models\Qwen2.5-14B-Instruct\model-00001-of-00008.safetensors` |
| 1.582 | 1698703696 | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\models\Qwen2.5-14B-Instruct\model-00008-of-00008.safetensors` |
| 1.088 | 1168138808 | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\계약 법률 문서 서식 데이터\2.AI학습모델파일\계약 법률 문서 서식 자동 생성 모델\model\model-00004-of-00004.safetensors` |
| 1.088 | 1168138808 | `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\계약 법률 문서 서식 데이터\2.AI학습모델파일\계약 법률 문서 주요 내용 추출 모델\model\model-00004-of-00004.safetensors` |

---

## 산출물 경로

- `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\prep_contract\t1_teacher_results.json` exists=True
- `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\prep_contract\t1_student_results.json` exists=True
- `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\prep_contract\t1_teacher_console.log` exists=True
- `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\prep_contract\t2_results.json` exists=True
- `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\prep_contract\t2_out` exists=True
- `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\prep_contract\extract.py` exists=True
- `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\prep_contract\t3_results.json` exists=True
- `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\prep_contract\t4_results.json` exists=True
- `C:\Users\DMLAB\Desktop\학부-AI서비스 개발\prep_contract\PREP_REPORT.md` exists=False