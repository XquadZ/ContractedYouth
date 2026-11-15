# -*- coding: utf-8 -*-
"""run3 공통 경로·유틸."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\DMLAB\Desktop\학부-AI서비스 개발")
RUNTIME_ROOT = Path(r"C:\Users\DMLAB\pilot_root")
PILOT = ROOT / "pilot"
RUN3 = ROOT / "run3"
SMOKE = RUN3 / "smoke"
SEED = 42

LLAMA_SERVER = RUNTIME_ROOT / "tools" / "llama.cpp" / "llama-server.exe"
QWEN3_GGUF = RUNTIME_ROOT / "models" / "Qwen3-32B-GGUF" / "Qwen3-32B-Q6_K.gguf"
LOCAL_QWEN25 = RUNTIME_ROOT / "models" / "Qwen2.5-14B-Instruct"
HF_QWEN25 = "Qwen/Qwen2.5-14B-Instruct"


def resolve_student_model() -> str:
    """Prefer local snapshot if DOWNLOAD_OK / config present."""
    if (LOCAL_QWEN25 / "config.json").exists() and (LOCAL_QWEN25 / "model.safetensors.index.json").exists():
        shards = list(LOCAL_QWEN25.glob("model-*-of-*.safetensors"))
        if shards and all(p.stat().st_size > 1_000_000_000 for p in shards):
            return str(LOCAL_QWEN25)
    return HF_QWEN25

SYSTEM_SFT = "너는 대학생에게 법률 정보를 쉽고 정확하게 설명하는 안내 AI다."
FOOTER = "구체적인 사안은 대한법률구조공단(132) 등 전문 기관 상담을 권합니다."

TEACHER_SYSTEM = (
    "너는 대학생에게 법률 정보를 쉽고 정확하게 설명하는 안내 AI다. "
    "확실하지 않은 내용은 단정하지 않는다."
)

TEACHER_USER = """아래는 실제 법률 상담 질문과, 변호사가 작성한 답변입니다.
변호사 답변의 내용만을 근거로, 법률을 모르는 대학생이 이해할 수 있도록 쉽게 다시 설명하세요.

[질문]
{question}

[변호사 답변]
{answer}

[작성 규칙]
- 결론은 반드시 변호사 답변의 결론과 같아야 합니다.
- 변호사 답변에 없는 법리·제도·기관명·전화번호·절차·조문·판례를 새로 추가하지 마세요. (마지막 줄의 대한법률구조공단(132) 안내만 예외)
- 법조문 번호와 판례 번호는 변호사 답변에 나온 것만 쓰세요.
- 질문이나 답변에 없는 사실(금액·날짜·행위)을 지어내지 마세요.
- 질문에 나온 당사자 표기(甲·乙·丙, A·B 등)를 그대로 쓰고, 행위의 주체를 바꾸지 마세요.
- "변호사 답변에 따르면", "위 답변에서" 같은 표현을 쓰지 말고, 질문자에게 직접 설명하듯 쓰세요.
- 한국어로만 쓰고, 전체 길이는 공백 포함 400~800자로 하세요.
- 변호사 답변이 질문에 실제로 답하지 않거나, 내용이 부족해 해설을 쓸 수 없으면 다른 내용 없이 [SKIP] 만 출력하세요.

[출력 형식]
1. 🔍 핵심 쟁점: 무엇이 문제인지 1~2문장
2. 📜 관련 법 원칙: 적용되는 법리를 쉬운 말로
3. 💡 이유: 결론에 이르는 논리를 단계별로
4. 📝 이렇게 하세요: 질문자가 할 수 있는 구체적 행동
마지막 줄(문구 그대로, 한 번만): 구체적인 사안은 대한법률구조공단(132) 등 전문 기관 상담을 권합니다."""


class NewlineTqdmStream:
    """\\r 진행바를 줄바꿈으로 바꿔 Get-Content -Wait / tail -f 에서도 % 막대가 보이게 함."""

    def write(self, s: str) -> int:
        if not s:
            return 0
        sys.__stdout__.write(s.replace("\r", "\n"))
        sys.__stdout__.flush()
        return len(s)

    def flush(self) -> None:
        sys.__stdout__.flush()


TQDM_BAR_FORMAT = "{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}{postfix}]"


def make_tqdm(iterable, *, desc: str, unit: str = "it"):
    """tail/Get-Content -Wait 용 tqdm (ascii 가로바 + 퍼센트)."""
    from tqdm import tqdm

    return tqdm(
        iterable,
        desc=desc,
        unit=unit,
        file=NewlineTqdmStream(),
        ascii=True,
        mininterval=1.0,
        dynamic_ncols=False,
        bar_format=TQDM_BAR_FORMAT,
    )


def log(msg: str) -> None:
    print(msg, flush=True)


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def existing_ids(path: Path, id_key: str = "id") -> set[str]:
    return {str(r[id_key]) for r in load_jsonl(path) if id_key in r}
